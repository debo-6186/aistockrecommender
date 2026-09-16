"""
The report generator.

By the time it is called the numbers are settled: the analyser has priced the
allocation from live quotes and saved it. What is left is turning that record
into something a person will actually read, and getting it to their inbox.

The split is deliberate. Analysis and delivery fail for different reasons and
should not fail together - a webhook outage must not cost the user the analysis
they paid for, which is why the recommendation is already in the database
before this agent is asked to do anything.
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "host_agent"))

from agent_core.callbacks import log_agent_entry, log_tool_call, log_tool_result
from agent_core.models import MODEL, generation_config
from agent_core.schemas import ReportNarrative

from report import send_report_email

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from database import get_agent_state, get_db, update_agent_state
except ImportError as exc:  # pragma: no cover - the agent can still render
    logger.warning("Database functions unavailable (%s); reports cannot be collected", exc)
    get_agent_state = None
    get_db = None
    update_agent_state = None

# Where the analyser leaves the priced report. A forty-position allocation does
# not belong in an A2A message, so it travels through Postgres and the message
# carries only the session id.
REPORT_HANDOFF_NAME = "priced_report"


AGENT_INSTRUCTION = """
You turn a finished stock allocation into a report an investor will read, and
send it to them.

# Working through a request

The message carries a session id. Call `load_report` with it to collect the
priced allocation the analyser produced.

Read what came back, then call `write_narrative` to compose the covering note -
the subject line, the headline, the summary, what matters most, and anything
the investor should know before acting. Then call `send_report` to render and
deliver it.

# What the covering note is for

The tables carry the numbers. Your note tells the investor what the report
says: what was analysed, what the allocation actually does with their money,
and how it follows the strategy they described. Write to someone who knows
their own portfolio but not this analysis.

Name the caveats plainly. A position that could not be priced, a holding with
no share count, a stock excluded for want of data - each one changes what the
investor can act on, and burying it is worse than saying it.

# Judgement calls that are yours to make

- If `load_report` finds nothing, say so and stop. There is nothing to send.
- If the report has no email address, say so and stop - a report with nowhere
  to go is not a failure you can fix by sending it somewhere else.
- If the allocation recommends holding cash rather than buying anything, that is
  a legitimate result. Report it as the finding it is, not as an error.

# What you must never do

- Never restate a number differently from how the report records it, and never
  compute a new one. The arithmetic was done upstream from live prices.
- Never soften a SELL or a risk warning to make the report read better.
""".strip()


def narrative_instruction(context: ReadonlyContext) -> str:
    """Give the narrative writer the report it is describing."""
    state = dict(context.state or {})
    report = state.get("report") or {}

    return f"""
You write the covering note for a stock allocation report that has already been
produced. The numbers below are settled - your job is to say what they mean.

# What to write

- `subject_line`: specific to this report. "Your March allocation: 4 buys,
  1 sell" beats "Your Stock Report".
- `headline`: one sentence on what the report recommends overall.
- `summary`: two or three short paragraphs - what was analysed, what the
  allocation does, and how it follows the investor's stated strategy.
- `what_changed`: the decisions that matter most, one line each, biggest first.
- `caveats`: what the investor needs to know before acting.

# Rules

Every figure you quote must match the report exactly. Do not recompute
anything, do not convert currencies, and do not round differently.

If a position could not be priced, or a holding had no share count, or a stock
was excluded for want of data, that belongs in `caveats`. So does a report that
recommends holding cash - say plainly that nothing cleared the bar.

Write plainly. No greeting, no sign-off, no "I hope this finds you well".

# The investor

Market: {report.get("market_preference", "US")}
Currency: {report.get("currency_symbol", "$")}
Strategy, in their words: {state.get("strategy") or "not recorded"}

# The report

{json.dumps(report, indent=2)[:40_000]}
""".strip()


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------


def load_report(session_id: str, tool_context: ToolContext) -> dict:
    """Collect the priced allocation the analyser produced for this session.

    Args:
        session_id: The session the report belongs to.

    Returns:
        A summary of what the report contains, or why none could be found.
    """
    if not session_id:
        return {"status": "error", "message": "A session id is needed to find the report."}
    if get_agent_state is None:
        return {"status": "error", "message": "No database is configured, so no report can be collected."}

    try:
        db = next(get_db())
        try:
            row = get_agent_state(db, session_id, REPORT_HANDOFF_NAME)
            raw = (row.state_data or "") if row is not None else ""
        finally:
            db.close()
    except Exception as exc:
        logger.error("Could not load the report for %s: %s", session_id, exc)
        return {"status": "error", "message": f"Could not load the report: {exc}"}

    if not raw.strip():
        return {
            "status": "error",
            "message": (
                f"No report is waiting for session {session_id}. The analysis has "
                "not finished, or it failed before producing one."
            ),
        }

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"status": "error", "message": f"The report could not be read back: {exc}"}

    report = payload.get("report") or {}
    tool_context.state["report"] = report
    tool_context.state["session_id"] = session_id
    tool_context.state["email"] = payload.get("email", "")
    tool_context.state["strategy"] = payload.get("strategy", "")

    recommendations = report.get("individual_stock_recommendations") or []
    tally: dict[str, int] = {}
    for line in recommendations:
        verdict = (line.get("recommendation") or "?").upper()
        tally[verdict] = tally.get(verdict, 0) + 1

    return {
        "status": "ok",
        "email": payload.get("email", ""),
        "market": report.get("market_preference", "US"),
        "positions": len(recommendations),
        "verdicts": tally,
        "allocation_lines": len(report.get("allocation_breakdown") or []),
        "could_not_price": payload.get("could_not_price") or [],
        "risk_warnings": len(report.get("risk_warnings") or []),
        "holding_cash": bool(report.get("cash_reserve_recommendation")),
    }


def send_report(tool_context: ToolContext) -> dict:
    """Render the report with its covering note and email it to the investor.

    Call this once `write_narrative` has produced the note.

    Returns:
        Where the report went, and what the delivery service said.
    """
    state = tool_context.state
    report = state.get("report")
    if not report:
        return {"status": "error", "message": "No report has been loaded yet."}

    email = state.get("email", "")
    if not email:
        return {
            "status": "error",
            "message": "The report carries no email address, so there is nowhere to send it.",
        }

    narrative = state.get("narrative")
    if isinstance(narrative, str):
        try:
            narrative = json.loads(narrative)
        except json.JSONDecodeError:
            narrative = None
    if not narrative:
        logger.warning("Sending without a covering note - none was written")
        narrative = {}

    # The renderer reads the note off the report, so they travel together.
    payload = dict(report)
    payload["narrative"] = narrative

    delivery = send_report_email(
        analysis_response=json.dumps(payload),
        email_to=email,
        subject=narrative.get("subject_line") or None,
    )

    delivered = delivery.startswith("Success")
    _record_outcome(state.get("session_id", ""), delivered, delivery)
    tool_context.state["delivered"] = delivered

    return {
        "status": "ok" if delivered else "delivery_failed",
        "emailed_to": email,
        "subject": narrative.get("subject_line", ""),
        "delivery": delivery,
    }


def _record_outcome(session_id: str, delivered: bool, detail: str) -> None:
    """Note on the handoff row whether the report actually went out."""
    if not session_id or update_agent_state is None:
        return
    try:
        db = next(get_db())
        try:
            row = get_agent_state(db, session_id, REPORT_HANDOFF_NAME)
            payload = json.loads(row.state_data) if row and row.state_data else {}
            payload["delivered"] = delivered
            payload["delivery_detail"] = detail[:500]
            update_agent_state(db, session_id, REPORT_HANDOFF_NAME, json.dumps(payload))
        finally:
            db.close()
    except Exception as exc:
        logger.error("Could not record the delivery outcome for %s: %s", session_id, exc)


# ----------------------------------------------------------------------
# Agents
# ----------------------------------------------------------------------


def build_narrative_agent() -> LlmAgent:
    """The specialist that writes the covering note."""
    return LlmAgent(
        model=MODEL,
        name="write_narrative",
        description=(
            "Writes the covering note for a finished allocation report: subject "
            "line, headline, summary, the decisions that matter, and the caveats."
        ),
        instruction=narrative_instruction,
        generate_content_config=generation_config(temperature=0.4),
        output_schema=ReportNarrative,
        output_key="narrative",
        before_agent_callback=log_agent_entry,
    )


def create_agent() -> LlmAgent:
    """Build the report generator."""
    return LlmAgent(
        model=MODEL,
        name="stock_report_generator_agent",
        description="Turns a finished allocation into a readable report and emails it.",
        instruction=AGENT_INSTRUCTION,
        generate_content_config=generation_config(temperature=0.3),
        tools=[
            load_report,
            AgentTool(agent=build_narrative_agent()),
            send_report,
        ],
        before_agent_callback=log_agent_entry,
        before_tool_callback=log_tool_call,
        after_tool_callback=log_tool_result,
    )


root_agent = None

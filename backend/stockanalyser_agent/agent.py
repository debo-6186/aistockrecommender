"""
The stock analysis agent.

The agent is handed a brief and a toolbox - market data over MCP, an allocation
specialist, and a delivery step - and decides for itself how to get from one to
the other. What stays as plain Python is the part that must not be improvised:
the money arithmetic, the database write and the email.
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, List, Optional

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.callbacks import log_agent_entry, log_tool_call
from agent_core.models import MODEL, generation_config
from agent_core import a2a_client
from agent_core.schemas import PortfolioRecommendation

from analysis_prompts import ANALYST_INSTRUCTION, allocation_instruction
from config import current_config
from database import get_db, save_portfolio_analysis, save_stock_recommendation, update_agent_state
from logger import get_logger, setup_logging

load_dotenv()
setup_logging()
logger = get_logger(__name__)

# MCP payloads are large; the analyst sees a digest while the full record is
# kept in state for the allocation step.
_DIGEST_CHARS = 1200

# Where the priced report is left for the report generator. A forty-position
# allocation does not belong in an A2A message, so it travels through Postgres
# and the message carries only the session id.
REPORT_HANDOFF_NAME = "priced_report"
REPORT_GENERATOR_NAME = "stock_report_generator_agent"


# ----------------------------------------------------------------------
# Market data capture
# ----------------------------------------------------------------------


def _parse_mcp_payload(raw: Any) -> Optional[dict]:
    """Pull the JSON document out of whatever shape MCP handed back."""
    try:
        if hasattr(raw, "content"):
            content = raw.content
            if isinstance(content, list) and content:
                first = content[0]
                if hasattr(first, "text"):
                    return json.loads(first.text)
            return None
        if isinstance(raw, dict):
            # ADK hands MCP results back wrapped; unwrap the common shapes.
            for key in ("result", "content", "text"):
                inner = raw.get(key)
                if isinstance(inner, str):
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        continue
                if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                    text = inner[0].get("text")
                    if isinstance(text, str):
                        return json.loads(text)
            return raw
        if isinstance(raw, str):
            return json.loads(raw)
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.debug("Could not parse MCP payload: %s", exc)
    return None


def _current_price(payload: dict) -> Optional[float]:
    """Read the traded price, which sits in a different place for ETFs."""
    if payload.get("stock_type") == "EQUITY":
        price = (payload.get("core_valuation_metrics") or {}).get("currentPrice")
    else:
        price = (payload.get("trading_valuation") or {}).get("regularMarketPrice")
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return None


def capture_market_data(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> Optional[dict]:
    """Keep every market-data payload, and hand the analyst a digest of it.

    The full record goes into session state where the allocation step reads it.
    The analyst only needs to know the fetch worked and roughly what came back,
    so returning the whole document into its context would be waste.
    """
    if not tool.name.startswith("get_"):
        return None

    symbol = str(args.get("symbol") or args.get("query") or "").upper().strip()
    payload = _parse_mcp_payload(tool_response)
    if payload is None:
        logger.warning("%s returned nothing parseable for %s", tool.name, symbol or "?")
        return None

    document = json.dumps(payload, default=str)

    research = dict(tool_context.state.get("research") or {})
    entry = dict(research.get(symbol) or {})
    entry[tool.name] = document
    entry["fetched_at"] = datetime.now().isoformat()
    research[symbol] = entry
    tool_context.state["research"] = research

    if tool.name == "get_stock_info" and symbol:
        price = _current_price(payload)
        if price is not None:
            prices = dict(tool_context.state.get("prices") or {})
            prices[symbol] = price
            tool_context.state["prices"] = prices
            logger.info("Recorded price for %s: %s", symbol, price)
        else:
            logger.warning("No current price in the %s payload", symbol)

    digest = document[:_DIGEST_CHARS]
    return {
        "symbol": symbol,
        "status": "recorded",
        "bytes_recorded": len(document),
        "digest": digest + ("..." if len(document) > _DIGEST_CHARS else ""),
        "note": "Full data is held for the allocation step; you do not need to repeat it back.",
    }


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------


def record_analysis_context(
    user_id: str,
    session_id: str,
    email: str,
    market: str,
    investment_amount: float,
    strategy: str,
    portfolio_context: str,
    tool_context: ToolContext,
) -> dict:
    """Record who this analysis is for and what it has to satisfy.

    Call this first, reading the values straight out of the brief. Pass an
    empty string for anything the brief genuinely does not contain.

    Args:
        user_id: The user id from the brief.
        session_id: The session id from the brief.
        email: Where the finished report is emailed.
        market: "US" or "INDIA".
        investment_amount: The budget for new investment.
        strategy: The investor's strategy, quoted from the brief verbatim.
        portfolio_context: The parsed portfolio statement from the brief.

    Returns:
        The recorded context.
    """
    market_normalised = (market or "US").upper().strip()
    if market_normalised not in {"US", "INDIA"}:
        market_normalised = "US"

    tool_context.state.update(
        {
            "user_id": user_id.strip(),
            "session_id": session_id.strip(),
            "email": email.strip(),
            "market": market_normalised,
            "currency_symbol": "₹" if market_normalised == "INDIA" else "$",
            "investment_amount": float(investment_amount or 0),
            "strategy": strategy.strip(),
            "portfolio_context": portfolio_context.strip(),
        }
    )

    problems = []
    if float(investment_amount or 0) <= 0:
        problems.append("the investment amount is zero or missing")
    if "@" not in email:
        problems.append("no usable email address was given")

    return {
        "status": "ok" if not problems else "incomplete_brief",
        "market": market_normalised,
        "investment_amount": float(investment_amount or 0),
        "problems": problems,
    }


def record_stock_list(
    existing_stocks: List[str], new_stocks: List[str], tool_context: ToolContext
) -> dict:
    """Record which stocks this analysis covers.

    Args:
        existing_stocks: Tickers the investor already holds.
        new_stocks: Tickers they are considering buying.

    Returns:
        The combined list, which is what you need market data for.
    """
    existing = [s.upper().strip() for s in existing_stocks if s and s.strip()]
    new = [s.upper().strip() for s in new_stocks if s and s.strip()]
    tool_context.state["existing_stocks"] = existing
    tool_context.state["new_stocks"] = new

    combined = existing + [s for s in new if s not in existing]
    return {
        "status": "ok" if combined else "error",
        "tickers_to_research": combined,
        "message": "" if combined else "The brief lists no stocks to analyse.",
    }


def record_share_count(ticker: str, shares: float, tool_context: ToolContext) -> dict:
    """Record how many shares of a holding the investor owns.

    Only positions recorded here can be rated SELL, and the number is what
    sizes the sale. Record one per holding listed in the brief.

    Args:
        ticker: The ticker the count applies to.
        shares: Number of shares held.

    Returns:
        Every share count recorded so far.
    """
    counts = dict(tool_context.state.get("share_counts") or {})
    counts[ticker.upper().strip()] = float(shares)
    tool_context.state["share_counts"] = counts
    return {"status": "ok", "share_counts": counts}


def get_macro_backdrop(tool_context: ToolContext) -> dict:
    """Research the current macro and geopolitical backdrop for equities.

    Call this once per analysis, for the portfolio as a whole - not once per
    ticker. It looks at rates and central bank policy, oil and energy prices,
    active geopolitical conflicts or trade tensions, and the state of crowded
    sector trades such as the AI investment cycle, so the allocation step can
    weigh a stock's fundamentals against the environment it will be held in.

    Returns:
        A macro summary, or a note that macro research is unavailable.
    """
    cached = tool_context.state.get("macro_context")
    if cached:
        return {"status": "cached", "macro_backdrop": cached}

    market = tool_context.state.get("market", "US")
    market_name = "Indian" if market == "INDIA" else "US"
    query = (
        f"What are the current macroeconomic and geopolitical conditions most "
        f"relevant to {market_name} equity investors right now? Cover interest "
        "rates and central bank policy, oil and energy prices, active "
        "geopolitical conflicts or trade tensions, and the state of the AI "
        "investment cycle including any bubble concerns. Summarise the "
        "prevailing risks and tailwinds, and say whether each is structural or "
        "likely to reverse, with the timeframe of anything you cite."
    )

    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY is not set; skipping macro research")
        result = "Macro research is unavailable (no PERPLEXITY_API_KEY configured)."
        tool_context.state["macro_context"] = result
        return {"status": "unavailable", "macro_backdrop": result}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        response = client.chat.completions.create(
            model="sonar-reasoning-pro",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a macro strategist briefing an equity portfolio "
                        "manager before they price a set of stocks. Be concise "
                        "and concrete, say whether each factor is structural or "
                        "likely to reverse, and state the timeframe for anything "
                        "time-sensitive."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        result = (
            response.choices[0].message.content.strip()
            if response.choices
            else "The macro research service returned no answer."
        )
        # sonar-reasoning-pro prefixes a chain-of-thought block; the allocation
        # step only needs the answer that follows it.
        if "<think>" in result and "</think>" in result:
            result = result.split("</think>", 1)[1].strip()
        status = "ok"
    except Exception as exc:
        logger.error("Macro backdrop research failed: %s", exc)
        result = f"Macro research failed ({exc}); proceed without it and say so."
        status = "error"

    tool_context.state["macro_context"] = result
    return {"status": status, "macro_backdrop": result}


def research_status(tool_context: ToolContext) -> dict:
    """Check which stocks have market data and which are still missing it.

    Use this before building the allocation, to confirm nothing was skipped.

    Returns:
        Which tickers have data, which have a price, and which have neither.
    """
    existing = list(tool_context.state.get("existing_stocks") or [])
    new = list(tool_context.state.get("new_stocks") or [])
    wanted = existing + [s for s in new if s not in existing]

    research = tool_context.state.get("research") or {}
    prices = tool_context.state.get("prices") or {}

    return {
        "requested": wanted,
        "with_data": [t for t in wanted if t in research],
        "with_price": [t for t in wanted if t in prices],
        "missing": [t for t in wanted if t not in research],
    }


def _research_digest(state: dict) -> str:
    """Lay out everything gathered, for the allocation step to reason over."""
    research = state.get("research") or {}
    if not research:
        return "No market data was gathered."

    blocks = []
    for ticker, entry in research.items():
        parts = [f"{'=' * 50}", f"Ticker: {ticker}", f"{'=' * 50}"]
        for tool_name, document in entry.items():
            if tool_name == "fetched_at":
                continue
            parts.append(f"--- {tool_name} ---")
            parts.append(document)
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def build_allocation_instruction(context: ReadonlyContext) -> str:
    state = dict(context.state or {})
    return allocation_instruction(
        market=state.get("market", "US"),
        currency_symbol=state.get("currency_symbol", "$"),
        investment_amount=float(state.get("investment_amount") or 0),
        strategy=state.get("strategy", ""),
        share_counts=state.get("share_counts") or {},
        stock_data=_research_digest(state),
        macro_context=state.get("macro_context", ""),
    )


def _parse_money(value: str) -> float:
    """Read a currency-prefixed amount written by the model."""
    if not value:
        return 0.0
    cleaned = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned) if cleaned not in {"", "-", ".", "-."} else 0.0
    except ValueError:
        return 0.0


def deliver_report(tool_context: ToolContext) -> dict:
    """Price the allocation, save it, and hand it over for delivery.

    Computes every share count from the live prices gathered during research and
    stores the report against the session, then asks the report generator to
    write it up and email it. Call this once the allocation is built.

    Returns:
        What was priced and saved, and what the report generator said.
    """
    state = tool_context.state
    raw = state.get("allocation_report")
    if not raw:
        return {
            "status": "error",
            "message": "No allocation has been built yet. Call the allocation agent first.",
        }

    try:
        report = raw if isinstance(raw, dict) else json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return {"status": "error", "message": f"The allocation could not be read back: {exc}"}

    prices: dict = state.get("prices") or {}
    symbol = state.get("currency_symbol", "$")
    market = state.get("market", "US")

    # Share counts are arithmetic on live prices, so they are computed here
    # rather than being taken from the model.
    priced, unpriced = [], []
    for line in report.get("individual_stock_recommendations") or []:
        ticker = (line.get("ticker") or "").upper().strip()
        rating = (line.get("recommendation") or "").upper()
        price = prices.get(ticker)

        if rating not in {"BUY", "SELL"}:
            continue
        if price is None:
            unpriced.append(ticker)
            continue

        line["entry_price"] = f"{symbol}{price:.2f}"
        priced.append(ticker)

        if rating == "BUY":
            amount = _parse_money(line.get("investment_amount"))
            if amount > 0 and price > 0:
                line["number_of_shares"] = f"{amount / price:.4f} shares"

    for line in report.get("allocation_breakdown") or []:
        ticker = (line.get("ticker") or "").upper().strip()
        price = prices.get(ticker)
        amount = _parse_money(line.get("investment_amount"))
        if price and price > 0 and amount > 0:
            line["number_of_shares"] = f"{amount / price:.4f} shares"

    report["entry_prices"] = prices
    report["recommendation_date"] = datetime.now().isoformat()
    report["market_preference"] = market
    report["currency_symbol"] = symbol

    session_id = state.get("session_id") or ""
    user_id = state.get("user_id") or ""
    saved = False
    if session_id and user_id:
        try:
            db = next(get_db())
            try:
                save_portfolio_analysis(
                    db=db,
                    session_id=session_id,
                    user_id=user_id,
                    portfolio_analysis=state.get("portfolio_context", ""),
                    investment_amount=str(state.get("investment_amount", 0)),
                    email_id=state.get("email", ""),
                )
                saved = bool(
                    save_stock_recommendation(
                        db=db,
                        session_id=session_id,
                        user_id=user_id,
                        recommendation=report,
                    )
                )
            finally:
                db.close()
        except Exception as exc:
            logger.error("Could not save the report for session %s: %s", session_id, exc)
    else:
        logger.warning("No session or user id in the brief; skipping the database write")

    tool_context.state["allocation_report"] = report

    # Delivery is somebody else's job. The report generator writes the covering
    # note and sends the email; by the time it runs the analysis is already
    # saved, so a webhook outage cannot cost the user the work they paid for.
    email = state.get("email", "")
    handed_off = _hand_off_for_delivery(
        session_id=session_id,
        report=report,
        email=email,
        strategy=state.get("strategy", ""),
        could_not_price=unpriced,
    )

    if not handed_off:
        return {
            "status": "saved_but_not_sent",
            "priced": priced,
            "could_not_price": unpriced,
            "saved_to_database": saved,
            "message": (
                "The allocation is priced and saved but could not be queued for "
                "delivery. Say the analysis is complete and the report will follow."
            ),
        }

    delivery = _request_report(session_id)
    tool_context.state["delivered"] = not delivery.startswith("Error")

    return {
        "status": "ok",
        "priced": priced,
        "could_not_price": unpriced,
        "saved_to_database": saved,
        "handed_to": REPORT_GENERATOR_NAME,
        "emailed_to": email,
        "delivery": delivery,
    }


def _hand_off_for_delivery(
    session_id: str,
    report: dict,
    email: str,
    strategy: str,
    could_not_price: list,
) -> bool:
    """Leave the priced report where the report generator will collect it."""
    if not session_id:
        logger.error("No session id in the brief; the report cannot be handed off")
        return False

    payload = {
        "report": report,
        "email": email,
        "strategy": strategy,
        "could_not_price": could_not_price,
        "handed_off_at": datetime.now().isoformat(),
    }
    try:
        db = next(get_db())
        try:
            update_agent_state(db, session_id, REPORT_HANDOFF_NAME, json.dumps(payload))
            logger.info("Handed the priced report off for session %s", session_id)
            return True
        finally:
            db.close()
    except Exception as exc:
        logger.error("Could not hand off the report for %s: %s", session_id, exc)
        return False


def _request_report(session_id: str) -> str:
    """Ask the report generator to write up and send this session's report."""
    url = current_config.STOCK_REPORT_GENERATOR_AGENT_URL
    brief = (
        "Generate and send the stock report for this session.\n\n"
        f"SESSION ID: {session_id}\n\n"
        "Call `load_report` with that session id, write the covering note, then "
        "send it."
    )
    logger.info("Asking %s to deliver the report for %s", url, session_id)
    return a2a_client.send_sync(url, brief)


# ----------------------------------------------------------------------
# Agents
# ----------------------------------------------------------------------


def _mcp_toolset() -> MCPToolset:
    """Market data over the project's MCP server."""
    directory = current_config.MCP_DIRECTORY
    logger.info("Loading MCP tools from %s", directory)

    env = {**os.environ}
    env["MCP_TIMEOUT"] = os.getenv("MCP_TIMEOUT", "30")

    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=[os.path.join(directory, "server.py")],
                env=env,
            ),
            # The default is 5s, and it governs every MCP call, not just the
            # initial connection - too short for a live yfinance round trip.
            timeout=float(os.getenv("MCP_TIMEOUT", "30")),
        )
    )


def build_allocation_agent() -> LlmAgent:
    """The specialist that turns research into a structured allocation."""
    return LlmAgent(
        model=MODEL,
        name="allocation_agent",
        description=(
            "Turns the market data gathered so far into a full allocation "
            "report: a per-stock BUY/HOLD/SELL call with reasoning, a budget "
            "split, and the risks that come with it."
        ),
        instruction=build_allocation_instruction,
        generate_content_config=generation_config(temperature=0.2),
        output_schema=PortfolioRecommendation,
        output_key="allocation_report",
        before_agent_callback=log_agent_entry,
    )


def create_agent() -> LlmAgent:
    """Build the analyst agent."""
    return LlmAgent(
        model=MODEL,
        name="stock_analyser_agent",
        description="Researches stocks and produces an allocation report for one investor.",
        instruction=ANALYST_INSTRUCTION,
        generate_content_config=generation_config(temperature=0.3),
        tools=[
            record_analysis_context,
            record_stock_list,
            record_share_count,
            get_macro_backdrop,
            research_status,
            _mcp_toolset(),
            AgentTool(agent=build_allocation_agent()),
            deliver_report,
        ],
        before_agent_callback=log_agent_entry,
        before_tool_callback=log_tool_call,
        after_tool_callback=capture_market_data,
    )


root_agent = None

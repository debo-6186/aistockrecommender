"""
The host agent: a conversational coordinator for portfolio analysis.

The agent is given a goal, a set of policies and a live view of what it already
knows, and it decides for itself what to ask next and when it has enough to
delegate. Conversation history and collected facts both live in ADK session
state, persisted to Postgres, so nothing has to be reconstructed and pasted
back into the prompt on each turn.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import threading
import time
import uuid
from typing import Any, AsyncIterable, List, Optional

import boto3
import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_core.callbacks import log_agent_entry, log_tool_call, log_tool_result
from agent_core.models import MODEL, generation_config
from agent_core.sessions import get_session_service

from . import tickers
from .prompts import coordinator_instruction
from .specialists import build_market_researcher
from .remote_agent_connection import RemoteAgentConnections

from database import (  # noqa: E402
    get_agent_state,
    get_db,
    get_session,
    mark_portfolio_statement_uploaded,
    update_agent_state,
)
from config import current_config  # noqa: E402

load_dotenv()
nest_asyncio.apply()

logger = logging.getLogger("host_agent_api.host_agent")
logger.setLevel(logging.INFO)

ANALYSER_AGENT_NAME = "Stock Analyser Agent"
DOCUMENT_AGENT_NAME = "document_analyser_agent"

# The document analyser writes its structured extraction to this row rather
# than returning it as text, so a long holdings list cannot be truncated by
# the model summarising its own work. See document_analyser_agent/agent.py.
DOCUMENT_HANDOFF_NAME = "document_analyser"

# The shape __main__.py and the /sessions endpoints expect back from _load_state.
EMPTY_STATE: dict = {
    "stock_report_response": "",
    "existing_portfolio_stocks": [],
    "new_stocks": [],
    "investment_amount": 0.0,
    "receiver_email_id": "",
    "diversification_preference": "",
    "share_counts": {},
    "market_preference": "",
}


def _blank_state() -> dict:
    return json.loads(json.dumps(EMPTY_STATE))


class HostAgent:
    """Coordinates the conversation and delegates analysis over A2A."""

    def __init__(self):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        # __main__.py writes to this before each turn; it is transport context,
        # not conversation state.
        self.current_session_id = {"id": "", "user_id": "", "is_file_uploaded": False}
        # Snapshot of the last observed session state, so the synchronous
        # _load_state() contract still works from inside async handlers.
        self._state_snapshots: dict[str, dict] = {}

        self._agent = self._build_agent()
        self._session_service = get_session_service()
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=self._session_service,
            memory_service=InMemoryMemoryService(),
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_agent(self) -> LlmAgent:
        def instruction(context: ReadonlyContext) -> str:
            # The coordinator needs to know who it can delegate to; that is
            # connection-time information rather than session state.
            merged = dict(context.state or {})
            merged["available_agents"] = self.agents or "none connected"
            return coordinator_instruction(_StateView(merged))

        return LlmAgent(
            model=MODEL,
            name="portfolio_coordinator",
            description="Coordinates portfolio intake and delegates stock analysis.",
            instruction=instruction,
            generate_content_config=generation_config(temperature=0.3),
            tools=[
                self.record_market,
                self.record_holdings,
                self.record_share_count,
                self.record_budget,
                self.record_strategy,
                self.record_email,
                self.add_candidate_stocks,
                self.browse_sector_watchlist,
                self.analyse_portfolio_document,
                self.analyse_portfolio_text,
                self.request_full_analysis,
                AgentTool(agent=build_market_researcher()),
            ],
            before_agent_callback=log_agent_entry,
            before_tool_callback=log_tool_call,
            after_tool_callback=log_tool_result,
        )

    async def _async_init_components(self, remote_agent_addresses: List[str]):
        errors: list[str] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        ) as client:
            for address in remote_agent_addresses:
                try:
                    logger.info("Connecting to remote agent at %s", address)
                    card = await A2ACardResolver(client, address).get_agent_card()
                    self.remote_agent_connections[card.name] = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.cards[card.name] = card
                    logger.info("Connected to %s", card.name)
                except Exception as exc:
                    errors.append(f"{address}: {type(exc).__name__}: {exc}")
                    logger.error("Could not connect to %s: %s", address, exc)

        if self.remote_agent_connections:
            logger.info(
                "Connected to %d agents: %s",
                len(self.remote_agent_connections),
                list(self.remote_agent_connections),
            )
        else:
            logger.error("No remote agents connected. Errors: %s", errors)

        self.agents = (
            "\n".join(
                json.dumps({"name": c.name, "description": c.description})
                for c in self.cards.values()
            )
            or "No agents connected"
        )

    @classmethod
    async def create(cls, remote_agent_addresses: List[str]) -> "HostAgent":
        instance = cls()
        await instance._async_init_components(remote_agent_addresses)
        return instance

    # ------------------------------------------------------------------
    # Session state
    # ------------------------------------------------------------------

    def _session_user(self) -> str:
        return self.current_session_id.get("user_id") or "anonymous"

    async def _get_or_create_session(self, session_id: str, user_id: str):
        session = await self._session_service.get_session(
            app_name=self._agent.name, user_id=user_id, session_id=session_id
        )
        if session is not None:
            return session

        logger.info("Creating new ADK session %s for user %s", session_id, user_id)
        return await self._session_service.create_session(
            app_name=self._agent.name,
            user_id=user_id,
            session_id=session_id,
            state=self._seed_state(session_id),
        )

    def _seed_state(self, session_id: str) -> dict:
        """Initial state for a new session.

        Picks up anything the database already knows - a market preference set
        on the session row, an uploaded statement, or state written by the
        previous implementation - so an in-flight conversation is not reset.
        """
        state = _blank_state()
        try:
            db = next(get_db())
            try:
                legacy = get_agent_state(db, session_id, "host_agent")
                if legacy and legacy.state_data:
                    state.update(json.loads(legacy.state_data))
                    logger.info("Seeded session %s from stored agent state", session_id)

                row = get_session(db, session_id)
                if row is not None:
                    if getattr(row, "market_preference", None):
                        state["market_preference"] = row.market_preference
                    state["portfolio_uploaded"] = bool(
                        getattr(row, "portfolio_statement_uploaded", False)
                    )
                    state["input_format"] = getattr(row, "input_format", "") or "pdf"
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not seed state for session %s: %s", session_id, exc)

        state.setdefault("portfolio_uploaded", False)
        state.setdefault("analysis_dispatched", False)
        return state

    def _load_state(self) -> dict:
        """Return the latest known state for the current session.

        Kept for the API layer, which mirrors this into the agent_states table
        after each turn and reads it for the /sessions endpoints.
        """
        session_id = self.current_session_id.get("id")
        if not session_id:
            return _blank_state()
        snapshot = self._state_snapshots.get(session_id)
        if snapshot is None:
            return _blank_state()
        return {k: v for k, v in snapshot.items() if not k.startswith("_")}

    def _snapshot(self, session_id: str, state: dict) -> None:
        merged = _blank_state()
        merged.update(state or {})
        self._state_snapshots[session_id] = merged

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    async def stream(
        self, query: str, session_id: str, user_id: str = ""
    ) -> AsyncIterable[dict[str, Any]]:
        """Run one conversational turn."""
        self.current_session_id = {
            "id": session_id,
            "user_id": user_id,
            "is_file_uploaded": self.current_session_id.get("is_file_uploaded", False),
        }
        adk_user = user_id or "anonymous"

        session = await self._get_or_create_session(session_id, adk_user)
        dispatched_before = bool(session.state.get("analysis_dispatched"))

        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        response_text = ""

        try:
            async for event in self._runner.run_async(
                user_id=adk_user, session_id=session.id, new_message=content
            ):
                if not event.is_final_response():
                    yield {"is_task_complete": False, "updates": "Working on it..."}
                    continue

                if event.content and event.content.parts:
                    texts = [p.text for p in event.content.parts if getattr(p, "text", None)]
                    response_text = "\n".join(texts).strip()

            final_state = await self._refresh_snapshot(session_id, adk_user)

            if not response_text:
                logger.warning("Turn produced no text for session %s", session_id)
                response_text = "Sorry, I did not manage to put a reply together. Could you say that again?"

            # Ending the session is a fact about state, not about wording: the
            # API layer is told the conversation is over because the analysis
            # was actually dispatched, not because the model said so.
            if final_state.get("analysis_dispatched") and not dispatched_before:
                yield {
                    "is_task_complete": True,
                    "content": json.dumps(
                        {"message": response_text, "end_session": True}
                    ),
                }
                return

            yield {"is_task_complete": True, "content": response_text}

        except Exception as exc:
            message = str(exc)
            logger.error("Turn failed for session %s: %s", session_id, message, exc_info=True)
            if any(code in message for code in ("500 INTERNAL", "503 UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                yield {
                    "is_task_complete": True,
                    "content": "The AI service is briefly unavailable. Please try that again in a moment.",
                }
            else:
                yield {
                    "is_task_complete": True,
                    "content": "Something went wrong handling that message. Please try again.",
                }

    async def _refresh_snapshot(self, session_id: str, adk_user: str) -> dict:
        try:
            session = await self._session_service.get_session(
                app_name=self._agent.name, user_id=adk_user, session_id=session_id
            )
            state = dict(session.state) if session else {}
        except Exception as exc:
            logger.warning("Could not read back state for %s: %s", session_id, exc)
            state = {}
        self._snapshot(session_id, state)
        return state

    # ------------------------------------------------------------------
    # Tools - recording what the user tells us
    # ------------------------------------------------------------------

    def record_market(self, market: str, tool_context: ToolContext) -> dict:
        """Record which market the user invests in.

        Every stock in the analysis must belong to this market, so record it
        before resolving any tickers.

        Args:
            market: The market, as the user described it - "US", "USA",
                "India", "Indian" and similar variations are all understood.

        Returns:
            The normalised market, or an error if it was not recognisable.
        """
        normalised = market.upper().strip()
        if normalised in {"USA", "UNITED STATES", "AMERICA", "US MARKET"}:
            normalised = "US"
        elif normalised in {"IND", "INDIAN", "BHARAT", "INDIA MARKET", "NSE", "BSE"}:
            normalised = "INDIA"

        if normalised not in {"US", "INDIA"}:
            return {
                "status": "error",
                "message": f"'{market}' is not a market I support. Ask the user for US or India.",
            }

        tool_context.state["market_preference"] = normalised

        try:
            db = next(get_db())
            try:
                row = get_session(db, self.current_session_id.get("id", ""))
                if row is not None:
                    row.market_preference = normalised
                    db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not persist market preference to the session row: %s", exc)

        return {"status": "ok", "market": normalised}

    def record_holdings(self, tickers: List[str], tool_context: ToolContext) -> dict:
        """Record the stocks the user already owns.

        Args:
            tickers: Tickers from the user's existing portfolio.

        Returns:
            The full holdings list and which of them still need a share count.
        """
        existing = list(tool_context.state.get("existing_portfolio_stocks") or [])
        for ticker in tickers:
            symbol = ticker.upper().strip()
            if symbol and symbol not in existing:
                existing.append(symbol)
        tool_context.state["existing_portfolio_stocks"] = existing

        share_counts = tool_context.state.get("share_counts") or {}
        return {
            "status": "ok",
            "holdings": existing,
            "missing_share_counts": [t for t in existing if t not in share_counts],
        }

    def record_share_count(
        self, ticker: str, shares: float, tool_context: ToolContext
    ) -> dict:
        """Record how many shares of a holding the user owns.

        Without this the analyst cannot size a SELL, so a holding with no share
        count can only ever be rated HOLD.

        Args:
            ticker: The ticker the count applies to.
            shares: Number of shares held. An approximation is acceptable.

        Returns:
            Every share count recorded so far.
        """
        symbol = ticker.upper().strip()
        counts = dict(tool_context.state.get("share_counts") or {})
        counts[symbol] = float(shares)
        tool_context.state["share_counts"] = counts

        existing = list(tool_context.state.get("existing_portfolio_stocks") or [])
        return {
            "status": "ok",
            "share_counts": counts,
            "still_missing": [t for t in existing if t not in counts],
        }

    def record_budget(self, amount: float, tool_context: ToolContext) -> dict:
        """Record how much new money the user wants to invest.

        Args:
            amount: The amount, in the currency of their chosen market.

        Returns:
            The recorded amount.
        """
        if amount <= 0:
            return {"status": "error", "message": "The investment amount must be positive."}
        tool_context.state["investment_amount"] = float(amount)
        symbol = "₹" if tool_context.state.get("market_preference") == "INDIA" else "$"
        return {"status": "ok", "amount": f"{symbol}{float(amount):,.2f}"}

    def record_strategy(self, strategy: str, tool_context: ToolContext) -> dict:
        """Record the user's investment strategy in their own words.

        Store what they actually said - time horizon, risk appetite, sector
        preferences and all. The analyst reads this verbatim, so do not
        summarise it down to a category.

        Args:
            strategy: The user's description of how they want to invest.

        Returns:
            Confirmation that the strategy was recorded.
        """
        text = strategy.strip()
        if len(text) < 3:
            return {"status": "error", "message": "That strategy description is too short to be useful."}
        tool_context.state["diversification_preference"] = text
        return {"status": "ok", "strategy": text}

    def record_email(self, email: str, tool_context: ToolContext) -> dict:
        """Record where the finished report should be emailed.

        Recording the address does not start the analysis; call
        `request_full_analysis` for that.

        Args:
            email: The user's email address.

        Returns:
            The recorded address.
        """
        address = email.strip()
        if "@" not in address or "." not in address.split("@")[-1]:
            return {"status": "error", "message": f"'{email}' does not look like an email address."}
        tool_context.state["receiver_email_id"] = address
        return {"status": "ok", "email": address}

    # ------------------------------------------------------------------
    # Tools - working out what to analyse
    # ------------------------------------------------------------------

    def add_candidate_stocks(self, names: List[str], tool_context: ToolContext) -> dict:
        """Add stocks the user wants considered beyond their current holdings.

        Accepts company names or tickers; both are resolved to the correct
        symbol for the user's market. Anything listed on the wrong exchange is
        rejected rather than quietly converted.

        Args:
            names: Company names or tickers the user mentioned.

        Returns:
            What was added, what was rejected, and why.
        """
        market = tool_context.state.get("market_preference")
        if not market:
            return {
                "status": "error",
                "message": "Find out whether the user invests in the US or India first.",
            }

        try:
            resolution = tickers.resolve(names, market)
        except Exception as exc:
            logger.error("Ticker resolution failed: %s", exc)
            return {
                "status": "error",
                "message": f"Could not resolve those symbols ({exc}). Ask the user to give exact tickers.",
            }

        candidates = list(tool_context.state.get("new_stocks") or [])
        added = []
        for symbol in resolution.resolved:
            upper = symbol.upper().strip()
            if upper and upper not in candidates:
                candidates.append(upper)
                added.append(upper)
        tool_context.state["new_stocks"] = candidates

        return {
            "status": "ok",
            "added": added,
            "rejected": resolution.rejected,
            "explanation": resolution.explanation,
            "candidates": candidates,
        }

    def _watchlists(self) -> dict:
        """Load the sector watchlists that shipped with this build."""
        candidates = [
            os.path.join(os.path.dirname(__file__), "stock_data.json"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "stock_data.json"),
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path) as handle:
                        return json.load(handle)
                except Exception as exc:
                    logger.error("Could not read %s: %s", path, exc)
        logger.error("No stock_data.json found in %s", candidates)
        return {}

    def browse_sector_watchlist(self, sector: str, tool_context: ToolContext) -> dict:
        """List well-known stocks in a sector, for the user's market.

        Use this when the user asks for ideas in a sector rather than naming
        companies. Calling it with an unrecognised sector returns the list of
        sectors that do exist, so it is safe to guess.

        Args:
            sector: The sector to browse, in plain words - "technology",
                "banking", "high dividend" and similar all work.

        Returns:
            The tickers in that sector, or the sectors available if there was
            no match.
        """
        market = tool_context.state.get("market_preference")
        if not market:
            return {
                "status": "error",
                "message": "Find out whether the user invests in the US or India first.",
            }

        data = self._watchlists()
        if not data:
            return {"status": "error", "message": "Watchlist data is unavailable."}

        # The file names categories by market prefix; only offer the user's own.
        prefix = "USA_" if market == "US" else "INDIA_"
        available = {k: v for k, v in data.items() if k.startswith(prefix)}

        def readable(key: str) -> str:
            name = key[len(prefix):].removesuffix("_STOCKS").replace("_", " ").lower()
            return name.removeprefix("top ")

        wanted = sector.strip().lower().replace("-", " ")
        aliases = {
            "tech": "technology",
            "it": "technology",
            "software": "technology",
            "bank": "financial",
            "banking": "financial",
            "finance": "financial",
            "auto": "automobile",
            "cars": "automobile",
            "automotive": "automobile",
            "pharma": "healthcare",
            "medical": "healthcare",
            "dividend": "high dividend",
            "growth": "high growth",
        }
        wanted = aliases.get(wanted, wanted)

        match = next((k for k in available if readable(k) == wanted), None)
        if match is None:
            # Fall back to a containment match before giving up.
            match = next((k for k in available if wanted and wanted in readable(k)), None)

        if match is None:
            return {
                "status": "no_such_sector",
                "message": f"There is no '{sector}' watchlist for the {market} market.",
                "available_sectors": sorted(readable(k) for k in available),
            }

        return {
            "status": "ok",
            "sector": readable(match),
            "market": market,
            "tickers": available[match],
        }

    async def analyse_portfolio_document(self, tool_context: ToolContext) -> dict:
        """Read the portfolio statement the user uploaded for this session.

        Works for PDF statements, scanned statements and screenshots. Call this
        once a document has been uploaded; the holdings it finds are recorded
        for you, so there is no need to call `record_holdings` afterwards.

        Returns:
            Structured holdings, or an explanation of what went wrong.
        """
        session_id = self.current_session_id.get("id", "")
        user_id = self.current_session_id.get("user_id", "")

        if not session_id:
            return {"status": "error", "message": "No session is active, so no upload can be found."}

        if not user_id:
            user_id = self._session_owner(session_id)
        if not user_id:
            return {"status": "error", "message": "Could not identify who uploaded the document."}

        market = tool_context.state.get("market_preference")
        brief = f"""Read the portfolio statement uploaded for this session.

SESSION ID: {session_id}
USER NAME: {user_id}
EXPECTED DOCUMENT TYPE: portfolio_statement
{f"The user invests in the {market} market. Note anything that does not belong there." if market else ""}

Use `read_document` with that session id and user name, then extract it as a
portfolio_statement. If it turns out to be a different kind of document, say
which."""

        return await self._ask_document_analyser(brief, session_id, tool_context)

    async def analyse_portfolio_text(self, portfolio_text: str, tool_context: ToolContext) -> dict:
        """Read holdings the user typed into the chat.

        Handles anything from "AAPL 30%, GOOGL 20%, MSFT 50%" to a prose
        description of what they own. The holdings it finds are recorded for
        you, so there is no need to call `record_holdings` afterwards.

        Args:
            portfolio_text: Exactly what the user typed about their holdings.

        Returns:
            Structured holdings, or an explanation of what went wrong.
        """
        if not portfolio_text or len(portfolio_text.strip()) < 3:
            return {"status": "error", "message": "No portfolio text was provided."}

        session_id = self.current_session_id.get("id", "")
        market = tool_context.state.get("market_preference")
        brief = f"""The user typed their holdings into the chat rather than uploading a file.

SESSION ID: {session_id}
EXPECTED DOCUMENT TYPE: portfolio_statement
{f"The user invests in the {market} market. Note anything that does not belong there." if market else ""}

Record this text with `record_document_text`, then extract it as a
portfolio_statement:

{portfolio_text}"""

        return await self._ask_document_analyser(brief, session_id, tool_context)

    # ------------------------------------------------------------------
    # Talking to the document analyser
    # ------------------------------------------------------------------

    def _session_owner(self, session_id: str) -> str:
        """Look up who owns a session, when the request did not say."""
        try:
            db = next(get_db())
            try:
                row = get_session(db, session_id)
                return row.user_id if row else ""
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not look up the owner of session %s: %s", session_id, exc)
            return ""

    def _clear_state_row(self, session_id: str, agent_name: str) -> None:
        """Drop a previous handoff, so a stale one cannot be read as new."""
        if not session_id:
            return
        try:
            db = next(get_db())
            try:
                update_agent_state(db, session_id, agent_name, "")
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Could not clear the %s row for %s: %s", agent_name, session_id, exc)

    def _read_state_row(self, session_id: str, agent_name: str) -> Optional[dict]:
        """Read back what an agent left for this session, if anything."""
        if not session_id:
            return None
        try:
            db = next(get_db())
            try:
                row = get_agent_state(db, session_id, agent_name)
                if row is None or not (row.state_data or "").strip():
                    return None
                return json.loads(row.state_data)
            finally:
                db.close()
        except Exception as exc:
            logger.error("Could not read the %s row for %s: %s", agent_name, session_id, exc)
            return None

    async def _ask_document_analyser(
        self, brief: str, session_id: str, tool_context: ToolContext
    ) -> dict:
        """Send a document to the analyser and merge back what it found.

        The A2A reply is prose; the structured extraction comes back through
        the database, so nothing depends on the remote model echoing a long
        holdings list accurately.
        """
        if DOCUMENT_AGENT_NAME not in self.remote_agent_connections:
            return {
                "status": "error",
                "message": (
                    "The document reader is not reachable right now. Ask the user to "
                    "type their holdings instead, or to try the upload again shortly."
                ),
            }

        self._clear_state_row(session_id, DOCUMENT_HANDOFF_NAME)
        # Awaited rather than run through the synchronous send_message, which
        # would block the event loop for the whole read - and reading a scan
        # means an OCR round trip, not a few milliseconds.
        reply = await self._send_with_retry(DOCUMENT_AGENT_NAME, brief)
        if isinstance(reply, str) and reply.startswith("Error"):
            logger.error("Document analyser call failed: %s", reply)
            return {
                "status": "error",
                "message": "The document reader could not be reached. Ask the user to try again.",
            }

        result = self._read_state_row(session_id, DOCUMENT_HANDOFF_NAME)
        if result is None:
            logger.error("No extraction was handed back for session %s", session_id)
            return {
                "status": "error",
                "message": (
                    "The document was sent for reading but no result came back. "
                    "Ask the user to try the upload again, or to type their holdings."
                ),
            }

        if result.get("status") != "ok":
            return result

        tool_context.state["portfolio_uploaded"] = True
        self._merge_intake(result, tool_context)

        # The holdings are in state now. Returning the whole extraction as well
        # would put the same list in the coordinator's context a second time.
        holdings = result.get("holdings") or []
        share_counts = result.get("share_counts") or {}
        return {
            "status": "ok",
            "read_method": result.get("read_method", "unknown"),
            "detected_market": result.get("detected_market", "UNKNOWN"),
            "holdings_found": len(holdings),
            "tickers": result.get("tickers") or [],
            "share_counts_known_for": list(share_counts),
            "missing_share_counts": result.get("missing_share_counts") or [],
            "notes": result.get("notes", ""),
            "recorded": "Holdings and share counts are already saved to state.",
        }

    def _merge_intake(self, result: dict, tool_context: ToolContext) -> None:
        """Fold extracted holdings and share counts straight into state.

        Saves the coordinator a round trip: the facts are recorded as soon as
        they are known, and the reply it gets already reflects them.
        """
        existing = list(tool_context.state.get("existing_portfolio_stocks") or [])
        for ticker in result.get("tickers") or []:
            symbol = str(ticker).upper().strip()
            if symbol and symbol not in existing:
                existing.append(symbol)
        tool_context.state["existing_portfolio_stocks"] = existing

        counts = dict(tool_context.state.get("share_counts") or {})
        for ticker, shares in (result.get("share_counts") or {}).items():
            if shares is not None:
                counts[str(ticker).upper().strip()] = float(shares)
        tool_context.state["share_counts"] = counts

        tool_context.state["stock_report_response"] = json.dumps(
            result.get("holdings") or [], indent=2
        )

    # ------------------------------------------------------------------
    # Tools - delegation
    # ------------------------------------------------------------------

    def request_full_analysis(self, tool_context: ToolContext) -> dict:
        """Hand the complete brief to the Stock Analyser Agent.

        Call this once the market, holdings, budget, strategy and email address
        are all known. If anything is missing the tool says what, and nothing
        is dispatched - go and collect it, then call again.

        Returns:
            Either a confirmation that the analysis is running, or the list of
            facts still outstanding.
        """
        state = tool_context.state
        missing = []
        if not state.get("market_preference"):
            missing.append("which market they invest in")
        if not (state.get("existing_portfolio_stocks") or state.get("new_stocks")):
            missing.append("their holdings or at least one stock to consider")
        if not (state.get("investment_amount") or 0) > 0:
            missing.append("how much they want to invest")
        if not state.get("diversification_preference"):
            missing.append("what kind of investor they are")
        if not state.get("receiver_email_id"):
            missing.append("their email address")

        if missing:
            return {
                "status": "incomplete",
                "missing": missing,
                "message": "Not dispatched. Collect the missing details and call this again.",
            }

        if state.get("analysis_dispatched"):
            return {
                "status": "already_dispatched",
                "message": "The analysis is already running for this session.",
            }

        if ANALYSER_AGENT_NAME not in self.remote_agent_connections:
            return {
                "status": "error",
                "message": (
                    f"{ANALYSER_AGENT_NAME} is not reachable right now. Tell the user "
                    "the analysis service is temporarily unavailable."
                ),
            }

        brief = self._build_brief(state.to_dict())
        logger.info("Dispatching analysis brief (%d chars) to %s", len(brief), ANALYSER_AGENT_NAME)
        self.send_message_background(agent_name=ANALYSER_AGENT_NAME, task=brief)

        state["analysis_dispatched"] = True
        return {
            "status": "dispatched",
            "message": (
                "The analysis is running. Tell the user their stock allocation "
                f"report will be emailed to {state.get('receiver_email_id')}."
            ),
        }

    def _build_brief(self, state: dict) -> str:
        """Assemble everything the analyst needs, in one message."""
        existing = state.get("existing_portfolio_stocks") or []
        new = state.get("new_stocks") or []
        counts = state.get("share_counts") or {}
        market = state.get("market_preference", "US")
        symbol = "₹" if market == "INDIA" else "$"

        if counts:
            holdings_block = "\n".join(f"- {t}: {s} shares" for t, s in counts.items())
            no_counts = [t for t in existing if t not in counts]
            if no_counts:
                holdings_block += (
                    f"\n\nNo share count available for: {', '.join(no_counts)}. "
                    "These positions can only be rated HOLD, never SELL."
                )
        else:
            holdings_block = (
                "No share counts were provided. No position may be rated SELL; "
                "use HOLD and say why."
            )

        portfolio_context = state.get("stock_report_response") or "No statement was parsed."

        return f"""
PORTFOLIO ANALYSIS REQUEST

USER ID: {self.current_session_id.get("user_id", "unknown")}
SESSION ID: {self.current_session_id.get("id", "unknown")}
MARKET: {market}
CURRENCY: {symbol}
INVESTMENT AMOUNT: {symbol}{float(state.get("investment_amount") or 0):,.2f}
RECEIVER EMAIL ID: {state.get("receiver_email_id", "")}

EXISTING PORTFOLIO STOCKS: {", ".join(existing) if existing else "None"}
NEW STOCKS TO CONSIDER: {", ".join(new) if new else "None"}

CURRENT HOLDINGS AND SHARE COUNTS:
{holdings_block}

PARSED PORTFOLIO STATEMENT:
{portfolio_context}

THE USER'S INVESTMENT STRATEGY, IN THEIR OWN WORDS:
{state.get("diversification_preference", "")}

Every recommendation must be justified against that strategy - its time
horizon, its risk appetite and any sector preferences it states. Analyse both
the existing holdings and the new candidates, and allocate the investment
amount across whatever you rate BUY.
""".strip()

    # ------------------------------------------------------------------
    # A2A transport
    # ------------------------------------------------------------------

    async def _send_message_async(self, agent_name: str, task: str):
        connection = self.remote_agent_connections.get(agent_name)
        if connection is None:
            raise ValueError(f"Agent {agent_name} not found")

        message_id = str(uuid.uuid4())
        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams.model_validate(
                {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": task}],
                        "messageId": message_id,
                        "contextId": str(uuid.uuid4()),
                    }
                }
            ),
        )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            ) as http_client:
                from a2a.client import A2AClient

                client = A2AClient(http_client, connection.card, url=connection.agent_url)
                response: SendMessageResponse = await client.send_message(request)

            if not isinstance(response.root, SendMessageSuccessResponse) or not isinstance(
                response.root.result, Task
            ):
                logger.error("Non-success response from %s", agent_name)
                return f"Error: invalid response from {agent_name}"

            payload = json.loads(response.root.model_dump_json(exclude_none=True))
            parts: list = []
            for artifact in payload.get("result", {}).get("artifacts") or []:
                parts.extend(artifact.get("parts") or [])
            logger.info("Received %d parts from %s", len(parts), agent_name)
            return parts

        except httpx.TimeoutException as exc:
            logger.error("Timeout talking to %s: %s", agent_name, exc)
            return f"Error: {agent_name} timed out. It may still be processing."
        except Exception as exc:
            logger.error("Error talking to %s: %s", agent_name, exc)
            return f"Error: could not reach {agent_name}: {exc}"

    _RETRYABLE = ("timeout", "connection", "network", "unavailable", "server error")

    async def _send_with_retry(self, agent_name: str, task: str, attempts: int = 3):
        """Await a remote agent, retrying only what is worth retrying.

        `_send_message_async` reports failure by returning a string beginning
        "Error" rather than by raising, so both shapes are treated as failure
        here - checking only for exceptions would make this loop never retry.
        """
        last_error = ""
        for attempt in range(attempts):
            try:
                result = await self._send_message_async(agent_name, task)
                if not (isinstance(result, str) and result.startswith("Error")):
                    return result
                last_error = result
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"

            if attempt == attempts - 1 or not any(
                word in last_error.lower() for word in self._RETRYABLE
            ):
                break
            logger.warning("Retrying %s after: %s", agent_name, last_error)
            await asyncio.sleep(2 ** attempt)

        logger.error("Giving up on %s: %s", agent_name, last_error)
        return f"Error: could not reach {agent_name}: {last_error}"

    def send_message(self, agent_name: str, task: str):
        """Send a task to a remote agent and wait for its reply."""
        if agent_name not in self.remote_agent_connections:
            return (
                f"Error: agent '{agent_name}' not found. "
                f"Available: {list(self.remote_agent_connections)}"
            )

        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                return asyncio.run(self._send_message_async(agent_name, task))
            except Exception as exc:
                last_error = exc
                retryable = any(
                    word in str(exc).lower()
                    for word in ("timeout", "connection", "network", "unavailable", "server error")
                )
                if not retryable or attempt == 2:
                    break
                time.sleep(2 ** attempt)

        logger.error("Giving up on %s: %s", agent_name, last_error)
        return f"Error: could not reach {agent_name}: {last_error}"

    def send_message_background(self, agent_name: str, task: str) -> str:
        """Fire a task at a remote agent without blocking the conversation."""

        def run():
            try:
                result = self.send_message(agent_name, task)
                logger.info("Background task to %s finished: %s", agent_name, str(result)[:200])
            except Exception as exc:
                logger.error("Background task to %s failed: %s", agent_name, exc)

        threading.Thread(target=run, daemon=True, name=f"a2a-{agent_name}").start()
        return f"Task dispatched to {agent_name}."

    # ------------------------------------------------------------------
    # File handling and diagnostics used by the API layer
    # ------------------------------------------------------------------

    def store_portfolio_file(self, user_name: str, file_path: str, session_id: str) -> str:
        """Store an uploaded portfolio statement locally or in S3."""
        try:
            extension = os.path.splitext(file_path)[1]
            lowered = extension.lower()
            if lowered == ".pdf":
                input_format = "pdf"
            elif lowered in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}:
                input_format = "image"
            else:
                input_format = "unknown"

            filename = f"{user_name}_{session_id}_portfolio_statement{extension}"
            logger.info("Storing %s upload for session %s as %s", input_format, session_id, filename)

            if current_config.is_local():
                storage_path = current_config.LOCAL_STORAGE_PATH
                os.makedirs(storage_path, exist_ok=True)
                target = os.path.join(storage_path, filename)
                shutil.copy2(file_path, target)
                location = target
            else:
                bucket = current_config.S3_BUCKET_NAME
                boto3.client("s3").upload_file(file_path, bucket, filename)
                location = f"s3://{bucket}/{filename}"

            if session_id:
                try:
                    db = next(get_db())
                    try:
                        mark_portfolio_statement_uploaded(db, session_id, input_format=input_format)
                    finally:
                        db.close()
                except Exception as exc:
                    logger.error("Could not record the upload for %s: %s", session_id, exc)

            return f"Portfolio file stored successfully at: {location}"
        except Exception as exc:
            logger.error("Error storing portfolio file: %s", exc)
            return f"Error: {exc}"

    def get_agent_status(self) -> str:
        """Human-readable status of the remote agent connections."""
        if not self.remote_agent_connections:
            return "**Connected Agents Status:**\n\nNo agents are connected."

        lines = ["**Connected Agents Status:**", ""]
        for name, connection in self.remote_agent_connections.items():
            lines.append(f"- **{name}** at {connection.agent_url}")
        return "\n".join(lines)

    def test_agent_connection(self, agent_name: str) -> str:
        """Send a trivial message to a remote agent to check it responds."""
        if agent_name not in self.remote_agent_connections:
            return (
                f"Agent '{agent_name}' is not connected. "
                f"Available: {list(self.remote_agent_connections)}"
            )
        result = self.send_message(agent_name, "Connection test. Reply with 'ok'.")
        if isinstance(result, str) and result.startswith("Error"):
            return f"{agent_name} did not respond: {result}"
        return f"{agent_name} responded successfully."


class _StateView:
    """Minimal stand-in for ReadonlyContext when rendering the state brief."""

    def __init__(self, state: dict):
        self.state = state


def _get_initialized_host_agent_sync() -> HostAgent:
    """Build a fully connected HostAgent from a synchronous context."""
    urls = [
        current_config.STOCK_ANALYSER_AGENT_URL,
        current_config.DOCUMENT_ANALYSER_AGENT_URL,
    ]

    async def build():
        return await HostAgent.create(remote_agent_addresses=urls)

    return asyncio.run(build())


root_agent = None

"""
Ticker resolution.

The old code made two LLM calls for every batch of stocks the user mentioned:
one to turn names into symbols, then a second to check those symbols against
the chosen market. Both parsed free-form JSON out of a text response. This is
one structured-output call that does both jobs.
"""

import json
import logging
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_core.models import MODEL, generation_config, genai_client
from agent_core.schemas import TickerResolution

logger = logging.getLogger("host_agent_api.tickers")

_SYSTEM = """
You convert what a user typed into exchange-correct stock tickers, and you
reject anything listed on the wrong exchange.

US market: symbols carry no country suffix - AAPL, GOOGL, MSFT, JPM, VOO, SPY.
India market: symbols carry .NS (NSE) or .BO (BSE) - RELIANCE.NS, TCS.BO,
INFY.NS. An unmistakably Indian company typed without a suffix should be
resolved to its .NS form.

Put every symbol that belongs to the requested market in `resolved`, uppercase.
Put anything listed elsewhere, or that you cannot identify as a real listed
security, in `rejected`, and say briefly in `explanation` what was wrong with
each one. Never guess at a symbol you do not recognise - reject it instead.
""".strip()


def resolve(names: List[str], market_preference: str) -> TickerResolution:
    """Resolve user-supplied names or symbols for a specific market."""
    market_name = "India" if market_preference == "INDIA" else "US"
    logger.info("Resolving %s for the %s market", names, market_name)

    client = genai_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=(
            f"Requested market: {market_name}\n"
            f"User input: {', '.join(names)}\n\n"
            f"Resolve these to {market_name} market tickers."
        ),
        config=generation_config(
            temperature=0.0,
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=TickerResolution,
        ),
    )

    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, TickerResolution):
        return parsed
    return TickerResolution.model_validate(json.loads(response.text))

"""
Specialist agents the coordinator can call as tools.

Exposed via AgentTool rather than as sub_agents: the coordinator keeps hold of
the conversation and gets an answer back, instead of handing the user over.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from google.adk.agents import LlmAgent

from agent_core.models import MODEL, generation_config
from agent_core.callbacks import log_tool_call, log_tool_result

from .prompts import MARKET_RESEARCHER_INSTRUCTION

logger = logging.getLogger("host_agent_api.specialists")


def search_market_knowledge(query: str) -> str:
    """Look up current stock market facts, prices, news or company data.

    Use for anything time-sensitive or specific enough that answering from
    memory would risk being wrong or stale.

    Args:
        query: The question to research, phrased as a full question.

    Returns:
        A researched answer, or an explanation of why the lookup failed.
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        logger.warning("PERPLEXITY_API_KEY is not set; cannot research live market data")
        return (
            "Live market lookup is unavailable right now. Answer from general "
            "knowledge if you can do so accurately, and say the figure may be stale."
        )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        response = client.chat.completions.create(
            model="sonar",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a stock market research assistant. Answer factually "
                        "and concisely. Always state the date or timeframe for any "
                        "price or market figure you quote."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        if response.choices:
            return response.choices[0].message.content.strip()
        return "The research service returned no answer."
    except Exception as exc:
        logger.error("Market knowledge lookup failed: %s", exc)
        return f"Live market lookup failed ({exc}). Say so rather than guessing at figures."


def build_market_researcher() -> LlmAgent:
    """An agent that answers stock questions outside the main workflow."""
    return LlmAgent(
        model=MODEL,
        name="market_researcher",
        description=(
            "Answers general stock market and investing questions - concepts, "
            "company background, current prices and news. Use this for any "
            "stock-related question that is not part of collecting the user's "
            "portfolio details."
        ),
        instruction=MARKET_RESEARCHER_INSTRUCTION,
        generate_content_config=generation_config(temperature=0.3),
        tools=[search_market_knowledge],
        before_tool_callback=log_tool_call,
        after_tool_callback=log_tool_result,
    )

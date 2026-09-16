"""
Central model configuration for every agent in the backend.

One place decides which Gemini model the system talks to, and how it is
configured. Agents import from here instead of hard-coding model ids at each
call site, so a model bump is a one-line change.
"""

import logging
import os

from google.genai import types

logger = logging.getLogger(__name__)

# The single model the whole backend runs on.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

# Thinking budget is opt-in: unset means we send no thinking_config at all,
# which keeps us compatible with model builds that do not accept the field.
_THINKING_BUDGET = os.getenv("GEMINI_THINKING_BUDGET")


def _thinking_config() -> types.ThinkingConfig | None:
    if _THINKING_BUDGET is None:
        return None
    try:
        return types.ThinkingConfig(
            include_thoughts=False,
            thinking_budget=int(_THINKING_BUDGET),
        )
    except ValueError:
        logger.warning(
            "GEMINI_THINKING_BUDGET=%r is not an integer; ignoring it",
            _THINKING_BUDGET,
        )
        return None


def generation_config(
    temperature: float = 0.4,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    response_mime_type: str | None = None,
    response_schema: object | None = None,
) -> types.GenerateContentConfig:
    """Build a GenerateContentConfig with the backend's shared defaults.

    Conversational agents want some warmth; analysis agents pass a lower
    temperature. Everything else stays consistent across agents.
    """
    kwargs: dict = {"temperature": temperature}

    thinking = _thinking_config()
    if thinking is not None:
        kwargs["thinking_config"] = thinking
    if system_instruction is not None:
        kwargs["system_instruction"] = system_instruction
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if response_mime_type is not None:
        kwargs["response_mime_type"] = response_mime_type
    if response_schema is not None:
        kwargs["response_schema"] = response_schema

    return types.GenerateContentConfig(**kwargs)


def genai_client():
    """Return a google-genai client configured the same way ADK configures itself.

    Used by the few call sites that need a direct one-shot generate_content
    call (document parsing, ticker normalisation) rather than a full agent.
    """
    from google import genai

    if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
        logger.info("Using Vertex AI backend for model %s", MODEL)
        return genai.Client(vertexai=True)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE"
        )
    logger.info("Using Google AI API backend for model %s", MODEL)
    return genai.Client(api_key=api_key)

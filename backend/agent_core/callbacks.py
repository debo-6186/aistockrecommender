"""
Cross-cutting agent behaviour, expressed as ADK callbacks.

Logging and other concerns that apply to every tool belong here rather than
being repeated inside each tool body.
"""

import logging
from typing import Any, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import BaseTool, ToolContext

logger = logging.getLogger(__name__)

_PREVIEW_CHARS = 400


def _truncate(value: Any, limit: int = _PREVIEW_CHARS) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... ({len(text)} chars)"


def log_tool_call(
    tool: BaseTool, args: dict[str, Any], tool_context: ToolContext
) -> Optional[dict]:
    """Trace every tool invocation with its arguments."""
    rendered = ", ".join(f"{k}={_truncate(v, 120)}" for k, v in args.items())
    logger.info("tool -> %s(%s)", tool.name, rendered)
    return None


def log_tool_result(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: Any,
) -> Optional[dict]:
    """Trace what each tool gave back, truncated."""
    logger.info("tool <- %s: %s", tool.name, _truncate(tool_response))
    return None


def log_agent_entry(callback_context: CallbackContext) -> None:
    """Note which agent picked up the turn - useful when delegation is dynamic."""
    logger.info("agent -> %s", callback_context.agent_name)
    return None

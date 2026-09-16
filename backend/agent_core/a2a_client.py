"""
A minimal A2A client for agent-to-agent calls.

The host agent keeps a resolved connection per remote agent because it talks to
several and wants their cards at startup. An agent that calls exactly one
downstream service at a known URL needs none of that machinery - just send the
message and read the reply.
"""

import json
import logging
import uuid

import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(300.0, connect=60.0, read=300.0, write=60.0)


async def send(agent_url: str, text: str) -> str:
    """Send one message to an A2A agent and return its reply as text.

    Raises nothing: transport problems come back as a string beginning "Error",
    because the caller is a tool whose job is to report what happened rather
    than to propagate an exception into the model's context.
    """
    message_id = str(uuid.uuid4())
    request = SendMessageRequest(
        id=message_id,
        params=MessageSendParams.model_validate(
            {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                    "messageId": message_id,
                    "contextId": str(uuid.uuid4()),
                }
            }
        ),
    )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as http_client:
            card = await A2ACardResolver(http_client, agent_url).get_agent_card()
            client = A2AClient(http_client, card, url=agent_url)
            response: SendMessageResponse = await client.send_message(request)

        if not isinstance(response.root, SendMessageSuccessResponse) or not isinstance(
            response.root.result, Task
        ):
            logger.error("Non-success response from %s", agent_url)
            return f"Error: invalid response from {agent_url}"

        payload = json.loads(response.root.model_dump_json(exclude_none=True))
        texts: list[str] = []
        for artifact in payload.get("result", {}).get("artifacts") or []:
            for part in artifact.get("parts") or []:
                if isinstance(part, dict) and part.get("text"):
                    texts.append(part["text"])
        return "\n".join(texts).strip() or "(the agent replied with no text)"

    except httpx.TimeoutException as exc:
        logger.error("Timeout talking to %s: %s", agent_url, exc)
        return f"Error: {agent_url} timed out. It may still be processing."
    except Exception as exc:
        logger.error("Error talking to %s: %s", agent_url, exc)
        return f"Error: could not reach {agent_url}: {exc}"


def send_sync(agent_url: str, text: str) -> str:
    """Blocking wrapper, for use from a synchronous tool body.

    The tool body itself typically runs inside ADK's own event loop, so
    `asyncio.run()` cannot be used directly here - it raises if a loop is
    already running on this thread. Run the coroutine on a fresh loop in a
    separate thread instead, and block on that thread's result.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(send(agent_url, text))

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, send(agent_url, text))
        return future.result()

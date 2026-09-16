import os

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)
from agent import create_agent
from agent_executor import StockReportGeneratorAgentExecutor
from dotenv import load_dotenv
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from logger import setup_logging, get_logger

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from agent_core.sessions import get_session_service

load_dotenv()

# Setup logging
setup_logging()
logger = get_logger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""

    pass


def main():
    """Starts the agent server."""
    host = "0.0.0.0"  # Listen on all interfaces to accept connections from other containers
    port = 10004
    advertised = os.getenv("STOCK_REPORT_GENERATOR_AGENT_URL", f"http://localhost:{port}")
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            if not os.getenv("GOOGLE_API_KEY"):
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )

        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="generate_stock_report",
            name="Generate and send a stock report",
            description=(
                "Turn a finished stock allocation into a readable report - a covering "
                "note explaining what it recommends and why - and email it to the "
                "investor."
            ),
            tags=["report", "email", "portfolio", "delivery"],
            examples=[
                "Generate and send the report for this session",
                "Write up the allocation and email it",
            ],
        )
        agent_card = AgentCard(
            name="stock_report_generator_agent",
            description=(
                "Turns a finished stock allocation into a readable report and delivers "
                "it to the investor by email."
            ),
            url=f"{advertised.rstrip('/')}/",
            version="1.0.0",
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain"],
            capabilities=capabilities,
            skills=[skill],
        )

        adk_agent = create_agent()
        runner = Runner(
            app_name=agent_card.name,
            agent=adk_agent,
            artifact_service=InMemoryArtifactService(),
            session_service=get_session_service(),
            memory_service=InMemoryMemoryService(),
        )
        agent_executor = StockReportGeneratorAgentExecutor(runner)

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=InMemoryTaskStore(),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # Build the Starlette app
        app = server.build()

        # Add custom health check endpoint
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def health_check(request):
            return JSONResponse({"status": "healthy", "service": "Stock Report Generator Agent"})

        # Add health route to the app
        app.routes.insert(0, Route("/health", health_check))

        logger.info("Added custom /health endpoint")

        uvicorn.run(app, host=host, port=port)
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()

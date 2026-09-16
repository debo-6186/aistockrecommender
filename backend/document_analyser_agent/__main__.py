import logging
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
from agent_executor import DocumentAnalyserAgentExecutor
from dotenv import load_dotenv
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner

import sys as _sys

_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_core.sessions import get_session_service

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Exception for missing API key."""

    pass


def main():
    """Starts the agent server."""
    # Bind on all interfaces so other containers can reach it; the card
    # advertises the address callers should actually use.
    host = "0.0.0.0"
    port = 10003
    advertised = os.getenv("DOCUMENT_ANALYSER_AGENT_URL", f"http://localhost:{port}")
    try:
        # Check for API key only if Vertex AI is not configured
        if not os.getenv("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE":
            if not os.getenv("GOOGLE_API_KEY"):
                raise MissingAPIKeyError(
                    "GOOGLE_API_KEY environment variable not set and GOOGLE_GENAI_USE_VERTEXAI is not TRUE."
                )

        capabilities = AgentCapabilities(streaming=True)
        skill = AgentSkill(
            id="document_analyse",
            name="Analyse financial documents",
            description=(
                "Read an uploaded financial document - a portfolio statement, a broker "
                "contract note, or a company annual or quarterly report - and return its "
                "contents as structured data. Handles PDFs with a text layer, scanned "
                "PDFs and screenshots, using OCR where there is no text to extract."
            ),
            tags=["document", "ocr", "portfolio", "contract-note", "annual-report"],
            examples=[
                "Read the portfolio statement uploaded for this session",
                "Extract the trades from this contract note",
                "Summarise the figures in this quarterly report",
            ],
        )
        agent_card = AgentCard(
            name="document_analyser_agent",
            description=(
                "Reads uploaded financial documents of any supported type and returns "
                "structured, schema-validated data from them."
            ),
            url=f"{advertised.rstrip('/')}/",
            version="2.0.0",
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
        agent_executor = DocumentAnalyserAgentExecutor(runner)

        request_handler = DefaultRequestHandler(
            agent_executor=agent_executor,
            task_store=InMemoryTaskStore(),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        app = server.build()

        # Orchestrators health-check this before routing to the agent, so it has
        # to exist - a missing route reads as an unhealthy task, not a missing
        # endpoint, and the container is restarted in a loop.
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def health_check(request):
            return JSONResponse({"status": "healthy", "service": "Document Analyser Agent"})

        app.routes.insert(0, Route("/health", health_check))
        logger.info("Added /health endpoint")

        uvicorn.run(app, host=host, port=port)
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()

"""
Postgres-backed session persistence for all ADK agents.

Sessions, their event history and their state all live in the same Postgres
instance the rest of the backend uses. ADK owns those tables and manages them,
which replaces the hand-rolled "serialise a dict into agent_states, then paste
the transcript back into the next prompt" approach.
"""

import logging
import os

from google.adk.sessions import BaseSessionService, DatabaseSessionService, InMemorySessionService

logger = logging.getLogger(__name__)

_session_service: BaseSessionService | None = None


def _database_url() -> str | None:
    """Resolve the Postgres URL the same way the app config does."""
    env = os.getenv("ENVIRONMENT", "local").lower()
    if env == "production":
        url = os.getenv("DATABASE_URL_PRODUCTION") or os.getenv("DATABASE_URL")
    else:
        url = os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    return url


def _normalise(url: str) -> str:
    """DatabaseSessionService needs an async driver, unlike the rest of the app."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_session_service() -> BaseSessionService:
    """Return the process-wide session service.

    Falls back to in-memory only when no database is configured, so local
    experiments still run, but production always persists.
    """
    global _session_service
    if _session_service is not None:
        return _session_service

    url = _database_url()
    if not url:
        logger.warning(
            "No DATABASE_URL configured - falling back to InMemorySessionService. "
            "Conversation state will not survive a restart."
        )
        _session_service = InMemorySessionService()
        return _session_service

    try:
        _session_service = DatabaseSessionService(db_url=_normalise(url))
        logger.info("ADK sessions persisting to Postgres")
    except Exception as exc:  # pragma: no cover - startup diagnostics
        logger.error("Could not open DatabaseSessionService (%s); using in-memory", exc)
        _session_service = InMemorySessionService()

    return _session_service

"""
The document analyser.

One agent reads every kind of document the product accepts. The pipeline is the
same for all of them - find the file, get text out of it, extract that text
against a schema - and what varies per type is a registry entry, not a code
path. See doc_types.py.

The agent decides how to approach a document it cannot immediately place. What
stays fixed is the shape of the answer, which is a validated schema rather than
prose the caller has to pick apart.
"""

import json
import logging
import os
import sys

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "host_agent"))

from agent_core.callbacks import log_agent_entry, log_tool_call, log_tool_result
from agent_core.models import MODEL, generation_config, genai_client
from agent_core.schemas import DocumentClassification

import doc_types
import reader

load_dotenv()
logger = logging.getLogger(__name__)

try:
    from database import get_db, mark_portfolio_statement_uploaded, update_agent_state
except ImportError as exc:  # pragma: no cover - the agent still reads documents
    logger.warning("Database functions unavailable (%s); results will not be handed back", exc)
    get_db = None
    mark_portfolio_statement_uploaded = None
    update_agent_state = None

# Where the host picks the structured result up. The A2A reply carries prose;
# the extraction itself travels through Postgres, so a long holdings list
# cannot be truncated by the model summarising its own work.
HANDOFF_AGENT_NAME = "document_analyser"



_MAX_EXTRACTION_CHARS = 60_000


AGENT_INSTRUCTION = f"""
You read uploaded financial documents and report what is in them, as structured
data. Getting text out of the file and making sense of that text are both your
job.

# The documents you handle

{doc_types.classifier_hints()}

# Working through a request

The message you are sent carries a session id, the name of the user who
uploaded the file, and sometimes the document text inline. Read it, then:

- `read_document` when a file was uploaded - it finds the upload for that
  session and gets text out of it, using OCR when the file is a scan or a
  screenshot.
- `record_document_text` instead when the message carries the text inline
  rather than pointing at an upload.

Then `classify_document` to establish what you are looking at, and
`extract_document` to pull it apart against that type's schema.

If the caller has already told you which type to expect, you may go straight to
`extract_document` with it. Classify when the message does not say, or when
what you read does not match what was claimed - a mismatch is worth reporting,
not quietly working around.

# Reporting back

Say what the document was, what you extracted, and anything the caller needs to
know before acting on it. For holdings, state explicitly which positions carry
no share count - that gap decides whether they can be sold later, so it must be
said rather than implied.

# Judgement calls that are yours to make

- If `read_document` finds nothing, or OCR comes back empty, say so and stop.
  Never guess at contents you could not read.
- If the document turns out not to be the type it was sent as, report what it
  actually is rather than forcing it into the wrong schema.
- If a scan is legible in places and not in others, extract what is legible and
  say which parts were not.

# What you must never do

- Never invent a ticker, a figure, a quantity or a date. Everything you report
  comes from the document.
- Never derive a share count from a percentage and a total.
""".strip()


CLASSIFIER_SYSTEM = f"""
You identify which kind of financial document a piece of text is.

The supported types are:

{doc_types.classifier_hints()}

Decide from what the text actually contains, not from what it is titled. A
document that matches none of these is 'unknown' - say so rather than choosing
the nearest fit, because the caller handles an unknown document better than a
misfiled one.
""".strip()


# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------


def read_document(session_id: str, user_name: str, tool_context: ToolContext) -> dict:
    """Find the document uploaded for a session and get its text.

    Handles PDFs with a text layer, scanned PDFs and screenshots. Which route
    is taken is decided from the file itself, not from its extension: a PDF
    whose text layer comes back near-empty is a scan, and gets OCR'd.

    Args:
        session_id: The session the upload belongs to.
        user_name: The user id the file was stored under.

    Returns:
        How much text was read and how it was obtained, or why it failed.
    """
    if not session_id or not user_name:
        return {
            "status": "error",
            "message": "A session id and a user name are both needed to find the upload.",
        }

    file_bytes, extension = reader.fetch_upload(session_id, user_name)
    if not file_bytes:
        return {
            "status": "error",
            "message": f"No uploaded document was found for session {session_id}.",
        }

    text, method = reader.read_bytes(file_bytes, extension)
    if method == "failed" or not text.strip():
        return {
            "status": "error",
            "message": (
                f"The {extension} upload was found ({len(file_bytes)} bytes) but no text "
                "could be read from it, by text layer or by OCR."
            ),
        }

    tool_context.state["document_text"] = text
    tool_context.state["session_id"] = session_id
    tool_context.state["user_name"] = user_name
    tool_context.state["read_method"] = method

    _mark_uploaded(session_id, "pdf" if extension == ".pdf" else "image")

    return {
        "status": "ok",
        "characters": len(text),
        "file_extension": extension,
        "read_method": method,
        "note": (
            "Read by OCR - the file had no usable text layer."
            if method == "ocr"
            else "Read from the file's own text layer."
        ),
        "preview": text[:800],
    }


def record_document_text(
    document_text: str, session_id: str, tool_context: ToolContext
) -> dict:
    """Take document text the caller supplied inline, instead of an upload.

    Args:
        document_text: The text to analyse, exactly as it was given.
        session_id: The session it belongs to, or an empty string.

    Returns:
        Confirmation of how much text was recorded.
    """
    if not document_text or len(document_text.strip()) < 3:
        return {"status": "error", "message": "No document text was provided."}

    tool_context.state["document_text"] = document_text
    tool_context.state["session_id"] = session_id
    tool_context.state["read_method"] = "inline"
    if session_id and get_db is not None:
        _mark_uploaded(session_id, "text")

    return {"status": "ok", "characters": len(document_text), "preview": document_text[:800]}


def classify_document(tool_context: ToolContext) -> dict:
    """Work out which supported type the document that was read is.

    Returns:
        The type, how confident the call was, and what decided it.
    """
    text = tool_context.state.get("document_text") or ""
    if not text.strip():
        return {"status": "error", "message": "No document has been read yet."}

    try:
        client = genai_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Document text:\n\n{text[:_MAX_EXTRACTION_CHARS]}",
            config=generation_config(
                temperature=0.0,
                system_instruction=CLASSIFIER_SYSTEM,
                response_mime_type="application/json",
                response_schema=DocumentClassification,
            ),
        )
    except Exception as exc:
        logger.error("Classification failed: %s", exc)
        return {"status": "error", "message": f"Could not classify the document: {exc}"}

    parsed = getattr(response, "parsed", None)
    if not isinstance(parsed, DocumentClassification):
        try:
            parsed = DocumentClassification.model_validate(json.loads(response.text))
        except Exception as exc:
            return {"status": "error", "message": f"The classification could not be read: {exc}"}

    tool_context.state["document_type"] = parsed.document_type
    logger.info(
        "Classified as %s (%s): %s",
        parsed.document_type,
        parsed.confidence,
        parsed.reasoning,
    )
    return {
        "status": "ok",
        "document_type": parsed.document_type,
        "confidence": parsed.confidence,
        "reasoning": parsed.reasoning,
        "supported_types": doc_types.supported(),
    }


def extract_document(document_type: str, tool_context: ToolContext) -> dict:
    """Extract the document against the schema for its type.

    Args:
        document_type: One of the supported types, as returned by
            `classify_document`.

    Returns:
        The structured extraction, or why it could not be produced.
    """
    spec = doc_types.get(document_type)
    if spec is None:
        return {
            "status": "error",
            "message": f"'{document_type}' is not a supported type.",
            "supported_types": doc_types.supported(),
        }

    text = tool_context.state.get("document_text") or ""
    if not text.strip():
        return {"status": "error", "message": "No document has been read yet."}

    if len(text) > _MAX_EXTRACTION_CHARS:
        logger.warning(
            "Document is %d chars; truncating to %d for extraction",
            len(text),
            _MAX_EXTRACTION_CHARS,
        )
        text = text[:_MAX_EXTRACTION_CHARS]

    try:
        client = genai_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=f"Document text:\n\n{text}",
            config=generation_config(
                temperature=0.0,
                system_instruction=spec.instruction,
                response_mime_type="application/json",
                response_schema=spec.schema,
            ),
        )
    except Exception as exc:
        logger.error("Extraction of %s failed: %s", document_type, exc)
        return {"status": "error", "message": f"Could not read the document: {exc}"}

    parsed = getattr(response, "parsed", None)
    if not isinstance(parsed, spec.schema):
        try:
            parsed = spec.schema.model_validate(json.loads(response.text))
        except Exception as exc:
            return {"status": "error", "message": f"The extraction could not be read back: {exc}"}

    payload = parsed.model_dump()

    if not payload.get(spec.validity_field, True):
        result = {
            "status": "wrong_document_type",
            "document_type": document_type,
            "message": payload.get("rejection_reason")
            or f"This does not look like a {document_type.replace('_', ' ')}.",
        }
        _hand_off(tool_context, result)
        return result

    # The caller gets the whole extraction; the model gets a summary of it.
    # It has no use for the full document back in its context, and a long
    # holdings list repeated there is exactly the waste worth avoiding.
    record = {
        "status": "ok",
        "document_type": document_type,
        "read_method": tool_context.state.get("read_method", "unknown"),
        "extraction": payload,
    }
    record.update(_shape_for_caller(document_type, payload))

    tool_context.state["extraction"] = record
    _hand_off(tool_context, record)
    return _summarise(document_type, spec, payload, record["read_method"])


# ----------------------------------------------------------------------
# Handing the result back
# ----------------------------------------------------------------------


def _summarise(document_type: str, spec, payload: dict, read_method: str) -> dict:
    """What the model needs to know to report back, and no more."""
    summary: dict = {
        "status": "ok",
        "document_type": document_type,
        "read_method": read_method,
        "handed_off": True,
    }

    for field in spec.summary_fields:
        value = payload.get(field)
        if isinstance(value, list):
            summary[f"{field}_count"] = len(value)
            if field == "holdings":
                summary["tickers"] = [
                    h.get("ticker") for h in value if isinstance(h, dict) and h.get("ticker")
                ]
            elif value and all(isinstance(v, str) for v in value):
                summary[field] = value
        else:
            summary[field] = value

    if payload.get("notes"):
        summary["notes"] = payload["notes"]
    return summary


def _shape_for_caller(document_type: str, payload: dict) -> dict:
    """Lift the fields a caller acts on to the top level.

    A portfolio's tickers and share counts are what the host merges into its
    own state, so they are surfaced rather than left nested for it to dig out.
    """
    if document_type != "portfolio_statement":
        return {}

    holdings = payload.get("holdings") or []
    return {
        "detected_market": payload.get("detected_market", "UNKNOWN"),
        "holdings": holdings,
        "tickers": [h.get("ticker") for h in holdings if h.get("ticker")],
        "share_counts": {
            h["ticker"]: h["shares"]
            for h in holdings
            if h.get("ticker") and h.get("shares") is not None
        },
        "missing_share_counts": payload.get("holdings_missing_share_counts") or [],
        "notes": payload.get("notes", ""),
    }


def _hand_off(tool_context: ToolContext, result: dict) -> None:
    """Write the extraction where the calling agent will read it.

    A2A carries text, and asking the model to echo a long extraction back as
    JSON invites truncation. The structured result goes through Postgres
    instead, keyed by session, and the A2A reply is left to be prose.
    """
    session_id = tool_context.state.get("session_id") or ""
    if not session_id or update_agent_state is None:
        logger.warning("No session id or no database; the caller cannot collect this result")
        return

    try:
        db = next(get_db())
        try:
            update_agent_state(db, session_id, HANDOFF_AGENT_NAME, json.dumps(result))
            logger.info("Handed off %s result for session %s", result.get("status"), session_id)
        finally:
            db.close()
    except Exception as exc:
        logger.error("Could not hand off the result for %s: %s", session_id, exc)


def _mark_uploaded(session_id: str, input_format: str) -> None:
    if mark_portfolio_statement_uploaded is None:
        return
    try:
        db = next(get_db())
        try:
            mark_portfolio_statement_uploaded(db, session_id, input_format=input_format)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not record the upload for %s: %s", session_id, exc)


def create_agent() -> LlmAgent:
    """Build the document analyser."""
    return LlmAgent(
        model=MODEL,
        name="document_analyser_agent",
        description="Reads uploaded financial documents and returns structured data from them.",
        instruction=AGENT_INSTRUCTION,
        generate_content_config=generation_config(temperature=0.2),
        tools=[read_document, record_document_text, classify_document, extract_document],
        before_agent_callback=log_agent_entry,
        before_tool_callback=log_tool_call,
        after_tool_callback=log_tool_result,
    )


root_agent = None

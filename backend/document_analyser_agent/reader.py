"""
Getting text out of an uploaded file.

Two things happen here and both are deterministic: finding the bytes, wherever
they were stored, and turning them into text. The choice between a PDF's own
text layer and vision OCR is made on evidence - how much text the layer
actually yielded - rather than on the file extension, because a scanned
statement is a PDF whose text layer is empty.
"""

import io
import logging
import os
from typing import Optional, Tuple

import fitz  # PyMuPDF
from google.genai import types

from agent_core.models import MODEL, generation_config, genai_client

from config import current_config

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")

# Below this many characters a PDF's text layer is treated as absent and the
# pages are rasterised for OCR instead. A genuine one-page statement clears
# this comfortably; a scan yields either nothing or a few stray ligatures.
_TEXT_LAYER_MIN_CHARS = 120

# Rasterising at 2x gives the vision model enough resolution to read table
# rows without producing images too large to send.
_OCR_ZOOM = 2.0
_OCR_MAX_PAGES = 20

OCR_INSTRUCTION = """
You transcribe financial documents from images.

Reproduce every piece of text you can see, preserving the table structure: keep
each row on its own line and separate columns with ' | '. Include headers,
totals and footnotes.

Transcribe only what is visible. Do not summarise, do not reorder, do not
correct anything that looks wrong, and never fill in a value that is cut off or
illegible - write [illegible] instead. A missing figure is recoverable; an
invented one is not.
""".strip()


# ----------------------------------------------------------------------
# Locating the upload
# ----------------------------------------------------------------------


def _local_bytes(base: str, extensions: tuple[str, ...]) -> Tuple[Optional[bytes], str]:
    root = current_config.LOCAL_STORAGE_PATH
    for ext in extensions:
        path = os.path.join(root, base + ext)
        if os.path.exists(path):
            logger.info("Reading %s", path)
            with open(path, "rb") as handle:
                return handle.read(), ext
    return None, ""


def _s3_bytes(base: str, extensions: tuple[str, ...]) -> Tuple[Optional[bytes], str]:
    import boto3

    bucket = current_config.S3_BUCKET_NAME
    client = boto3.client("s3")
    for ext in extensions:
        key = base + ext
        buffer = io.BytesIO()
        try:
            client.download_fileobj(bucket, key, buffer)
            buffer.seek(0)
            logger.info("Downloaded s3://%s/%s", bucket, key)
            return buffer.read(), ext
        except Exception as exc:
            logger.debug("s3://%s/%s not available: %s", bucket, key, exc)
    return None, ""


def fetch_upload(session_id: str, user_name: str) -> Tuple[Optional[bytes], str]:
    """Find the file uploaded for this session, whatever format it was saved in.

    Returns the bytes and the extension it was found under, or (None, "") when
    nothing is there.
    """
    if not session_id or not user_name:
        return None, ""

    base = f"{user_name}_{session_id}_portfolio_statement"
    extensions = (".pdf",) + IMAGE_EXTENSIONS

    if current_config.is_local():
        return _local_bytes(base, extensions)
    return _s3_bytes(base, extensions)


# ----------------------------------------------------------------------
# Bytes to text
# ----------------------------------------------------------------------


def _ocr_images(parts: list[types.Part]) -> str:
    """Transcribe rendered pages or a photo with the vision model."""
    client = genai_client()
    response = client.models.generate_content(
        model=MODEL,
        contents=parts + [types.Part.from_text(text="Transcribe this document.")],
        config=generation_config(temperature=0.0, system_instruction=OCR_INSTRUCTION),
    )
    return (response.text or "").strip()


def _pdf_pages_as_images(file_bytes: bytes) -> list[types.Part]:
    """Render a PDF's pages to PNGs the vision model can read."""
    parts: list[types.Part] = []
    with fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf") as document:
        pages = min(len(document), _OCR_MAX_PAGES)
        if len(document) > _OCR_MAX_PAGES:
            logger.warning(
                "PDF has %d pages; OCR is limited to the first %d",
                len(document),
                _OCR_MAX_PAGES,
            )
        matrix = fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM)
        for number in range(pages):
            pixmap = document.load_page(number).get_pixmap(matrix=matrix)
            parts.append(
                types.Part.from_bytes(data=pixmap.tobytes("png"), mime_type="image/png")
            )
    return parts


def read_pdf(file_bytes: bytes) -> Tuple[str, str]:
    """Read a PDF, falling back to OCR when it has no usable text layer.

    Returns the text and how it was obtained, so the caller can say which.
    """
    try:
        with fitz.open(stream=io.BytesIO(file_bytes), filetype="pdf") as document:
            text = "".join(page.get_text() for page in document)
            page_count = len(document)
    except Exception as exc:
        logger.error("Could not open the PDF: %s", exc)
        return "", "failed"

    if len(text.strip()) >= _TEXT_LAYER_MIN_CHARS:
        logger.info("Read %d chars from the text layer of %d pages", len(text), page_count)
        return text, "text_layer"

    logger.info(
        "Text layer yielded only %d chars across %d pages; falling back to OCR",
        len(text.strip()),
        page_count,
    )
    try:
        transcribed = _ocr_images(_pdf_pages_as_images(file_bytes))
    except Exception as exc:
        logger.error("OCR of the PDF failed: %s", exc)
        return text, "failed"

    logger.info("OCR produced %d chars", len(transcribed))
    return transcribed, "ocr"


def read_image(file_bytes: bytes, extension: str) -> Tuple[str, str]:
    """Transcribe a screenshot or photo of a document."""
    mime = "image/jpeg" if extension in {".jpg", ".jpeg"} else f"image/{extension.lstrip('.')}"
    try:
        transcribed = _ocr_images(
            [types.Part.from_bytes(data=file_bytes, mime_type=mime)]
        )
    except Exception as exc:
        logger.error("OCR of the image failed: %s", exc)
        return "", "failed"

    logger.info("OCR produced %d chars from the %s upload", len(transcribed), extension)
    return transcribed, "ocr"


def read_bytes(file_bytes: bytes, extension: str) -> Tuple[str, str]:
    """Turn an uploaded file into text, choosing the route by what it is."""
    if extension == ".pdf":
        return read_pdf(file_bytes)
    if extension in IMAGE_EXTENSIONS:
        return read_image(file_bytes, extension)
    return "", "failed"

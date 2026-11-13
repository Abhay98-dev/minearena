"""Multi-format enterprise document reader (PDF, DOCX, TXT, JSON, CSV, MD).
Extracts raw text streams completely in-memory without writing files to disk.
"""
import io
import json
from typing import Set

import PyPDF2

from .docx_reader import DocxReadError, read_docx_text

SUPPORTED_EXTENSIONS: Set[str] = {".docx", ".pdf", ".txt", ".json", ".csv", ".md", ".log"}


class UnsupportedFileError(ValueError):
    """The file extension is not among supported formats."""


class DocumentReadError(ValueError):
    """Failed to parse or extract text from document."""


def read_pdf_text(data: bytes) -> str:
    """Extract text from PDF pages in memory."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        if len(reader.pages) == 0:
            raise DocumentReadError("PDF document has 0 pages.")
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text.strip())
        extracted = "\n\n".join(pages_text)
        if not extracted.strip():
            raise DocumentReadError("PDF contains no extractable text (document may be a scanned raster image).")
        return extracted
    except Exception as e:
        if isinstance(e, DocumentReadError):
            raise
        raise DocumentReadError(f"Failed to read PDF document: {e}") from e


def read_text_file(data: bytes) -> str:
    """Decode raw bytes into text using standard encodings."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentReadError("Failed to decode text file with standard encodings.")


def extract_document_text(data: bytes, filename: str) -> str:
    """Unified entry point to extract text from any supported format."""
    lower_name = filename.lower()
    ext = "." + lower_name.rsplit(".", 1)[-1] if "." in lower_name else ""

    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(
            f"Unsupported file format '{ext}'. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".docx":
        try:
            return read_docx_text(data)
        except DocxReadError as e:
            raise DocumentReadError(str(e)) from e
    elif ext == ".pdf":
        return read_pdf_text(data)
    elif ext == ".json":
        text = read_text_file(data)
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=2)
        except Exception:
            return text
    else:  # .txt, .csv, .md, .log
        return read_text_file(data)

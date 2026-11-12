"""Small, dependency-free text extractor for Word .docx (Open XML) documents."""
from io import BytesIO
import zlib
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


class DocxReadError(ValueError):
    """The uploaded file is not a readable Word document."""


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_XML_BYTES = 12 * 1024 * 1024


def _paragraph_text(paragraph) -> str:
    parts = []
    for node in paragraph.iter():
        if node.tag == _W + "t":
            parts.append(node.text or "")
        elif node.tag == _W + "tab":
            parts.append("\t")
        elif node.tag in (_W + "br", _W + "cr"):
            parts.append("\n")
    return "".join(parts)


def _body_paragraphs(node):
    """Yield paragraphs in document order, descending through tables/cells."""
    for child in node:
        if child.tag == _W + "p":
            yield child
        else:
            yield from _body_paragraphs(child)


def _xml_text(xml_bytes: bytes, *, body_only: bool) -> str:
    root = ET.fromstring(xml_bytes)
    if body_only:
        body = root.find(_W + "body")
        if body is None:
            return ""
        paragraphs = _body_paragraphs(body)
    else:
        paragraphs = root.iter(_W + "p")
    return "\n".join(text for p in paragraphs if (text := _paragraph_text(p)).strip())


def read_docx_text(data: bytes) -> str:
    """Extract visible paragraph/table text from a DOCX, without writing it to disk."""
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "word/document.xml" not in names:
                raise DocxReadError("Missing document body")
            parts = ["word/document.xml"]
            parts.extend(sorted(
                name for name in names
                if name.startswith(("word/header", "word/footer", "word/footnotes", "word/endnotes"))
                and name.endswith(".xml")
            ))
            total_size = 0
            extracted = []
            for name in parts:
                info = archive.getinfo(name)
                total_size += info.file_size
                if total_size > _MAX_XML_BYTES:
                    raise DocxReadError("Document content is too large")
                xml = archive.read(name)
                extracted.append(_xml_text(xml, body_only=(name == "word/document.xml")))
    except DocxReadError:
        raise
    except (BadZipFile, KeyError, ET.ParseError, OSError, RuntimeError, EOFError, zlib.error, ValueError) as exc:
        raise DocxReadError("Invalid Word document") from exc

    text = "\n".join(part for part in extracted if part).strip()
    if not text:
        raise DocxReadError("The Word document contains no readable text")
    return text

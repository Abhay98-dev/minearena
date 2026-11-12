"""DOCX uploads enter the existing text privacy gateway without changing its contract."""
import asyncio
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from starlette.requests import Request

from app.core import config
from app.core.errors import GatewayError
from app.api.routes.gateway import process_file
from app.database import db
from app.privacy.mapping import mapping_store


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx(paragraphs, table_paragraphs=()):
    def p(text):
        return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'

    table = "".join(f"<w:tr><w:tc>{p(text)}</w:tc></w:tr>" for text in table_paragraphs)
    xml = (f'<w:document xmlns:w="{WORD_NS}"><w:body>'
           f'{"".join(p(text) for text in paragraphs)}<w:tbl>{table}</w:tbl>'
           "<w:sectPr/></w:body></w:document>")
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


@pytest.fixture
def api_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUDIT_DB_PATH", str(tmp_path / "audit.db"))
    monkeypatch.setattr(config, "LLM_FALLBACK", "")
    monkeypatch.setenv("PRIVACY_NER", "heuristic")
    monkeypatch.setenv("PRIVACY_USE_PRESIDIO", "0")
    monkeypatch.setenv("MOCK_MODE", "echo")
    db.init_db()


def _request(body):
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/v1/gateway/process-file", "raw_path": b"/api/v1/gateway/process-file",
        "query_string": b"", "headers": [(b"content-type", DOCX_MIME.encode())],
        "client": ("test", 123), "server": ("test", 80), "root_path": "",
    }
    return Request(scope, receive)


def test_docx_with_multiple_people_and_table_content_uses_existing_gateway(api_setup):
    body = _docx(
        ["Applicant: Rahul Sharma", "PAN: ABCDE1234F"],
        ["Co-applicant: Priya Nair", "PAN: ABCPE1234F"],
    )
    result = asyncio.run(process_file(
        _request(body), filename="loan-records.docx", task="summarize", provider="mock",
    ))

    assert mapping_store.active_count() == 0
    assert "Co-applicant: Priya Nair" in result["original_text"]
    assert {e["type"] for e in result["entities"]} >= {"PERSON", "PAN"}
    assert "Rahul Sharma" not in result["outbound_payload"]
    assert "Priya Nair" not in result["outbound_payload"]
    assert "ABCDE1234F" not in result["outbound_payload"]
    assert "ABCPE1234F" not in result["outbound_payload"]


@pytest.mark.parametrize("filename,body,status,code", [
    ("legacy.doc", b"not a docx", 415, "UNSUPPORTED_FILE"),
    ("broken.docx", b"not a zip archive", 400, "INVALID_DOCUMENT"),
])
def test_docx_upload_reports_safe_file_errors(api_setup, filename, body, status, code):
    with pytest.raises(GatewayError) as exc:
        asyncio.run(process_file(_request(body), filename=filename, provider="mock"))
    assert exc.value.http_status == status
    assert exc.value.code == code

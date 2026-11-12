import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.core import config
from app.core.errors import GatewayError
from app.services.docx_reader import DocxReadError, read_docx_text
from app.services.gateway_service import process_document

router = APIRouter()


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1)
    task: Literal["summarize", "extract"] = "summarize"
    provider: str = Field(default_factory=lambda: config.DEFAULT_PROVIDER)


@router.post("/gateway/process")
async def process(req: ProcessRequest):
    request_id = "req_" + uuid.uuid4().hex[:12]
    return await process_document(req.text, req.task, req.provider, request_id)


@router.post("/gateway/process-file", openapi_extra={
    "requestBody": {"required": True, "content": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
            "schema": {"type": "string", "format": "binary"},
        },
    }},
})
async def process_file(
    request: Request,
    filename: str = Query(...),
    task: Literal["summarize", "extract"] = "summarize",
    provider: str = Query(config.DEFAULT_PROVIDER),
):
    """Accept a raw DOCX body; no multipart parser or disk storage is needed."""
    if not filename.lower().endswith(".docx"):
        raise GatewayError("UNSUPPORTED_FILE")

    max_upload_bytes = max(config.MAX_INPUT_CHARS * 1024, 1024 * 1024)
    contents = bytearray()
    async for chunk in request.stream():
        if len(contents) + len(chunk) > max_upload_bytes:
            raise GatewayError("INPUT_TOO_LARGE")
        contents.extend(chunk)
    if not contents:
        raise GatewayError("INVALID_DOCUMENT")
    try:
        text = await asyncio.to_thread(read_docx_text, bytes(contents))
    except DocxReadError as exc:
        raise GatewayError("INVALID_DOCUMENT") from exc

    request_id = "req_" + uuid.uuid4().hex[:12]
    return await process_document(text, task, provider, request_id)

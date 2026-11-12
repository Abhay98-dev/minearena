import asyncio
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.core import config
from app.core.errors import GatewayError
from app.privacy import destroy_mapping, sanitize_document, validate_outbound_payload
from app.services.docx_reader import DocxReadError, read_docx_text
from app.services.gateway_service import process_document
from app.services.llm.factory import get_provider

router = APIRouter()


class ProcessRequest(BaseModel):
    text: str = Field(..., min_length=1)
    task: Literal["summarize", "extract"] = "summarize"
    provider: str = Field(default_factory=lambda: config.DEFAULT_PROVIDER)


class InspectRequest(BaseModel):
    text: str = Field(..., min_length=1)
    task: Literal["summarize", "extract"] = "summarize"
    provider: str = Field(default_factory=lambda: config.DEFAULT_PROVIDER)


@router.post("/gateway/inspect")
async def inspect(req: InspectRequest):
    """Instant pre-flight inspection: returns masked text, detected entities, exact outbound
    payload and outbound guard verification without waiting for an LLM response."""
    request_id = "req_inspect_" + uuid.uuid4().hex[:10]
    t0 = time.perf_counter()
    if len(req.text) > config.MAX_INPUT_CHARS:
        raise GatewayError("INPUT_TOO_LARGE", request_id)
    prov = get_provider(req.provider, request_id)
    san = await asyncio.to_thread(sanitize_document, req.text, request_id)
    handle = san["mapping_handle"]
    try:
        outbound = prov.build_payload(san["sanitized_text"], req.task)
        guard = await asyncio.to_thread(validate_outbound_payload, outbound, handle)
        return {
            "request_id": request_id,
            "status": "safe" if guard["safe"] else "blocked",
            "original_text": req.text,
            "sanitized_text": san["sanitized_text"],
            "outbound_payload": outbound,
            "entities": san["entities"],
            "leakage_guard": {
                "safe": guard["safe"],
                "leakage_count": guard["leakage_count"],
                "findings": guard["findings"],
            },
            "processing_time_ms": int((time.perf_counter() - t0) * 1000),
        }
    finally:
        destroy_mapping(handle)


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

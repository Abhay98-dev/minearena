import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core import config
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

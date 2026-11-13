"""OpenAI-compatible Reverse Proxy Endpoint for MineArena Privacy Gateway.
Allows any external AI client (LangChain, LlamaIndex, OpenAI Python SDK, cURL)
to use MineArena simply by pointing base_url to: http://<host>:8000/v1
All PII is transparently sanitized before reaching the model and restored locally.
"""
import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core import config
from app.core.errors import GatewayError
from app.database import db
from app.privacy import destroy_mapping, reinsert_placeholders, sanitize_document, validate_outbound_payload
from app.services.llm.base import LLMError, LLMTimeout
from app.services.llm.factory import get_provider

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "minearena-privacy-guard"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    provider: Optional[str] = None


@router.get("/models")
async def list_models():
    """Returns available models in OpenAI format."""
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": "minearena-privacy-guard",
                "object": "model",
                "created": now,
                "owned_by": "minearena",
                "permission": [],
                "root": "minearena-privacy-guard",
                "parent": None,
            },
            {
                "id": "gemini-2.5-flash",
                "object": "model",
                "created": now,
                "owned_by": "google",
                "permission": [],
                "root": "gemini-2.5-flash",
                "parent": None,
            },
            {
                "id": "mock-privacy-eval",
                "object": "model",
                "created": now,
                "owned_by": "minearena-local",
                "permission": [],
                "root": "mock-privacy-eval",
                "parent": None,
            },
        ],
    }


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest, raw_req: Request):
    """OpenAI-compatible Chat Completion proxy with DPDP-2023 compliance gateway."""
    t0 = time.perf_counter()
    request_id = "req_proxy_" + uuid.uuid4().hex[:10]
    handle = None

    # Determine backend provider
    provider_name = req.provider or config.DEFAULT_PROVIDER
    if "gemini" in req.model.lower():
        provider_name = "gemini"
    elif "mock" in req.model.lower():
        provider_name = "mock"

    prov = get_provider(provider_name, request_id)

    # Extract all text from messages
    user_texts = [m.content for m in req.messages if m.role == "user"]
    combined_user_text = "\n\n".join(user_texts) if user_texts else (req.messages[-1].content if req.messages else "")

    if not combined_user_text.strip():
        raise HTTPException(status_code=400, detail="No prompt or user message content provided")

    try:
        # 1. Sanitize local input
        san = await asyncio.to_thread(sanitize_document, combined_user_text, request_id)
        handle = san["mapping_handle"]

        # 2. Guard outbound payload
        outbound = prov.build_payload(san["sanitized_text"], "summarize")
        guard = await asyncio.to_thread(validate_outbound_payload, outbound, handle)
        if not guard["safe"]:
            raise GatewayError(
                "OUTBOUND_PII_LEAKAGE_BLOCKED",
                request_id,
                {"leakage_count": guard["leakage_count"], "findings": guard["findings"]},
            )

        # 3. Call LLM with sanitized prompt
        t_llm = time.perf_counter()
        try:
            llm_text = await asyncio.wait_for(
                prov.generate(san["sanitized_text"], "summarize"),
                config.LLM_TIMEOUT_S + 5,
            )
        except (LLMTimeout, asyncio.TimeoutError) as e:
            raise GatewayError("LLM_PROVIDER_TIMEOUT", request_id) from e
        except LLMError as e:
            raise GatewayError("LLM_PROVIDER_ERROR", request_id) from e

        llm_ms = int((time.perf_counter() - t_llm) * 1000)

        # 4. Local reinsertion
        rein = await asyncio.to_thread(reinsert_placeholders, llm_text, handle)
        final_text = rein["restored_text"]

        total_ms = int((time.perf_counter() - t0) * 1000)
        overhead_ms = max(0, total_ms - llm_ms)

        # 5. Audit
        entity_types = sorted(list({e["type"] for e in san["entities"]}))
        db.save_audit({
            "request_id": request_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "success",
            "provider": prov.name,
            "model": prov.model,
            "entity_types": entity_types,
            "sanitized_payload": outbound,
            "leakage_count": 0,
            "missing_count": len(rein["missing_placeholders"]),
            "llm_time_ms": llm_ms,
            "processing_time_ms": total_ms,
            "gateway_overhead_ms": overhead_ms,
            "error_code": None,
        })

        # 6. Standard OpenAI response shape
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": final_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(combined_user_text.split()),
                "completion_tokens": len(final_text.split()),
                "total_tokens": len(combined_user_text.split()) + len(final_text.split()),
            },
            "privacy_gateway": {
                "status": "dpdp_protected",
                "entities_masked": len(san["entities"]),
                "entity_types": entity_types,
                "outbound_leaks": 0,
                "sanitized_tokens_sent": san["sanitized_text"],
                "gateway_overhead_ms": overhead_ms,
            },
        }
    finally:
        if handle:
            destroy_mapping(handle)


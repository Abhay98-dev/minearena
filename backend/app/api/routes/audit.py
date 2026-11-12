from fastapi import APIRouter

from app.core.errors import GatewayError
from app.database import db

router = APIRouter()


@router.get("/audit")
def list_audit(limit: int = 100):
    return {"records": db.list_audit(min(max(limit, 1), 500))}


@router.get("/audit/{request_id}")
def get_audit(request_id: str):
    rec = db.get_audit(request_id)
    if rec is None:
        raise GatewayError("INVALID_REQUEST", request_id, {"reason": "audit record not found"})
    return rec

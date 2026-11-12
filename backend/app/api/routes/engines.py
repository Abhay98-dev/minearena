import json
from pathlib import Path

from fastapi import APIRouter

from app.core.errors import GatewayError
from app.privacy.detection.detection_service import engine_status

router = APIRouter()

RESULTS = Path(__file__).resolve().parents[4] / "evaluation" / "results.json"


@router.get("/engines")
def engines():
    """Status of each local detection layer (loaded / disabled / failed + reason)."""
    return engine_status()


@router.get("/evaluation")
def evaluation():
    """Latest offline evaluation report produced by evaluation/run_eval.py (synthetic data only)."""
    if not RESULTS.is_file():
        raise GatewayError("INVALID_REQUEST", None, {"reason": "no evaluation report yet; run evaluation/run_eval.py"})
    return json.loads(RESULTS.read_text(encoding="utf-8"))

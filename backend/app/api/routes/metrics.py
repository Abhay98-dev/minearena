from fastapi import APIRouter

from app.database import db

router = APIRouter()


@router.get("/metrics")
def metrics():
    return db.metrics()

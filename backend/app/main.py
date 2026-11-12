"""Run from repo root:  uvicorn app.main:app --reload --app-dir backend"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import audit, gateway, health, metrics
from app.core import config
from app.core.errors import GatewayError
from app.database import db

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="MineArena PS-02 Privacy Gateway", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(GatewayError)
async def _gw(_: Request, e: GatewayError):
    return JSONResponse(status_code=e.http_status, content=e.to_dict())


@app.exception_handler(RequestValidationError)
async def _val(_: Request, e: RequestValidationError):
    # never echo the submitted body (it may contain PII): report field locations only
    locs = [".".join(str(p) for p in err["loc"]) for err in e.errors()]
    return JSONResponse(status_code=400, content=GatewayError("INVALID_REQUEST", None, {"fields": locs}).to_dict())


@app.exception_handler(Exception)
async def _any(_: Request, e: Exception):
    return JSONResponse(status_code=500, content=GatewayError("INTERNAL_ERROR").to_dict())


app.include_router(health.router, prefix="/api/v1")
app.include_router(gateway.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")

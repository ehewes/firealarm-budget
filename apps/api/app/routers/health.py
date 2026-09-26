"""Probes: /v1/health is liveness (touches nothing), /v1/ready proves the database."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from supabase import AsyncClient

from app.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "git_sha": os.environ.get("GIT_SHA", "dev")}


@router.get("/ready")
async def ready(db: AsyncClient = Depends(get_db)) -> JSONResponse:
    try:
        await db.table("scrapes").select("id").limit(1).execute()
    except Exception as exc:  # reporting any failure is the probe's whole job
        return JSONResponse({"status": "unavailable", "detail": type(exc).__name__}, 503)
    return JSONResponse({"status": "ok"})

"""Probes. /healthz is liveness (touches nothing); /readyz proves the database and queue."""

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool

from api.deps import get_pool

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "git_sha": os.environ.get("GIT_SHA", "dev")}


@router.get("/readyz")
async def readyz(pool: AsyncConnectionPool = Depends(get_pool)) -> JSONResponse:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute("select queue_length from pgmq.metrics('scrape')")
            row = await cur.fetchone()
    except Exception as exc:  # the probe's whole job is to report any failure
        return JSONResponse({"status": "unavailable", "detail": type(exc).__name__}, 503)
    return JSONResponse({"status": "ok", "queue_depth": int(row["queue_length"]) if row else 0})

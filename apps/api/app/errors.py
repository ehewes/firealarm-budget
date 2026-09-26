"""`EdenError` and the one error shape: `{"error": {"code": ..., "message": ...}}`.

Codes are stable and listed in docs/API.md; messages are written for the shopper
(Grok relays them), never internals.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class EdenError(Exception):
    def __init__(
        self, code: str, message: str, status: int = 400, *, headers: dict[str, str] | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.headers = headers or {}


async def eden_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, EdenError)
    return JSONResponse(
        {"error": {"code": exc.code, "message": exc.message}},
        status_code=exc.status,
        headers=exc.headers,
    )

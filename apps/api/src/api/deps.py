"""FastAPI dependencies: the pool, settings and the (optional) signed-in user."""

import logging

from fastapi import Depends, Header, Request
from psycopg_pool import AsyncConnectionPool

from api.auth import AuthError, TokenVerifier
from api.errors import ApiError
from api.settings import ApiSettings

logger = logging.getLogger(__name__)


def get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


def get_settings(request: Request) -> ApiSettings:
    return request.app.state.settings


# Plain `def`, not `async def`: FastAPI runs it in its threadpool, which is where
# the JWKS fetch inside `verify` belongs.
def optional_user(request: Request, authorization: str | None = Header(default=None)) -> str | None:
    """The user id from a valid Bearer token, or None.

    An invalid token is treated as a guest rather than an error here: a stale
    session cookie in the browser should not stop anyone from using the gate.
    Endpoints that need a user use `required_user`.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    verifier: TokenVerifier | None = request.app.state.verifier
    if verifier is None:
        return None
    try:
        claims = verifier.verify(authorization[7:].strip())
    except AuthError as exc:
        logger.info("ignoring an invalid bearer token: %s", exc)
        return None
    return str(claims["sub"])


def required_user(user: str | None = Depends(optional_user)) -> str:
    if user is None:
        raise ApiError(401, "sign_in_required", "Sign in to do that.")
    return user

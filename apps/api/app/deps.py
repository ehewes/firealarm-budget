"""Request dependencies: settings, the Supabase client, and the caller."""

from fastapi import Depends, Header, Request
from supabase import AsyncClient

from app.auth import AuthError, User
from app.config import Settings
from app.errors import EdenError


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> AsyncClient:
    return request.app.state.db


# Plain `def`: FastAPI runs it in a thread, which is where the JWKS fetch belongs.
def optional_user(
    request: Request, authorization: str | None = Header(default=None)
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return request.app.state.verifier.verify(authorization[7:].strip())
    except AuthError:
        return None


def current_user(user: User | None = Depends(optional_user)) -> User:
    """Any signed-in user, anonymous included (the web app signs guests in anonymously)."""
    if user is None:
        raise EdenError("unauthenticated", "Sign in (or refresh the page) and try again.", 401)
    return user


def client_ip(request: Request) -> str:
    """The shopper's IP. CF-Connecting-IP is trustworthy: the only way in is Cloudflare's tunnel."""
    for header in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

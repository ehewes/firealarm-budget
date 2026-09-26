"""Verifying Supabase access tokens.

Asymmetric keys only (ES256, RS256), fetched from the project's JWKS and cached.
Accepting HS256 as well would reopen algorithm confusion: a token "signed" with a
public key used as an HMAC secret. Supabase projects and CLI 2.71+ sign with
asymmetric keys, so nothing legitimate needs it.
"""

from typing import Any

import jwt


class AuthError(Exception):
    """The token is missing, malformed, expired or not ours."""


class TokenVerifier:
    def __init__(self, supabase_url: str, *, issuer: str | None = None):
        base = supabase_url.rstrip("/")
        self.issuer = issuer or f"{base}/auth/v1"
        self._jwks = jwt.PyJWKClient(
            f"{base}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=600, timeout=5
        )

    def verify(self, token: str) -> dict[str, Any]:
        """The token's claims. Blocking (the first call fetches the JWKS): call it off the loop."""
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc
        if claims.get("role") != "authenticated" or claims.get("is_anonymous"):
            raise AuthError("not a signed-in user")
        return claims

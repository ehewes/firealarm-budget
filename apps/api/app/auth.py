"""Verifying the Supabase JWT the web app sends (anonymous users included).

The key is chosen by the token's declared algorithm, and each algorithm only ever
gets its own kind of key: HS256 tokens are checked with SUPABASE_JWT_SECRET (legacy
projects), ES256/RS256 tokens with the project's JWKS. A public key is never used as
an HMAC secret, which is what makes algorithm confusion impossible here.
"""

from dataclasses import dataclass

import jwt

from app.config import Settings


class AuthError(Exception):
    """The token is missing, malformed, expired, or not from our Supabase project."""


@dataclass(frozen=True, slots=True)
class User:
    id: str
    is_anonymous: bool


class Verifier:
    def __init__(self, settings: Settings):
        base = settings.supabase_url.rstrip("/")
        self.issuer = settings.supabase_jwt_issuer or f"{base}/auth/v1"
        self.secret = settings.supabase_jwt_secret
        self._jwks = jwt.PyJWKClient(
            f"{base}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=600, timeout=5
        )

    def verify(self, token: str) -> User:
        """Blocking on the first call (it fetches the JWKS), so call it from a sync dependency."""
        try:
            alg = jwt.get_unverified_header(token).get("alg")
            if alg == "HS256":
                if not self.secret:
                    raise AuthError("HS256 token but SUPABASE_JWT_SECRET is not set")
                key: object = self.secret
            elif alg in ("ES256", "RS256"):
                key = self._jwks.get_signing_key_from_jwt(token).key
            else:
                raise AuthError(f"unsupported algorithm {alg!r}")
            claims = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(str(exc)) from exc
        if claims.get("role") != "authenticated":
            raise AuthError("not a user token")
        return User(id=str(claims["sub"]), is_anonymous=bool(claims.get("is_anonymous")))

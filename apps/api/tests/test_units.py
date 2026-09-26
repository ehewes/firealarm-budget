"""Tests that need no database: auth, IP hashing, settings, the Grok link."""

import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from starlette.requests import Request

from api.auth import AuthError, TokenVerifier
from api.client_ip import client_ip, ip_hash
from api.services.grok import grok_prompt, grok_url
from api.settings import ApiSettings

ISSUER = "https://proj.supabase.co/auth/v1"


class _Key:
    def __init__(self, key):
        self.key = key


@pytest.fixture
def signer():
    private = ec.generate_private_key(ec.SECP256R1())
    verifier = TokenVerifier("https://proj.supabase.co")
    verifier._jwks = type(
        "Jwks", (), {"get_signing_key_from_jwt": lambda self, t: _Key(private.public_key())}
    )()

    def sign(**claims):
        body = {
            "sub": "0b7d3c1e-0000-4000-8000-000000000001",
            "aud": "authenticated",
            "iss": ISSUER,
            "role": "authenticated",
            "exp": int(time.time()) + 600,
            **claims,
        }
        return jwt.encode(body, private, algorithm="ES256")

    return verifier, sign


def test_valid_token(signer):
    verifier, sign = signer
    assert verifier.verify(sign())["sub"].startswith("0b7d3c1e")


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "anon"},
        {"iss": "https://elsewhere/auth/v1"},
        {"exp": int(time.time()) - 10},
        {"role": "anon"},
        {"is_anonymous": True},
    ],
)
def test_rejected_tokens(signer, claims):
    verifier, sign = signer
    with pytest.raises(AuthError):
        verifier.verify(sign(**claims))


def test_hs256_is_refused(signer):
    verifier, _ = signer
    forged = jwt.encode(
        {"sub": "x", "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60},
        "a-guessable-secret-that-is-at-least-32-bytes-long",
        algorithm="HS256",
    )
    with pytest.raises(AuthError):
        verifier.verify(forged)


def _request(headers: dict[str, str], peer: str = "10.0.0.9") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


def test_client_ip_prefers_cloudflare():
    assert client_ip(_request({"CF-Connecting-IP": "203.0.113.7"})) == "203.0.113.7"
    assert client_ip(_request({"X-Forwarded-For": "198.51.100.1, 10.0.0.1"})) == "198.51.100.1"
    assert client_ip(_request({})) == "10.0.0.9"


def test_ip_hash_groups_ipv6_by_64_and_never_stores_the_address():
    a = ip_hash("2001:db8:1:2:aaaa::1", "salt")
    b = ip_hash("2001:db8:1:2:bbbb::2", "salt")
    assert a == b and len(a) == 32 and "2001" not in a
    assert ip_hash("203.0.113.7", "salt") != ip_hash("203.0.113.7", "other-salt")


def test_production_refuses_unsafe_settings():
    unsafe = ApiSettings(_env_file=None, environment="production")
    assert len(unsafe.production_problems()) >= 2
    safe = ApiSettings(
        _env_file=None,
        environment="production",
        ip_hash_salt="x" * 32,
        supabase_url="https://proj.supabase.co",
        public_base_url="https://go.edenmatrix.xyz",
    )
    assert safe.production_problems() == []


def test_grok_link_carries_the_context_url():
    prompt = grok_prompt(
        domain="joinfleek.com",
        title="Ralph Lauren",
        context_url="https://go.edenmatrix.xyz/api/v1/public/sessions/EM-7K2Q9X4M.md",
    )
    url = grok_url(prompt)
    assert url.startswith("https://grok.com/?q=")
    assert parse_qs(urlsplit(url).query)["q"][0] == prompt
    assert "EM-7K2Q9X4M.md" in prompt

import json
import time
from decimal import Decimal

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth import AuthError, Verifier
from app.config import Settings
from app.services import jev as jev_module
from app.services.jev import DecideError, Jev


@pytest.fixture
def free_budget(monkeypatch):
    spent: list[float] = []

    async def left(db, monthly):
        return Decimal("5")

    async def add(db, key, amount=1):
        spent.append(amount)
        return Decimal(str(amount))

    monkeypatch.setattr(jev_module.usage, "jev_budget_left", left)
    monkeypatch.setattr(jev_module.usage, "add", add)
    return spent


def _jev(handler) -> Jev:
    settings = Settings(_env_file=None, openrouter_api_key="test-key")
    return Jev(settings, db=None, transport=httpx.MockTransport(handler))


def _choice(key, chosen, confidence=0.9):
    return {
        key: {
            "type": "choice",
            "choice": chosen,
            "probabilities": {chosen: confidence},
            "confidence": confidence,
        }
    }


async def test_place_asks_category_then_type_and_records_cost(free_budget):
    asked = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        asked.append(next(iter(body["questions"])))
        assert body["model"] == "typesafe/jev-1.13"
        answer = (
            _choice("category", "bottoms")
            if "category" in body["questions"]
            else _choice("type", "trousers")
        )
        return httpx.Response(200, json={"answers": answer, "usage": {"cost": 0.00001}})

    assert await _jev(handler).place("Ralph Lauren Trousers/Pant") == ("bottoms", "trousers")
    assert asked == ["category", "type"]
    assert free_budget == [0.00001, 0.00001]


async def test_unsure_placement_falls_back(free_budget):
    def handler(request):
        return httpx.Response(200, json={"answers": _choice("category", "tops", confidence=0.3)})

    assert await _jev(handler).place("Mystery item") is None


async def test_errors_are_decide_errors(free_budget):
    def handler(request):
        return httpx.Response(200, json={"error": {"message": "upstream"}})

    with pytest.raises(DecideError):
        await _jev(handler).fits_notes(["baggy"], "Jeans")


async def test_no_key_means_unavailable():
    with pytest.raises(jev_module.Unavailable):
        await Jev(Settings(_env_file=None), db=None).decide({}, {})


def _claims(**extra):
    return {
        "sub": "user-1",
        "aud": "authenticated",
        "iss": "http://127.0.0.1:54321/auth/v1",
        "role": "authenticated",
        "is_anonymous": True,
        "exp": int(time.time()) + 600,
        **extra,
    }


def test_hs256_with_the_project_secret():
    secret = "super-secret-jwt-token-with-at-least-32-characters-long"
    verifier = Verifier(Settings(_env_file=None, supabase_jwt_secret=secret))
    user = verifier.verify(jwt.encode(_claims(), secret, algorithm="HS256"))
    assert user.id == "user-1" and user.is_anonymous
    with pytest.raises(AuthError):
        verifier.verify(jwt.encode(_claims(aud="anon"), secret, algorithm="HS256"))


def test_es256_via_jwks_and_no_secret_for_hs256():
    private = ec.generate_private_key(ec.SECP256R1())
    verifier = Verifier(Settings(_env_file=None))

    class _Key:
        key = private.public_key()

    verifier._jwks = type("Jwks", (), {"get_signing_key_from_jwt": lambda self, t: _Key()})()
    assert verifier.verify(jwt.encode(_claims(), private, algorithm="ES256")).id == "user-1"
    with pytest.raises(AuthError):  # HS256 is refused when no secret is configured
        verifier.verify(jwt.encode(_claims(), "x" * 40, algorithm="HS256"))

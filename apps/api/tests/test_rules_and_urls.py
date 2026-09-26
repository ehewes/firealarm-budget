import pytest

from app.config import Settings
from app.errors import EdenError
from app.models import Rules
from app.services.grok import grok_bot_prompt, grok_url
from app.services.rules import merge, parse_text, passes, why, with_query
from app.services.urls import canonical, normalize_prefix, require_allowed

PANT = {
    "title": "Ralph Lauren Trousers/Pant RV # 1273",
    "price": 260.0,
    "per_piece": 13.0,
    "pieces": 20,
    "currency": "USD",
    "tree_path": ["bottoms", "trousers", "standard"],
}
KNIT = {
    "title": "Premium Ralph Lauren Cable Knit Jumpers",
    "price": 220.0,
    "per_piece": 22.0,
    "pieces": 10,
    "currency": "USD",
    "tree_path": ["tops", "knitwear", "premium"],
}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https:/www.joinfleek.com/collections/nike", "https://www.joinfleek.com/collections/nike"),
        (
            "https://www.joinfleek.com/collections/nike",
            "https://www.joinfleek.com/collections/nike",
        ),
        ("www.joinfleek.com/collections/nike", "https://www.joinfleek.com/collections/nike"),
        ("/joinfleek.com/x", "https://joinfleek.com/x"),
    ],
)
def test_prefix_normalisation(raw, expected):
    assert normalize_prefix(raw) == expected


def test_canonical_strips_tracking_and_credentials():
    assert (
        canonical(
            "https:/www.JoinFleek.com/products/9475004989678?click_source=X&page=2&token=t#top"
        )
        == "https://www.joinfleek.com/products/9475004989678?page=2"
    )
    with pytest.raises(EdenError):
        canonical("https://127.0.0.1/x")
    with pytest.raises(EdenError):
        canonical("ftp://joinfleek.com/x")


def test_allowlist():
    domains = frozenset({"joinfleek.com"})
    assert require_allowed("https://www.joinfleek.com/x", domains) == "joinfleek.com"
    with pytest.raises(EdenError) as err:
        require_allowed("https://evil-joinfleek.com/x", domains)
    assert err.value.code == "domain_not_allowed"


def test_hard_filters_and_why():
    rules = Rules(max_per_piece=14, exclude_categories=["shorts"])
    assert passes(PANT, rules) and not passes(KNIT, rules)
    assert why(PANT, rules) == "$13.00/pc under your $14.00 cap"
    assert passes(KNIT, Rules(grades=["premium"])) and not passes(PANT, Rules(grades=["premium"]))
    assert passes(PANT, Rules(include_categories=["pants"]))  # matches "Pant" in the title
    assert not passes({**PANT, "per_piece": None}, Rules(max_per_piece=100))  # unverifiable is out
    assert passes(PANT, Rules(min_pieces=20)) and not passes(KNIT, Rules(min_pieces=20))


def test_query_overrides_and_merge():
    base = Rules(max_per_piece=20, grades=["premium"])
    assert with_query(base, max_per_piece=14, category="bottoms").max_per_piece == 14
    assert with_query(base, max_per_piece=30, category=None).max_per_piece == 20
    merged = merge(base, Rules(grades=["standard"]))
    assert merged.grades == ["standard"] and merged.max_per_piece == 20


def test_plain_language_parsing():
    rules = parse_text("Premium only, under $14/piece, no shorts, at least 20 pieces")
    assert rules.grades == ["premium"]
    assert rules.max_per_piece == 14
    assert rules.exclude_categories == ["shorts"]
    assert rules.min_pieces == 20
    assert parse_text("only bottoms under 500").model_dump(exclude_defaults=True) == {
        "max_total": 500.0,
        "include_categories": ["bottoms"],
    }
    assert parse_text("prefer baggy fits").notes == ["prefer baggy fits"]


def test_grok_link_points_at_the_products_endpoint():
    settings = Settings(_env_file=None, web_origin="https://go.edenmatrix.xyz")
    url = grok_url(
        settings, code="EM-7K2Q9X4M", store="joinfleek.com", collection="April EOM RL Drop"
    )
    assert url.startswith("https://grok.com/?q=")
    assert "go.edenmatrix.xyz%2Fv1%2Fsessions%2FEM-7K2Q9X4M%2Fproducts" in url


def test_grok_bot_prompt_keeps_a_session_log_on_the_bots_computer():
    settings = Settings(_env_file=None, web_origin="https://go.edenmatrix.xyz")
    prompt = grok_bot_prompt(settings, code="EM-7K2Q9X4M", store="zara.com", collection="Shirts")
    assert "https://go.edenmatrix.xyz/v1/sessions/EM-7K2Q9X4M/products" in prompt
    assert "/workspace/eden-matrix/sessions.md" in prompt
    assert "https://go.edenmatrix.xyz/s/EM-7K2Q9X4M" in prompt and "list_my_sessions" in prompt

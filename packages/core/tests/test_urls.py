import pytest

from eden_core.urls import BadUrl, canonical, is_public_hostname, origin_of, same_site, site_of


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The entry gate hands over no scheme: https is assumed.
        (
            "joinfleek.com/collections/april-eom-rl-drop",
            "https://joinfleek.com/collections/april-eom-rl-drop",
        ),
        # joinfleek's click tracking is stripped, so both links are one page.
        (
            "https://www.joinfleek.com/products/9475004989678"
            "?click_source=COLLECTIONS&click_source_details=Ralph+Lauren",
            "https://www.joinfleek.com/products/9475004989678",
        ),
        # Meaningful parameters survive, sorted so order does not matter.
        (
            "https://shop.example.org/c?page=2&sort=price&utm_source=x",
            "https://shop.example.org/c?page=2&sort=price",
        ),
        ("https://Shop.Example.ORG:443/A#frag", "https://shop.example.org/A"),
        ("http://example.org", "http://example.org/"),
        # Credentials in the query never get stored.
        ("https://example.org/p?token=abc&id=7", "https://example.org/p?id=7"),
        # IDN hosts become punycode.
        ("https://bücher.de/x", "https://xn--bcher-kva.de/x"),
        # Product and discount codes are left alone.
        ("https://example.org/p?code=SUMMER", "https://example.org/p?code=SUMMER"),
    ],
)
def test_canonical(raw, expected):
    assert canonical(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ftp://example.org/x",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://[::1]/x",
        "https://printer.local/x",
        "https://user:pw@example.org/",
        "https://example.org:8443/",
        "https://nodot/",
        "https://example.123/",
    ],
)
def test_canonical_rejects(raw):
    with pytest.raises(BadUrl):
        canonical(raw)


def test_public_hostnames():
    assert is_public_hostname("joinfleek.com")
    assert is_public_hostname("xn--bcher-kva.de")
    assert not is_public_hostname("10.0.0.1")
    assert not is_public_hostname("-bad.com")
    assert not is_public_hostname("widget.js.internal")


def test_sites_and_origins():
    assert site_of("WWW.JoinFleek.com") == "joinfleek.com"
    assert same_site("https://www.joinfleek.com/a", "https://joinfleek.com/b")
    assert not same_site("https://joinfleek.com/a", "https://evil-joinfleek.com/a")
    assert origin_of("https://www.joinfleek.com/collections/x?y=1") == "https://www.joinfleek.com"
    assert origin_of("not a url") is None

"""Turning a prefixed store URL into the one canonical address we scrape, and the allowlist.

Canonical form is the identity of a page for scrape reuse: addresses that differ only in
tracking parameters, fragment, host case or default port are the same page. Path case
and trailing slashes are kept, since plenty of stores treat those as different pages.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.errors import EdenError

# Click tracking. Stripping it is what makes joinfleek's
# `/products/9475004989678?click_source=COLLECTIONS&click_source_details=…` one page.
_TRACKING = frozenset(
    {
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "_ga",
        "_gl",
        "srsltid",
        "ref_src",
        "click_source",
        "click_source_details",
    }
)
# Credentials or personal data: never stored, never scraped with.
_SENSITIVE = frozenset(
    {"token", "access_token", "id_token", "refresh_token", "session", "sid", "password", "email"}
)
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_prefix(raw: str) -> str:
    """The target URL from whatever followed our domain in the address bar.

    Browsers and Next collapse `//` in a path, so `edenmatrix/https://x` arrives as
    `https:/x`. A bare `joinfleek.com/...` means https.
    """
    value = raw.strip().lstrip("/")
    value = re.sub(r"^(https?):/+", r"\1://", value, flags=re.IGNORECASE)
    if "://" not in value:
        value = "https://" + value
    return value


def canonical(url: str) -> str:
    parts = urlsplit(normalize_prefix(url))
    if parts.scheme.lower() not in ("http", "https"):
        raise EdenError("invalid_url", "Only http and https store pages can be read.")
    if parts.username or parts.password:
        raise EdenError("invalid_url", "That address has a username or password in it.")
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        raise EdenError("invalid_url", "That is not a valid store address.") from exc
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels) or labels[-1].isdigit():
        raise EdenError("invalid_url", "That is not a valid store address.")
    if port not in (None, 80, 443):
        raise EdenError("invalid_url", "Only standard web ports are supported.")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING
        and k.lower() not in _SENSITIVE
        and not k.lower().startswith("utm_")
    )
    return urlunsplit(("https", host, parts.path or "/", urlencode(query), ""))


def site_of(url_or_host: str) -> str:
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def require_allowed(url: str, domains: frozenset[str]) -> str:
    """The store's domain, if it is on the allowlist; otherwise `domain_not_allowed`.

    When set to '*' or left empty, all public store domains are permitted.
    """
    site = site_of(url)
    if "*" in domains or not domains or "" in domains:
        return site
    if not any(site == d or site.endswith("." + d) for d in domains):
        raise EdenError(
            "domain_not_allowed",
            f"Eden Matrix doesn't support {site} yet. Supported: {', '.join(sorted(domains))}.",
        )
    return site


def same_site(a: str, b: str) -> bool:
    return site_of(a) == site_of(b)

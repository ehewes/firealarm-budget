"""URL rules the API and the scraper must agree on.

`canonical` is the identity of a page for reuse and deduplication: two addresses
that differ only in tracking parameters, fragment, host case or default port are
the same page, so they share one scrape. It is deliberately conservative: path
case and trailing slashes are kept, because plenty of sites treat them as
different pages.
"""

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class BadUrl(ValueError):
    """Not an address we will fetch. The message is safe to show the shopper."""


# Parameters that only say where a click came from. Stripping them is what lets
# joinfleek's `?click_source=COLLECTIONS&click_source_details=…` product links
# resolve to the same page as a bare link to the product.
TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "dclid",
        "msclkid",
        "yclid",
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
TRACKING_PREFIXES = ("utm_",)

# Parameters that can carry credentials or personal data. A shopper who pastes a
# logged-in link should not have their token scraped, stored and shown to Grok.
# `code`, `state` and `key` are left alone on purpose: shops use them for product
# and discount codes far more often than a shopper pastes an OAuth callback.
SENSITIVE_PARAMS = frozenset(
    {
        "token",
        "access_token",
        "id_token",
        "refresh_token",
        "auth",
        "session",
        "sid",
        "password",
        "email",
        "sig",
        "signature",
        "jwt",
        "api_key",
        "apikey",
        "secret",
    }
)

# Suffixes that are never public websites.
_PRIVATE_SUFFIXES = (
    ".local",
    ".localhost",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".test",
    ".invalid",
    ".example",
    ".onion",
)
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_TLD = re.compile(r"^(xn--[a-z0-9-]{2,59}|[a-z]{2,63})$")


def _host(raw: str) -> str:
    """Lower-cased ASCII (punycode) host, or BadUrl."""
    host = raw.strip().rstrip(".").lower()
    if not host:
        raise BadUrl("That address has no site in it.")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise BadUrl("That site name is not valid.") from exc


def is_public_hostname(host: str) -> bool:
    """A syntactically public DNS name: no IP literals, no local-only suffixes."""
    try:
        ipaddress.ip_address(host.strip("[]"))
        return False
    except ValueError:
        pass
    if host == "localhost" or host.endswith(_PRIVATE_SUFFIXES):
        return False
    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253:
        return False
    return all(_LABEL.match(label) for label in labels) and bool(_TLD.match(labels[-1]))


def canonical(url: str) -> str:
    """The canonical form of an http(s) URL. Raises BadUrl for anything else.

    A missing scheme means https, since the entry gate never includes one.
    """
    raw = url.strip()
    if not raw:
        raise BadUrl("That address is empty.")
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise BadUrl("Only http and https pages can be read.")
    if parts.username or parts.password:
        raise BadUrl("Addresses with a username or password in them are not supported.")
    host = _host(parts.hostname or "")
    try:
        port = parts.port
    except ValueError as exc:
        raise BadUrl("That address has an invalid port.") from exc
    if port not in (None, 80, 443):
        raise BadUrl("Only standard web ports are supported.")
    if not is_public_hostname(host):
        raise BadUrl("That is not a public website.")

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _dropped(key)
    ]
    query.sort()
    path = parts.path or "/"
    return urlunsplit((scheme, host, path, urlencode(query, doseq=True), ""))


def _dropped(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in TRACKING_PARAMS
        or lowered in SENSITIVE_PARAMS
        or lowered.startswith(TRACKING_PREFIXES)
    )


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def site_of(host: str) -> str:
    """The host without a leading `www.`: joinfleek.com and www.joinfleek.com are one site."""
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, other: str) -> bool:
    return site_of(host_of(url)) == site_of(host_of(other))


def origin_of(url: str) -> str | None:
    """`scheme://host` of a URL or Referer value, or None if it has neither."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.hostname.lower()}"

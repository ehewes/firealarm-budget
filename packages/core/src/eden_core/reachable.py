"""Where the scraper is allowed to go. Adapted from stock-aggregator's magpie.

The destination here is somebody else's input (a URL a shopper typed, or a link
taken out of a page written by a stranger), so every address a name resolves to
has to be on the public internet. A name answering with one public and one
private address is the ordinary way this check is got around, so all of them are
checked, not the first.

Run on every redirect hop through an httpx request hook, not just on the URL
that was submitted: a public page can answer `302 Location: http://169.254.169.254/`.

Known limit, kept from the original: a name that passes here and resolves to
something else on the next lookup (DNS rebinding) is not caught. Pinning the
resolved address means replacing the transport, not inspecting it.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class NotReachable(RuntimeError):
    """The address is not on the public internet, so we will not fetch it."""


def _private(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return True
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
        parsed = parsed.ipv4_mapped
    return (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local  # 169.254/16, the cloud metadata address
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed.is_unspecified
        or parsed in ipaddress.ip_network("100.64.0.0/10")  # CGNAT, which includes the tailnet
    )


async def resolve(host: str, *, timeout: float = 3.0) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP), timeout
        )
    except (TimeoutError, socket.gaierror, UnicodeError):
        return []
    return [str(info[4][0]) for info in infos]


async def check(url: str, *, timeout: float = 3.0) -> None:
    """Raise NotReachable unless every address the URL's host resolves to is public."""
    host = urlsplit(url).hostname
    if not host:
        raise NotReachable("no host in that address")
    try:
        ipaddress.ip_address(host)
        found = [host]
    except ValueError:
        found = await resolve(host, timeout=timeout)
    if not found:
        raise NotReachable(f"{host} does not resolve")
    private = [address for address in found if _private(address)]
    if private:
        raise NotReachable(f"{host} is not a public address")

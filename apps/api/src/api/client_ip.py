"""Who is asking, as far as rate limiting needs to know.

`CF-Connecting-IP` is trusted because the only way into this stack is the
Cloudflare tunnel, and Cloudflare overwrites that header on every request. The
web app forwards it when it calls the API on a shopper's behalf.
"""

import hashlib
import hmac
import ipaddress

from fastapi import Request


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded.strip()
    chain = request.headers.get("x-forwarded-for")
    if chain:
        return chain.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(ip: str, salt: str) -> str:
    """A keyed hash of the address, never the address itself.

    IPv6 is reduced to its /64 first: one household or phone gets a whole /64,
    so counting individual addresses would let one person look like millions.
    """
    try:
        parsed = ipaddress.ip_address(ip)
        if isinstance(parsed, ipaddress.IPv6Address):
            ip = str(ipaddress.ip_network(f"{parsed}/64", strict=False).network_address)
    except ValueError:
        pass
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]

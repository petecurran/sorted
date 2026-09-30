"""The laptop trust rule: the one caller Sorted trusts without a password is the presenter's own laptop.

Everyone else is remote. Remote callers get the public site, and the council console asks them for its password
(server.py). A request is remote if any of these holds:

- it comes from another address, or through a proxy (phones through the tunnel, visitors to a hosted copy);
- it is addressed to a name other than this machine (a site that points its own domain at 127.0.0.1, DNS rebinding);
- it comes from a page on another site, open in this laptop's browser (its Origin gives it away).

Each check fails closed: a missing or unreadable header counts as remote. See docs/decisions/0004-laptop-trust-rule.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
PROXY_HEADERS = ("cf-ray", "cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded")


def is_remote(client_host: str, headers: Mapping[str, str]) -> bool:
    """False only for the presenter's laptop. `headers` must be case-insensitive, like Starlette's Headers."""
    if client_host not in LOOPBACK or any(h in headers for h in PROXY_HEADERS):
        return True
    if _hostname("//" + headers.get("host", "")) not in LOOPBACK:
        return True
    origin = headers.get("origin")
    return origin is not None and _hostname(origin) not in LOOPBACK


def _hostname(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:  # a malformed header, such as an unclosed IPv6 bracket
        return None

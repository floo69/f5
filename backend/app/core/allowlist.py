"""Host allowlist for every network fetch an agent or MCP tool can trigger (enforced in code).

Default: only the mock portal (localhost:8100). Anything else — including the real UIDAI
site — is refused before a request is made. Redirects are not followed.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from backend.app.settings import settings

MAX_FETCH = 15 * 1024 * 1024


class BlockedHost(PermissionError):
    pass


def host_of(url: str) -> str:
    try:
        u = urlsplit(url)
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError:  # malformed port, e.g. "localhost:8100.evil.com"
        return ""
    if u.scheme not in ("http", "https") or not u.hostname:
        return ""
    return f"{u.hostname.lower()}:{port}"


def allowed(url: str, hosts: list[str] | None = None) -> bool:
    h = host_of(url)
    allow = [x.lower() for x in (hosts if hosts is not None else settings.allowed_hosts)]
    # "localhost:8100" also matches 127.0.0.1:8100 (same machine, same port)
    alias = {h, h.replace("127.0.0.1:", "localhost:")}
    return bool(h) and any(a in alias for a in allow)


def check(url: str, hosts: list[str] | None = None) -> None:
    if not allowed(url, hosts):
        raise BlockedHost(f"host not in allowlist: {host_of(url) or url!r}")


def _client() -> httpx.Client:  # tests swap this for an in-process client
    return httpx.Client(follow_redirects=False, timeout=10.0)


def fetch(url: str, hosts: list[str] | None = None, data: dict | None = None
          ) -> httpx.Response:
    """GET (or form POST when `data` is given) an allowlisted URL; no redirects followed."""
    check(url, hosts)
    with _client() as c:
        r = c.post(url, data=data) if data is not None else c.get(url)
    if len(r.content) > MAX_FETCH:
        raise ValueError("response too large")
    return r


def origins(hosts: list[str] | None = None) -> str:
    """Playwright MCP --allowed-origins value."""
    return ";".join(f"http://{h}" for h in (hosts or settings.allowed_hosts))

"""Operator authentication, rate limiting and WebSocket origin checks.

Design:
* Reading state (dashboard, history, WebSocket stream) is public by default.
* Anything that changes the simulation requires the operator API key
  (``X-API-Key`` header) when ``OPERATOR_API_KEY`` is set.
* Expensive or third-party-facing routes are rate limited per client.
* The WebSocket only accepts browser connections from allowed origins.
"""
import hmac
import logging
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, WebSocket

from .config import settings

log = logging.getLogger("crowdflow.security")


def client_ip(conn: Request | WebSocket) -> str:
    """Client address. X-Forwarded-For is trusted only when TRUST_PROXY is on."""
    if settings.trust_proxy:
        fwd = conn.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return conn.client.host if conn.client else "unknown"


def require_operator(request: Request) -> None:
    """Dependency for state-changing routes."""
    expected = settings.operator_api_key
    if not expected:  # auth disabled (local development)
        return
    supplied = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="operator_key_required",
                            headers={"WWW-Authenticate": "ApiKey"})


class RateLimiter:
    """Sliding-window limiter, in memory (per process)."""

    def __init__(self, bucket: str, limit_attr: str):
        self.bucket = bucket
        self.limit_attr = limit_attr
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        limit = getattr(settings, self.limit_attr)
        if limit <= 0:  # disabled
            return
        window = settings.rate_limit_window_sec
        now = time.monotonic()
        q = self.hits[client_ip(request)]
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            retry = max(1, int(window - (now - q[0])) + 1)
            raise HTTPException(status_code=429, detail="rate_limited", headers={"Retry-After": str(retry)})
        q.append(now)
        if len(self.hits) > 10_000:  # bound memory: drop idle clients
            for ip in [k for k, v in self.hits.items() if not v or now - v[-1] >= window]:
                del self.hits[ip]

    def reset(self) -> None:
        self.hits.clear()


operator_limiter = RateLimiter("operator", "rate_limit_operator")
geo_limiter = RateLimiter("geo", "rate_limit_geo")
parse_limiter = RateLimiter("parse", "rate_limit_parse")
live_limiter = RateLimiter("live", "rate_limit_live")

operator_guard = [Depends(require_operator), Depends(operator_limiter)]


def origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:  # non-browser client (curl, scripts); browsers always send Origin
        return True
    if origin in settings.cors_origins or "*" in settings.cors_origins:
        return True
    host = ws.headers.get("host", "")
    return origin.split("://", 1)[-1] == host  # same-origin (e.g. behind the nginx proxy)


class WsConnections:
    """Caps simultaneous WebSocket clients, total and per IP."""

    def __init__(self):
        self.total = 0
        self.per_ip: dict[str, int] = defaultdict(int)

    def acquire(self, ip: str) -> bool:
        if self.total >= settings.ws_max_connections or self.per_ip[ip] >= settings.ws_max_per_ip:
            return False
        self.total += 1
        self.per_ip[ip] += 1
        return True

    def release(self, ip: str) -> None:
        self.total = max(0, self.total - 1)
        self.per_ip[ip] -= 1
        if self.per_ip[ip] <= 0:
            self.per_ip.pop(ip, None)


ws_connections = WsConnections()

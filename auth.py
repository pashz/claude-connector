"""HTTP middleware for optional MCP API key enforcement."""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

# Open without auth so load balancers and uptime checks still work.
PUBLIC_PATHS = frozenset({"/", "/health"})


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests to protected routes when the bearer token does not match."""

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse(
                {
                    "error": "unauthorized",
                    "message": "Missing or invalid Authorization header. Use: Bearer <MCP_API_KEY>",
                },
                status_code=401,
            )

        token = auth[7:].strip()
        if not secrets.compare_digest(token, self._api_key):
            return JSONResponse(
                {"error": "unauthorized", "message": "Invalid API key."},
                status_code=401,
            )

        return await call_next(request)


def build_http_middleware(api_key: str) -> list[Middleware]:
    """Return Starlette middleware stack when MCP_API_KEY is configured."""
    if not api_key:
        return []
    return [Middleware(APIKeyMiddleware, api_key=api_key)]

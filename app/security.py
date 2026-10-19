from __future__ import annotations

import secrets
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings


class RestRoomSecurityMiddleware:
    """Optional API-key + Origin guard. Default is open door (no key)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        protected_prefixes: Iterable[str] = (),
        exempt_paths: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.settings = settings
        self.protected_prefixes = tuple(prefix.rstrip('/') or '/' for prefix in protected_prefixes)
        self.exempt_paths = {path.rstrip('/') or '/' for path in exempt_paths}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get('type') != 'http':
            await self.app(scope, receive, send)
            return

        path = (scope.get('path') or '').rstrip('/') or '/'
        if not self._is_protected(path):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        origin = headers.get('origin')
        if origin and not self._origin_allowed(origin):
            response = JSONResponse(status_code=403, content={'detail': 'Origin is not allowed.'})
            await response(scope, receive, send)
            return

        method = (scope.get('method') or 'GET').upper()
        if method != 'OPTIONS' and self._auth_enabled() and not self._api_key_allowed(headers):
            response = JSONResponse(
                status_code=401,
                content={'detail': 'Missing or invalid API key.'},
                headers={'WWW-Authenticate': 'Bearer'},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _is_protected(self, path: str) -> bool:
        if path in self.exempt_paths:
            return False
        return any(path == prefix or path.startswith(prefix + '/') for prefix in self.protected_prefixes)

    def _auth_enabled(self) -> bool:
        return bool((self.settings.api_key or '').strip())

    def _api_key_allowed(self, headers: Headers) -> bool:
        expected = (self.settings.api_key or '').strip()
        if not expected:
            return True
        presented = headers.get('x-api-key')
        if not presented:
            auth_header = headers.get('authorization') or ''
            if auth_header.lower().startswith('bearer '):
                presented = auth_header.split(' ', 1)[1].strip()
        return bool(presented) and secrets.compare_digest(presented, expected)

    def _origin_allowed(self, origin: str) -> bool:
        allowed = self.settings.allowed_origins_list
        normalized = origin.rstrip('/')
        if not allowed or '*' in allowed:
            return True
        return normalized in allowed


def build_cors_kwargs(settings: Settings) -> dict | None:
    allowed = settings.allowed_origins_list
    if not allowed:
        return None
    allow_all = '*' in allowed
    return {
        'allow_origins': ['*'] if allow_all else allowed,
        'allow_methods': ['GET', 'POST', 'DELETE', 'OPTIONS'],
        'allow_headers': ['Authorization', 'Content-Type', 'X-API-Key', 'Mcp-Session-Id'],
        'expose_headers': ['Mcp-Session-Id'],
    }


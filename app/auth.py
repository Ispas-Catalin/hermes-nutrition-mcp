from __future__ import annotations

from collections.abc import Awaitable, Callable
from hmac import compare_digest
from typing import Any


class BearerAuthMiddleware:
    def __init__(self, app: Callable[..., Awaitable[Any]], token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        auth_header = headers.get(b"authorization", b"").decode("latin1")
        expected = f"Bearer {self.token}"
        if not compare_digest(auth_header, expected):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b'{"error":"Unauthorized"}'})
            return

        await self.app(scope, receive, send)


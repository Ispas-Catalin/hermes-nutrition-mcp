from __future__ import annotations

import asyncio

import pytest

from app.auth import BearerAuthMiddleware


@pytest.mark.parametrize(
    ("header", "status"),
    [
        (b"Bearer secret", 200),
        (b"Bearer nope", 401),
        (b"", 401),
    ],
)
def test_bearer_auth_middleware(header: bytes, status: int) -> None:
    async def app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent = []

    async def send(message):
        sent.append(message)

    middleware = BearerAuthMiddleware(app, token="secret")
    asyncio.run(
        middleware(
            {
                "type": "http",
                "headers": [(b"authorization", header)] if header else [],
            },
            None,
            send,
        )
    )
    assert sent[0]["status"] == status


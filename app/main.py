from __future__ import annotations

import contextlib
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from app import __version__
from app.auth import BearerAuthMiddleware
from app.config import Settings
from app.tools import NutritionService, register_tools


def create_mcp_server(service: NutritionService, settings: Settings) -> Any:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    mcp = FastMCP(
        "nutrition-mcp",
        host=settings.host,
        port=settings.port,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.mcp_allowed_hosts,
            allowed_origins=settings.mcp_allowed_origins,
        ),
        instructions=(
            "Use these tools to store and retrieve nutrition data. "
            "Foods, aliases, recipes, and meal logs live in SQLite; do not store macros in memory."
        ),
    )
    register_tools(mcp, service)
    return mcp


def create_app(settings: Settings | None = None) -> Starlette:
    settings = settings or Settings.from_env()
    service = NutritionService(settings)
    mcp = create_mcp_server(service, settings)

    async def homepage(_request: Any) -> PlainTextResponse:
        return PlainTextResponse("nutrition-mcp is running\n")

    async def health_endpoint(_request: Any) -> JSONResponse:
        payload = service.health()
        payload["version"] = __version__
        return JSONResponse(payload)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette):
        async with mcp.session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/", homepage, methods=["GET"]),
            Route("/health", health_endpoint, methods=["GET"]),
            Mount("/mcp", app=mcp.streamable_http_app()),
        ],
        middleware=[Middleware(BearerAuthMiddleware, token=settings.mcp_token)],
        lifespan=lifespan,
    )


app = create_app()


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

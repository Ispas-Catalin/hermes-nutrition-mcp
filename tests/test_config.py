from __future__ import annotations

from app.config import Settings


def test_mcp_allowed_hosts_include_lan_and_localhost() -> None:
    settings = Settings(public_hosts=("192.168.1.142", "nutrition-mcp"))

    assert "192.168.1.142:*" in settings.mcp_allowed_hosts
    assert "nutrition-mcp:*" in settings.mcp_allowed_hosts
    assert "localhost:*" in settings.mcp_allowed_hosts
    assert "127.0.0.1:*" in settings.mcp_allowed_hosts


def test_mcp_allowed_origins_include_lan() -> None:
    settings = Settings(public_hosts=("192.168.1.142",))

    assert "http://192.168.1.142:*" in settings.mcp_allowed_origins
    assert "https://192.168.1.142:*" in settings.mcp_allowed_origins

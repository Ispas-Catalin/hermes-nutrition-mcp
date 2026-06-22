from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEZONE = "Europe/Bucharest"
DEFAULT_PUBLIC_HOSTS = ("192.168.1.142", "nutrition-mcp")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("/data")
    timezone: str = DEFAULT_TIMEZONE
    host: str = "0.0.0.0"
    port: int = 8765
    mcp_token: str | None = None
    public_hosts: tuple[str, ...] = DEFAULT_PUBLIC_HOSTS

    @property
    def db_path(self) -> Path:
        return self.data_dir / "nutrition.db"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    @property
    def mcp_allowed_hosts(self) -> list[str]:
        hosts = ["127.0.0.1", "localhost", "[::1]", *self.public_hosts]
        patterns: list[str] = []
        for host in hosts:
            if host:
                patterns.append(f"{host}:*")
                patterns.append(host)
        return _dedupe(patterns)

    @property
    def mcp_allowed_origins(self) -> list[str]:
        origins: list[str] = []
        for host in self.mcp_allowed_hosts:
            origins.append(f"http://{host}")
            origins.append(f"https://{host}")
        return _dedupe(origins)

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("MCP_TOKEN") or None
        public_hosts = _parse_csv(os.environ.get("PUBLIC_HOSTS"))
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", "/data")),
            timezone=os.environ.get("TZ", DEFAULT_TIMEZONE),
            host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "8765")),
            mcp_token=token,
            public_hosts=public_hosts or DEFAULT_PUBLIC_HOSTS,
        )


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TIMEZONE = "Europe/Bucharest"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("/data")
    timezone: str = DEFAULT_TIMEZONE
    host: str = "0.0.0.0"
    port: int = 8765
    mcp_token: str | None = None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "nutrition.db"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("MCP_TOKEN") or None
        return cls(
            data_dir=Path(os.environ.get("DATA_DIR", "/data")),
            timezone=os.environ.get("TZ", DEFAULT_TIMEZONE),
            host=os.environ.get("HOST", "0.0.0.0"),
            port=int(os.environ.get("PORT", "8765")),
            mcp_token=token,
        )


"""Settings, model ids, and paths. Every value can be overridden by an env var."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _path(var: str, default: Path) -> Path:
    return Path(os.environ.get(var, str(default)))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: _path("RADAR_DATA_DIR", REPO_ROOT / "data"))
    public_dir: Path = field(
        default_factory=lambda: _path("RADAR_PUBLIC_DIR", REPO_ROOT / "public_data")
    )
    model_fast: str = field(
        default_factory=lambda: os.environ.get("RADAR_MODEL_FAST", "claude-haiku-4-5-20251001")
    )
    model_writer: str = field(
        default_factory=lambda: os.environ.get("RADAR_MODEL_WRITER", "claude-sonnet-5-5")
    )
    model_reasoning: str = field(
        default_factory=lambda: os.environ.get("RADAR_MODEL_REASONING", "claude-opus-5-5")
    )

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def complaints_path(self) -> Path:
        return self.work_dir / "complaints.parquet"


def get_settings() -> Settings:
    return Settings()

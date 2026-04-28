"""Global configuration via pydantic-settings (reads from .env)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LM Studio
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    lm_studio_model: str = "Qwen2.5-7B-Instruct-Q4_K_M"
    lm_studio_embedding_model: str = "text-embedding-nomic-embed-text-v1.5"

    # Database
    sqlite_path: Path = Path("data/sqlite/echo.db")
    chroma_path: Path = Path("data/chroma")

    # Cognitive parameters
    max_workspace_slots: int = 7
    consolidation_interval_seconds: int = 3600
    reflection_trigger_interval: int = 5
    memory_decay_interval_seconds: int = 300

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: object) -> list[str]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v  # type: ignore[return-value]


# Singleton instance — import this everywhere
settings = Settings()

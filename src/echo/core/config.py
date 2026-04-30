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
    reflection_trigger_interval: int = 3
    memory_decay_interval_seconds: int = 300

    # GitHub OAuth
    github_client_id: str = ""
    github_token: str = ""

    # LLM provider selection
    llm_provider: Literal["copilot", "lm_studio"] = "lm_studio"
    copilot_model: str = "gpt-4o"

    # HuggingFace fallback embeddings (free Inference API)
    hf_token: str = ""  # optional — higher rate limits if provided
    # Must produce 768-dim vectors to match the ChromaDB semantic_memory collection.
    # paraphrase-multilingual-mpnet-base-v2 is 768-dim AND multilingual (IT/EN/ES…)
    hf_embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

    # Ollama embeddings (primary backend — local daemon, no Python deps, fast).
    # Pull the model once: `ollama pull paraphrase-multilingual:278m-mpnet-base-v2-fp16`
    # ⚠️  Model MUST produce 768-dim vectors to match existing ChromaDB collections.
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "paraphrase-multilingual:278m-mpnet-base-v2-fp16"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # Curiosity / idle-time autonomous learning
    curiosity_enabled: bool = True
    # Seconds of inactivity before a curiosity cycle is allowed to run.
    # Default: 180 s = 3 minutes — aligned with the 5-min light heartbeat so
    # ECHO can research after just one idle heartbeat interval.
    # Override via ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS env var.
    curiosity_idle_threshold_seconds: int = 180
    curiosity_max_topics: int = 3          # LLM-extracted topics per cycle
    curiosity_max_arxiv_results: int = 2   # papers per topic
    curiosity_max_hn_results: int = 3      # news articles per topic
    curiosity_max_brave_results: int = 3   # web results per topic (Brave Search MCP)

    # Self-prediction timeout (seconds).
    # On low-power devices (e.g. phone CPUs) the LLM call inside predict_response
    # can take tens of seconds. Reduce this value (e.g. ECHO_PREDICT_TIMEOUT_S=5)
    # in .env to cap it and keep retrieval snappy.
    predict_timeout_s: float = 10.0

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

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
    memory_decay_interval_seconds: int = 3600

    # GitHub OAuth
    github_client_id: str = ""
    github_token: str = ""

    # Wiki auto-sync from GitHub repository
    # ECHO fetches all .md files from this repo and ingests them into its wiki
    wiki_sync_repo: str = "https://github.com/Invernomut0/echo"
    wiki_sync_enabled: bool = True
    wiki_sync_interval_h: int = 24        # hours between full re-syncs
    wiki_sync_max_files: int = 10         # max .md files per sync cycle (keep low to avoid token quota)

    # Language for all ECHO-generated text (prompts, Telegram messages, self-modification notes)
    # Use BCP-47 codes: 'it' Italian, 'en' English, 'es' Spanish, etc.
    echo_language: str = "it"

    # LLM provider selection
    llm_provider: Literal["copilot", "lm_studio", "openai", "groq", "anthropic", "ollama", "opencode", "openrouter", "cerebras", "unsloth"] = "opencode"
    copilot_model: str = "gpt-4o"

    # OpenCode (opencode.ai — OpenAI-compatible zen gateway)
    # Docs: https://opencode.ai/docs/zen/
    opencode_api_key: str = ""
    opencode_model: str = "big-pickle"
    opencode_base_url: str = "https://opencode.ai/zen/v1"

    # OpenRouter (openrouter.ai — unified gateway to 300+ models)
    # Docs: https://openrouter.ai/docs
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Cerebras (cloud.cerebras.ai — ultra-fast inference, generous free tier)
    # Docs: https://inference-docs.cerebras.ai
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"

    # Unsloth Studio (local OpenAI-compatible inference server)
    # Start with: unsloth-studio serve  (default port 2242)
    # Docs: https://github.com/unslothai/unsloth
    unsloth_api_key: str = "unsloth"   # local server ignores the key, but client requires a value
    unsloth_model: str = "unsloth/Llama-3.2-3B-Instruct"
    unsloth_base_url: str = "http://localhost:2242/v1"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Anthropic (Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-20241022"

    # Ollama (chat — separate from embedding config above)
    ollama_chat_model: str = "llama3.2"

    # HuggingFace fallback embeddings (free Inference API)
    hf_token: str = ""  # optional — higher rate limits if provided
    # Must produce 768-dim vectors to match the ChromaDB semantic_memory collection.
    # paraphrase-multilingual-mpnet-base-v2 is 768-dim AND multilingual (IT/EN/ES…)
    hf_embedding_model: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"

    # Ollama embeddings (primary backend — local daemon, no Python deps, fast).
    # Pull the model once: `ollama pull paraphrase-multilingual:278m-mpnet-base-v2-fp16`
    # ⚠️  Model MUST produce 768-dim vectors to match existing ChromaDB collections.
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "nomic-embed-text"   # widely available; override with paraphrase-multilingual:278m if needed

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # Telegram bot integration (long polling)
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_poll_interval_seconds: float = 1.0
    telegram_update_timeout_seconds: int = 30
    telegram_request_timeout_seconds: float = 40.0
    telegram_allowed_chat_ids: list[int] = Field(default_factory=list)
    telegram_history_turns: int = 6
    telegram_max_reply_chars: int = 3900
    telegram_goal_notifications_enabled: bool = True

    # Curiosity / idle-time autonomous learning
    curiosity_enabled: bool = True
    # Seconds of inactivity before a curiosity cycle is allowed to run.
    # Default: 180 s = 3 minutes — aligned with the 5-min light heartbeat so
    # ECHO can research after just one idle heartbeat interval.
    # Override via ECHO_CURIOSITY_IDLE_THRESHOLD_SECONDS env var.
    # Consolidation heartbeat intervals
    consolidation_light_interval_s: int = 300    # light cycle every 5 min
    consolidation_deep_interval_s: int = 43_200  # deep/REM cycle every 12 h

    curiosity_idle_threshold_seconds: int = 900   # 15 min idle before curiosity fires
    curiosity_max_topics: int = 1                 # topics per cycle (1 = minimal token usage)
    curiosity_max_arxiv_results: int = 2          # papers per topic
    curiosity_max_hn_results: int = 2             # news articles per topic
    curiosity_max_brave_results: int = 2          # web results per topic (Brave Search MCP)

    # Self-prediction timeout (seconds).
    # On low-power devices (e.g. phone CPUs) the LLM call inside predict_response
    # can take tens of seconds. Reduce this value (e.g. ECHO_PREDICT_TIMEOUT_S=5)
    # in .env to cap it and keep retrieval snappy.
    predict_timeout_s: float = 10.0

    # Maximum concurrent LLM calls for agent deliberation.
    # Set to 1 for local/slow LLM backends (LM Studio, Ollama) to avoid
    # flooding the server with parallel requests that cause Channel Errors.
    # Set higher (3-6) for fast API backends (OpenAI, Copilot, Groq).
    # Keep at 1-2 for Cerebras free tier (60 RPM limit) to avoid 429s.
    max_concurrent_agent_calls: int = 1

    # Minimum seconds between LLM chat calls (0 = disabled).
    # Set to 1.1 for Cerebras free tier (60 RPM = 1/sec, with 0.1s headroom).
    # Set to 0 for fast/paid providers (OpenAI, Groq, etc.).
    llm_rate_limit_min_interval_s: float = 1.1

    # Drive scoring via LLM runs every N interactions (1 = every turn).
    # Increase to 3+ on slow local backends to reduce LM Studio contention.
    # Between scored turns the previous drive values are reused with slight decay.
    drive_scoring_interval: int = 3

    # Minimum message length (chars) to trigger wiki update and interest inference.
    # Conversational greetings (<60 chars) rarely contain new facts worth storing.
    wiki_update_min_chars: int = 60

    # ---------------------------------------------------------------------------
    # LLM max_tokens per call category
    # Thinking models (e.g. gemma-4-e4b, QwQ, DeepSeek-R1) consume a large
    # portion of the token budget for internal reasoning. Increase these values
    # when using a thinking model; reduce for fast non-thinking backends.
    # ---------------------------------------------------------------------------

    # User-facing: agents deliberation + final synthesis
    # NOTE: thinking models (gemma-4, QwQ, DeepSeek-R1) spend ~80-90% of max_tokens
    # on internal reasoning. Set high enough that content tokens remain after thinking.
    # synthesis: 1024 is too low — thinking eats ~600, leaving only ~400 for output.
    # Raise to 3072 so detailed responses (~800 content tokens) complete without cutoff.
    llm_max_tokens_agent: int = 1024         # each specialist agent (Analyst, Explorer …)
    llm_max_tokens_synthesis: int = 3072     # orchestrator final answer

    # User-facing: self-prediction (pre-response internal forecast)
    llm_max_tokens_self_prediction: int = 600

    # User-facing: motivational drive scoring (post-interaction)
    llm_max_tokens_drive_scoring: int = 1200

    # User-facing: bootstrap identity beliefs at first startup
    llm_max_tokens_bootstrap: int = 1024

    # Reflection (every N interactions)
    llm_max_tokens_reflection: int = 1024

    # Consolidation / sleep cycles
    llm_max_tokens_consolidation_patterns: int = 1024   # pattern extraction
    llm_max_tokens_consolidation_dedup: int = 400        # duplicate detection
    llm_max_tokens_dream: int = 600                      # dream narrative
    llm_max_tokens_creative_synthesis: int = 500         # creative bridge
    llm_max_tokens_swarm_dream: int = 600                # swarm dream persona

    # Curiosity / autonomous learning
    llm_max_tokens_topic_extraction: int = 1200         # extract topics from memories
    llm_max_tokens_zpd_topics: int = 1200               # ZPD adjacent topic suggestion
    llm_max_tokens_goal_reflect: int = 1800             # goal reflection & planning
    llm_max_tokens_goal_pursue: int = 1200              # goal search interpretation
    llm_max_tokens_interest_infer: int = 600            # interest topic inference

    # Initiative engine (proactive messages)
    llm_max_tokens_initiative_insight: int = 800        # daily insight generation
    llm_max_tokens_initiative_question: int = 600       # question generation
    llm_max_tokens_initiative_reflection: int = 600     # proactive self-reflection

    # Learning / self-evaluation
    llm_max_tokens_meta_insight: int = 600              # meta-learning insight
    llm_max_tokens_skill_assessment: int = 800          # skill self-assessment

    # Memory
    llm_max_tokens_associative_cross: int = 600         # cross-pollination check
    llm_max_tokens_associative_cluster: int = 800       # temporal clustering
    llm_max_tokens_semantic_dedup: int = 500            # semantic dedup check
    llm_max_tokens_semantic_conflict: int = 400         # conflict detection
    llm_max_tokens_semantic_merge: int = 400            # merge suggestion

    # Wiki document processing
    llm_max_tokens_wiki_ingest: int = 3000              # full doc extraction
    llm_max_tokens_wiki_page: int = 1500                # entity/concept page write
    llm_max_tokens_wiki_update: int = 1200              # page update
    llm_max_tokens_wiki_interaction: int = 1000         # post-interaction update
    llm_max_tokens_wiki_search: int = 1500              # search results page

    # Self-model
    llm_max_tokens_echo_md: int = 2048                  # echo.md self-rewrite
    llm_max_tokens_metacognition: int = 300             # cognitive model review

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

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def parse_telegram_chat_ids(cls, v: object) -> list[int]:
        """Accept JSON array or comma-separated chat IDs from env."""
        if v is None or v == "":
            return []

        parsed: object = v
        if isinstance(v, str):
            raw = v.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = [part.strip() for part in raw.split(",") if part.strip()]

        if isinstance(parsed, (list, tuple, set)):
            out: list[int] = []
            for item in parsed:
                try:
                    out.append(int(item))
                except (TypeError, ValueError):
                    continue
            return out

        try:
            return [int(parsed)]
        except (TypeError, ValueError):
            return []


# Singleton instance — import this everywhere
settings = Settings()

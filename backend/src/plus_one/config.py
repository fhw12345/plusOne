"""Application configuration via Pydantic Settings.

All env vars are validated at startup. See ``.env.example`` for the full list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level settings — read from env + .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # === App ===
    app_env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # === Tool fixtures ===
    # Tools (Reddit, XHS, Google Places) read pre-collected JSON from this
    # directory in v1. Live API wiring is a follow-up batch.
    fixtures_dir: Path = Path("fixtures")

    # === Agent Maestro (LLM gateway) ===
    # Maestro is an Anthropic-API-compatible gateway exposing Claude / GPT / Gemini
    # under one endpoint. All LLM traffic routes through it; per-role model
    # assignment lives in core/llm/roles.py.
    maestro_base_url: str = "http://localhost:23333/api/anthropic"
    maestro_auth_token: str = Field(default="Powered by Agent Maestro")

    # Default sampling defaults (overridable per call)
    llm_default_temperature: float = 0.7
    llm_default_max_tokens: int = 4096

    # === DB ===
    database_url: str = "postgresql+asyncpg://plus_one:dev@localhost:5432/plus_one"
    # Pool sizing — tuned for local-dev defaults (ADR-006). Production at
    # scale would override these via env. ``db_pool_size + db_pool_max_overflow``
    # is the hard ceiling on concurrent open connections.
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    # DB-level kill switch for runaway queries. The agent cycle has its own
    # per-phase timeout (see core/agents/framework/cycle.py); this is the
    # safety net at the SQL layer.
    db_statement_timeout_ms: int = 30_000

    # === Redis ===
    redis_url: str = "redis://localhost:6379/0"

    # === Auth ===
    jwt_secret: str = Field(default="change-me")
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60

    # Magic-link tokens are short-lived; long enough for a user to switch
    # apps, short enough to limit interception.
    magic_link_ttl_minutes: int = 15

    # Where the frontend is reachable, used to build the magic-link URL
    # included in emails. Local dev default works against the next.js
    # dev server; production override via env.
    frontend_base_url: str = "http://localhost:3000"

    # Email sender selection — the console sender writes magic-link URLs
    # to server logs. Must be opt-in (NOT inferred from app_env) so a
    # staging deployment can never accidentally leak credentials to its
    # log aggregator. Set to True only on a developer's local machine.
    allow_console_email_sender: bool = False

    # Cookie settings for the auth JWT. JWT lands in body AND in an
    # httpOnly cookie so the frontend can choose; non-browser clients
    # (CLI / mobile) use the body, browser SPAs use the cookie.
    auth_cookie_name: str = "plus_one_session"
    auth_cookie_secure: bool = True  # set False on plain-http localhost
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # === SMTP (batch-2m) ===
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "plus one"

    # === Admin seed (batch-2m) ===
    admin_username: str = "admin"
    admin_password: str = "admin"  # noqa: S105
    admin_email: str = "ffffhhhww@qq.com"

    # === Email-code login (batch-2m) ===
    email_code_ttl_minutes: int = 10
    email_code_length: int = 6
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15

    # === Observability ===
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3001"


settings = Settings()

"""
Configuración centralizada de la app.
Lee variables de entorno desde .env con validación tipada via Pydantic.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Todas las configuraciones de la app en un solo lugar."""

    # --- App ---
    app_name: str = "Anoven"
    app_env: str = "development"  # development | staging | production
    debug: bool = True

    # --- Database ---
    # En desarrollo: SQLite local. En producción: Postgres.
    # Cambiamos solo esta string al deployar.
    database_url: str = "sqlite:///./anoven.db"

    # --- Auth ---
    jwt_secret: str = "CAMBIA-ESTO-EN-PROD"  # firma de los JWT — secreto
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 días

    # --- LLM ---
    anthropic_api_key: str = ""
    default_model: str = "claude-haiku-4-5-20251001"
    google_ai_api_key: str = ""

    # --- Context window management ---
    # Effective input budget = CONTEXT_MAX_TOKENS - CONTEXT_OUTPUT_RESERVED = 191808
    # trim strategy: oldest-first preserving last 2 (Evans DDD 2003 — adapter concern, not domain)
    context_max_tokens: int = 200000        # Claude Sonnet 4.6 total window
    context_output_reserved: int = 8192    # tokens reserved for model output
    context_warning_threshold: float = 0.70  # warn at 70% of effective budget
    context_compact_threshold: float = 1.00  # trim when hitting 100% of effective budget

    # --- Google OAuth ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    frontend_url: str = "http://localhost:3000"

    # --- Engram (memoria persistente) ---
    engram_url: str = "http://localhost:7437"
    # Timeout corto: si engram no responde rápido, el chat sigue sin memoria
    # (degradación elegante). Mejor responder sin memoria que colgar el chat.
    engram_timeout_seconds: float = 3.0

    # --- CORS ---
    cors_origins: list[str] = [
        "http://localhost:3000",  # Next.js default
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Instancia única, importable desde cualquier lado
settings = Settings()

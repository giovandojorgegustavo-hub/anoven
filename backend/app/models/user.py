"""
Modelo User — la tabla users de la BD.

SQLAlchemy lee esta clase y AUTO-GENERA la tabla por nosotros.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """Un usuario del sistema Anoven."""

    __tablename__ = "users"

    # === Identidad ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    # === Auth ===
    # password_hash es OPCIONAL — los users de Google no tienen password local.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Identifica de dónde vino el user: "local" (email+password) o "google".
    # En el futuro podríamos agregar "github", "microsoft", etc.
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", nullable=False)

    # ID único que Google asigna al user (solo si auth_provider="google").
    # Indexado para lookups rápidos durante el callback de OAuth.
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)

    # === Rol ===
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)

    # === Onboarding (Fase 2) ===
    # Estado: "pending" → user recién registrado, falta hacer entrevista
    #         "in_progress" → empezó la entrevista, no terminó
    #         "passed" → pasó la entrevista, sistema desbloqueado
    #         "failed_quality" → no pasó el quality gate, tiene que reintentar
    onboarding_state: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)

    # Score 0-100 del último intento de entrevista (NULL si nunca terminó una).
    onboarding_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cuántas veces intentó la entrevista.
    onboarding_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Feedback del último intento (cuando falla, para mostrarle al user qué mejorar).
    onboarding_last_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Perfil JSON extraído por el Entrevistador (cuando pasa).
    # Lo usa MentorMatcher + Promptifex. También sirve como insight de negocio para vos.
    onboarding_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # === Project activo (Fase 4.2) ===
    # FK al project que el user tiene seleccionado como "contexto actual".
    # NULL si el user todavía no tiene projects (recién creado).
    # NO ponemos ForeignKey real acá porque crearía ciclo entre tablas;
    # validamos a nivel app.
    active_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # === Research opt-in (Fase 7) ===
    # Si True, Anoven puede usar conversaciones anonimizadas para mejorar
    # producto, marketing y prompts. Default False — consent explícito.
    research_opt_in: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # === Per-user model override (sdd/per-mentor-model-assignment-v1, 2026-06-08) ===
    # NULL = no override (fall through to mentor default or env DEFAULT_MODEL).
    # When set, wins over mentor default per ModelResolver chain.
    # Valid values gated by DB CHECK constraint (see migration) AND MODEL_WHITELIST
    # in app/services/model_resolver.py — keep both in sync.
    model_override: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # === Timestamps ===
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} provider={self.auth_provider}>"

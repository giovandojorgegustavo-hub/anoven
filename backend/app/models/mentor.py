"""
Modelos Mentor y UserMentor.

Mentor: la entidad global (un mentor que existe en el sistema).
UserMentor: la asignación (qué user tiene acceso a qué mentor).

Esto te permite:
  - Como admin, crear mentores que aparezcan para todos los users nuevos.
  - Asignar mentores específicos a users específicos.
  - Que cada user vea SOLO los mentores asignados a él/ella.
"""

from datetime import datetime
import json
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, Text, JSON
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base



class _JSONList(TypeDecorator):
    """Stores a Python list[str] as a JSON TEXT in PostgreSQL.
    Returns [] when NULL or unparseable (fail-safe).
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return '[]'
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []


class Mentor(Base):
    """Un mentor del sistema. Vive globalmente; el acceso lo controla UserMentor."""

    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Slug — identificador corto para invocar (ej: "estrategia", "marketing")
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)

    # Nombre visible (ej: "Estrategia", "Marketing")
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    # Canon — autores de referencia, separados por coma
    canon: Mapped[str] = mapped_column(String(500), nullable=False)

    # Filosofía — frase guía del mentor
    filosofia: Mapped[str] = mapped_column(String(500), nullable=False)

    # System prompt — la instrucción completa que se le pasa a Claude.
    # Almacenado en BD para poder editar sin redeployar.
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # Quién lo creó (NULL = mentor del sistema, no de un user específico)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    # Visibility:
    #   "private"    → solo el creador
    #   "shareable"  → puede ser asignado a otros users
    #   "global"     → auto-asignado a todos los users nuevos (los 5 default)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)

    # Estado del mentor:
    #   "draft"    → en construcción, no usable todavía
    #   "active"   → disponible para usar
    #   "archived" → ya no se usa, pero queda guardado
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # ===== FASE 6 — Versionado + curación =====
    # version: número de versión actual de este mentor (incrementa con cada curación)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # prev_version_id: punta a la versión anterior si existe (FK self).
    # Se mantiene NULL para v1; se llena cuando se cura a v2, v3, etc.
    prev_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mentors.id"), nullable=True
    )

    # curated_at: timestamp de cuándo se curó esta versión específica.
    # NULL para versiones initial_seed (nunca pasaron por Promptifex SDD).
    curated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # curator: quién curó esta versión.
    #   "initial_seed"   → entró por seed_verticals.py (sin curar)
    #   "promptifex_sdd" → pasó por el SDD pipeline de Promptifex
    #   "manual_admin"   → editado a mano por admin
    curator: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # eval_suite_topic_key: link a la eval suite en engram que valida este mentor.
    # Ej: "anoven-promptifex/eval-suite/v1.2"
    eval_suite_topic_key: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Phase 2 — Tool gating: JSON array of tool slugs this mentor can invoke.
    # Default [] = legacy path (no tools, no agentic loop).
    # Example: '["mem_search"]', '["mem_search", "mem_save"]'
    allowed_tools: Mapped[list] = mapped_column(_JSONList, nullable=False, default=list)
    # Cross-mentor invocation gating (cycle: call-mentor-multi-agent, 2026-06-08).
    # Which mentors this mentor is allowed to invoke via call_mentor tool.
    # Default [] = cannot call any mentor (Creador MUST stay []).
    # ADR-3: JSONB for proper type checking (allowed_tools is TEXT — historical).
    allowed_callees: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Max cross-mentor calls per outer turn (NULL = system default = 2).
    # Per-mentor override for cost control (X6.2). Admin-configurable.
    max_callees_per_turn: Mapped[int | None] = mapped_column(Integer, nullable=True)


    # Per-mentor Claude model assignment (sdd/per-mentor-model-assignment-v1, 2026-06-08).
    # NULL = fall through to users.model_override (if set) then env DEFAULT_MODEL.
    # Valid values gated by DB CHECK constraint (see migration) AND MODEL_WHITELIST
    # in app/services/model_resolver.py — keep both in sync.
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)

    def __repr__(self) -> str:
        return f"<Mentor id={self.id} slug={self.slug} v={self.version}>"


class UserMentor(Base):
    """Asignación: qué user tiene acceso a qué mentor."""

    __tablename__ = "user_mentors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    mentor_id: Mapped[int] = mapped_column(Integer, ForeignKey("mentors.id"), nullable=False)

    # De dónde vino esta asignación:
    #   "default"            → automática al registrarse
    #   "created_by_self"    → el user lo creó
    #   "assigned_by_admin"  → vos como admin lo asignaste
    source: Mapped[str] = mapped_column(String(30), default="default", nullable=False)

    # Activo o desactivado (sin borrar)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Razón corta de por qué el MentorMatcher eligió este mentor para este user.
    # Solo se llena cuando source='matched'. Para defaults queda NULL.
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<UserMentor user={self.user_id} mentor={self.mentor_id} active={self.active}>"

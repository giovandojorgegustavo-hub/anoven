"""
MentorSkill -- skill de markdown asociado a un mentor.

Permite inyectar bloques de conocimiento practico en el system_prompt
de forma dinamica sin redeploy. Un mentor puede tener N skills; cada
skill tiene contenido en markdown, orden (position) y habilitacion.
"""

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.database import Base


class JSONListTypeDecorator(TypeDecorator):
    """Serializa/deserializa list[str] <-> JSON TEXT para SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return []


class MentorSkill(Base):
    """
    Skill de markdown vinculada a un mentor.

    content: cuerpo del skill en markdown (lo que se inyecta al system_prompt)
    triggers: palabras clave que activan el skill (NULL = siempre activo)
    position: orden ascendente dentro del mentor
    enabled: si false, el skill se excluye del system_prompt pero queda en la BD
    """

    __tablename__ = "mentor_skills"
    __table_args__ = (
        UniqueConstraint("mentor_id", "slug", name="uq_mentor_skills_mentor_slug"),
        Index("ix_mentor_skills_mentor_id_2", "mentor_id"),
        Index("ix_mentor_skills_enabled_2", "mentor_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    mentor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mentors.id", ondelete="CASCADE"),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON array de strings -- NULL significa always-on
    triggers: Mapped[Optional[list]] = mapped_column(
        JSONListTypeDecorator, nullable=True
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<MentorSkill id={self.id} mentor_id={self.mentor_id} "
            f"slug={self.slug!r} enabled={self.enabled}>"
        )

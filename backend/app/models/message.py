"""
Modelo Message — un mensaje dentro de una Conversation.

Separado de InterviewMessage porque las conversaciones de mentor son un
contexto distinto al de la entrevista. Comparten estructura pero el FK
apunta a `conversations`, no a `interview_attempts`.

author_user_id (agregado en anoven-shared-projects):
  - NULL  → turno del asistente (el mentor). El frontend muestra el nombre
            del mentor cuando author_user_id IS NULL.
  - NOT NULL → turno del user que escribió el mensaje.
  Esto permite al SharedProjectContextBuilder saber quién dijo qué cuando
  comprime el historial en proyectos con múltiples members.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id"),
        index=True,
        nullable=False,
    )

    # "user" | "assistant" — coincide con lo que espera Anthropic.
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # NULL = turno del asistente (no tiene author humano).
    # NOT NULL = user que escribió este mensaje (para proyectos compartidos).
    # Columna agregada en migración shared_projects_001_create.sql.
    author_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    author: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[author_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} conv={self.conversation_id} role={self.role}>"

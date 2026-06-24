"""
Modelo MentorRequest — pedidos de mentores que NO existen todavía en el catálogo.

Dos fuentes posibles:
  - 'interview' → Evaluador detectó dolores que no cubre el catálogo actual.
  - 'manual' → user lo pidió explícito (futuro: botón "pedí un mentor").

Cada request tiene status:
  - 'pending' → esperando que el user lo cree con el Creador, o que vos como
    admin lo armes y lo apruebes para el catálogo público.
  - 'created' → el user efectivamente lo armó (vinculado a created_mentor_id).
  - 'rejected' → vos como admin descartaste la sugerencia.

Esto NO es el mismo flujo que Mentor.status='pending_review' (Fase 5.5) —
ese es para mentores YA CREADOS esperando curación. MentorRequest es para
mentores QUE TODAVÍA NO EXISTEN.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MentorRequest(Base):
    __tablename__ = "mentor_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )

    # "interview" | "manual"
    source: Mapped[str] = mapped_column(String(20), nullable=False)

    proposed_name: Mapped[str] = mapped_column(String(120), nullable=False)
    proposed_canon: Mapped[str | None] = mapped_column(String(500), nullable=True)
    why: Mapped[str] = mapped_column(Text, nullable=False)

    # "pending" | "created" | "rejected"
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    # Si el user creó el mentor a partir de este request, lo linkeamos.
    created_mentor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mentors.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

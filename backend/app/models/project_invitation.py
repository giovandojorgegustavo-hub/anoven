"""
Modelo ProjectInvitation — invitación pendiente (o resuelta) para unirse a un proyecto.

Ciclo de vida:
  status: pending → accepted | rejected | expired | revoked

  - 'pending'  → enviada, esperando respuesta del invitado.
  - 'accepted' → invitado aceptó; se crea el ProjectMember correspondiente.
  - 'rejected' → invitado rechazó; el user puede ser re-invitado después.
  - 'expired'  → marcada lazily cuando alguien intenta accionar una invitación
                 cuyo expires_at < NOW(). No hay cron job en v1.
  - 'revoked'  → el owner la canceló antes de que el invitado respondiera.

Constraint de unicidad:
  - UNIQUE parcial (project_id, invited_user_id) WHERE status='pending'
    → solo una pendiente activa por (project, user) al mismo tiempo.
    → creado como índice parcial en la migración DDL; acá lo omitimos
      para no duplicar la definición (PostgreSQL-only feature).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project


ALLOWED_STATUSES = ("pending", "accepted", "rejected", "expired", "revoked")


class ProjectInvitation(Base):
    __tablename__ = "project_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    invited_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    invited_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # "pending" | "accepted" | "rejected" | "expired" | "revoked"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="raise",
    )

    invited_user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_user_id],
        lazy="raise",
    )

    invited_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_by_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectInvitation id={self.id} project={self.project_id} "
            f"invited_user={self.invited_user_id} status={self.status!r}>"
        )

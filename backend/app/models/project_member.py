"""
Modelo ProjectMember — membresía activa de un user en un proyecto.

Ciclo de vida:
  - Creado cuando el owner invita y el invitado acepta (role='member'),
    O cuando el proyecto se crea (owner insertado directo, role='owner').
  - Eliminado cuando el owner kickea al miembro, o cuando el miembro
    abandona el proyecto.

Constraints:
  - UNIQUE (project_id, user_id) — un user solo puede ser member una vez.
  - role CHECK ('owner' | 'member') — solo dos roles en v1.
  - invited_by_user_id NOT NULL — para el owner inicial, apunta a sí mismo.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project


ALLOWED_ROLES = ("owner", "member")


class ProjectMember(Base):
    __tablename__ = "project_members"

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # "owner" | "member"
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Para el owner inicial: apunta a sí mismo.
    # Para members: apunta al user que envió la invitación (el owner al momento).
    invited_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="raise",
    )

    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        lazy="raise",
    )

    invited_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_by_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectMember id={self.id} project={self.project_id} "
            f"user={self.user_id} role={self.role!r}>"
        )

"""
Modelo ProjectMentor — asignación de un mentor a un proyecto compartido.

Semántica:
  - Un project owner decide qué mentores están disponibles en el proyecto.
  - Todos los members del proyecto pueden usar esos mentores dentro del contexto
    del proyecto.
  - UNIQUE (project_id, mentor_id) — un mentor solo se asigna una vez por proyecto.

Diferencia con UserMentor:
  - UserMentor = asignación global de mentor a user (quién tiene acceso al mentor).
  - ProjectMentor = asignación contextual de mentor a proyecto (qué mentor
    se usa para las conversaciones de ese proyecto).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.mentor import Mentor
    from app.models.user import User
    from app.models.project import Project


class ProjectMentor(Base):
    __tablename__ = "project_mentors"

    __table_args__ = (
        UniqueConstraint("project_id", "mentor_id", name="uq_project_mentors_project_mentor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    mentor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mentors.id", ondelete="CASCADE"),
        nullable=False,
    )

    added_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────

    project: Mapped["Project"] = relationship(
        "Project",
        foreign_keys=[project_id],
        lazy="raise",
    )

    mentor: Mapped["Mentor"] = relationship(
        "Mentor",
        foreign_keys=[mentor_id],
        lazy="raise",
    )

    added_by: Mapped["User"] = relationship(
        "User",
        foreign_keys=[added_by_user_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectMentor id={self.id} project={self.project_id} "
            f"mentor={self.mentor_id}>"
        )

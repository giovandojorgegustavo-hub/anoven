"""
Modelos Project y UseCase.

Project = agrupación de alto nivel para el user
         (ej: "Bonabowl", "Mi café boutique", "Tesis doctoral").
UseCase = sub-agrupación dentro de un project
         (ej: "Marketing Instagram", "Pricing").

Toda conversación con un mentor vive dentro de un (project, use_case). Eso permite:
  - Filtrar conversaciones por contexto.
  - Inyectar memoria scoped al project / use_case en Fase 4.3+.
  - Aplicar reglas con scope global / project / use_case en Fase 4.5.

Cada user nuevo arranca con un project default "General" + un use_case
default "Charla libre". El user puede crear más cuando quiera.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    # Slug único por user (no globalmente). En migration agregamos
    # UNIQUE(user_id, slug) si hace falta.
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Marca el "General" default. Para que el frontend pueda identificarlo
    # incluso si el user renombra.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} user={self.user_id} slug={self.slug}>"


class UseCase(Base):
    __tablename__ = "use_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id"),
        index=True,
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<UseCase id={self.id} project={self.project_id} slug={self.slug}>"

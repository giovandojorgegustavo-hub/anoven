"""
Repository ProjectMentor — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.

Gestiona la asignación de mentores a proyectos compartidos.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.project_mentor import ProjectMentor


class ProjectMentorRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Queries individuales ──────────────────────────────────────────────────

    def get_by_project_mentor(
        self, project_id: int, mentor_id: int
    ) -> ProjectMentor | None:
        """Busca la asignación (project_id, mentor_id)."""
        stmt = (
            select(ProjectMentor)
            .where(ProjectMentor.project_id == project_id)
            .where(ProjectMentor.mentor_id == mentor_id)
        )
        return self.db.execute(stmt).scalars().first()

    def exists(self, project_id: int, mentor_id: int) -> bool:
        """True si el mentor ya está asignado al proyecto."""
        return self.get_by_project_mentor(project_id, mentor_id) is not None

    # ── Listas ────────────────────────────────────────────────────────────────

    def list_for_project(self, project_id: int) -> list[ProjectMentor]:
        """
        Todos los mentores asignados al proyecto, con eager load del mentor.
        Ordenados por added_at ASC.
        """
        stmt = (
            select(ProjectMentor)
            .where(ProjectMentor.project_id == project_id)
            .options(selectinload(ProjectMentor.mentor))
            .order_by(ProjectMentor.added_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Escrituras ────────────────────────────────────────────────────────────

    def create(
        self,
        project_id: int,
        mentor_id: int,
        added_by_user_id: int,
    ) -> ProjectMentor:
        """Asigna un mentor al proyecto. Flush sin commit."""
        pm = ProjectMentor(
            project_id=project_id,
            mentor_id=mentor_id,
            added_by_user_id=added_by_user_id,
        )
        self.db.add(pm)
        self.db.flush()
        return pm

    def delete(self, mentor: ProjectMentor) -> None:
        """Desasigna el mentor del proyecto. Flush sin commit."""
        self.db.delete(mentor)
        self.db.flush()

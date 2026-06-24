"""
ProjectMentorService — lógica de negocio para asignación de mentores a proyectos.

Responsabilidades:
  - Asignar / desasignar mentores (solo el owner)
  - Listar mentores asignados (cualquier miembro)

Invariante A1.3 STRICT: NUNCA importar fastapi.

Alistair Cockburn — Hexagonal Architecture, 2005.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project_mentor import ProjectMentor
from app.repositories.project_member_repo import ProjectMemberRepository
from app.repositories.project_mentor_repo import ProjectMentorRepository
from app.services.project_member_service import (
    NotMemberError,
    NotOwnerError,
    SharedProjectsError,
)


# ============================================================
# Excepciones de dominio adicionales
# ============================================================

class MentorNotFoundError(SharedProjectsError):
    """El mentor no existe o no está activo."""


class MentorAlreadyAssignedError(SharedProjectsError):
    """El mentor ya está asignado a este proyecto."""


class MentorNotAssignedError(SharedProjectsError):
    """El mentor no está asignado a este proyecto."""


class ProjectMentorService:
    """
    Servicio de dominio para gestión de mentores en proyectos compartidos.
    """

    def __init__(self, db: Session):
        self.db = db
        self.mentor_repo_project = ProjectMentorRepository(db)
        self.member_repo = ProjectMemberRepository(db)

    def _get_mentor(self, mentor_id: int):
        from app.repositories.mentor_repo import MentorRepository
        return MentorRepository(self.db).get_by_id(mentor_id)

    def _assert_is_owner(self, project_id: int, user_id: int):
        member = self.member_repo.get_by_project_user(project_id, user_id)
        if member is None or member.role != "owner":
            raise NotOwnerError(
                "Solo el owner puede gestionar los mentores del proyecto."
            )
        return member

    def add_mentor(
        self,
        project_id: int,
        mentor_id: int,
        owner_user_id: int,
    ) -> ProjectMentor:
        """
        Asigna un mentor al proyecto.

        Validaciones:
          1. owner_user_id es owner del proyecto
          2. mentor existe y está activo
          3. mentor no está ya asignado
        """
        self._assert_is_owner(project_id, owner_user_id)

        mentor = self._get_mentor(mentor_id)
        if mentor is None or mentor.status != "active":
            raise MentorNotFoundError(
                "El mentor no existe o no está disponible."
            )

        if self.mentor_repo_project.exists(project_id, mentor_id):
            raise MentorAlreadyAssignedError(
                "Ese mentor ya está asignado a este proyecto."
            )

        pm = self.mentor_repo_project.create(
            project_id=project_id,
            mentor_id=mentor_id,
            added_by_user_id=owner_user_id,
        )
        self.db.commit()
        return pm

    def remove_mentor(
        self,
        project_id: int,
        mentor_id: int,
        owner_user_id: int,
    ) -> None:
        """Desasigna un mentor del proyecto (solo el owner)."""
        self._assert_is_owner(project_id, owner_user_id)

        pm = self.mentor_repo_project.get_by_project_mentor(project_id, mentor_id)
        if pm is None:
            raise MentorNotAssignedError(
                "Ese mentor no está asignado a este proyecto."
            )

        self.mentor_repo_project.delete(pm)
        self.db.commit()

    def list_mentors(
        self,
        project_id: int,
        requesting_user_id: int,
    ) -> list[ProjectMentor]:
        """
        Lista los mentores asignados al proyecto.
        Accesible para cualquier miembro o el owner.
        """
        if not self.member_repo.exists(project_id, requesting_user_id):
            raise NotMemberError(
                "Debés ser miembro del proyecto para ver sus mentores."
            )
        return self.mentor_repo_project.list_for_project(project_id)

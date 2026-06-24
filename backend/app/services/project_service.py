"""
ProjectService — orquesta projects + use_cases para un user.
"""

import re

from sqlalchemy.orm import Session

from app.models.project import Project, UseCase
from app.repositories.project_repo import ProjectRepository, UseCaseRepository
from app.repositories.project_member_repo import ProjectMemberRepository


class ProjectError(Exception):
    pass


class ProjectNotFound(ProjectError):
    pass


class UseCaseNotFound(ProjectError):
    pass


class NotYours(ProjectError):
    pass


class CannotDeleteDefault(ProjectError):
    pass


class CannotDeleteWithConversations(ProjectError):
    pass


class ProjectService:
    def __init__(self, db: Session):
        self.db = db
        self.project_repo = ProjectRepository(db)
        self.use_case_repo = UseCaseRepository(db)
        self.member_repo = ProjectMemberRepository(db)

    # ============================================================
    # Default project bootstrap
    # ============================================================

    def ensure_default_for_user(self, user_id: int) -> Project:
        """
        Garantiza que el user tenga un project default 'General' con un
        use_case default 'Charla libre'. Idempotente.

        Se llama:
          - Al crear un user (auth_service.register / login_or_register_google)
          - En la migración 4.2 para users existentes
        """
        existing = self.project_repo.get_default_for_user(user_id)
        if existing is not None:
            # Asegurar que tenga al menos un use_case default
            default_uc = self.use_case_repo.get_default_for_project(existing.id)
            if default_uc is None:
                self.use_case_repo.create(
                    project_id=existing.id,
                    slug="charla-libre",
                    name="Charla libre",
                    description="Conversaciones sin tema específico.",
                    is_default=True,
                )
            return existing

        project = self.project_repo.create(
            user_id=user_id,
            slug="general",
            name="General",
            description="Tu espacio default para charlas con mentores.",
            is_default=True,
        )
        self.use_case_repo.create(
            project_id=project.id,
            slug="charla-libre",
            name="Charla libre",
            description="Conversaciones sin tema específico.",
            is_default=True,
        )
        # El owner debe ser miembro de su propio proyecto, sino el guard
        # require_project_member rechaza con 403.
        self.member_repo.add_member(
            project_id=project.id,
            user_id=user_id,
            role="owner",
            invited_by_user_id=user_id,
        )
        self.db.commit()
        return project

    # ============================================================
    # Projects (user-facing)
    # ============================================================

    def list_for_user(self, user_id: int) -> list[Project]:
        return self.project_repo.list_for_user(user_id)

    def get_for_user(self, project_id: int, user_id: int) -> Project:
        p = self.project_repo.get_by_id(project_id)
        if p is None or p.user_id != user_id:
            raise ProjectNotFound(f"Project {project_id} no existe.")
        return p

    def create_for_user(
        self,
        user_id: int,
        name: str,
        description: str | None = None,
    ) -> Project:
        """
        Crea un project nuevo para el user con un use_case default
        'Charla libre'. El slug se deriva del name.
        """
        slug = _slugify(name)
        # Si el slug ya existe para este user, lo desambiguamos.
        existing = self.project_repo.list_for_user(user_id)
        slugs = {p.slug for p in existing}
        if slug in slugs:
            i = 2
            while f"{slug}-{i}" in slugs:
                i += 1
            slug = f"{slug}-{i}"

        project = self.project_repo.create(
            user_id=user_id,
            slug=slug,
            name=name,
            description=description,
            is_default=False,
        )
        self.use_case_repo.create(
            project_id=project.id,
            slug="charla-libre",
            name="Charla libre",
            description="Conversaciones sin tema específico.",
            is_default=True,
        )
        # El owner debe ser miembro de su propio proyecto, sino el guard
        # require_project_member rechaza con 403.
        self.member_repo.add_member(
            project_id=project.id,
            user_id=user_id,
            role="owner",
            invited_by_user_id=user_id,
        )
        self.db.commit()
        return project

    def update_project(
        self,
        project_id: int,
        user_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Project:
        project = self.get_for_user(project_id, user_id)
        return self.project_repo.update(project, name=name, description=description)

    def delete_project(self, project_id: int, user_id: int) -> None:
        """
        Borra un project. Safety:
          - NO se puede borrar el default
          - NO se puede borrar si tiene conversations asignadas
        """
        project = self.get_for_user(project_id, user_id)
        if project.is_default:
            raise CannotDeleteDefault("No podés borrar el project default.")

        # Chequeo si hay conversations en cualquier use_case de este project
        from app.models.conversation import Conversation
        from sqlalchemy import select, func
        ucs = self.use_case_repo.list_for_project(project_id)
        if ucs:
            uc_ids = [u.id for u in ucs]
            stmt = select(func.count(Conversation.id)).where(
                Conversation.use_case_id.in_(uc_ids)
            )
            count = self.db.execute(stmt).scalar_one()
            if count > 0:
                raise CannotDeleteWithConversations(
                    f"Este project tiene {count} conversaciones. "
                    "Borralas o moverlas a otro project antes."
                )

        # Borramos use_cases primero (cascade no está seteado)
        for uc in ucs:
            self.db.delete(uc)
        self.project_repo.delete(project)

    # ============================================================
    # Use cases
    # ============================================================

    def list_use_cases(self, project_id: int, user_id: int) -> list[UseCase]:
        # Verificación de ownership.
        self.get_for_user(project_id, user_id)
        return self.use_case_repo.list_for_project(project_id)

    def update_use_case(
        self,
        project_id: int,
        use_case_id: int,
        user_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> UseCase:
        # Verificar ownership del project
        self.get_for_user(project_id, user_id)
        uc = self.use_case_repo.get_by_id(use_case_id)
        if uc is None or uc.project_id != project_id:
            raise UseCaseNotFound(f"Use case {use_case_id} no existe.")
        return self.use_case_repo.update(uc, name=name, description=description)

    def create_use_case_for_user(
        self,
        project_id: int,
        user_id: int,
        name: str,
        description: str | None = None,
    ) -> UseCase:
        # Verificación de ownership del project.
        self.get_for_user(project_id, user_id)

        slug = _slugify(name)
        existing = self.use_case_repo.list_for_project(project_id)
        slugs = {u.slug for u in existing}
        if slug in slugs:
            i = 2
            while f"{slug}-{i}" in slugs:
                i += 1
            slug = f"{slug}-{i}"

        return self.use_case_repo.create(
            project_id=project_id,
            slug=slug,
            name=name,
            description=description,
            is_default=False,
        )


# ============================================================
# Helpers
# ============================================================

_SLUG_NON_ALPHA = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Slug simple: lowercase, sin acentos básicos, espacios → '-'."""
    text = name.lower().strip()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    text = _SLUG_NON_ALPHA.sub("-", text).strip("-")
    return text[:60] or "sin-nombre"

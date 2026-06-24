"""
Repository ProjectMember — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.
Solo traducción de queries a objetos de dominio.

Patrón lazy="raise" en las relaciones del modelo fuerza cargado
explícito con selectinload — evita N+1 silenciosos.
"""

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models.project_member import ProjectMember


class ProjectMemberRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Queries individuales ──────────────────────────────────────────────────

    def get_by_id(self, member_id: int) -> ProjectMember | None:
        """Carga un member por id (sin eager load de relaciones)."""
        return self.db.get(ProjectMember, member_id)

    def get_by_project_user(
        self, project_id: int, user_id: int
    ) -> ProjectMember | None:
        """
        Busca el row de membresía para (project_id, user_id).
        Usado por require_project_member / require_project_owner deps.
        """
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.user_id == user_id)
        )
        return self.db.execute(stmt).scalars().first()

    def get_owner(self, project_id: int) -> ProjectMember | None:
        """Devuelve el member con role='owner' del proyecto."""
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .where(ProjectMember.role == "owner")
        )
        return self.db.execute(stmt).scalars().first()

    def exists(self, project_id: int, user_id: int) -> bool:
        """True si el user ya es member (o owner) del proyecto."""
        return self.get_by_project_user(project_id, user_id) is not None

    # ── Listas ────────────────────────────────────────────────────────────────

    def list_for_project(self, project_id: int) -> list[ProjectMember]:
        """
        Todos los members de un proyecto, con eager load del user.
        Ordenados por joined_at ASC (owner primero por ser el más antiguo).
        """
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .options(selectinload(ProjectMember.user))
            .order_by(ProjectMember.joined_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_for_user(self, user_id: int) -> list[ProjectMember]:
        """
        Todos los proyectos donde el user es member o owner.
        Con eager load del project para evitar N+1 al iterar la lista.
        """
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.user_id == user_id)
            .options(selectinload(ProjectMember.project))
            .order_by(ProjectMember.joined_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Conteos ───────────────────────────────────────────────────────────────

    def count_for_project(self, project_id: int) -> int:
        """Cantidad total de members (incluye owner). Usado para el cap de 20."""
        stmt = (
            select(func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.project_id == project_id)
        )
        return self.db.execute(stmt).scalar_one()

    # ── Escrituras ────────────────────────────────────────────────────────────

    def create(
        self,
        project_id: int,
        user_id: int,
        role: str,
        invited_by_user_id: int,
    ) -> ProjectMember:
        """
        Inserta un nuevo member. Usa flush (sin commit) para que la capa
        de servicio controle la transacción completa.
        """
        member = ProjectMember(
            project_id=project_id,
            user_id=user_id,
            role=role,
            invited_by_user_id=invited_by_user_id,
        )
        self.db.add(member)
        self.db.flush()
        return member

    def delete(self, member: ProjectMember) -> None:
        """
        Elimina el member. Flush sin commit — el servicio hace commit.
        Úsalo para kick o para que un member abandone el proyecto.
        """
        self.db.delete(member)
        self.db.flush()

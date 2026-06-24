"""
Repository ProjectInvitation — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.

Nota sobre lazy expiry (ADR-7):
  list_pending_for_user filtra expires_at > NOW() a nivel DB — NO marca
  las expiradas como efecto secundario. La escritura (mark_expired) solo
  ocurre cuando el user intenta aceptar/rechazar una invitación ya vencida,
  desde la capa de servicio. Esto evita write amplification bajo el polling de 30s.
"""

from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models.project_invitation import ProjectInvitation


class ProjectInvitationRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Queries individuales ──────────────────────────────────────────────────

    def get_by_id(self, invitation_id: int) -> ProjectInvitation | None:
        """Carga una invitación por id (sin eager load)."""
        return self.db.get(ProjectInvitation, invitation_id)

    def get_pending(
        self, project_id: int, invited_user_id: int
    ) -> ProjectInvitation | None:
        """
        Busca una invitación pendiente activa para (project, user).
        Usado para evitar invitaciones duplicadas (antes del UNIQUE index).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(ProjectInvitation)
            .where(ProjectInvitation.project_id == project_id)
            .where(ProjectInvitation.invited_user_id == invited_user_id)
            .where(ProjectInvitation.status == "pending")
            .where(ProjectInvitation.expires_at > now)
        )
        return self.db.execute(stmt).scalars().first()

    def has_pending(self, project_id: int, invited_user_id: int) -> bool:
        """True si existe una invitación pendiente activa para (project, user)."""
        return self.get_pending(project_id, invited_user_id) is not None

    # ── Listas ────────────────────────────────────────────────────────────────

    def list_pending_for_user(
        self, user_id: int, filter_expired: bool = True
    ) -> list[ProjectInvitation]:
        """
        Invitaciones pendientes del user, con eager load del project
        para evitar N+1 al renderizar la lista de invitaciones.

        filter_expired=True (default): solo devuelve las que aún no vencieron.
        Esto es read-only — NO marca como expired. (ADR-7 / Issue 3)
        """
        stmt = (
            select(ProjectInvitation)
            .where(ProjectInvitation.invited_user_id == user_id)
            .where(ProjectInvitation.status == "pending")
            .options(selectinload(ProjectInvitation.project))
            .order_by(ProjectInvitation.created_at.desc())
        )
        if filter_expired:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(ProjectInvitation.expires_at > now)
        return list(self.db.execute(stmt).scalars().all())

    def count_pending_for_user(self, user_id: int) -> int:
        """
        Cantidad de invitaciones pendientes del user (no vencidas).
        Usado para el badge en el header (polling 30s).
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(func.count())
            .select_from(ProjectInvitation)
            .where(ProjectInvitation.invited_user_id == user_id)
            .where(ProjectInvitation.status == "pending")
            .where(ProjectInvitation.expires_at > now)
        )
        return self.db.execute(stmt).scalar_one()

    def list_for_project(self, project_id: int) -> list[ProjectInvitation]:
        """
        Todas las invitaciones del proyecto (todas status), visible por el owner.
        Con eager load del invited_user para el panel de gestión.
        """
        stmt = (
            select(ProjectInvitation)
            .where(ProjectInvitation.project_id == project_id)
            .options(selectinload(ProjectInvitation.invited_user))
            .order_by(ProjectInvitation.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Escrituras ────────────────────────────────────────────────────────────

    def create(
        self,
        project_id: int,
        invited_user_id: int,
        invited_by_user_id: int,
        expires_at: datetime,
    ) -> ProjectInvitation:
        """Crea una nueva invitación en estado 'pending'."""
        inv = ProjectInvitation(
            project_id=project_id,
            invited_user_id=invited_user_id,
            invited_by_user_id=invited_by_user_id,
            status="pending",
            expires_at=expires_at,
        )
        self.db.add(inv)
        self.db.flush()
        return inv

    def update_status(
        self,
        invitation: ProjectInvitation,
        new_status: str,
    ) -> ProjectInvitation:
        """
        Actualiza el status y marca responded_at si corresponde.
        La validación de transición válida es responsabilidad del servicio.
        """
        invitation.status = new_status
        if new_status in ("accepted", "rejected", "revoked", "expired"):
            invitation.responded_at = datetime.now(timezone.utc)
        self.db.flush()
        return invitation

    def mark_expired(self, invitation: ProjectInvitation) -> ProjectInvitation:
        """
        Marca la invitación como expirada (lazy expiry desde el servicio).
        Solo se llama cuando alguien intenta aceptar/rechazar y ya venció.
        """
        return self.update_status(invitation, "expired")

    def mark_accepted(self, invitation: ProjectInvitation) -> ProjectInvitation:
        return self.update_status(invitation, "accepted")

    def mark_rejected(self, invitation: ProjectInvitation) -> ProjectInvitation:
        return self.update_status(invitation, "rejected")

    def mark_revoked(self, invitation: ProjectInvitation) -> ProjectInvitation:
        return self.update_status(invitation, "revoked")

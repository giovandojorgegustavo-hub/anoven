"""
ProjectMemberService — lógica de negocio para membresía en proyectos compartidos.

Responsabilidades:
  - Invitar, aceptar, rechazar invitaciones
  - Kick de members por el owner
  - Leave del proyecto por un member
  - Listado de members e invitaciones pendientes

Invariante A1.3 STRICT: NUNCA importar fastapi.
Todas las excepciones son de dominio puro — la capa de rutas las traduce a HTTP.

Alistair Cockburn — Hexagonal Architecture, 2005: esta es la lógica de negocio
(policy); rutas y repositorios son adapters.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.project_invitation import ProjectInvitation
from app.models.project_member import ProjectMember
from app.repositories.project_invitation_repo import ProjectInvitationRepository
from app.repositories.project_member_repo import ProjectMemberRepository

if TYPE_CHECKING:
    pass


# ============================================================
# Excepciones de dominio
# ============================================================

class SharedProjectsError(Exception):
    """Base de todas las excepciones de proyectos compartidos."""


class ProjectNotShareableError(SharedProjectsError):
    """No se pueden invitar miembros a un proyecto default."""


class UserNotFoundError(SharedProjectsError):
    """El email invitado no existe en Anoven."""


class AlreadyMemberError(SharedProjectsError):
    """El usuario ya es miembro del proyecto."""


class InvitationAlreadyPendingError(SharedProjectsError):
    """Ya existe una invitación pendiente para este usuario en este proyecto."""


class MaxMembersReachedError(SharedProjectsError):
    """El proyecto ya alcanzó el límite de 20 miembros."""


class InvitationNotFoundError(SharedProjectsError):
    """La invitación no existe."""


class InvitationNotYoursError(SharedProjectsError):
    """Esta invitación no te pertenece."""


class InvitationExpiredError(SharedProjectsError):
    """La invitación ya venció."""


class InvitationNotPendingError(SharedProjectsError):
    """La invitación no está en estado pendiente."""
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"La invitación tiene estado '{status}'.")


class OwnerCannotLeaveError(SharedProjectsError):
    """El owner no puede abandonar el proyecto; primero transferir o eliminar."""


class NotOwnerError(SharedProjectsError):
    """No sos el owner del proyecto."""


class TargetNotMemberError(SharedProjectsError):
    """El usuario target no es miembro del proyecto."""


class CannotKickSelfError(SharedProjectsError):
    """El owner no puede kickearse a sí mismo."""


class NotMemberError(SharedProjectsError):
    """No sos miembro del proyecto."""


MAX_MEMBERS = 20
DEFAULT_INVITATION_DAYS = 7


class ProjectMemberService:
    """
    Servicio de dominio para membresía en proyectos compartidos.

    Recibe Session (SQLAlchemy) directamente: los repos se construyen
    internamente. Esto simplifica la inyección en rutas FastAPI que
    ya tienen acceso a la session via Depends(get_db).
    """

    def __init__(self, db: Session):
        self.db = db
        self.member_repo = ProjectMemberRepository(db)
        self.invitation_repo = ProjectInvitationRepository(db)

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _get_project(self, project_id: int):
        from app.repositories.project_repo import ProjectRepository
        repo = ProjectRepository(self.db)
        return repo.get_by_id(project_id)

    def _get_user_by_email(self, email: str):
        from app.repositories.user_repo import UserRepository
        repo = UserRepository(self.db)
        return repo.get_by_email(email)

    def _assert_is_owner(self, project_id: int, user_id: int) -> ProjectMember:
        """Valida que user_id es owner del proyecto. Lanza NotOwnerError si no."""
        member = self.member_repo.get_by_project_user(project_id, user_id)
        if member is None or member.role != "owner":
            raise NotOwnerError(
                "Solo el owner puede realizar esta acción."
            )
        return member

    # ── Invitar ───────────────────────────────────────────────────────────────

    def invite_user(
        self,
        project_id: int,
        invited_user_email: str,
        invited_by_user_id: int,
        days_to_expire: int = DEFAULT_INVITATION_DAYS,
    ) -> ProjectInvitation:
        """
        Invita a un usuario (por email) al proyecto.

        Validaciones (en orden):
          1. Proyecto no es default (is_default=True → ProjectNotShareableError)
          2. Email existe en Anoven (UserNotFoundError si no)
          3. No es ya miembro (AlreadyMemberError)
          4. No hay invitación pendiente (InvitationAlreadyPendingError)
          5. Proyecto < 20 miembros (MaxMembersReachedError)
          6. Crear invitación con expires_at = NOW() + days_to_expire
        """
        # 1. Validar proyecto no es default
        project = self._get_project(project_id)
        if project is not None and getattr(project, "is_default", False):
            raise ProjectNotShareableError(
                "No podés invitar personas a tu proyecto personal por defecto."
            )

        # 2. Buscar usuario invitado por email
        invited_user = self._get_user_by_email(invited_user_email)
        if invited_user is None:
            raise UserNotFoundError(
                f"No encontramos a '{invited_user_email}' en Anoven."
            )

        # 3. Verificar que no sea ya miembro
        if self.member_repo.exists(project_id, invited_user.id):
            raise AlreadyMemberError(
                "Ese usuario ya es miembro del proyecto."
            )

        # 4. Verificar que no haya invitación pendiente
        if self.invitation_repo.has_pending(project_id, invited_user.id):
            raise InvitationAlreadyPendingError(
                "Ya hay una invitación pendiente para ese usuario."
            )

        # 5. Verificar cap de members
        current_count = self.member_repo.count_for_project(project_id)
        if current_count >= MAX_MEMBERS:
            raise MaxMembersReachedError(
                f"El proyecto ya tiene {MAX_MEMBERS} miembros. No podés agregar más."
            )

        # 6. Crear invitación
        expires_at = datetime.now(timezone.utc) + timedelta(days=days_to_expire)
        invitation = self.invitation_repo.create(
            project_id=project_id,
            invited_user_id=invited_user.id,
            invited_by_user_id=invited_by_user_id,
            expires_at=expires_at,
        )
        self.db.commit()
        return invitation

    # ── Aceptar invitación ────────────────────────────────────────────────────

    def accept_invitation(
        self, invitation_id: int, current_user_id: int
    ) -> ProjectMember:
        """
        Acepta la invitación y crea el ProjectMember.

        Validaciones:
          1. Invitación existe (InvitationNotFoundError)
          2. Invitación es para current_user (InvitationNotYoursError)
          3. Lazy expire: si vencida, marcar 'expired' + InvitationExpiredError
          4. Status debe ser 'pending' (InvitationNotPendingError)
          5. Cap re-check (MaxMembersReachedError)
          6. Crear ProjectMember + marcar invitación como 'accepted'
        """
        inv = self.invitation_repo.get_by_id(invitation_id)
        if inv is None:
            raise InvitationNotFoundError("La invitación no existe.")

        if inv.invited_user_id != current_user_id:
            raise InvitationNotYoursError(
                "Esta invitación no te pertenece."
            )

        # Lazy expire check
        now = datetime.now(timezone.utc)
        inv_expires = inv.expires_at
        # Normalizar timezone para comparación
        if inv_expires.tzinfo is None:
            inv_expires = inv_expires.replace(tzinfo=timezone.utc)
        if inv_expires <= now:
            self.invitation_repo.mark_expired(inv)
            self.db.commit()
            raise InvitationExpiredError(
                "Esta invitación venció. Pedile al owner que te invite de nuevo."
            )

        if inv.status != "pending":
            raise InvitationNotPendingError(inv.status)

        # Cap re-check al momento de aceptar
        current_count = self.member_repo.count_for_project(inv.project_id)
        if current_count >= MAX_MEMBERS:
            raise MaxMembersReachedError(
                f"El proyecto ya tiene {MAX_MEMBERS} miembros. No podés unirte."
            )

        # Transacción: crear member + marcar invitación como accepted
        new_member = self.member_repo.create(
            project_id=inv.project_id,
            user_id=current_user_id,
            role="member",
            invited_by_user_id=inv.invited_by_user_id,
        )
        self.invitation_repo.mark_accepted(inv)
        self.db.commit()
        return new_member

    # ── Rechazar invitación ───────────────────────────────────────────────────

    def reject_invitation(
        self, invitation_id: int, current_user_id: int
    ) -> ProjectInvitation:
        """
        Rechaza la invitación. Validaciones similares a accept (sin crear member).
        """
        inv = self.invitation_repo.get_by_id(invitation_id)
        if inv is None:
            raise InvitationNotFoundError("La invitación no existe.")

        if inv.invited_user_id != current_user_id:
            raise InvitationNotYoursError(
                "Esta invitación no te pertenece."
            )

        # Lazy expire
        now = datetime.now(timezone.utc)
        inv_expires = inv.expires_at
        if inv_expires.tzinfo is None:
            inv_expires = inv_expires.replace(tzinfo=timezone.utc)
        if inv_expires <= now:
            self.invitation_repo.mark_expired(inv)
            self.db.commit()
            raise InvitationExpiredError(
                "Esta invitación ya venció."
            )

        if inv.status != "pending":
            raise InvitationNotPendingError(inv.status)

        self.invitation_repo.mark_rejected(inv)
        self.db.commit()
        return inv

    # ── Abandonar proyecto ────────────────────────────────────────────────────

    def leave_project(self, project_id: int, current_user_id: int) -> None:
        """
        El member abandona el proyecto.
        El owner no puede abandonar (usar delete_project en su lugar).
        """
        member = self.member_repo.get_by_project_user(project_id, current_user_id)
        if member is None:
            raise NotMemberError("No sos miembro de este proyecto.")

        if member.role == "owner":
            raise OwnerCannotLeaveError(
                "Como owner, no podés abandonar el proyecto. "
                "Podés eliminarlo si ya no lo necesitás."
            )

        self.member_repo.delete(member)
        self.db.commit()

    # ── Kick member ───────────────────────────────────────────────────────────

    def kick_member(
        self, project_id: int, target_user_id: int, owner_user_id: int
    ) -> None:
        """
        El owner expulsa a un member del proyecto.
        No puede kickear al owner (ni a sí mismo).
        """
        self._assert_is_owner(project_id, owner_user_id)

        if target_user_id == owner_user_id:
            raise CannotKickSelfError(
                "No podés expulsarte a vos mismo del proyecto."
            )

        target = self.member_repo.get_by_project_user(project_id, target_user_id)
        if target is None:
            raise TargetNotMemberError(
                "El usuario a expulsar no es miembro del proyecto."
            )

        if target.role == "owner":
            raise NotOwnerError(
                "No podés expulsar al owner del proyecto."
            )

        self.member_repo.delete(target)
        self.db.commit()

    # ── Listados ──────────────────────────────────────────────────────────────

    def list_members(
        self, project_id: int, requesting_user_id: int
    ) -> list[ProjectMember]:
        """
        Lista los miembros del proyecto.
        Solo accesible para miembros o el owner.
        """
        if not self.member_repo.exists(project_id, requesting_user_id):
            raise NotMemberError(
                "Debés ser miembro del proyecto para ver su lista de integrantes."
            )
        return self.member_repo.list_for_project(project_id)

    def list_my_invitations(self, user_id: int) -> list[ProjectInvitation]:
        """Invitaciones pendientes no vencidas del usuario."""
        return self.invitation_repo.list_pending_for_user(user_id)

    def count_my_pending_invitations(self, user_id: int) -> int:
        """Cantidad de invitaciones pendientes (para el badge del header)."""
        return self.invitation_repo.count_pending_for_user(user_id)

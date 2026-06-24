"""
SupportTicketService — lógica de negocio para el dominio de support tickets.

Principio: Robert C. Martin — Clean Architecture, 2017.
  - NUNCA imports de fastapi.* (invariante A1.3)
  - NUNCA manipulación directa de Session (delega a repos)
  - Lanza excepciones de dominio; los routes las traducen a HTTPException

Alistair Cockburn — Hexagonal Architecture, 2005:
  - TicketStorageAdapter es el puerto de almacenamiento; el servicio no
    conoce el filesystem directamente.

Eric Evans — DDD, 2003:
  - SupportTicket es aggregate root; las transiciones de estado se hacen
    solo a través de ticket.transition_to() (invariante de dominio).
"""

from datetime import datetime, timezone

from app.models.support_ticket import (
    SupportTicket,
    InvalidStateTransition,
    ALLOWED_TYPES,
    ALLOWED_STATUSES,
)
from app.models.ticket_attachment import (
    TicketAttachment,
    ALLOWED_MIMES,
    MAX_ATTACHMENT_SIZE_BYTES,
    MAX_ATTACHMENTS_PER_TICKET,
)
from app.repositories.support_ticket_repo import SupportTicketRepository
from app.repositories.ticket_attachment_repo import TicketAttachmentRepository
from app.services.ticket_storage_adapter import (
    TicketStorageAdapter,
    AttachmentMimeNotAllowed,
    AttachmentStorageError,
)
from app.schemas.support_ticket import TicketCreate, TicketRespondPayload


# ── Excepciones de dominio ────────────────────────────────────────────────────

class SupportTicketError(Exception):
    """Base para todas las excepciones del dominio de tickets."""
    pass


class TicketNotFoundError(SupportTicketError):
    """El ticket no existe."""
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} no encontrado")


class TicketForbiddenError(SupportTicketError):
    """El usuario no tiene permiso para acceder a este ticket."""
    def __init__(self, ticket_id: int, user_id: int):
        self.ticket_id = ticket_id
        self.user_id = user_id
        super().__init__(f"Sin acceso al ticket {ticket_id}")


class RateLimitExceededError(SupportTicketError):
    """El usuario creó demasiados tickets en el último período."""
    pass


class AttachmentValidationError(SupportTicketError):
    """El archivo no pasa la validación (MIME, tamaño, cantidad)."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class AttachmentNotFoundError(SupportTicketError):
    """El attachment no existe."""
    pass


class InvalidStatusTransitionError(SupportTicketError):
    """Transición de estado no permitida."""
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Transición no permitida: {from_status} → {to_status}")


class MissingResponseForCloseError(SupportTicketError):
    """Se intentó cerrar un ticket sin admin_response."""
    pass


# ── Service ───────────────────────────────────────────────────────────────────

RATE_LIMIT_MAX = 5
RATE_LIMIT_HOURS = 1


class SupportTicketService:
    """
    Orquesta la creación, consulta y gestión de support tickets.
    NUNCA importa fastapi. Lanza excepciones de dominio.
    """

    def __init__(
        self,
        ticket_repo: SupportTicketRepository,
        attachment_repo: TicketAttachmentRepository,
        storage: TicketStorageAdapter,
    ):
        self._ticket_repo = ticket_repo
        self._attachment_repo = attachment_repo
        self._storage = storage

    # ── User: crear ticket ────────────────────────────────────────────────────

    def create_ticket(
        self,
        user_id: int,
        ticket_in: TicketCreate,
    ) -> SupportTicket:
        """
        Crea un nuevo ticket de soporte.

        Valida rate limit (5 tickets/hora por usuario).
        El ticket se crea sin attachments — se adjuntan en un segundo paso.

        Raises:
          RateLimitExceededError: si el usuario supera 5 tickets/hora
        """
        recent_count = self._ticket_repo.count_recent_for_user(
            user_id, hours=RATE_LIMIT_HOURS
        )
        if recent_count >= RATE_LIMIT_MAX:
            raise RateLimitExceededError(
                f"Superaste el límite de {RATE_LIMIT_MAX} tickets por hora. "
                "Intenta más tarde."
            )

        ticket = self._ticket_repo.create(
            user_id=user_id,
            ticket_type=ticket_in.ticket_type,
            title=ticket_in.title,
            description=ticket_in.description,
            conversation_id=ticket_in.conversation_id,
            mentor_id=ticket_in.mentor_id,
            status="open",
        )
        return ticket

    # ── User: adjuntar archivo ────────────────────────────────────────────────

    def add_attachment_to_ticket(
        self,
        user_id: int,
        ticket_id: int,
        file_data: bytes,
        original_filename: str,
        mime_type: str,
    ) -> TicketAttachment:
        """
        Valida y adjunta un archivo a un ticket.

        Validates:
          - El usuario es dueño del ticket
          - MIME en lista blanca + magic bytes
          - Tamaño ≤ 5 MB
          - No supera el máximo de 3 attachments por ticket

        Raises:
          TicketNotFoundError, TicketForbiddenError,
          AttachmentValidationError, AttachmentStorageError
        """
        # ownership check
        ticket = self._ticket_repo.get_for_user(user_id, ticket_id)
        if ticket is None:
            # Determinar si el ticket existe pero no es del user
            raw = self._ticket_repo.get_by_id(ticket_id)
            if raw is None:
                raise TicketNotFoundError(ticket_id)
            raise TicketForbiddenError(ticket_id, user_id)

        # count check
        current_count = self._attachment_repo.count_for_ticket(ticket_id)
        if current_count >= MAX_ATTACHMENTS_PER_TICKET:
            raise AttachmentValidationError(
                code="max_attachments_exceeded",
                message="Máximo 3 capturas por ticket.",
            )

        # size check
        if len(file_data) > MAX_ATTACHMENT_SIZE_BYTES:
            raise AttachmentValidationError(
                code="file_too_large",
                message="La imagen supera los 5 MB. Intenta con una más liviana.",
            )

        if len(file_data) == 0:
            raise AttachmentValidationError(
                code="empty_file",
                message="El archivo está vacío.",
            )

        # MIME + magic bytes validation (done inside storage adapter write)
        try:
            rel_path, safe_filename = self._storage.write(
                ticket_id=ticket_id,
                data=file_data,
                declared_mime=mime_type,
                original_name=original_filename,
            )
        except AttachmentMimeNotAllowed:
            raise AttachmentValidationError(
                code="unsupported_media_type",
                message="Solo aceptamos imágenes PNG, JPEG o WebP.",
            )
        except AttachmentStorageError:
            raise  # re-raise — route maps to 500

        attachment = self._attachment_repo.create(
            ticket_id=ticket_id,
            user_id=user_id,
            file_path=rel_path,
            original_name=original_filename[:255],
            mime_type=mime_type,
            size_bytes=len(file_data),
        )
        return attachment

    # ── User: leer tickets ────────────────────────────────────────────────────

    def get_user_ticket(self, user_id: int, ticket_id: int) -> SupportTicket:
        """
        Devuelve el ticket del usuario.

        Raises:
          TicketForbiddenError: si el ticket existe pero no es del usuario (403, NO 404)
          TicketNotFoundError: si el ticket no existe
        """
        ticket = self._ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        if ticket.user_id != user_id:
            # 403 MANDATORY — nunca 404 que leakea existencia
            raise TicketForbiddenError(ticket_id, user_id)
        return ticket

    def list_user_tickets(
        self,
        user_id: int,
        status: str | None = None,
    ) -> list[SupportTicket]:
        """Lista los tickets del usuario, más reciente primero."""
        return self._ticket_repo.list_for_user(user_id, status=status)

    def read_attachment(
        self,
        attachment_id: int,
        requester_user_id: int,
        is_admin: bool,
    ) -> tuple[bytes, str, str]:
        """
        Devuelve (bytes, mime_type, original_name) del attachment.
        Solo owner del ticket o admin pueden acceder.

        Raises:
          AttachmentNotFoundError, TicketForbiddenError
        """
        att = self._attachment_repo.get_by_id(attachment_id)
        if att is None:
            raise AttachmentNotFoundError(f"Attachment {attachment_id} no encontrado")

        if not is_admin and att.user_id != requester_user_id:
            raise TicketForbiddenError(att.ticket_id, requester_user_id)

        data = self._storage.read(att.file_path)
        return data, att.mime_type, att.original_name

    # ── Admin: gestión ────────────────────────────────────────────────────────

    def admin_list_tickets(
        self,
        status: str | None = None,
        ticket_type: str | None = None,
    ) -> list[SupportTicket]:
        """Lista todos los tickets con filtros opcionales."""
        return self._ticket_repo.list_all(status=status, ticket_type=ticket_type)

    def admin_get_ticket(self, ticket_id: int) -> SupportTicket:
        """
        Devuelve cualquier ticket por id (acceso admin sin ownership check).

        Raises:
          TicketNotFoundError
        """
        ticket = self._ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def admin_update_ticket(
        self,
        ticket_id: int,
        update_in: TicketRespondPayload,
        admin_user_id: int,
    ) -> SupportTicket:
        """
        El admin responde y opcionalmente cambia el estado del ticket.

        Si new_status es None, solo guarda admin_response sin cambiar estado.
        Si new_status es 'closed', requiere admin_response (invariante de dominio).

        Raises:
          TicketNotFoundError, InvalidStatusTransitionError, MissingResponseForCloseError
        """
        ticket = self._ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)

        # Guardar respuesta siempre
        ticket.admin_response = update_in.admin_response
        ticket.admin_user_id = admin_user_id
        if ticket.responded_at is None:
            ticket.responded_at = datetime.now(timezone.utc)

        # Transición de estado solo si se especificó
        if update_in.new_status is not None and update_in.new_status != ticket.status:
            if update_in.new_status == "closed" and not ticket.admin_response:
                raise MissingResponseForCloseError(
                    "Debes escribir una respuesta antes de cerrar el ticket."
                )
            try:
                ticket.transition_to(update_in.new_status)
            except InvalidStateTransition as e:
                raise InvalidStatusTransitionError(e.from_status, e.to_status) from e

        self._ticket_repo.save(ticket)
        return ticket

    def admin_close_ticket(
        self,
        ticket_id: int,
        admin_user_id: int,
    ) -> SupportTicket:
        """
        Cierra un ticket. Requiere que ya tenga admin_response.

        Raises:
          TicketNotFoundError, MissingResponseForCloseError, InvalidStatusTransitionError
        """
        ticket = self._ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)

        if not ticket.admin_response:
            raise MissingResponseForCloseError(
                "Debes escribir una respuesta antes de cerrar el ticket."
            )

        try:
            ticket.transition_to("closed")
        except InvalidStateTransition as e:
            raise InvalidStatusTransitionError(e.from_status, e.to_status) from e

        ticket.admin_user_id = admin_user_id
        if ticket.responded_at is None:
            ticket.responded_at = datetime.now(timezone.utc)

        self._ticket_repo.save(ticket)
        return ticket

    def admin_reopen_ticket(
        self,
        ticket_id: int,
        admin_user_id: int,
    ) -> SupportTicket:
        """
        Reabre un ticket cerrado (closed → open).

        Raises:
          TicketNotFoundError, InvalidStatusTransitionError
        """
        ticket = self._ticket_repo.get_by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)

        try:
            ticket.transition_to("open")
        except InvalidStateTransition as e:
            raise InvalidStatusTransitionError(e.from_status, e.to_status) from e

        self._ticket_repo.save(ticket)
        return ticket

    def admin_unread_count(self) -> int:
        """Conteo de tickets open — para el badge del panel admin."""
        return self._ticket_repo.count_unread_for_admin()

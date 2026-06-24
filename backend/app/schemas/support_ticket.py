"""
Schemas Pydantic para el dominio support_tickets.

Copy en tuteo limeño culto (sin voseo). Audit gate:
  rg "vos|vení|tenés|querés|ponés|hacés|sos\b" → 0 hits esperados.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Attachment ────────────────────────────────────────────────────────────────

class AttachmentRead(BaseModel):
    id: int
    original_name: str
    mime_type: str
    size_bytes: int
    # La URL se construye en el route; el schema recibe el string ya formado.
    file_url: str

    model_config = {"from_attributes": True}


# ── Ticket — input ────────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    ticket_type: str = Field(
        ...,
        description="Tipo de ticket: bug, mejora, pregunta, otro",
        pattern="^(bug|mejora|pregunta|otro)$",
    )
    title: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Título del ticket (3–200 caracteres)",
    )
    description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Descripción detallada del problema o sugerencia",
    )
    conversation_id: Optional[int] = Field(None, description="ID de la conversación relacionada (opcional)")
    mentor_id: Optional[int] = Field(None, description="ID del mentor relacionado (opcional)")


# ── Ticket — output (user view) ───────────────────────────────────────────────

class TicketRead(BaseModel):
    """Vista resumida para el listado del usuario."""
    id: int
    ticket_type: str
    title: str
    description: str
    status: str
    admin_response: Optional[str]
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime]
    closed_at: Optional[datetime]
    conversation_id: Optional[int]
    mentor_id: Optional[int]
    attachments: list[AttachmentRead] = []

    model_config = {"from_attributes": True}


class TicketReadDetail(TicketRead):
    """Vista detallada — incluye lo mismo que TicketRead, extendible en v2."""
    pass


# ── Ticket — output (admin view) ─────────────────────────────────────────────

class TicketReadAdmin(BaseModel):
    """Vista admin: incluye user_id y campos de respuesta."""
    id: int
    user_id: int
    ticket_type: str
    title: str
    description: str
    status: str
    admin_response: Optional[str]
    admin_user_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    responded_at: Optional[datetime]
    closed_at: Optional[datetime]
    conversation_id: Optional[int]
    mentor_id: Optional[int]
    attachments: list[AttachmentRead] = []

    model_config = {"from_attributes": True}


class TicketReadDetailAdmin(TicketReadAdmin):
    """Vista detallada admin — misma info que TicketReadAdmin por ahora, extendible en v2."""
    pass


# ── Admin respond payload ─────────────────────────────────────────────────────

class TicketRespondPayload(BaseModel):
    admin_response: str = Field(
        ...,
        min_length=1,
        description="Respuesta del equipo Anoven al usuario",
    )
    new_status: Optional[str] = Field(
        None,
        description="Nuevo estado del ticket (in_progress o closed). Si no se envía, el estado no cambia.",
        pattern="^(open|in_progress|closed)$",
    )


# ── Unread count ──────────────────────────────────────────────────────────────

class UnreadCountRead(BaseModel):
    count: int

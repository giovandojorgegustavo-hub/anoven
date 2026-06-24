"""
Schemas Pydantic para Conversation y Message (chat con mentor).
"""

from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.mentor import MentorResponse


class ConversationCreate(BaseModel):
    """Body del POST /conversations — crear o resumir."""
    mentor_id: int
    force_new: bool = False


class ConversationResponse(BaseModel):
    """Lo que el backend devuelve al frontend cuando consulta una conversación.
    Incluye el mentor nested para que el frontend no tenga que hacer 2 fetches."""

    id: int
    mentor_id: int
    use_case_id: int | None = None
    title: str | None
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None
    is_focused: bool = False
    unread: bool = False
    mentor: MentorResponse
    message_count: int = 0
    project_name: str | None = None
    use_case_name: str | None = None
    # Shared project indicator — True when project has >1 member.
    # Used by frontend sidebar to show "Proyecto compartido" tooltip.
    is_shared_project: bool = False

    model_config = {"from_attributes": True}


class FocusUpdate(BaseModel):
    is_focused: bool


class MessageResponse(BaseModel):
    """Un mensaje del chat de mentor.

    author_user_id: id del user que escribio este mensaje (NULL = turno del mentor).
    author_email_redacted: local-part del email del autor (antes del @), listo para mostrar.
      Solo presente cuando el mensaje pertenece a otro miembro del proyecto compartido.
      NULL cuando es el propio user, cuando es turno del mentor, o cuando la conv es privada.
    """

    id: int
    role: str
    content: str
    created_at: datetime
    attachment_urls: list[str] = []
    # Shared-project authorship fields (anoven-shared-projects batch 6)
    author_user_id: int | None = None
    author_email_redacted: str | None = None

    model_config = {"from_attributes": True}


class SendChatMessageRequest(BaseModel):
    """Body del POST /conversations/{id}/messages."""

    content: str = Field(min_length=1, max_length=8000)
    # IDs de Attachments ya subidos via POST /attachments. Se mandan junto
    # con el texto y el backend los incluye en el contenido multimodal de
    # la llamada a Anthropic.
    attachment_ids: list[int] = Field(default_factory=list)

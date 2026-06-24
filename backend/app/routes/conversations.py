"""
Endpoints de conversaciones (chat con mentor).

Sesión 3.1:
  POST /conversations           — crea o resume última con un mentor
  GET  /conversations/{id}      — carga una conversación específica

Sesión 3.2 agregará:
  GET  /conversations/{id}/messages
  POST /conversations/{id}/messages (SSE streaming)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.conversation import Conversation
from app.models.user import User
from app.repositories.mentor_repo import MentorRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.project_repo import ProjectRepository, UseCaseRepository
from app.repositories.project_member_repo import ProjectMemberRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    FocusUpdate,
    MessageResponse,
    SendChatMessageRequest,
)
from app.schemas.mentor import MentorResponse
from app.services.conversation_service import (
    ConversationNotFound,
    ConversationService,
    MentorNotAccessible,
    MentorUnavailable,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


def _build_response(conv: Conversation, db: Session) -> ConversationResponse:
    """Nested response: conversation + mentor + message_count + project context."""
    mentor_repo = MentorRepository(db)
    msg_repo = MessageRepository(db)
    project_repo = ProjectRepository(db)
    uc_repo = UseCaseRepository(db)

    mentor = mentor_repo.get_by_id(conv.mentor_id)
    if mentor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mentor {conv.mentor_id} no encontrado.",
        )

    project_name = None
    use_case_name = None
    if conv.use_case_id is not None:
        uc = uc_repo.get_by_id(conv.use_case_id)
        if uc is not None:
            use_case_name = uc.name
            project = project_repo.get_by_id(uc.project_id)
            if project is not None:
                project_name = project.name

    # Unread: si nunca lo viste, o si el último mensaje es posterior a tu última visita.
    msg_count = len(msg_repo.list_for_conversation(conv.id))
    if msg_count == 0:
        unread = False
    elif conv.last_seen_at is None:
        unread = True
    else:
        unread = conv.updated_at > conv.last_seen_at

    # Shared project flag: True when project has >1 member (owner + at least 1 invited member).
    is_shared_project = False
    if conv.use_case_id is not None:
        uc_for_shared = uc_repo.get_by_id(conv.use_case_id)
        if uc_for_shared is not None:
            pm_repo = ProjectMemberRepository(db)
            is_shared_project = pm_repo.count_for_project(uc_for_shared.project_id) > 1

    return ConversationResponse(
        id=conv.id,
        mentor_id=conv.mentor_id,
        use_case_id=conv.use_case_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        last_seen_at=conv.last_seen_at,
        is_focused=conv.is_focused,
        unread=unread,
        mentor=MentorResponse.model_validate(mentor),
        message_count=msg_count,
        project_name=project_name,
        use_case_name=use_case_name,
        is_shared_project=is_shared_project,
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_or_resume(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Crea o resume conversación con un mentor en el active project del user.
    """
    service = ConversationService(db)
    try:
        conv = service.start_or_resume(
            user=current_user,
            mentor_id=payload.mentor_id,
            force_new=payload.force_new,
        )
    except MentorNotAccessible as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    return _build_response(conv, db)


@router.get(
    "",
    response_model=list[ConversationResponse],
)
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lista las conversaciones del user EN SU PROJECT ACTIVO. Si está en el
    default project, también incluye conversaciones huérfanas (sin use_case).
    Para el sidebar de chat.
    """
    service = ConversationService(db)
    convs = service.list_for_user(current_user)
    return [_build_response(c, db) for c in convs]


@router.get(
    "/{conv_id}",
    response_model=ConversationResponse,
)
def get_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Carga una conversación si pertenece al user."""
    service = ConversationService(db)
    try:
        conv = service.get_for_user(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    return _build_response(conv, db)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


@router.patch(
    "/{conv_id}",
    response_model=ConversationResponse,
)
def rename_conversation(
    conv_id: int,
    payload: "ConversationUpdate",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    try:
        conv = service.rename_title(conv_id, current_user.id, payload.title)
    except ConversationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return _build_response(conv, db)


@router.post("/{conv_id}/seen", response_model=ConversationResponse)
def mark_seen(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marca la conversación como vista (resetea unread)."""
    service = ConversationService(db)
    try:
        conv = service.get_for_user(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    service.repo.mark_seen(conv)
    return _build_response(conv, db)


@router.patch("/{conv_id}/focus", response_model=ConversationResponse)
def toggle_focus(
    conv_id: int,
    payload: FocusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Toggle del flag is_focused."""
    service = ConversationService(db)
    try:
        conv = service.get_for_user(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    service.repo.toggle_focus(conv, payload.is_focused)
    return _build_response(conv, db)


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = ConversationService(db)
    try:
        service.delete_for_user(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return None


@router.get(
    "/{conv_id}/messages",
    response_model=list[MessageResponse],
)
def list_messages(
    conv_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los mensajes de una conversación en orden cronológico.

    Para proyectos compartidos, enriquece cada mensaje con author_email_redacted:
    el local-part del email del autor (solo para mensajes de OTROS miembros).
    """
    service = ConversationService(db)
    try:
        msgs = service.list_messages(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # Enrich messages with author_email_redacted for shared-project conversations.
    # Only fetch users when there are messages with a different author_user_id.
    other_author_ids = {
        m.author_user_id
        for m in msgs
        if m.author_user_id is not None and m.author_user_id != current_user.id
    }
    if other_author_ids:
        from app.models.user import User as UserModel
        users_by_id = {
            u.id: u
            for u in db.query(UserModel).filter(UserModel.id.in_(other_author_ids)).all()
        }
        enriched = []
        for m in msgs:
            email_redacted = None
            if (
                m.author_user_id is not None
                and m.author_user_id != current_user.id
                and m.author_user_id in users_by_id
            ):
                raw_email = users_by_id[m.author_user_id].email
                email_redacted = raw_email.split("@")[0] if "@" in raw_email else raw_email
            mr = MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                attachment_urls=getattr(m, "attachment_urls", []),
                author_user_id=m.author_user_id,
                author_email_redacted=email_redacted,
            )
            enriched.append(mr)
        return enriched

    # No other authors — return as MessageResponse with author_user_id only.
    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            attachment_urls=getattr(m, "attachment_urls", []),
            author_user_id=m.author_user_id,
        )
        for m in msgs
    ]


@router.post("/{conv_id}/messages")
def send_message(
    conv_id: int,
    payload: SendChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Envía un mensaje del user y devuelve la respuesta del mentor via SSE.

    Streaming protocol:
        data: {"text": "..."}\\n\\n
        ...
        data: [DONE]\\n\\n

    El frontend lee con `fetch + ReadableStream` (mismo patrón que el Entrevistador).

    anoven-shared-projects (R-arch-3):
    Después de cargar la conv, verifica que el user sigue siendo member del
    proyecto asociado. Previene acceso de usuarios expulsados de proyectos
    compartidos que aún tienen convs activas.
    """
    service = ConversationService(db)

    # Cargar conv primero para obtener project_id (R-arch-3 pre-check)
    try:
        conv_for_guard = service.get_for_user(conv_id, current_user.id)
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # R-arch-3: guard de membresía para proyectos compartidos.
    # Solo aplica si la conv tiene use_case asignado (proyecto no default).
    if conv_for_guard.use_case_id is not None:
        from app.repositories.project_repo import UseCaseRepository
        from app.repositories.project_member_repo import ProjectMemberRepository
        _uc_guard = UseCaseRepository(db).get_by_id(conv_for_guard.use_case_id)
        if _uc_guard is not None:
            _pm_guard = ProjectMemberRepository(db).get_by_project_user(
                _uc_guard.project_id, current_user.id
            )
            if _pm_guard is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No eres miembro de este proyecto.",
                )

    try:
        generator = service.send_user_message_and_stream(
            conv_id=conv_id,
            user_id=current_user.id,
            content=payload.content,
            attachment_ids=payload.attachment_ids,
        )
    except ConversationNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except MentorUnavailable as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

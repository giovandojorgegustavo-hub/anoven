"""
Endpoints del Entrevistador.

Sesión 2.1: POST /interviews/start
Sesión 2.2: GET /interviews/{id}/messages + POST /interviews/{id}/messages (SSE)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.interview import (
    EvaluationResponse,
    InterviewAttemptResponse,
    InterviewMessageResponse,
    SendMessageRequest,
)
from app.services.interview_service import (
    AlreadyPassed,
    AttemptClosed,
    AttemptNotFound,
    AttemptNotReadyForEvaluation,
    InterviewService,
)


router = APIRouter(prefix="/interviews", tags=["interviews"])


@router.post(
    "/start",
    response_model=InterviewAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_interview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inicia o resume un intento. Idempotente."""
    service = InterviewService(db)
    try:
        return service.start_or_resume(current_user)
    except AlreadyPassed as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get(
    "/{attempt_id}/messages",
    response_model=list[InterviewMessageResponse],
)
def list_messages(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los mensajes del intento en orden cronológico."""
    service = InterviewService(db)
    try:
        return service.list_messages(attempt_id, current_user.id)
    except AttemptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{attempt_id}/messages")
def send_message(
    attempt_id: int,
    payload: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Envía un mensaje del user y devuelve la respuesta del Entrevistador via SSE.

    Streaming protocol (Server-Sent Events):
        data: {"text": "Hola"}\\n\\n
        data: {"text": ", "}\\n\\n
        data: {"text": "contame..."}\\n\\n
        data: [DONE]\\n\\n

    El frontend debe leer con `fetch + ReadableStream` (no EventSource, porque
    EventSource solo soporta GET).
    """
    service = InterviewService(db)
    try:
        # `send_user_message_and_stream` valida y devuelve un generator.
        generator = service.send_user_message_and_stream(
            attempt_id=attempt_id,
            user_id=current_user.id,
            content=payload.content,
        )
    except AttemptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AttemptClosed as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            # Sin esto algunos proxies bufferean SSE y todo aparece de golpe.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{attempt_id}/evaluate",
    response_model=EvaluationResponse,
)
def evaluate_attempt(
    attempt_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Corre el Evaluador sobre el attempt cerrado. Idempotente: si ya fue
    evaluado, devuelve el resultado guardado sin re-llamar a Anthropic.

    Solo funciona si el attempt está en estado 'completed' (es decir, el
    marker [INTERVIEW_COMPLETE] ya fue emitido).
    """
    service = InterviewService(db)
    try:
        result = service.evaluate_attempt(attempt_id, current_user.id)
    except AttemptNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AttemptNotReadyForEvaluation as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return EvaluationResponse(**result)

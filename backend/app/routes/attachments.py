"""
Endpoints para uploads de imágenes que el user adjunta al chat.

Storage: filesystem local en /home/anoven/anoven-app/storage/uploads/.
Archivos servidos via FastAPI StaticFiles montado en /storage/.
"""

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import SessionLocal, get_db
from app.models.attachment import Attachment
from app.models.user import User
from app.services.document_indexer import count_pdf_pages, index_attachment, IndexingError


logger = logging.getLogger(__name__)


# Anthropic API hard limits:
#  - 100 paginas / PDF (rechazo explicito en mensaje de error)
#  - ~30 MB de payload total / request (despues de base64 inflation ~22 MB raw)
# Para mantener margen seguro, forzamos RAG cuando size_bytes > 8 MB raw,
# aunque tenga menos de 100 paginas. Sin esto, PDFs densos con imagenes
# (typical brand manuals) revientan con 413 al mandarlos enteros a Anthropic.
RAG_PAGE_THRESHOLD = 100
RAG_SIZE_THRESHOLD = 8 * 1024 * 1024  # 8 MB raw -> ~11 MB base64


def _index_pdf_background(attachment_id: int, conversation_id: int | None) -> None:
    # BackgroundTasks corre fuera del request -> session propia.
    db = SessionLocal()
    try:
        result = index_attachment(db, attachment_id, conversation_id=conversation_id)
        logger.info(f"[indexer-bg] att={attachment_id} OK chunks={result.get("chunks")}")
    except IndexingError as e:
        logger.error(f"[indexer-bg] att={attachment_id} failed: {e}")
    except Exception:
        logger.exception(f"[indexer-bg] att={attachment_id} unexpected error")
    finally:
        db.close()


STORAGE_ROOT = Path(os.environ.get(
    "ANOVEN_STORAGE_ROOT",
    "/home/anoven/anoven-app/storage/uploads",
))


ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    conversation_id: int | None = Form(None),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sube una imagen o PDF. Retorna el Attachment con la URL publica para usar
    en el siguiente POST /conversations/{id}/messages.
    """
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo no permitido: {file.content_type}. Solo PNG, JPEG, WebP, GIF, PDF, DOCX, DOC.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Archivo más grande que 50MB.",
        )

    ext = (file.filename or "").split(".")[-1].lower() if "." in (file.filename or "") else "bin"
    if file.content_type == "image/jpeg":
        ext = "jpg"
    elif file.content_type == "image/png":
        ext = "png"
    elif file.content_type == "image/webp":
        ext = "webp"
    elif file.content_type == "image/gif":
        ext = "gif"
    elif file.content_type == "application/pdf":
        ext = "pdf"
    elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        ext = "docx"
    elif file.content_type == "application/msword":
        ext = "doc"

    user_dir = STORAGE_ROOT / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    target = user_dir / name
    target.write_bytes(contents)

    relative = f"{current_user.id}/{name}"
    attachment = Attachment(
        user_id=current_user.id,
        mime_type=file.content_type,
        file_path=relative,
        original_name=file.filename,
        size_bytes=len(contents),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    page_count = None
    needs_indexing = False
    if file.content_type == "application/pdf":
        try:
            page_count = count_pdf_pages(target)
        except IndexingError as e:
            logger.warning(f"[upload] no page_count for att={attachment.id}: {e}")
        if page_count is not None:
            attachment.page_count = page_count
            if page_count > RAG_PAGE_THRESHOLD or len(contents) > RAG_SIZE_THRESHOLD:
                needs_indexing = True
        db.commit()
        db.refresh(attachment)

    if needs_indexing and background_tasks is not None:
        background_tasks.add_task(_index_pdf_background, attachment.id, conversation_id)

    return {
        "id": attachment.id,
        "url": f"/storage/{relative}",
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "page_count": page_count,
        "is_indexed": attachment.is_indexed,
        "indexing": needs_indexing,
    }

@router.get("/{attachment_id}")
async def get_attachment(
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Status polling para el frontend: is_indexed mientras se procesa."""
    att = db.get(Attachment, attachment_id)
    if att is None or att.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    needs_rag = att.mime_type == "application/pdf" and (
        (att.page_count or 0) > RAG_PAGE_THRESHOLD
        or (att.size_bytes or 0) > RAG_SIZE_THRESHOLD
    )
    failed = att.index_status == "failed"
    return {
        "id": att.id,
        "mime_type": att.mime_type,
        "size_bytes": att.size_bytes,
        "page_count": att.page_count,
        "is_indexed": att.is_indexed,
        "indexing": needs_rag and not att.is_indexed and not failed,
        "index_status": att.index_status,
        "index_progress": att.index_progress,
        "index_error": att.index_error,
    }

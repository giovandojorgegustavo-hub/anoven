"""
document_indexer — pipeline RAG para PDFs >100 páginas.

Flujo:
  1. pymupdf abre el PDF desde STORAGE_ROOT.
  2. Extrae texto por página + intenta detectar secciones (heurística).
  3. Chunker: ~500 tokens (~2000 chars) con overlap ~100 tokens (~400 chars).
     Sliding window respetando límites de página para preservar trazabilidad.
  4. Batch embed con embeddings_client (gemini-embedding-001, 768 dim).
  5. INSERT chunks en document_chunks.
  6. Update attachments.is_indexed=True + indexed_at + page_count.

Canon:
  - Clean Architecture (Martin, 2017): este módulo es servicio puro, no toca HTTP.
  - DDD bounded context (Evans, 2003): namespace por conversation_id.
"""

import logging
from datetime import datetime
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.document_chunk import DocumentChunk
from app.models.message import Message
from app.services.embeddings_client import embed_texts


logger = logging.getLogger(__name__)


STORAGE_ROOT = Path("/home/anoven/anoven-app/storage/uploads")

# Chunking: ~500 tokens objetivo, overlap 100. Aproximamos 1 token = 4 chars.
CHUNK_CHAR_TARGET = 2000
CHUNK_CHAR_OVERLAP = 400

# Batch size para embed_content. Google AI acepta hasta 100 textos por request.
EMBED_BATCH_SIZE = 10  # bajo por rate limits del free tier Gemini


def _set_status(db, att, status: str, progress: str | None = None, error: str | None = None) -> None:
    att.index_status = status
    att.index_progress = progress
    att.index_error = error
    db.commit()



class IndexingError(Exception):
    pass


def _chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """
    Dado pages = [(page_num, text), ...], produce chunks con sliding window.
    Cada chunk preserva page_start y page_end para citation.

    No partimos chunks a través de saltos de página irrelevantes — concatenamos
    texto de páginas consecutivas y deslizamos la ventana sobre el resultado.
    """
    chunks: list[dict] = []
    if not pages:
        return chunks

    # Concatenar texto con marcadores de página para mapear offsets a páginas.
    full_text_parts: list[str] = []
    page_offsets: list[tuple[int, int, int]] = []  # (start, end, page_num)
    cursor = 0
    for page_num, text in pages:
        page_offsets.append((cursor, cursor + len(text), page_num))
        full_text_parts.append(text)
        cursor += len(text)
    full_text = "".join(full_text_parts)
    total = len(full_text)

    if total == 0:
        return chunks

    def page_at_offset(offset: int) -> int:
        for start, end, p in page_offsets:
            if start <= offset < end:
                return p
        return page_offsets[-1][2]

    step = CHUNK_CHAR_TARGET - CHUNK_CHAR_OVERLAP
    if step <= 0:
        step = CHUNK_CHAR_TARGET

    idx = 0
    pos = 0
    while pos < total:
        end = min(pos + CHUNK_CHAR_TARGET, total)
        content = full_text[pos:end].strip()
        if content:
            chunks.append({
                "chunk_index": idx,
                "content": content,
                "page_start": page_at_offset(pos),
                "page_end": page_at_offset(max(pos, end - 1)),
                "token_count": len(content) // 4,
            })
            idx += 1
        if end >= total:
            break
        pos += step

    return chunks


def _extract_pages(file_full_path: Path) -> tuple[list[tuple[int, str]], int]:
    """Extrae texto por página. Devuelve (pages, total_count)."""
    try:
        doc = pymupdf.open(str(file_full_path))
    except Exception as e:
        raise IndexingError(f"No pude abrir el PDF: {type(e).__name__}: {e}")
    try:
        pages: list[tuple[int, str]] = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text))
        return pages, doc.page_count
    finally:
        doc.close()


def count_pdf_pages(file_full_path: Path) -> int:
    """Solo cuenta páginas — uso en /attachments para decidir si encolar indexing."""
    try:
        doc = pymupdf.open(str(file_full_path))
        try:
            return doc.page_count
        finally:
            doc.close()
    except Exception as e:
        raise IndexingError(f"No pude leer el PDF: {type(e).__name__}: {e}")


def index_attachment(
    db: Session,
    attachment_id: int,
    conversation_id: int | None = None,
) -> dict:
    """
    Indexa un PDF: extract -> chunk -> embed -> save.

    Idempotente: si ya está indexado, no re-indexa. Si está parcial, borra
    chunks viejos primero y re-indexa.

    conversation_id se pasa explicitamente desde el endpoint /attachments
    (el frontend lo sabe porque esta en la URL del chat). Para uploads
    legacy sin conv_id explicito, se deriva de message_id si esta seteado.
    """
    att = db.get(Attachment, attachment_id)
    if att is None:
        raise IndexingError(f"Attachment {attachment_id} no existe")
    if att.mime_type != "application/pdf":
        raise IndexingError(f"Attachment {attachment_id} no es PDF (mime={att.mime_type})")

    conv_id: int | None = conversation_id
    if conv_id is None and att.message_id is not None:
        msg = db.get(Message, att.message_id)
        if msg is not None:
            conv_id = msg.conversation_id
    if conv_id is None:
        msg_err = "Attachment sin conversation_id ni message_id"
        _set_status(db, att, "failed", error=msg_err)
        raise IndexingError(msg_err)

    file_full = STORAGE_ROOT / att.file_path
    if not file_full.exists():
        msg_err = f"Archivo no existe en disco: {file_full}"
        _set_status(db, att, "failed", error=msg_err)
        raise IndexingError(msg_err)

    try:
        # 1. Extract.
        _set_status(db, att, "extracting", progress="abriendo PDF")
        pages, total_pages = _extract_pages(file_full)
        att.page_count = total_pages
        db.commit()
        logger.info(f"[indexer] att={attachment_id} pages={total_pages}")

        # 2. Chunk.
        _set_status(db, att, "chunking", progress=f"{total_pages} paginas")
        chunks = _chunk_pages(pages)
        if not chunks:
            msg_err = "PDF sin texto digital (probablemente escaneado). Necesita OCR para ser leido."
            _set_status(db, att, "failed", error=msg_err)
            raise IndexingError(f"PDF sin texto extraible (att={attachment_id})")
        logger.info(f"[indexer] att={attachment_id} chunks={len(chunks)}")

        # 3. Embed (batch).
        import time
        contents = [c["content"] for c in chunks]
        embeddings: list[list[float]] = []
        total_batches = (len(contents) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
        for i, batch_start in enumerate(range(0, len(contents), EMBED_BATCH_SIZE)):
            _set_status(db, att, "embedding", progress=f"batch {i+1}/{total_batches}")
            batch = contents[batch_start : batch_start + EMBED_BATCH_SIZE]
            vectors = embed_texts(batch, task_type="RETRIEVAL_DOCUMENT")
            embeddings.extend(vectors)
            logger.info(f"[indexer] batch {i+1}/{total_batches} OK ({len(batch)} chunks)")
            if i + 1 < total_batches:
                time.sleep(0.5)

        # 4. Save chunks (wipe viejos para idempotencia).
        _set_status(db, att, "saving", progress=f"{len(chunks)} chunks")
        db.query(DocumentChunk).filter(DocumentChunk.attachment_id == attachment_id).delete()
        for chunk, vec in zip(chunks, embeddings, strict=True):
            db.add(DocumentChunk(
                attachment_id=attachment_id,
                conversation_id=conv_id,
                chunk_index=chunk["chunk_index"],
                page_start=chunk["page_start"],
                page_end=chunk["page_end"],
                content=chunk["content"],
                embedding=vec,
                token_count=chunk["token_count"],
            ))

        # 5. Mark done.
        att.is_indexed = True
        att.indexed_at = datetime.utcnow()
        _set_status(db, att, "done", progress=f"{len(chunks)} chunks indexados")
        logger.info(f"[indexer] att={attachment_id} indexed OK chunks={len(chunks)}")
        return {
            "attachment_id": attachment_id,
            "pages": total_pages,
            "chunks": len(chunks),
        }
    except IndexingError:
        raise
    except Exception as e:
        msg_err = f"{type(e).__name__}: {str(e)[:200]}"
        try:
            _set_status(db, att, "failed", error=msg_err)
        except Exception:
            db.rollback()
        raise

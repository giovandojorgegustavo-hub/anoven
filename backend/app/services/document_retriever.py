"""
document_retriever — retrieval de chunks RAG por conversación.

Flujo:
  1. embed_one(query, task_type=RETRIEVAL_QUERY).
  2. Vector similarity search filtrado por conversation_id (bounded context).
  3. top-k chunks ordenados por similaridad coseno.
  4. Formateo del bloque de contexto para inyectar en el prompt.

Canon: Evans, DDD 2003 (bounded context). Chip Huyen, AI Engineering 2024
[Tier 2] (RAG retrieval semantics).
"""

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.attachment import Attachment
from app.models.document_chunk import DocumentChunk
from app.services.embeddings_client import embed_one


logger = logging.getLogger(__name__)


DEFAULT_TOP_K = 10
MAX_CONTEXT_CHARS = 24000  # ~6000 tokens para el bloque RAG, deja espacio al modelo.


def has_indexed_documents(db: Session, conversation_id: int) -> bool:
    """True si la conversación tiene al menos un PDF indexado listo para RAG."""
    stmt = (
        select(Attachment.id)
        .where(Attachment.is_indexed.is_(True))
        .join(DocumentChunk, DocumentChunk.attachment_id == Attachment.id)
        .where(DocumentChunk.conversation_id == conversation_id)
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def search_chunks(
    db: Session,
    conversation_id: int,
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> list[DocumentChunk]:
    """
    Embed la query y devuelve los top_k chunks de ESA conversación por similaridad
    coseno descendente. Sin chunks indexados, devuelve [].
    """
    if not query or not query.strip():
        return []

    try:
        query_vec = embed_one(query, task_type="RETRIEVAL_QUERY")
    except Exception:
        logger.exception("[retriever] embed query failed")
        return []

    # pgvector: <=> operador para cosine distance (0=identico, 2=opuesto).
    # Orden ASC: distancias chicas primero = mas similar.
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.conversation_id == conversation_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
        .limit(top_k)
    )
    return list(db.execute(stmt).scalars().all())


def chunks_to_context_text(chunks: list[DocumentChunk]) -> str:
    """
    Formatea los chunks recuperados como un bloque de texto que se inyecta
    en el message al modelo. Cada chunk lleva su page_start/page_end para
    que el modelo pueda citar paginas concretas.

    Trunca a MAX_CONTEXT_CHARS para evitar inflar la request sin necesidad.
    """
    if not chunks:
        return ""
    parts: list[str] = [
        "=== Fragmentos relevantes del documento (RAG) ===",
        "Estas son las secciones mas pertinentes a la pregunta. "
        "Cita las paginas cuando respondas (ej: \"segun pags. 12-14...\").",
        "",
    ]
    used = sum(len(p) for p in parts)
    for c in chunks:
        page_label = (
            f"[pags. {c.page_start}-{c.page_end}]"
            if c.page_start and c.page_end and c.page_start != c.page_end
            else f"[pag. {c.page_start}]" if c.page_start else "[pag. ?]"
        )
        fragment = f"\n--- Fragmento {c.chunk_index} {page_label} ---\n{c.content}\n"
        if used + len(fragment) > MAX_CONTEXT_CHARS:
            parts.append("\n[...fragmentos adicionales omitidos por espacio...]")
            break
        parts.append(fragment)
        used += len(fragment)
    return "\n".join(parts)

"""
Modelo DocumentChunk — chunks indexados de PDFs >100 páginas (RAG).

Anthropic API límite: 100 pág/PDF. Para PDFs largos, indexamos con
gemini-embedding-001 (768 dim Matryoshka) y retrieval por conversation_id.

Bounded context: namespace por conversación (Evans, DDD 2003).
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    attachment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("attachments.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("attachment_id", "chunk_index", name="uq_chunk_attachment_index"),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} att={self.attachment_id} idx={self.chunk_index}>"

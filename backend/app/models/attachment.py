"""
Modelo Attachment — adjuntos (imágenes) en mensajes del chat.

Por ahora solo soporta imágenes. Audio/video quedan para una fase posterior
cuando definamos cuál proveedor (Whisper, Gemini multimodal) y cuál pipeline.

Storage: local filesystem en `/home/anoven/anoven-app/storage/uploads/`.
Path: `/storage/uploads/{user_id}/{conv_id}/{uuid}.{ext}`.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("messages.id"), index=True, nullable=True
    )

    # "image/png", "image/jpeg", "image/webp"
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    # Path relativo en disco — el endpoint /storage lo sirve.
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # RAG: para PDFs >100 páginas indexamos a document_chunks (gemini-embedding-001).
    # Si is_indexed=False y mime es image/* o PDF chico -> se manda nativo a Claude.
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_indexed: Mapped[bool] = mapped_column(default=False, nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Progress + error feedback para que el frontend muestre estado real.
    index_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    index_progress: Mapped[str | None] = mapped_column(String(80), nullable=True)
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<Attachment id={self.id} user={self.user_id} mime={self.mime_type}>"

"""
Repository para Message (chat con mentor).

Cambios en anoven-shared-projects:
  - create() acepta author_user_id opcional (NULL para turnos del asistente).
  - get_authors_for_conversation() devuelve el set de user_ids que escribieron
    en la conversación (excluye NULL = asistente). Usado por SharedProjectContextBuilder.
"""

from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.message import Message
from app.models.conversation import Conversation


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_conversation(self, conv_id: int) -> list[Message]:
        """Mensajes de una conversación, en orden cronológico."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        conv_id: int,
        role: str,
        content: str,
        author_user_id: int | None = None,
    ) -> Message:
        """
        Crea un mensaje y actualiza el updated_at de la conversación
        en el mismo commit — así la sidebar puede ordenar por actividad reciente.

        author_user_id:
          - int  → turno de un user humano (role='user' en proyectos compartidos).
          - None → turno del asistente (role='assistant'), o proyecto privado
                   donde no es necesario trackear authorship por mensaje.
        """
        msg = Message(
            conversation_id=conv_id,
            role=role,
            content=content,
            author_user_id=author_user_id,
        )
        self.db.add(msg)

        conv = self.db.get(Conversation, conv_id)
        if conv is not None:
            conv.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(msg)
        return msg

    def get_authors_for_conversation(self, conv_id: int) -> set[int]:
        """
        Devuelve el set de user_ids que escribieron mensajes humanos en
        la conversación (excluye author_user_id IS NULL = turnos de asistente).

        Usado por SharedProjectContextBuilder para determinar si hay más
        de un author y construir el resumen por autor.
        """
        stmt = (
            select(Message.author_user_id)
            .where(Message.conversation_id == conv_id)
            .where(Message.author_user_id.is_not(None))
            .distinct()
        )
        rows = self.db.execute(stmt).scalars().all()
        return set(rows)

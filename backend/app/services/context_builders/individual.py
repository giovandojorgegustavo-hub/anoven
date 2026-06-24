"""
IndividualContextBuilder — estrategia de contexto para proyectos individuales.

Adapter del comportamiento actual de trim_history() al Port ContextBuilder.
No agrega lógica nueva — solo adapta la interfaz para que conversation_service
pueda conmutar estrategias polimórficamente.

Alistair Cockburn — Hexagonal Architecture, 2005.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.context_window import trim_history


class IndividualContextBuilder:
    """
    Wraps el trim_history() existente al contrato ContextBuilder.

    Comportamiento idéntico al de antes de la introducción del Strategy pattern:
      - oldest-first drop
      - preserve last 2 messages
      - no author summary

    Esta clase es el adapter "sin cambios" para proyectos de un solo miembro.
    """

    def __init__(self, db: Session, conversation_id: int):
        self.db = db
        self.conversation_id = conversation_id

    def build(
        self,
        conversation_id: int,
        max_tokens: int,
        output_reserved: int,
    ) -> tuple[list[dict], dict]:
        """
        Carga el historial desde DB y aplica trim_history().

        Returns:
            (messages, status) donde messages son dicts {role, content}.
        """
        from app.repositories.message_repo import MessageRepository

        msg_repo = MessageRepository(self.db)
        all_msgs = msg_repo.list_for_conversation(conversation_id)

        raw_history: list[dict] = [
            {"role": m.role, "content": m.content}
            for m in all_msgs
        ]

        trimmed, status = trim_history(raw_history, max_tokens, output_reserved)
        return trimmed, status

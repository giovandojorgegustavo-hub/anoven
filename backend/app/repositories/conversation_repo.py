"""
Repository para Conversation.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, conv_id: int) -> Conversation | None:
        return self.db.get(Conversation, conv_id)

    def list_for_user(self, user_id: int) -> list[Conversation]:
        """Todas las conversaciones del user, ordenadas por updated_at desc."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
        )
        return list(self.db.execute(stmt).scalars().all())

    def latest_for_user_mentor_and_use_case(
        self,
        user_id: int,
        mentor_id: int,
        use_case_id: int | None,
    ) -> Conversation | None:
        """La conversación más reciente del user con ese mentor en ese use_case.
        Si use_case_id es None, busca conversaciones SIN use_case (legacy)."""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.mentor_id == mentor_id)
        )
        if use_case_id is None:
            stmt = stmt.where(Conversation.use_case_id.is_(None))
        else:
            stmt = stmt.where(Conversation.use_case_id == use_case_id)
        stmt = stmt.order_by(desc(Conversation.updated_at))
        return self.db.execute(stmt).scalars().first()

    def list_for_user_in_use_cases(
        self,
        user_id: int,
        use_case_ids: list[int],
        include_orphans: bool = False,
    ) -> list[Conversation]:
        """
        Conversaciones del user dentro de los use_cases indicados.
        Si include_orphans=True, también las que tienen use_case_id=NULL.
        """
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
        )
        if use_case_ids and include_orphans:
            stmt = stmt.where(
                (Conversation.use_case_id.in_(use_case_ids))
                | (Conversation.use_case_id.is_(None))
            )
        elif use_case_ids:
            stmt = stmt.where(Conversation.use_case_id.in_(use_case_ids))
        elif include_orphans:
            stmt = stmt.where(Conversation.use_case_id.is_(None))
        else:
            return []
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        user_id: int,
        mentor_id: int,
        use_case_id: int | None = None,
    ) -> Conversation:
        conv = Conversation(
            user_id=user_id,
            mentor_id=mentor_id,
            use_case_id=use_case_id,
        )
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def set_title(self, conv_id: int, title: str) -> Conversation | None:
        conv = self.db.get(Conversation, conv_id)
        if conv is None:
            return None
        conv.title = title
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def mark_seen(self, conv: Conversation) -> Conversation:
        from datetime import datetime
        conv.last_seen_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def toggle_focus(self, conv: Conversation, focused: bool) -> Conversation:
        conv.is_focused = focused
        self.db.commit()
        self.db.refresh(conv)
        return conv

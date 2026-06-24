"""
Modelo Rule — instrucción persistente del user con scope flexible.

Scope se determina por qué FKs están llenos:
  - global    → project_id=NULL  + use_case_id=NULL  (aplica en todos los chats)
  - project   → project_id=N     + use_case_id=NULL  (aplica en ese project)
  - use_case  → project_id=N     + use_case_id=M     (aplica solo en ese use_case)

Las rules activas se inyectan al system_prompt en cada turn (Sesión 4.5),
DESPUÉS del CLAUDE.md para ganar recency.
"""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True, nullable=False
    )

    # Scope (NULL = no aplica filtro a ese nivel)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id"), index=True, nullable=True
    )
    use_case_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("use_cases.id"), index=True, nullable=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<Rule id={self.id} user={self.user_id} "
            f"project={self.project_id} use_case={self.use_case_id} active={self.active}>"
        )

    @property
    def scope(self) -> str:
        if self.use_case_id is not None:
            return "use_case"
        if self.project_id is not None:
            return "project"
        return "global"

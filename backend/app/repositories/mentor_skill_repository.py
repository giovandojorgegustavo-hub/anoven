"""
MentorSkillRepository -- acceso a la tabla mentor_skills.

Unico punto de verdad para consultas SQL de skills. SkillLoader
es el unico caller de list_enabled_for_mentor(); las routes admin
usan el resto de los metodos.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.mentor_skill import MentorSkill


class MentorSkillRepository:
    """Acceso a mentor_skills."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_enabled_for_mentor(self, mentor_id: int) -> list[MentorSkill]:
        """
        Devuelve las skills habilitadas del mentor, ordenadas por position ASC.
        Llamado exclusivamente por SkillLoader.
        """
        stmt = (
            select(MentorSkill)
            .where(
                MentorSkill.mentor_id == mentor_id,
                MentorSkill.enabled == True,  # noqa: E712
            )
            .order_by(MentorSkill.position.asc(), MentorSkill.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def list_all_for_mentor(self, mentor_id: int) -> list[MentorSkill]:
        """Todas las skills del mentor (incluyendo disabled). Para admin UI."""
        stmt = (
            select(MentorSkill)
            .where(MentorSkill.mentor_id == mentor_id)
            .order_by(MentorSkill.position.asc(), MentorSkill.id.asc())
        )
        return list(self.db.execute(stmt).scalars())

    def list_all(self) -> list[MentorSkill]:
        """Todas las skills de todos los mentores. Para admin list view."""
        stmt = select(MentorSkill).order_by(
            MentorSkill.mentor_id.asc(),
            MentorSkill.position.asc(),
        )
        return list(self.db.execute(stmt).scalars())

    def get_by_id(self, skill_id: int) -> Optional[MentorSkill]:
        return self.db.get(MentorSkill, skill_id)

    def get_by_slug_and_mentor(
        self, mentor_id: int, slug: str
    ) -> Optional[MentorSkill]:
        stmt = select(MentorSkill).where(
            MentorSkill.mentor_id == mentor_id,
            MentorSkill.slug == slug,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def max_position_for_mentor(self, mentor_id: int) -> int:
        """Devuelve el maximo position actual del mentor (0 si no hay rows)."""
        result = self.db.execute(
            select(func.max(MentorSkill.position)).where(
                MentorSkill.mentor_id == mentor_id
            )
        ).scalar()
        return result if result is not None else 0

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self,
        mentor_id: int,
        slug: str,
        title: str,
        content: str,
        triggers: Optional[list] = None,
        position: Optional[int] = None,
        enabled: bool = True,
    ) -> MentorSkill:
        if position is None:
            position = self.max_position_for_mentor(mentor_id) + 1
        skill = MentorSkill(
            mentor_id=mentor_id,
            slug=slug,
            title=title,
            content=content,
            triggers=triggers,
            position=position,
            enabled=enabled,
        )
        self.db.add(skill)
        self.db.commit()
        self.db.refresh(skill)
        return skill

    def update(self, skill_id: int, **fields) -> Optional[MentorSkill]:
        skill = self.get_by_id(skill_id)
        if skill is None:
            return None
        allowed = {"title", "content", "triggers", "enabled", "position"}
        for k, v in fields.items():
            if k in allowed:
                setattr(skill, k, v)
        skill.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(skill)
        return skill

    def delete(self, skill_id: int) -> bool:
        skill = self.get_by_id(skill_id)
        if skill is None:
            return False
        self.db.delete(skill)
        self.db.commit()
        return True

    def bulk_create(
        self,
        mentor_id: int,
        skills: list[dict],
    ) -> list[MentorSkill]:
        """
        Inserta multiples skills de una vez (para Promptifex initial_skills).
        skills: lista de dicts con keys: slug, title, content, triggers (opt).
        positions: 0, 1, 2, ... segun el orden de la lista.
        Silencioso en errores -- nunca bloquea event: mentor_created.
        """
        created = []
        for i, s in enumerate(skills):
            try:
                skill = MentorSkill(
                    mentor_id=mentor_id,
                    slug=s["slug"],
                    title=s["title"],
                    content=s["content"],
                    triggers=s.get("triggers"),
                    position=i,
                    enabled=True,
                )
                self.db.add(skill)
            except Exception:
                continue
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            return []
        return created

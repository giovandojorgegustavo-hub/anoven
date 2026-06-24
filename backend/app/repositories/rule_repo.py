"""
Repository para Rule.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.models.rule import Rule


class RuleRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, rule_id: int) -> Rule | None:
        return self.db.get(Rule, rule_id)

    def list_for_user(self, user_id: int) -> list[Rule]:
        """Todas las rules del user (activas o no), ordenadas por scope global→project→use_case."""
        stmt = (
            select(Rule)
            .where(Rule.user_id == user_id)
            .order_by(
                Rule.project_id.is_(None).desc(),  # global primero (project NULL)
                Rule.use_case_id.is_(None).desc(),  # project antes que use_case
                Rule.created_at.desc(),
            )
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_active_for_scope(
        self,
        user_id: int,
        project_id: int | None,
        use_case_id: int | None,
    ) -> list[Rule]:
        """
        Devuelve las rules activas que aplican a ese scope. Una rule aplica si:
          - es global (project=NULL Y use_case=NULL), O
          - es del project (project=X) y el chat es en ese project, O
          - es del use_case (use_case=Y) y el chat es en ese use_case.
        """
        conditions = [
            (Rule.project_id.is_(None)) & (Rule.use_case_id.is_(None)),
        ]
        if project_id is not None:
            conditions.append(
                (Rule.project_id == project_id) & (Rule.use_case_id.is_(None))
            )
        if use_case_id is not None:
            conditions.append(Rule.use_case_id == use_case_id)

        stmt = (
            select(Rule)
            .where(Rule.user_id == user_id)
            .where(Rule.active == True)
            .where(or_(*conditions))
            .order_by(Rule.created_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        user_id: int,
        content: str,
        project_id: int | None = None,
        use_case_id: int | None = None,
    ) -> Rule:
        rule = Rule(
            user_id=user_id,
            content=content,
            project_id=project_id,
            use_case_id=use_case_id,
            active=True,
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def set_active(self, rule_id: int, active: bool) -> Rule | None:
        rule = self.db.get(Rule, rule_id)
        if rule is None:
            return None
        rule.active = active
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def delete(self, rule_id: int) -> bool:
        rule = self.db.get(Rule, rule_id)
        if rule is None:
            return False
        self.db.delete(rule)
        self.db.commit()
        return True

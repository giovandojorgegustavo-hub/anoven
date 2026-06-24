"""
RuleService — orquesta CRUD de rules + builder del block para inyección.
"""

from sqlalchemy.orm import Session

from app.models.rule import Rule
from app.repositories.project_repo import ProjectRepository, UseCaseRepository
from app.repositories.rule_repo import RuleRepository


class RuleError(Exception):
    pass


class RuleNotFound(RuleError):
    pass


class InvalidScope(RuleError):
    pass


class RuleService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RuleRepository(db)
        self.project_repo = ProjectRepository(db)
        self.use_case_repo = UseCaseRepository(db)

    def list_for_user(self, user_id: int) -> list[Rule]:
        return self.repo.list_for_user(user_id)

    def create_for_user(
        self,
        user_id: int,
        content: str,
        project_id: int | None = None,
        use_case_id: int | None = None,
    ) -> Rule:
        """
        Valida que el scope sea coherente con la ownership del user.
        - Si project_id viene, debe pertenecer al user.
        - Si use_case_id viene, project_id también debe estar y el use_case
          tiene que pertenecer a ese project.
        """
        if project_id is not None:
            project = self.project_repo.get_by_id(project_id)
            if project is None or project.user_id != user_id:
                raise InvalidScope(f"Project {project_id} no pertenece al user.")

        if use_case_id is not None:
            if project_id is None:
                raise InvalidScope(
                    "use_case_id requiere también project_id."
                )
            uc = self.use_case_repo.get_by_id(use_case_id)
            if uc is None or uc.project_id != project_id:
                raise InvalidScope(
                    f"use_case {use_case_id} no pertenece al project {project_id}."
                )

        return self.repo.create(
            user_id=user_id,
            content=content,
            project_id=project_id,
            use_case_id=use_case_id,
        )

    def toggle_active(self, rule_id: int, user_id: int, active: bool) -> Rule:
        rule = self.repo.get_by_id(rule_id)
        if rule is None or rule.user_id != user_id:
            raise RuleNotFound(f"Rule {rule_id} no existe.")
        updated = self.repo.set_active(rule_id, active)
        if updated is None:
            raise RuleNotFound(f"Rule {rule_id} no existe.")
        return updated

    def delete_for_user(self, rule_id: int, user_id: int) -> bool:
        rule = self.repo.get_by_id(rule_id)
        if rule is None or rule.user_id != user_id:
            raise RuleNotFound(f"Rule {rule_id} no existe.")
        return self.repo.delete(rule_id)

    # ============================================================
    # Builder del block para inyección al system_prompt
    # ============================================================

    def build_block_for_user(
        self,
        user_id: int,
        use_case_id: int | None,
    ) -> str:
        """
        Arma el bloque de reglas activas que aplican a este chat.
        Si no hay reglas, devuelve "".

        Se llama desde ConversationService.send_user_message_and_stream.
        El use_case_id de la conversación determina qué reglas project/use_case
        son aplicables.
        """
        project_id = None
        if use_case_id is not None:
            uc = self.use_case_repo.get_by_id(use_case_id)
            if uc is not None:
                project_id = uc.project_id

        rules = self.repo.list_active_for_scope(
            user_id=user_id,
            project_id=project_id,
            use_case_id=use_case_id,
        )
        if not rules:
            return ""

        lines = [
            "═══════════════════════════════════════════════════════",
            "REGLAS DEL USER (instrucciones persistentes — RESPETALAS)",
            "═══════════════════════════════════════════════════════",
            "",
            "Estas son reglas que el user dejó configuradas para CÓMO",
            "querés que le respondas. Tienen prioridad sobre tu estilo default:",
            "",
        ]
        for r in rules:
            scope_label = {"global": "GLOBAL", "project": "PROJECT", "use_case": "USE-CASE"}[r.scope]
            lines.append(f"- [{scope_label}] {r.content.strip()}")
        return "\n".join(lines)

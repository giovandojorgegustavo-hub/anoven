"""
Repository CostEvent — traducción SQLAlchemy → dominio.

NUNCA lógica de negocio aquí. NUNCA imports de fastapi.

En anoven-shared-projects se agrega billed_user_id para routing de costos:
  - user_id        = quién hizo el request (member o owner).
  - billed_user_id = quién paga (siempre el owner del proyecto).
  Para proyectos privados: billed_user_id = NULL (legacy behavior).

Nota: cost_tracker.py sigue siendo la capa de cálculo de USD.
Este repo se encarga solo de persistencia y queries.
"""

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.cost_event import CostEvent


class CostEventRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Escrituras ────────────────────────────────────────────────────────────

    def create(
        self,
        user_id: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        conversation_id: int | None = None,
        mentor_id: int | None = None,
        purpose: str = "chat",
        billed_user_id: int | None = None,
        usd_cost: float = 0.0,
    ) -> CostEvent:
        """
        Persiste un cost_event. Flush sin commit — el caller controla la transacción.

        billed_user_id:
          - None  → proyecto privado (costo cae en user_id).
          - int   → owner del proyecto compartido que absorbe el costo.
        """
        ev = CostEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            mentor_id=mentor_id,
            billed_user_id=billed_user_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            usd_cost=usd_cost,
            purpose=purpose,
        )
        self.db.add(ev)
        self.db.flush()
        return ev

    # ── Agregados ─────────────────────────────────────────────────────────────

    def aggregate_for_user(
        self,
        user_id: int,
        project_id: int | None = None,
    ) -> dict:
        """
        Agrega tokens y costo para un user como billed_user (owner dashboard).

        Si project_id se provee, filtra solo los cost_events de conversaciones
        de ese proyecto (join vía conversation.use_case.project_id — implementado
        inline en la ruta, este método no hace el join para mantener el repo simple).

        Devuelve dict con: total_input, total_output, total_cached, total_usd,
        y per_member breakdown (list de {user_id, input, output, usd}).

        Nota v1: breakdown por member requiere join conversation→use_case→project
        que se hace en la capa de servicio. Este método devuelve el agregado simple.
        """
        # Costos donde este user es el billed (owner de proyecto compartido)
        stmt_billed = (
            select(
                func.sum(CostEvent.input_tokens),
                func.sum(CostEvent.output_tokens),
                func.sum(CostEvent.cached_tokens),
                func.sum(CostEvent.usd_cost),
            )
            .where(CostEvent.billed_user_id == user_id)
        )

        # Costos propios sin billed (proyectos privados del owner)
        stmt_own = (
            select(
                func.sum(CostEvent.input_tokens),
                func.sum(CostEvent.output_tokens),
                func.sum(CostEvent.cached_tokens),
                func.sum(CostEvent.usd_cost),
            )
            .where(CostEvent.user_id == user_id)
            .where(CostEvent.billed_user_id.is_(None))
        )

        def _sum_row(stmt):
            row = self.db.execute(stmt).one()
            return {
                "input_tokens":  int(row[0] or 0),
                "output_tokens": int(row[1] or 0),
                "cached_tokens": int(row[2] or 0),
                "usd_cost":      float(row[3] or 0.0),
            }

        billed = _sum_row(stmt_billed)
        own    = _sum_row(stmt_own)

        return {
            "total_input_tokens":  billed["input_tokens"]  + own["input_tokens"],
            "total_output_tokens": billed["output_tokens"] + own["output_tokens"],
            "total_cached_tokens": billed["cached_tokens"] + own["cached_tokens"],
            "total_usd_cost":      billed["usd_cost"]      + own["usd_cost"],
            # breakdown por member se resuelve en el servicio / ruta
        }

    def list_billed_to(self, owner_user_id: int) -> list[CostEvent]:
        """
        Devuelve todos los cost_events donde billed_user_id = owner_user_id.
        Permite al dashboard del owner ver los costos que generaron sus members.
        """
        stmt = (
            select(CostEvent)
            .where(CostEvent.billed_user_id == owner_user_id)
            .order_by(CostEvent.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

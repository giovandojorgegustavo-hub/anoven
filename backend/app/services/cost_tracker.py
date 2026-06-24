"""
Helper para persistir cost_events.

Precios (USD por 1M tokens) actualizados a junio 2026:
  - claude-haiku-4-5:    input $0.80,  output $4.00
  - claude-sonnet-4-6:   input $3.00,  output $15.00
  - claude-opus-4-8:     input $15.00, output $75.00

Si no reconocemos el modelo, no calculamos USD (queda en 0) pero igual
guardamos tokens — siempre se puede recalcular después con la tabla de precios.
"""

from sqlalchemy.orm import Session

from app.models.cost_event import CostEvent


_PRICING_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (15.00, 75.00),
}


def estimate_usd_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = _PRICING_PER_1M_TOKENS.get(model)
    if pricing is None:
        return 0.0
    in_per_1m, out_per_1m = pricing
    return (input_tokens / 1_000_000) * in_per_1m + (output_tokens / 1_000_000) * out_per_1m


def track_cost(
    db: Session,
    user_id: int,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    conversation_id: int | None = None,
    mentor_id: int | None = None,
    purpose: str = "chat",
    billed_user_id: int | None = None,
) -> CostEvent:
    """Persiste un cost_event. Fail-safe: nunca tira excepción a producción."""
    try:
        usd = estimate_usd_cost(model, input_tokens, output_tokens)
        ev = CostEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            mentor_id=mentor_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            usd_cost=usd,
            purpose=purpose,
            billed_user_id=billed_user_id if billed_user_id is not None else None,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev
    except Exception:
        db.rollback()
        # No re-raise — el costo no se trackea pero el chat sigue
        return None  # type: ignore[return-value]

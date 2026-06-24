"""
ModelResolver — selects the Claude model per chat request via a 3-tier
cascading chain.

Resolution order (FIXED, hard-coded — see ADR-2 in design):
  1. users.model_override  (winner if NOT NULL)
  2. mentors.model         (winner if NOT NULL)
  3. system default        (env DEFAULT_MODEL — current: claude-haiku-4-5-20251001)

Why a fixed order: we got bitten 3 times today by multi-layer config where
one layer silently overrode another (env vs settings.json vs FastAPI config).
The order is part of the architecture, not a runtime variable. To change
the order, change THIS code in a PR review, not a config flip.

Canon anchors:
  - Alistair Cockburn — Hexagonal Architecture (Ports & Adapters), 2005
    The resolver is a port with a known contract. Cache is an adapter.
  - Robert C. Martin — Clean Architecture, 2017
    Single Responsibility: this module's only reason to change is how
    model selection works.
  - Jez Humble + David Farley — Continuous Delivery, 2010
    Audit log is non-negotiable for production systems.
  - SycEval (arXiv:2502.08177, 2025)
    Don't trust the system's claim about which model ran. Show receipts.

SDD: sdd/per-mentor-model-assignment-v1 (engram obs #1291-#1294)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Final, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.effective_model import (
    ChainEntry,
    EffectiveModelResponse,
    ResolvedModel,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model whitelist — MUST be kept in sync with DB CHECK constraints in
# migrations/20260608_per_mentor_model.sql
#
# Update protocol: PR review required. Update SQL CHECK constraint in the
# SAME PR (otherwise CLI will reject models the DB accepts, or vice versa).
# ---------------------------------------------------------------------------
MODEL_WHITELIST: Final[frozenset[str]] = frozenset({
    "claude-haiku-4-5-20251001",
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
})


def is_valid_model(model: str) -> bool:
    """True iff `model` is in the whitelist. Used by CLI + admin endpoints
    before any write to the DB."""
    return model in MODEL_WHITELIST


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------
class ModelResolver:
    """Resolves the effective model for a (user_id, mentor_id) pair.

    Not a singleton — instantiated per-request or wrapped by CachedModelResolver
    for hot-path use. See model_resolver_cache.py.

    Constructor takes the DB session factory and the system default (from
    settings.default_model). Audit writes are async-dispatched and never
    block the primary resolution path.
    """

    def __init__(self, db_session: Session, default_model: str):
        self._db = db_session
        self._default_model = default_model

    def resolve(
        self,
        user_id: int,
        mentor_id: int,
        conversation_id: Optional[int] = None,
    ) -> ResolvedModel:
        """Resolve effective model for this user × mentor pair.

        Steps:
          1. Single SELECT pulling user.model_override + mentor.model.
          2. Apply cascade: user → mentor → system default.
          3. Async-dispatch audit log write (best-effort, never blocks).
          4. Return ResolvedModel.

        Behavior on invalid IDs (R6 in proposal):
          - Missing user → user_override is treated as NULL (fall through).
          - Missing mentor → mentor.model treated as NULL (fall through).
          - Both missing → return system default with WARNING log.
          - Never raises. Chat must degrade gracefully, not crash.
        """
        user_override, mentor_model = self._query_overrides(user_id, mentor_id)
        effective, source = self._cascade(user_override, mentor_model)

        resolved = ResolvedModel(
            effective_model=effective,
            source=source,
            resolved_at=datetime.now(timezone.utc),
        )

        # Synchronous audit write — FastAPI sync generators run in a thread
        # pool without a running event loop, so the previous asyncio.create_task
        # path silently no-op'd. Best-effort: errors logged, never propagated.
        self._write_audit_sync(
            user_id=user_id,
            mentor_id=mentor_id,
            conversation_id=conversation_id,
            effective_model=effective,
            source=source,
        )

        return resolved

    def resolve_with_chain(
        self,
        user_id: int,
        mentor_id: int,
    ) -> EffectiveModelResponse:
        """Variant used by the admin observability endpoint.

        Differences from resolve():
          - Returns the FULL chain (all 3 layers, including losing ones).
          - Does NOT write to audit (this is a debug surface, not a resolution event).
          - Does NOT consult the cache (always fresh from DB).
        """
        user_override, mentor_model = self._query_overrides(user_id, mentor_id)
        effective, source = self._cascade(user_override, mentor_model)

        chain = [
            ChainEntry(
                layer="user_override",
                user_id=user_id,
                value=user_override,
                exists=user_override is not None,
            ),
            ChainEntry(
                layer="mentor_default",
                mentor_id=mentor_id,
                value=mentor_model,
                exists=mentor_model is not None,
            ),
            ChainEntry(
                layer="system_default",
                value=self._default_model,
                exists=True,
            ),
        ]

        return EffectiveModelResponse(
            effective_model=effective,
            source=source,
            chain=chain,
            resolved_at=datetime.now(timezone.utc),
        )

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------
    def _query_overrides(self, user_id: int, mentor_id: int) -> tuple[Optional[str], Optional[str]]:
        """Single SELECT pulling user.model_override + mentor.model.

        Returns (user_override, mentor_model). Either may be None if:
          - The column value is NULL
          - The row does not exist (invalid ID)
        """
        sql = text("""
            SELECT
              (SELECT model_override FROM users   WHERE id = :uid) AS user_override,
              (SELECT model          FROM mentors WHERE id = :mid) AS mentor_model
        """)
        result = self._db.execute(sql, {"uid": user_id, "mid": mentor_id}).fetchone()
        if result is None:
            logger.warning(
                "Empty SELECT for user_id=%s mentor_id=%s — both treated as NULL",
                user_id, mentor_id,
            )
            return None, None
        return result.user_override, result.mentor_model

    def _cascade(
        self,
        user_override: Optional[str],
        mentor_model: Optional[str],
    ) -> tuple[str, str]:
        """Apply the fixed resolution order.

        Returns (effective_model, source).
        """
        if user_override is not None:
            if not is_valid_model(user_override):
                logger.error(
                    "Invalid model in users.model_override: %r — falling through",
                    user_override,
                )
            else:
                return user_override, "user_override"

        if mentor_model is not None:
            if not is_valid_model(mentor_model):
                logger.error(
                    "Invalid model in mentors.model: %r — falling through",
                    mentor_model,
                )
            else:
                return mentor_model, "mentor_default"

        return self._default_model, "system_default"

    def _write_audit_sync(
        self,
        user_id: int,
        mentor_id: int,
        conversation_id: Optional[int],
        effective_model: str,
        source: str,
    ) -> None:
        """Synchronous append-only write to model_resolution_audit.

        Best-effort. Logs ERROR on failure but does NOT raise — chat
        resolution must not depend on audit availability.

        Uses the request's DB session. Wrapped in try/except so a session
        in a weird state (uncommitted parent transaction, etc.) does not
        break the chat request.
        """
        try:
            sql = text("""
                INSERT INTO model_resolution_audit
                  (user_id, mentor_id, conversation_id, effective_model, source)
                VALUES (:uid, :mid, :cid, :model, :source)
            """)
            self._db.execute(sql, {
                "uid": user_id,
                "mid": mentor_id,
                "cid": conversation_id,
                "model": effective_model,
                "source": source,
            })
            self._db.commit()
        except Exception as e:
            logger.error("Audit write failed: %s", e, exc_info=True)

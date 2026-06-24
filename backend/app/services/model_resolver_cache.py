"""
CachedModelResolver — TTL cache wrapper around ModelResolver.

Wraps the resolver with a 60-second TTL LRU cache for hot-path use
(every chat message triggers a resolve call).

Design choice: TTL-only invalidation. Cross-process explicit invalidation
(e.g. CLI updates → notify FastAPI) adds complexity for a low-frequency
operation (admin changes a model assignment). 60s staleness window is
acceptable.

If you need instant invalidation, call POST /admin/cache/invalidate
after the CLI update — that hits the same Python process.

Design ref: sdd/per-mentor-model-assignment-v1/design ADR-2 (engram obs #1293)
Canon: Cockburn — Hexagonal Architecture (Ports & Adapters), 2005.
The cache is an adapter that wraps the port without changing the contract.
"""

import time
from typing import Optional

from app.schemas.effective_model import EffectiveModelResponse, ResolvedModel
from app.services.model_resolver import ModelResolver


CACHE_TTL_SECONDS = 60
CACHE_MAX_SIZE = 1024


class CachedModelResolver:
    """Same interface as ModelResolver — drop-in replacement.

    Internally maintains an LRU dict capped at CACHE_MAX_SIZE entries.
    Each entry: (user_id, mentor_id) → (resolved: ResolvedModel, cached_at: float).

    Entries beyond TTL are re-fetched on next access.
    Entries beyond CACHE_MAX_SIZE are evicted in LRU order on insert.
    """

    def __init__(self, inner: ModelResolver):
        self._inner = inner
        self._cache: dict[tuple[int, int], tuple[ResolvedModel, float]] = {}

    def resolve(
        self,
        user_id: int,
        mentor_id: int,
        conversation_id: Optional[int] = None,
    ) -> ResolvedModel:
        key = (user_id, mentor_id)
        now = time.monotonic()

        cached = self._cache.get(key)
        if cached is not None:
            resolved, cached_at = cached
            if (now - cached_at) < CACHE_TTL_SECONDS:
                # Cache hit — but still emit audit for THIS resolution event
                # (audit semantics: every chat message gets a row, even if
                # model was cached).
                if conversation_id is not None:
                    # Re-dispatch audit for the conversation (cached resolution
                    # is still a resolution event).
                    try:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        loop.create_task(self._inner._write_audit(
                            user_id=user_id,
                            mentor_id=mentor_id,
                            conversation_id=conversation_id,
                            effective_model=resolved.effective_model,
                            source=resolved.source,
                        ))
                    except RuntimeError:
                        pass
                return resolved

        # Cache miss or stale — fetch fresh
        resolved = self._inner.resolve(user_id, mentor_id, conversation_id)

        # LRU eviction if over capacity
        if len(self._cache) >= CACHE_MAX_SIZE:
            # Evict oldest entry (lowest cached_at)
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        self._cache[key] = (resolved, now)
        return resolved

    def resolve_with_chain(
        self,
        user_id: int,
        mentor_id: int,
    ) -> EffectiveModelResponse:
        """Pass-through — observability calls always fresh, never cached."""
        return self._inner.resolve_with_chain(user_id, mentor_id)

    def invalidate(self, user_id: int, mentor_id: int) -> None:
        """Remove a specific (user, mentor) entry from the cache."""
        self._cache.pop((user_id, mentor_id), None)

    def invalidate_user(self, user_id: int) -> None:
        """Remove all entries for a given user_id."""
        to_remove = [k for k in self._cache if k[0] == user_id]
        for k in to_remove:
            del self._cache[k]

    def invalidate_mentor(self, mentor_id: int) -> None:
        """Remove all entries for a given mentor_id."""
        to_remove = [k for k in self._cache if k[1] == mentor_id]
        for k in to_remove:
            del self._cache[k]

    def clear(self) -> None:
        """Drop the entire cache. Used by admin endpoint emergency."""
        self._cache.clear()

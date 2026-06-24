"""
context_window — pure token estimation and history trimming.

Inner-hex domain service: stdlib-only imports, no I/O, no SDK, no clock.
Same inputs always produce same outputs (referentially transparent).
Cockburn 2005 — Ports & Adapters: this is policy; callers are adapters.
"""

import copy
import json
from typing import Any

# Fixed overhead per image block per Anthropic published guidance (default quality).
_IMAGE_TOKENS = 1568

# Fixed overhead per message for role/structure framing (role key + list overhead).
_MESSAGE_OVERHEAD = 4


def estimate_tokens(content: str | list[Any]) -> int:
    """
    Return an integer approximation of the token cost of a message content value.

    For plain string content: len(json.dumps(content)) // 4
    For multimodal list-of-blocks: sum text estimates + 1568 per image block.
    Return value is always >= 0.
    """
    try:
        if isinstance(content, str):
            return max(0, len(json.dumps(content, ensure_ascii=False)) // 4)

        if isinstance(content, list):
            total = 0
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "text":
                    total += max(0, len(json.dumps(block.get("text", ""), ensure_ascii=False)) // 4)
                elif block_type == "image":
                    total += _IMAGE_TOKENS
                else:
                    serialized = json.dumps(block, ensure_ascii=False)
                    total += max(0, len(serialized) // 4)
            return max(0, total)

        # Fallback: serialize whatever was passed.
        return max(0, len(json.dumps(content, ensure_ascii=False)) // 4)

    except Exception:
        return 0


def _estimate_history_tokens(messages: list[dict]) -> int:
    """Sum token estimates across a full message list, including per-message overhead."""
    total = 0
    for msg in messages:
        total += _MESSAGE_OVERHEAD
        total += estimate_tokens(msg.get("content", ""))
    return max(0, total)


def trim_history(
    messages: list[dict],
    max_tokens: int,
    output_reserved: int,
) -> tuple[list[dict], dict]:
    """
    Return (trimmed_messages, status) where trimmed_messages fits within budget.

    Drop strategy: oldest-first, always preserve at least the last 2 messages.
    Operates on a deep copy — never mutates the input list.

    status keys:
        was_trimmed: bool
        dropped_count: int
        tokens_before: int
        tokens_after: int
        utilization_before: float
        utilization_after: float

    Raises ValueError if the result would be an empty list (bug guard).
    """
    if not messages:
        return ([], {
            "was_trimmed": False,
            "dropped_count": 0,
            "tokens_before": 0,
            "tokens_after": 0,
            "utilization_before": 0.0,
            "utilization_after": 0.0,
        })

    budget = max_tokens - output_reserved
    working = copy.deepcopy(messages)

    tokens_before = _estimate_history_tokens(working)
    utilization_before = tokens_before / budget if budget > 0 else 0.0

    if tokens_before <= budget:
        return (working, {
            "was_trimmed": False,
            "dropped_count": 0,
            "tokens_before": tokens_before,
            "tokens_after": tokens_before,
            "utilization_before": utilization_before,
            "utilization_after": utilization_before,
        })

    dropped_count = 0
    # Keep dropping from the front while over budget and more than 2 remain.
    while _estimate_history_tokens(working) > budget and len(working) > 2:
        working.pop(0)
        dropped_count += 1

    if not working:
        raise ValueError(
            "trim_history produced empty messages list — cannot call Anthropic API with zero messages"
        )

    tokens_after = _estimate_history_tokens(working)
    utilization_after = tokens_after / budget if budget > 0 else 0.0

    return (working, {
        "was_trimmed": True,
        "dropped_count": dropped_count,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "utilization_before": utilization_before,
        "utilization_after": utilization_after,
    })


# ============================================================
# Aliases and shared exports (added: anoven-shared-projects)
# ============================================================

# Alias para compatibilidad con referencias en design/tasks que usan 'count_tokens'.
# La función real se llama estimate_tokens — este alias permite usar cualquier nombre.
count_tokens = estimate_tokens

# STOPWORDS exportadas para uso de SharedProjectContextBuilder.
# Importar desde context_builders/shared_project.py si se necesita la lista completa.
# Esta es una versión mínima para búsqueda, diferente del set TF-IDF.
STOPWORDS = frozenset({
    "que", "lo", "de", "del", "el", "la", "los", "las", "un", "una", "uno",
    "y", "o", "es", "se", "te", "me", "mi", "tu", "su", "no", "si", "ya",
    "como", "más", "muy", "hay", "the", "a", "an", "of", "in", "on", "is",
})

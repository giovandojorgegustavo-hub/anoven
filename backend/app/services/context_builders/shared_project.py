"""
SharedProjectContextBuilder — Strategy D Hybrid para proyectos compartidos.

Algoritmo (ADR-4, ADR-5):
  1. Cargar historial completo de la conversación (DB)
  2. Aplicar trim_history() con presupuesto (max_tokens - 250 reservados para summary)
  3. Identificar mensajes descartados → agrupar por author_user_id
  4. TF-IDF stdlib para top-N keywords por autor (top-5 autores por msg count)
  5. Formatear bloque summary como system message
  6. Inyectar summary ANTES de la historia recortada

Propiedades:
  - Determinista: mismo input → mismo output (idempotente)
  - Sin deps externos: collections.Counter, math.log, re (stdlib)
  - Testable sin mocks: lógica pura separada de I/O DB

Invariante A1.3 STRICT: NUNCA importar fastapi.
Invariante A1.5: configuración via env (os.environ.get), no hardcoded.

ADR-5 — Kent Beck, TDD By Example, 2002:
  "Deterministic units come first; mocks of non-deterministic services last."
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services.context_window import estimate_tokens, trim_history

if TYPE_CHECKING:
    pass


# ============================================================
# Configuración via env (A1.5)
# ============================================================

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


SHARED_CONTEXT_MAX_AUTHORS: int = _env_int("SHARED_CONTEXT_MAX_AUTHORS", 5)
SHARED_CONTEXT_KEYWORDS_PER_AUTHOR: int = _env_int("SHARED_CONTEXT_KEYWORDS_PER_AUTHOR", 10)
SHARED_CONTEXT_TOKENS_PER_AUTHOR: int = _env_int("SHARED_CONTEXT_TOKENS_PER_AUTHOR", 50)

# Budget total para el bloque de author summary (suma de todos los autores)
_SUMMARY_TOKEN_BUDGET = SHARED_CONTEXT_MAX_AUTHORS * SHARED_CONTEXT_TOKENS_PER_AUTHOR


# ============================================================
# Stopwords (español + inglés mínimas para TF-IDF)
# ============================================================

STOPWORDS: frozenset[str] = frozenset({
    # Español
    "de", "del", "la", "el", "los", "las", "un", "una", "uno", "unos", "unas",
    "y", "o", "e", "u", "a", "al", "en", "con", "sin", "por", "para", "que",
    "qué", "es", "se", "lo", "te", "me", "mi", "tu", "su", "yo", "vos", "él",
    "no", "si", "sí", "ya", "como", "más", "muy", "tan", "hay", "hoy",
    "ser", "sos", "son", "soy", "era", "fue", "ha", "he", "han", "haber",
    "este", "esta", "esto", "ese", "esa", "eso", "esta", "aquí", "ahí",
    "puede", "podés", "quiero", "quiero", "tengo", "tener", "tiene", "tienes",
    "hacer", "hace", "hago", "decir", "dice", "digo", "ir", "voy", "ver",
    "pero", "sino", "también", "además", "porque", "porqué", "cuando", "donde",
    "sobre", "bajo", "entre", "hasta", "desde", "después", "antes", "ahora",
    "todos", "todo", "toda", "todas", "cada", "otro", "otra", "otros", "otras",
    # Inglés mínimo
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
    "but", "not", "is", "are", "was", "were", "be", "been", "have", "has",
    "do", "does", "did", "this", "that", "it", "he", "she", "we", "they",
    "with", "from", "by", "as", "so", "if", "my", "your", "our", "their",
})


def _tokenize(text: str) -> list[str]:
    """
    Tokeniza texto: lowercase, solo tokens alfabéticos >= 3 chars, sin stopwords.
    """
    tokens = re.findall(r"[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{3,}", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def _compute_tfidf(
    author_tokens: list[str],
    all_authors_tokens: dict[int, list[str]],
) -> dict[str, float]:
    """
    Calcula TF-IDF para los tokens de un autor dado el corpus de todos los autores.

    TF  = log(1 + count_of_term_in_author_corpus)
    IDF = log(N_authors / (1 + |authors_containing_term|))

    Returns: dict {term: score} (solo los términos del autor).
    """
    n_authors = len(all_authors_tokens)
    if n_authors == 0:
        return {}

    # TF para este autor
    tf = Counter(author_tokens)

    # IDF: en cuántos autores aparece cada término
    doc_freq: Counter[str] = Counter()
    for tokens in all_authors_tokens.values():
        for term in set(tokens):
            doc_freq[term] += 1

    scores: dict[str, float] = {}
    for term, count in tf.items():
        tf_score = math.log(1 + count)
        idf_score = math.log(n_authors / (1 + doc_freq.get(term, 0)))
        scores[term] = tf_score * idf_score

    return scores


def _top_n_keywords(scores: dict[str, float], n: int) -> list[str]:
    """Devuelve los top-n keywords ordenados por score descendente."""
    return [
        term for term, _ in sorted(scores.items(), key=lambda x: -x[1])
    ][:n]


# ============================================================
# SharedProjectContextBuilder
# ============================================================

class SharedProjectContextBuilder:
    """
    Construye el contexto para chats en proyectos compartidos.

    Para mensajes descartados por trim_history, genera un bloque de summary
    por autor con keywords TF-IDF, preservando el hilo narrativo de cada
    colaborador del proyecto.
    """

    def __init__(self, db: Session):
        self.db = db
        self._max_authors = SHARED_CONTEXT_MAX_AUTHORS
        self._keywords_per_author = SHARED_CONTEXT_KEYWORDS_PER_AUTHOR
        self._tokens_per_author = SHARED_CONTEXT_TOKENS_PER_AUTHOR

    def build(
        self,
        conversation_id: int,
        max_tokens: int,
        output_reserved: int,
    ) -> tuple[list[dict], dict]:
        """
        Construye la lista de mensajes con author summary prefix.

        Step 1: Cargar historial + trim con budget reducido (max - summary_budget)
        Step 2: Si no hay dropped → retornar trim estándar
        Step 3: Agrupar dropped por author_user_id → TF-IDF keywords
        Step 4: Formatear summary block (max SUMMARY_TOKEN_BUDGET tokens)
        Step 5: Retornar [system summary] + trimmed history
        """
        from app.repositories.message_repo import MessageRepository

        msg_repo = MessageRepository(self.db)
        all_msgs = msg_repo.list_for_conversation(conversation_id)

        if not all_msgs:
            return [], {"was_trimmed": False, "dropped_count": 0,
                        "tokens_before": 0, "tokens_after": 0,
                        "utilization_before": 0.0, "utilization_after": 0.0}

        # Reservar tokens para el bloque summary
        summary_reserve = _SUMMARY_TOKEN_BUDGET
        adjusted_max_tokens = max(max_tokens - summary_reserve, output_reserved + 100)

        # Construir raw history con author_user_id incluido para tracking
        raw_history: list[dict] = [
            {
                "role": m.role,
                "content": m.content,
                "_author_user_id": m.author_user_id,
                "_msg_id": m.id,
            }
            for m in all_msgs
        ]

        trimmed_with_meta, status = trim_history(
            [{"role": m["role"], "content": m["content"]} for m in raw_history],
            adjusted_max_tokens,
            output_reserved,
        )

        # Identificar mensajes dropped comparando por posición
        n_dropped = status.get("dropped_count", 0)
        dropped_with_meta = raw_history[:n_dropped]
        trimmed_with_meta_full = raw_history[n_dropped:]

        # Si no se descartó nada, retornar sin summary
        if n_dropped == 0:
            final_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in trimmed_with_meta_full
            ]
            return final_messages, status

        # Agrupar mensajes descartados por autor (skip assistant: author_user_id=None)
        groups: dict[int, list[str]] = defaultdict(list)
        for m in dropped_with_meta:
            author_id = m.get("_author_user_id")
            if author_id is not None:
                groups[author_id].append(m["content"])

        if not groups:
            # Solo mensajes del assistant descartados — no hay summary util
            final_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in trimmed_with_meta_full
            ]
            return final_messages, status

        # Seleccionar top-MAX_AUTHORS por cantidad de mensajes descartados
        sorted_authors = sorted(groups.items(), key=lambda x: -len(x[1]))
        top_authors = sorted_authors[:self._max_authors]

        # Tokenizar corpus por autor (para TF-IDF cross-author)
        all_authors_tokens: dict[int, list[str]] = {}
        for author_id, msgs in top_authors:
            combined_text = " ".join(msgs)
            all_authors_tokens[author_id] = _tokenize(combined_text)

        # Generar summary lines (respetar budget por autor)
        summary_lines: list[str] = []
        total_summary_tokens = 0

        for author_id, author_tokens in all_authors_tokens.items():
            if not author_tokens:
                continue

            scores = _compute_tfidf(author_tokens, all_authors_tokens)
            keywords = _top_n_keywords(scores, self._keywords_per_author)

            if not keywords:
                continue

            display_name = self._get_display_name(author_id)
            msg_count = len(groups[author_id])
            keywords_str = ", ".join(keywords)

            line = (
                f"- {display_name}: {keywords_str}. "
                f"Total mensajes omitidos: {msg_count}."
            )

            line_tokens = estimate_tokens(line)
            if total_summary_tokens + line_tokens > _SUMMARY_TOKEN_BUDGET:
                # Este autor no cabe — parar (no truncar a la mitad)
                break

            summary_lines.append(line)
            total_summary_tokens += line_tokens

        if summary_lines:
            summary_text = (
                "Resumen de mensajes anteriores omitidos por contexto:\n"
                + "\n".join(summary_lines)
            )
            summary_block = {"role": "system", "content": summary_text}
        else:
            summary_block = None

        # Ensamblar resultado final
        final_messages: list[dict] = []
        if summary_block is not None:
            final_messages.append(summary_block)

        for m in trimmed_with_meta_full:
            final_messages.append({"role": m["role"], "content": m["content"]})

        # Enriquecer status con info del summary
        status["author_summary_included"] = summary_block is not None
        status["summary_authors"] = len(summary_lines)
        status["summary_tokens"] = total_summary_tokens

        return final_messages, status

    def _get_display_name(self, user_id: int) -> str:
        """
        Devuelve el nombre redactado del autor para el summary block.

        Estrategia: full_name si existe, sino local-part del email.
        Nunca expone el email completo en el prompt (privacidad).
        """
        try:
            from app.repositories.user_repo import UserRepository
            user = UserRepository(self.db).get_by_id(user_id)
            if user is None:
                return f"Usuario #{user_id}"
            if user.full_name and user.full_name.strip():
                return user.full_name.strip().split()[0]  # Solo primer nombre
            if user.email:
                return user.email.split("@")[0]
            return f"Usuario #{user_id}"
        except Exception:
            return f"Usuario #{user_id}"

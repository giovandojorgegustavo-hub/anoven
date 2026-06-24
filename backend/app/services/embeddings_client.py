"""
embeddings_client — wrapper sobre gemini-embedding-001 (Google AI).

Devuelve vectors de 768 dim (Matryoshka truncation del 3072 nativo) para
encajar en pgvector ivfflat (<=2000 dim).

Singleton lazy del genai.Client para evitar reconectar por llamada.

Canon: Chip Huyen — AI Engineering, 2024 (Tier 2): batch embeddings cuando
el provider lo permite. Acá hacemos batch via embed_content con lista de
contents — Google AI procesa en una sola request.
"""

import logging
import time
from google import genai
from google.genai import types

from app.config import settings


logger = logging.getLogger(__name__)


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 768  # Matryoshka — truncate de 3072 nativo a 768 para ivfflat.


class EmbeddingError(Exception):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.google_ai_api_key:
            raise EmbeddingError("GOOGLE_AI_API_KEY no configurada en .env")
        _client = genai.Client(api_key=settings.google_ai_api_key)
    return _client


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """
    Embed N textos en UNA request. Devuelve lista de vectors (768 dim).

    task_type:
        RETRIEVAL_DOCUMENT — al indexar chunks del PDF.
        RETRIEVAL_QUERY    — al embedar la query del user para retrieval.

    Esta distinción mejora similarity. Google docs lo indican explícito.
    """
    if not texts:
        return []
    client = _get_client()
    # Retry con backoff exponencial para 429 (rate limit del free tier Gemini).
    delays = [0, 2, 5, 12, 25]  # ~44 seg total worst case
    last_exc: Exception | None = None
    for attempt, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        try:
            resp = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=EMBEDDING_DIM,
                    task_type=task_type,
                ),
            )
            break
        except Exception as e:
            last_exc = e
            msg = str(e)
            is_rate = "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if not is_rate or attempt == len(delays) - 1:
                logger.exception("Gemini embed_content failed")
                raise EmbeddingError(f"embed falló: {type(e).__name__}: {msg[:200]}")
            logger.warning(f"embed 429, retrying in {delays[attempt + 1]}s (attempt {attempt + 1}/{len(delays) - 1})")
    else:
        # Should not happen — break exits the loop on success.
        raise EmbeddingError(f"embed exhausted retries: {last_exc}")

    vectors = [list(e.values) for e in (resp.embeddings or [])]
    if len(vectors) != len(texts):
        raise EmbeddingError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
    return vectors


def embed_one(text: str, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Embed un texto. Default task_type = QUERY (uso típico = retrieval)."""
    return embed_texts([text], task_type=task_type)[0]

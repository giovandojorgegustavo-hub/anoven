"""
image_generator — Google Imagen 4 / Gemini para generar imágenes.

Default: imagen-4.0-generate-001 (calidad editorial).
Ultra:   imagen-4.0-ultra-generate-001 (top calidad, hero shots).

Anteriormente usaba gemini-3.1-flash-image (rápido pero básico).

Devuelve bytes PNG. Raises ImageGenerationError con mensaje legible si falla.
"""

import logging
from google import genai
from google.genai import types

from app.config import settings


logger = logging.getLogger(__name__)


# Mapping quality -> Google model name.
MODELS = {
    "standard": "imagen-4.0-generate-001",
    "ultra": "imagen-4.0-ultra-generate-001",
}
DEFAULT_QUALITY = "standard"


class ImageGenerationError(Exception):
    pass


_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.google_ai_api_key:
            raise ImageGenerationError("GOOGLE_AI_API_KEY no configurada en .env")
        _client = genai.Client(api_key=settings.google_ai_api_key)
    return _client


def generate_image(prompt: str, quality: str = DEFAULT_QUALITY) -> bytes:
    """
    Genera una imagen a partir de un prompt en inglés.

    quality:
        "standard" -> imagen-4.0-generate-001 (default, ~$0.04/img, calidad editorial)
        "ultra"    -> imagen-4.0-ultra-generate-001 (~$0.06/img, max calidad)

    Devuelve los bytes PNG de la primera imagen generada.
    """
    if not prompt or not prompt.strip():
        raise ImageGenerationError("Prompt vacío")

    model = MODELS.get(quality, MODELS[DEFAULT_QUALITY])
    client = _get_client()

    try:
        response = client.models.generate_images(
            model=model,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
    except Exception as e:
        logger.exception(f"Imagen API call failed (model={model})")
        raise ImageGenerationError(f"Llamada a {model} falló: {type(e).__name__}: {str(e)[:200]}")

    # Imagen 4 returns response.generated_images[i].image.image_bytes
    for gen in getattr(response, "generated_images", None) or []:
        img = getattr(gen, "image", None)
        if img is not None:
            data = getattr(img, "image_bytes", None)
            if data:
                return data

    raise ImageGenerationError(f"{model} no devolvió imagen en la respuesta")

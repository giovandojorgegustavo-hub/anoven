"""
Auto-generación de título para una conversación.

Se dispara UNA SOLA VEZ por conversación, después del primer turn completo
(1 mensaje del user + 1 del assistant). El título es una frase de 3 a 6
palabras que resume el tema, para que el sidebar muestre algo legible en
vez de "Conversación #42".

Usamos Haiku (modelo más barato y rápido) porque no necesitamos rigor de
canon — solo summarizar tema.
"""

import re

from anthropic import Anthropic

from app.config import settings


_client = Anthropic(api_key=settings.anthropic_api_key)


TITLE_SYSTEM_PROMPT = """\
Tu único trabajo es generar un TÍTULO CORTO para una conversación entre
un user y un mentor de Anoven.

REGLAS DURAS:

1. EXACTAMENTE entre 3 y 6 palabras. Ni más, ni menos.
2. En español rioplatense.
3. Captura el TEMA, no la pregunta. Ej: "Pricing café boutique" no "Cómo poner precio".
4. Si menciona un nombre propio de proyecto o negocio, inclílo. Ej: "Crecimiento Bonabowl Instagram".
5. Sin signos de puntuación al inicio/final. Sin comillas. Sin emojis.
6. NUNCA expliques. NUNCA escribas "el título es:" ni nada parecido.
7. Tu output debe ser SOLO el título plano, en una línea, nada más.

EJEMPLOS DE BUENOS TÍTULOS:
- Pricing café boutique
- Crecimiento Bonabowl Instagram
- Manejo del estrés laboral
- Arquitectura hexagonal microservicios
- Posicionamiento marca personal

EJEMPLOS DE MALOS TÍTULOS (no hagas esto):
- "Cómo hacer crecer mi negocio" (vago, pregunta)
- Crecimiento (1 palabra, vago)
- Marketing y posicionamiento de marca para café boutique en Buenos Aires (8+ palabras)
"""


def generate_title(user_message: str, assistant_message: str) -> str:
    """
    Llama a Claude Haiku con los dos primeros mensajes y devuelve un título
    limpio (3-6 palabras). Si el modelo devuelve algo raro, sanitizamos.
    """
    user_message = user_message.strip()[:500]
    assistant_message = assistant_message.strip()[:1500]

    response = _client.messages.create(
        model=settings.default_model,
        max_tokens=40,
        system=TITLE_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Mensaje del user:\n{user_message}\n\n"
                    f"Respuesta del mentor:\n{assistant_message}\n\n"
                    "Devolveme el título."
                ),
            }
        ],
    )

    raw = response.content[0].text if response.content else ""
    return _sanitize_title(raw)


def _sanitize_title(raw: str) -> str:
    """
    Limpia comillas, prefijos tipo 'Título:', puntuación de borde, espacios.
    Si el resultado queda fuera de 3-6 palabras, lo recortamos.
    """
    title = raw.strip()
    # Sacamos prefijos comunes que aparecen aún diciendo que no
    title = re.sub(r"^(título|titulo|title)\s*:\s*", "", title, flags=re.IGNORECASE)
    # Sacamos comillas envolventes
    title = title.strip("\"'`«»“”")
    # Sacamos punto/coma final
    title = title.rstrip(".,;:!?")
    # Una sola línea
    title = title.splitlines()[0].strip() if title else ""
    # Si el modelo se zarpó con palabras, cortamos a 6.
    words = title.split()
    if len(words) > 6:
        title = " ".join(words[:6])
    # Fallback si quedó vacío.
    if not title:
        title = "Conversación nueva"
    return title[:200]  # cap defensivo

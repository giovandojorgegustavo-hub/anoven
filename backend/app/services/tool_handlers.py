"""
Tool Handlers — mentor-tools-system SDD cycle.

Each handler is async. Handlers receive:
  - input: dict  (already validated against the schema by Anthropic)
  - mentor: Mentor
  - context: ToolContext

Handlers MUST return a dict (serialized to JSON string by dispatcher).
Handlers MUST NOT raise — the dispatcher wraps all calls in try/except.
If a handler raises, the dispatcher returns status=error to the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.tool_dispatcher import ToolContext

logger = logging.getLogger(__name__)

IMAGE_STORAGE_ROOT = Path("/home/anoven/anoven-app/storage/uploads")


def _truncate(s: str, max_chars: int) -> str:
    """Truncate a string to max_chars, appending '…' if cut."""
    if len(s) <= max_chars:
        return s
    return s[:max_chars - 1] + "…"


async def handle_mem_search(
    *,
    input: dict,
    mentor: Any,
    context: "ToolContext",
) -> dict:
    """
    Search engram for observations matching .

    Returns:
        {
            "count": int,
            "results": [
                {"id": int, "title": str, "content": str (first 600 chars),
                 "created_at": str | None},
                ...
            ]
        }

    Timeout: 1.5s (enforced by dispatcher via asyncio.wait_for).
    Failure: any exception propagates to dispatcher → status=error, LLM sees error dict.
    """
    from app.services.engram_client import engram

    query = input["query"]
    limit = min(int(input.get("limit", 5)), 10)
    project = context.engram_project

    # engram.search is synchronous HTTP — wrap in to_thread so the timeout fires
    results = await asyncio.to_thread(
        engram.search,
        query,
        project=project,
        limit=limit,
    )

    shaped = [
        {
            "id": r.get("id"),
            "title": r.get("title", ""),
            "content": _truncate(r.get("content", "").strip(), 600),
            "created_at": r.get("created_at"),
        }
        for r in results
    ]

    logger.info(
        "tool_mem_search completed",
        extra={
            "query": query[:80],
            "count": len(shaped),
            "mentor": mentor.slug,
            "project": project,
        },
    )

    return {"count": len(shaped), "results": shaped}


async def handle_generate_image(
    *,
    input: dict,
    mentor: Any,
    context: "ToolContext",
) -> dict:
    """
    Generate image via Gemini. Save as Attachment in DB linked to conversation.

    Returns:
        {
            "image_url": str,       # /storage/{user_id}/{filename}.png
            "attachment_id": int,   # DB Attachment.id
            "prompt_used": str,
        }

    Timeout: 30s (enforced by dispatcher — image gen is slow).
    On failure: raises (dispatcher catches → status=error, LLM sees error dict).
    """
    from app.services.image_generator import generate_image, ImageGenerationError
    from app.models.attachment import Attachment

    prompt = input["prompt"].strip()
    if not prompt:
        raise ValueError("prompt vacío")
    quality = (input.get("quality") or "standard").lower()
    if quality not in ("standard", "ultra"):
        quality = "standard"

    # image_generator.generate_image is synchronous — wrap so 30s timeout fires
    img_bytes = await asyncio.to_thread(generate_image, prompt, quality)

    # Save to filesystem
    user_dir = IMAGE_STORAGE_ROOT / str(context.user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    (user_dir / filename).write_bytes(img_bytes)
    relative_path = f"{context.user_id}/{filename}"
    image_url = f"/storage/{relative_path}"

    # Persist Attachment record via DB session from ToolContext
    db = context.db
    if db is None:
        raise RuntimeError("ToolContext.db is None — cannot save Attachment")

    att = Attachment(
        user_id=context.user_id,
        mime_type="image/png",
        file_path=relative_path,
        original_name=None,
        size_bytes=len(img_bytes),
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    logger.info(
        "tool_generate_image completed",
        extra={
            "attachment_id": att.id,
            "prompt": prompt[:80],
            "mentor": mentor.slug,
            "user_id": context.user_id,
        },
    )

    return {
        "image_url": image_url,
        "attachment_id": att.id,
        "file_path": relative_path,
        "mime_type": "image/png",
        "prompt_used": prompt,
    }


async def handle_mem_save(
    *,
    input: dict,
    mentor: Any,
    context: "ToolContext",
) -> dict:
    """
    Save a durable observation to engram memory.

    Rate limits are enforced by the dispatcher (NOT here):
      - 1 invocation per user turn
      - 3 invocations per conversation total
    If rate-limited, dispatcher returns status=rate_limited BEFORE calling this handler.

    Returns:
        {"success": True, "id": int, "title": str, "type": str}
        On engram failure: raises (dispatcher catches -> status=error, LLM sees error dict).

    Timeout: 2.0s (enforced by dispatcher via asyncio.wait_for).
    """
    from app.services.engram_client import engram

    title = input["title"].strip()
    body = input["content"].strip()
    obs_type = input.get("type", "user-fact")
    project = context.engram_project
    session_id = context.engram_session_id

    # engram.save_observation is synchronous HTTP -- wrap in to_thread so the timeout fires
    saved = await asyncio.to_thread(
        engram.save_observation,
        session_id=session_id,
        project=project,
        title=title,
        content=body,
        obs_type=obs_type,
    )

    if saved is None:
        # engram returned a non-201 response or raised internally; it logged the detail.
        raise RuntimeError("engram.save_observation returned None -- check server logs")

    logger.info(
        "tool_mem_save completed",
        extra={
            "id": saved.get("id"),
            "title": title[:80],
            "obs_type": obs_type,
            "mentor": mentor.slug,
            "project": project,
        },
    )

    return {
        "success": True,
        "id": saved.get("id"),
        "title": title,
        "type": obs_type,
    }

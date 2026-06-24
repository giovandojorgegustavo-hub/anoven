"""
Pydantic schemas for the model resolution observability surface.

Used by:
  - GET /admin/effective-model endpoint (returns full chain)
  - CLI wrapper /usr/local/bin/anoven-model (parses JSON response)
  - ModelResolver service (internal return shape)

Design ref: sdd/per-mentor-model-assignment-v1/design (engram obs #1293)
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


Source = Literal["user_override", "mentor_default", "system_default"]


class ResolvedModel(BaseModel):
    """Internal resolver return value. Pure data."""
    effective_model: str
    source: Source
    resolved_at: datetime


class ChainEntry(BaseModel):
    """One layer of the resolution chain.

    `exists` is True iff this layer has a non-NULL value configured for the
    target (user/mentor). The system_default layer always has exists=True
    because it falls back to env DEFAULT_MODEL.
    """
    layer: Source
    value: Optional[str] = None
    exists: bool
    user_id: Optional[int] = None
    mentor_id: Optional[int] = None


class EffectiveModelResponse(BaseModel):
    """Full observability response — used by admin endpoint and CLI."""
    effective_model: str
    source: Source
    chain: list[ChainEntry] = Field(min_length=3, max_length=3)
    resolved_at: datetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "effective_model": "claude-opus-4-7",
                "source": "user_override",
                "chain": [
                    {"layer": "user_override", "user_id": 12, "value": "claude-opus-4-7", "exists": True},
                    {"layer": "mentor_default", "mentor_id": 5, "value": "claude-sonnet-4-6", "exists": True},
                    {"layer": "system_default", "value": "claude-haiku-4-5-20251001", "exists": True},
                ],
                "resolved_at": "2026-06-08T14:23:45Z",
            }
        }
    }

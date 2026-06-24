"""
Schemas Pydantic para Rule.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class RuleResponse(BaseModel):
    id: int
    user_id: int
    project_id: int | None
    use_case_id: int | None
    content: str
    active: bool
    scope: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    project_id: int | None = None
    use_case_id: int | None = None


class RuleToggleActive(BaseModel):
    active: bool

"""
Schemas Pydantic para Project y UseCase.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class UseCaseResponse(BaseModel):
    id: int
    project_id: int
    slug: str
    name: str
    description: str | None
    is_default: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    slug: str
    name: str
    description: str | None
    is_default: bool
    created_at: datetime
    use_cases: list[UseCaseResponse] = []

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class UseCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

"""
Schemas Pydantic para Interview / Entrevistador.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class InterviewAttemptResponse(BaseModel):
    """Lo que el backend devuelve al frontend cuando consulta un intento."""

    id: int
    user_id: int
    status: str
    score: int | None
    evaluator_feedback: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class InterviewMessageResponse(BaseModel):
    """Un mensaje del chat de entrevista."""

    id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    """Body del POST /interviews/{id}/messages — el user manda su texto."""

    content: str = Field(min_length=1, max_length=4000)


class MatchedMentor(BaseModel):
    """Un mentor seleccionado por el MentorMatcher para el user."""

    slug: str
    nombre: str
    reason: str


class EvaluationResponse(BaseModel):
    """
    Lo que devuelve POST /interviews/{id}/evaluate al frontend.
    Incluye highlights (qué entendió el Evaluador) + matched_mentors
    (qué eligió el MentorMatcher). El profile_json y el feedback interno
    se quedan en BD.
    """

    score: int
    highlights: list[str]
    matched_mentors: list[MatchedMentor]

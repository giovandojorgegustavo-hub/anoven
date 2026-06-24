"""
Repository para InterviewAttempt — encapsula todo el SQL.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, desc, func

from app.models.interview_attempt import InterviewAttempt


class InterviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_in_progress_for_user(self, user_id: int) -> InterviewAttempt | None:
        """Busca el intento `in_progress` del user (debería haber máximo 1 a la vez)."""
        stmt = (
            select(InterviewAttempt)
            .where(InterviewAttempt.user_id == user_id)
            .where(InterviewAttempt.status == "in_progress")
            .order_by(desc(InterviewAttempt.started_at))
        )
        return self.db.execute(stmt).scalars().first()

    def get_latest_for_user(self, user_id: int) -> InterviewAttempt | None:
        """Devuelve el intento más reciente del user en cualquier estado."""
        stmt = (
            select(InterviewAttempt)
            .where(InterviewAttempt.user_id == user_id)
            .order_by(desc(InterviewAttempt.started_at))
        )
        return self.db.execute(stmt).scalars().first()

    def count_attempts(self, user_id: int) -> int:
        """Cuántos intentos tuvo el user en total (todos los estados)."""
        stmt = select(func.count(InterviewAttempt.id)).where(
            InterviewAttempt.user_id == user_id
        )
        return self.db.execute(stmt).scalar_one()

    def create(self, user_id: int) -> InterviewAttempt:
        """Crea un intento nuevo en estado `in_progress`."""
        attempt = InterviewAttempt(user_id=user_id, status="in_progress")
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    def save_evaluation(
        self,
        attempt_id: int,
        score: int,
        profile_json: str,
        evaluator_feedback: str,
    ) -> InterviewAttempt:
        """
        Persiste el resultado del Evaluador y mueve el attempt a 'evaluated'.
        El user.onboarding_state YA está en 'passed' desde el cierre — no se toca.
        """
        attempt = self.db.get(InterviewAttempt, attempt_id)
        if attempt is None:
            raise ValueError(f"Attempt {attempt_id} no existe")
        attempt.score = score
        attempt.profile_json = profile_json
        attempt.evaluator_feedback = evaluator_feedback
        attempt.status = "evaluated"
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

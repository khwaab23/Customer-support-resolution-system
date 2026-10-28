from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.models.admin_review import AdminReview


class AdminReviewRepository:
    def __init__(self, session: Session) -> None: self._session = session
    def get(self, review_id: UUID) -> AdminReview | None: return self._session.get(AdminReview, review_id)
    def get_by_workflow(self, workflow_id: str) -> AdminReview | None: return self._session.scalar(select(AdminReview).where(AdminReview.workflow_id == workflow_id))
    def get_by_ticket(self, ticket_id: str) -> AdminReview | None:
        statement = select(AdminReview).where(AdminReview.ticket_id == ticket_id).order_by(AdminReview.created_at.desc())
        return self._session.scalar(statement)
    def list(self, status: str | None, offset: int, limit: int) -> list[AdminReview]:
        stmt = select(AdminReview).order_by(AdminReview.created_at.desc())
        if status: stmt = stmt.where(AdminReview.review_status == status)
        return list(self._session.scalars(stmt.offset(offset).limit(limit)))
    def add(self, review: AdminReview) -> AdminReview: self._session.add(review); return review
    def decide(self, review_id: UUID, version: int, values: dict[str, object]) -> bool:
        result = self._session.execute(update(AdminReview).where(AdminReview.review_id == review_id, AdminReview.version == version, AdminReview.decision.is_(None)).values(**values, version=AdminReview.version + 1))
        return result.rowcount == 1

    def set_resume_state(self, review_id: UUID, state: str) -> None:
        self._session.execute(
            update(AdminReview).where(AdminReview.review_id == review_id).values(resume_state=state)
        )

    def other_approved_review_exists(self, order_id: str, review_id: UUID) -> bool:
        statement = select(
            exists().where(
                AdminReview.order_id == order_id,
                AdminReview.review_id != review_id,
                AdminReview.decision == "APPROVE",
            )
        )
        return bool(self._session.scalar(statement))

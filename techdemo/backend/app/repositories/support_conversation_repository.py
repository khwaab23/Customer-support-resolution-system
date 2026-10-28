from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.support_conversation import SupportConversation


class SupportConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conversation: SupportConversation) -> SupportConversation:
        self._session.add(conversation)
        return conversation

    def get_for_customer(self, conversation_id: UUID, customer_id: str, *, lock: bool = False) -> SupportConversation | None:
        statement = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id,
            SupportConversation.customer_id == customer_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def list_for_customer(self, customer_id: str, offset: int, limit: int) -> list[SupportConversation]:
        statement = (
            select(SupportConversation)
            .where(SupportConversation.customer_id == customer_id)
            .order_by(SupportConversation.updated_at.desc(), SupportConversation.conversation_id.asc())
            .offset(offset).limit(limit)
        )
        return list(self._session.scalars(statement))

    def touch(self, conversation: SupportConversation) -> None:
        conversation.updated_at = datetime.now(timezone.utc)
        conversation.version += 1

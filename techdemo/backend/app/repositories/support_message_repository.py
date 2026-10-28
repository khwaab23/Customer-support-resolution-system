from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.support_message import SupportMessage


class SupportMessageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, message: SupportMessage) -> SupportMessage:
        self._session.add(message)
        return message

    def get_customer_request(self, conversation_id: UUID, request_id: str) -> SupportMessage | None:
        return self._session.scalar(select(SupportMessage).where(
            SupportMessage.conversation_id == conversation_id,
            SupportMessage.sender_role == "CUSTOMER",
            SupportMessage.client_request_id == request_id,
        ))

    def get_assistant_reply(self, conversation_id: UUID, request_id: str) -> SupportMessage | None:
        return self._session.scalar(select(SupportMessage).where(
            SupportMessage.conversation_id == conversation_id,
            SupportMessage.sender_role == "ASSISTANT",
            SupportMessage.metadata_json["reply_to_request_id"].astext == request_id,
        ))

    def list_for_conversation(self, conversation_id: UUID, offset: int, limit: int) -> list[SupportMessage]:
        statement = (
            select(SupportMessage)
            .where(SupportMessage.conversation_id == conversation_id)
            .order_by(SupportMessage.created_at.asc(), SupportMessage.message_id.asc())
            .offset(offset).limit(limit)
        )
        return list(self._session.scalars(statement))

    def recent_for_conversation(self, conversation_id: UUID, limit: int) -> list[SupportMessage]:
        statement = (
            select(SupportMessage)
            .where(SupportMessage.conversation_id == conversation_id)
            .order_by(SupportMessage.created_at.desc(), SupportMessage.message_id.desc())
            .limit(limit)
        )
        return list(reversed(list(self._session.scalars(statement))))

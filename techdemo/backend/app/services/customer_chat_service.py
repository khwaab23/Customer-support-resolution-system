"""Conversation persistence and safe orchestration for customer support chat."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.customer_chat_agent import CustomerChatAgent
from app.models.support_conversation import SupportConversation
from app.models.support_message import SupportMessage
from app.repositories.order_repository import OrderRepository
from app.repositories.admin_review_repository import AdminReviewRepository
from app.repositories.support_conversation_repository import SupportConversationRepository
from app.repositories.support_message_repository import SupportMessageRepository
from app.schemas.chat import (
    ChatConversationCreateRequest, ChatConversationDetailResponse, ChatConversationResponse,
    ChatMessageCreateRequest, ChatMessageListResponse, ChatMessageResponse, ChatTurnResponse,
    ConversationStatus,
)
from app.services.support_workflow_service import SupportWorkflowService
from app.services.ticket_service import TicketOrderNotFoundError, TicketPersistenceError, TicketService
from app.tools.context import CustomerInvestigationContext


class ConversationNotFoundError(ValueError):
    pass


class ChatValidationError(ValueError):
    pass


class CustomerChatService:
    """Writes short chat messages; GET operations never invoke the model."""

    def __init__(
        self, session: Session, conversations: SupportConversationRepository,
        messages: SupportMessageRepository, orders: OrderRepository,
        agent: CustomerChatAgent, *, ticket_service: TicketService | None = None,
        workflow_service: SupportWorkflowService | None = None, review_ensurer=None,
        history_limit: int = 16,
    ) -> None:
        self._session, self._conversations, self._messages, self._orders = session, conversations, messages, orders
        self._agent, self._tickets, self._workflows = agent, ticket_service, workflow_service
        self._review_ensurer, self._history_limit = review_ensurer, history_limit

    def create(self, customer_id: str, payload: ChatConversationCreateRequest) -> ChatConversationResponse:
        if payload.selected_order_id:
            self._require_order(customer_id, payload.selected_order_id)
        conversation = SupportConversation(customer_id=customer_id, selected_order_id=payload.selected_order_id, status=ConversationStatus.OPEN.value)
        self._conversations.add(conversation)
        self._commit()
        return self._conversation_response(conversation)

    def list(self, customer_id: str, offset: int, limit: int):
        return [self._conversation_response(item) for item in self._conversations.list_for_customer(customer_id, offset, limit)]

    def detail(self, customer_id: str, conversation_id: UUID) -> ChatConversationDetailResponse:
        conversation = self._conversation(customer_id, conversation_id)
        messages = self._messages.list_for_conversation(conversation_id, 0, self._history_limit)
        return ChatConversationDetailResponse(**self._conversation_response(conversation).model_dump(), messages=[self._message_response(item) for item in messages])

    def messages(self, customer_id: str, conversation_id: UUID, offset: int, limit: int) -> ChatMessageListResponse:
        self._conversation(customer_id, conversation_id)
        return ChatMessageListResponse(messages=[self._message_response(item) for item in self._messages.list_for_conversation(conversation_id, offset, limit)], offset=offset, limit=limit)

    def select_order(self, customer_id: str, conversation_id: UUID, order_id: str) -> ChatConversationResponse:
        self._require_order(customer_id, order_id)
        conversation = self._conversation(customer_id, conversation_id, lock=True)
        conversation.selected_order_id = order_id
        self._conversations.touch(conversation)
        self._commit()
        return self._conversation_response(conversation)

    def send(self, customer_id: str, conversation_id: UUID, payload: ChatMessageCreateRequest) -> ChatTurnResponse:
        conversation = self._conversation(customer_id, conversation_id, lock=True)
        existing = self._messages.get_customer_request(conversation_id, payload.client_request_id)
        if existing is not None:
            reply = self._messages.get_assistant_reply(conversation_id, payload.client_request_id)
            return ChatTurnResponse(conversation=self._conversation_response(conversation), customer_message=self._message_response(existing), assistant_message=self._message_response(reply) if reply else None, idempotent_replay=True)
        customer_message = SupportMessage(conversation_id=conversation_id, sender_role="CUSTOMER", message_text=payload.message, client_request_id=payload.client_request_id)
        self._messages.add(customer_message)
        self._conversations.touch(conversation)
        try:
            self._commit()
        except ChatValidationError:
            # A concurrent request with the same caller-provided id may have
            # won the unique constraint. Return its durable result instead of
            # creating a second turn.
            existing = self._messages.get_customer_request(conversation_id, payload.client_request_id)
            if existing is not None:
                reply = self._messages.get_assistant_reply(conversation_id, payload.client_request_id)
                return ChatTurnResponse(conversation=self._conversation_response(conversation), customer_message=self._message_response(existing), assistant_message=self._message_response(reply) if reply else None, idempotent_replay=True)
            raise

        history = self._messages.recent_for_conversation(conversation_id, self._history_limit)
        history_input = [{"role": item.sender_role, "content": item.message_text} for item in history[:-1]]
        result = self._agent.respond(payload.message, selected_order_id=conversation.selected_order_id, history=history_input, context=CustomerInvestigationContext(customer_id=customer_id))
        escalation = self._maybe_escalate(conversation, payload.message, history)
        metadata = {**result.metadata, "reply_to_request_id": payload.client_request_id}
        if result.requires_escalation_confirmation:
            metadata["escalation_confirmation_requested"] = True
        if escalation:
            metadata.update(escalation)
        reply_text = escalation.get("message_text", result.message_text) if escalation else result.message_text
        assistant = SupportMessage(conversation_id=conversation_id, sender_role="ASSISTANT", message_text=reply_text, metadata_json=metadata)
        self._messages.add(assistant)
        self._conversations.touch(conversation)
        self._commit()
        return ChatTurnResponse(conversation=self._conversation_response(conversation), customer_message=self._message_response(customer_message), assistant_message=self._message_response(assistant))

    def _maybe_escalate(self, conversation: SupportConversation, message: str, history: list[SupportMessage]) -> dict | None:
        if conversation.linked_ticket_id or not conversation.selected_order_id or not self._confirmed(message, history):
            return None
        if self._tickets is None:
            return {"message_text": "I can prepare a support case, but case creation is temporarily unavailable.", "escalation_status": "UNAVAILABLE"}
        try:
            ticket = self._tickets.create_customer_ticket(conversation.customer_id, conversation.selected_order_id, message)
        except (TicketOrderNotFoundError, TicketPersistenceError):
            return {"message_text": "I could not create a support case. Please try again later.", "escalation_status": "FAILED"}
        conversation.linked_ticket_id = ticket.ticket_id
        conversation.status = ConversationStatus.ESCALATED.value
        workflow_status = "PENDING"
        if self._workflows is not None:
            try:
                state = self._workflows.start_workflow(ticket.ticket_id, CustomerInvestigationContext(conversation.customer_id))
                workflow_status = str(state.get("workflow_status", "PENDING"))
                if state.get("requires_human_review") and self._review_ensurer:
                    self._review_ensurer(str(state["workflow_id"]))
            except Exception:
                workflow_status = "PENDING_RECOVERY"
        return {"message_text": f"Your support case {ticket.ticket_id} was created. Workflow status: {workflow_status}. No refund has been approved or sent.", "escalation_status": workflow_status, "ticket_id": ticket.ticket_id}

    @staticmethod
    def _confirmed(message: str, history: list[SupportMessage]) -> bool:
        if message.strip().lower() not in {"yes", "yes please", "confirm", "create it", "create a case"}:
            return False
        return bool(history and any(
            item.sender_role == "ASSISTANT" and (item.metadata_json or {}).get("escalation_confirmation_requested")
            for item in history[-4:]
        ))

    def _conversation(self, customer_id: str, conversation_id: UUID, *, lock: bool = False) -> SupportConversation:
        conversation = self._conversations.get_for_customer(conversation_id, customer_id, lock=lock)
        if conversation is None:
            raise ConversationNotFoundError("Conversation not found")
        return conversation

    def _require_order(self, customer_id: str, order_id: str) -> None:
        order = self._orders.get_by_id(order_id)
        if order is None or order.customer_id != customer_id:
            raise ChatValidationError("Order not found")

    def _commit(self) -> None:
        try:
            self._session.commit()
        except (IntegrityError, SQLAlchemyError) as exc:
            self._session.rollback()
            raise ChatValidationError("Conversation update could not be saved") from exc

    @staticmethod
    def _review_status_for(value: SupportConversation, session: Session) -> str | None:
        if value.linked_ticket_id is None:
            return None
        try:
            review = AdminReviewRepository(session).get_by_ticket(value.linked_ticket_id)
        except SQLAlchemyError:
            return None
        if review is None:
            return "SUPPORT_CASE_OPEN"
        return {
            "PENDING": "HUMAN_REVIEW_REQUIRED",
            "INFORMATION_REQUESTED": "ADDITIONAL_INFORMATION_REQUESTED",
            "APPROVED_INTERNAL": "INTERNALLY_APPROVED_PROCESSING_NOT_STARTED",
            "REJECTED": "REQUEST_DECLINED",
        }.get(review.review_status, "HUMAN_REVIEW_REQUIRED")

    def _conversation_response(self, value: SupportConversation) -> ChatConversationResponse:
        response = ChatConversationResponse.model_validate(value)
        return response.model_copy(update={"review_status": self._review_status_for(value, self._session)})

    @staticmethod
    def _message_response(value: SupportMessage) -> ChatMessageResponse:
        response = ChatMessageResponse.model_validate(value)
        return response.model_copy(update={"metadata": value.metadata_json})

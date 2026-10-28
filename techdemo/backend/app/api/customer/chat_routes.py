"""Customer-scoped conversational support API. GET routes are side-effect free."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.customer_chat_agent import CustomerChatAgent
from app.agents.tool_executor import ToolExecutor
from app.api.auth.dependencies import require_csrf, require_customer
from app.core.database import get_db
from app.models.user import User
from app.repositories.admin_review_repository import AdminReviewRepository
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.shipment_repository import ShipmentRepository
from app.repositories.support_conversation_repository import SupportConversationRepository
from app.repositories.support_message_repository import SupportMessageRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.chat import (
    ChatConversationCreateRequest, ChatConversationDetailResponse, ChatConversationListResponse,
    ChatConversationResponse, ChatMessageCreateRequest, ChatMessageListResponse, ChatOrderSelectionRequest,
    ChatTurnResponse,
)
from app.services.admin_review_service import AdminReviewService
from app.services.customer_chat_service import ChatValidationError, ConversationNotFoundError, CustomerChatService
from app.services.ticket_service import TicketService
from app.tools.order_tools import OrderInvestigationTool
from app.tools.payment_tools import PaymentInvestigationTool
from app.tools.policy_tools import PolicyLookupTool
from app.tools.refund_tools import RefundHistoryInvestigationTool
from app.tools.return_tools import ReturnInvestigationTool
from app.tools.shipment_tools import ShipmentInvestigationTool
from app.workflows.factory import build_refund_eligibility_service, build_support_workflow_service

router = APIRouter(prefix="/chat")


def _customer_id(user: User) -> str:
    if user.customer_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer identity is incomplete")
    return user.customer_id


def get_chat_service(db: Annotated[Session, Depends(get_db)]) -> CustomerChatService:
    orders = OrderRepository(db)
    executor = ToolExecutor(
        OrderInvestigationTool(orders), ShipmentInvestigationTool(orders, ShipmentRepository(db)),
        PaymentInvestigationTool(orders, PaymentRepository(db)), ReturnInvestigationTool(orders, ReturnRepository(db)),
        RefundHistoryInvestigationTool(orders, RefundRepository(db)), PolicyLookupTool(),
    )
    workflows = build_support_workflow_service(db)
    reviews = AdminReviewService(
        db, AdminReviewRepository(db), TicketRepository(db), build_refund_eligibility_service(db),
        workflows, AuditEventRepository(db),
    )
    return CustomerChatService(
        db, SupportConversationRepository(db), SupportMessageRepository(db), orders, CustomerChatAgent(executor),
        ticket_service=TicketService(TicketRepository(db), orders, db), workflow_service=workflows,
        review_ensurer=reviews.ensure_for_paused_workflow,
    )


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")


@router.post("/conversations", response_model=ChatConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ChatConversationCreateRequest, user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)], service: Annotated[CustomerChatService, Depends(get_chat_service)],
) -> ChatConversationResponse:
    try:
        return service.create(_customer_id(user), payload)
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None


@router.get("/conversations", response_model=ChatConversationListResponse)
def list_conversations(
    user: Annotated[User, Depends(require_customer)], service: Annotated[CustomerChatService, Depends(get_chat_service)],
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ChatConversationListResponse:
    return ChatConversationListResponse(conversations=service.list(_customer_id(user), offset, limit), offset=offset, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=ChatConversationDetailResponse)
def get_conversation(conversation_id: UUID, user: Annotated[User, Depends(require_customer)], service: Annotated[CustomerChatService, Depends(get_chat_service)]) -> ChatConversationDetailResponse:
    try:
        return service.detail(_customer_id(user), conversation_id)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from None


@router.get("/conversations/{conversation_id}/messages", response_model=ChatMessageListResponse)
def list_messages(
    conversation_id: UUID, user: Annotated[User, Depends(require_customer)], service: Annotated[CustomerChatService, Depends(get_chat_service)],
    offset: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> ChatMessageListResponse:
    try:
        return service.messages(_customer_id(user), conversation_id, offset, limit)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from None


@router.post("/conversations/{conversation_id}/select-order", response_model=ChatConversationResponse)
def select_order(
    conversation_id: UUID, payload: ChatOrderSelectionRequest, user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)], service: Annotated[CustomerChatService, Depends(get_chat_service)],
) -> ChatConversationResponse:
    try:
        return service.select_order(_customer_id(user), conversation_id, payload.order_id)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from None
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None


@router.post("/conversations/{conversation_id}/messages", response_model=ChatTurnResponse)
def send_message(
    conversation_id: UUID, payload: ChatMessageCreateRequest, user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)], service: Annotated[CustomerChatService, Depends(get_chat_service)],
) -> ChatTurnResponse:
    try:
        return service.send(_customer_id(user), conversation_id, payload)
    except ConversationNotFoundError as exc:
        raise _not_found(exc) from None
    except ChatValidationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth.dependencies import require_csrf, require_customer
from app.core.database import get_db
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.order import CustomerOrderListResponse, CustomerOrderResponse
from app.schemas.ticket import TicketCreateRequest, TicketListResponse, TicketResponse
from app.schemas.workflow import WorkflowStartResponse
from app.services.admin_review_service import AdminReviewService, ReviewConflictError as AdminReviewConflictError
from app.repositories.admin_review_repository import AdminReviewRepository
from app.repositories.audit_event_repository import AuditEventRepository
from app.services.refund_eligibility_service import RefundEligibilityService
from app.workflows.factory import build_refund_eligibility_service, build_support_workflow_service
from app.services.support_workflow_service import SupportWorkflowService, WorkflowAccessError, WorkflowConflictError
from app.tools.context import CustomerInvestigationContext
from app.services.order_service import OrderService
from app.services.ticket_service import (
    TicketOrderNotFoundError,
    TicketPersistenceError,
    TicketService,
)

router = APIRouter()


def get_order_service(
    db: Annotated[Session, Depends(get_db)],
) -> OrderService:
    return OrderService(OrderRepository(db))


def get_ticket_service(
    db: Annotated[Session, Depends(get_db)],
) -> TicketService:
    return TicketService(TicketRepository(db), OrderRepository(db), db)


def customer_safe_review_status(db: Session, ticket_id: str) -> str | None:
    """Translate administrative state without exposing reviewer/audit details."""
    try:
        review = AdminReviewRepository(db).get_by_ticket(ticket_id)
    except SQLAlchemyError:
        # Review state is an optional enhancement. It must never make an
        # otherwise-working customer ticket unavailable during rollout.
        return None
    if review is None:
        return None
    statuses = {
        "PENDING": "UNDER_REVIEW",
        "INFORMATION_REQUESTED": "ADDITIONAL_INFORMATION_REQUESTED",
        "APPROVED_INTERNAL": "INTERNALLY_APPROVED_PROCESSING_NOT_STARTED",
        "REJECTED": "REQUEST_DECLINED",
    }
    return statuses.get(review.review_status, "UNDER_REVIEW")


def customer_ticket_response(db: Session, ticket) -> TicketResponse:
    response = TicketResponse.model_validate(ticket)
    return response.model_copy(update={"review_status": customer_safe_review_status(db, ticket.ticket_id)})


def get_workflow_service(db: Annotated[Session, Depends(get_db)]):
    return build_support_workflow_service(db)


def get_review_service(db: Annotated[Session, Depends(get_db)]) -> AdminReviewService:
    workflow = build_support_workflow_service(db)
    return AdminReviewService(
        db, AdminReviewRepository(db), TicketRepository(db),
        build_refund_eligibility_service(db), workflow, AuditEventRepository(db),
    )


def customer_id_for(user: User) -> str:
    """Defend against invalid identities even though auth already validates them."""
    if user.customer_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer identity is incomplete",
        )
    return user.customer_id


@router.get("/orders", response_model=CustomerOrderListResponse)
def list_orders(
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[OrderService, Depends(get_order_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> CustomerOrderListResponse:
    customer_id = customer_id_for(user)
    orders = service.list_customer_orders(customer_id, limit)
    return CustomerOrderListResponse(orders=orders)


@router.get("/orders/{order_id}", response_model=CustomerOrderResponse)
def get_order(
    order_id: str,
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[OrderService, Depends(get_order_service)],
) -> CustomerOrderResponse:
    customer_id = customer_id_for(user)
    order = service.get_customer_order(customer_id, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
    return CustomerOrderResponse.model_validate(order)


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_exclude_none=True,
)
def create_ticket(
    payload: TicketCreateRequest,
    user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
    db: Annotated[Session, Depends(get_db)],
) -> TicketResponse:
    try:
        ticket = service.create_customer_ticket(
            customer_id=customer_id_for(user),
            order_id=payload.order_id,
            message=payload.message,
        )
    except TicketOrderNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        ) from None
    except TicketPersistenceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket service unavailable",
        ) from None

    return customer_ticket_response(db, ticket)


@router.get("/tickets", response_model=TicketListResponse, response_model_exclude_none=True)
def list_tickets(
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TicketListResponse:
    tickets = service.list_customer_tickets(customer_id_for(user), limit)
    return TicketListResponse(tickets=[customer_ticket_response(db, ticket) for ticket in tickets])


@router.get("/tickets/{ticket_id}", response_model=TicketResponse, response_model_exclude_none=True)
def get_ticket(
    ticket_id: str,
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
    db: Annotated[Session, Depends(get_db)],
) -> TicketResponse:
    ticket = service.get_customer_ticket(customer_id_for(user), ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return customer_ticket_response(db, ticket)


@router.post("/tickets/{ticket_id}/workflow", response_model=WorkflowStartResponse)
def start_ticket_workflow(
    ticket_id: str,
    user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)],
    workflow: Annotated[SupportWorkflowService, Depends(get_workflow_service)],
    reviews: Annotated[AdminReviewService, Depends(get_review_service)],
) -> WorkflowStartResponse:
    """Explicit customer action only; listing a ticket never starts an AI run."""
    try:
        state = workflow.start_workflow(
            ticket_id, CustomerInvestigationContext(customer_id=customer_id_for(user))
        )
        created = False
        if state.get("requires_human_review"):
            reviews.ensure_for_paused_workflow(state["workflow_id"])
            created = True
        return WorkflowStartResponse(
            workflow_id=state["workflow_id"], workflow_status=state["workflow_status"], review_created=created
        )
    except (WorkflowAccessError, AdminReviewConflictError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found") from None
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None

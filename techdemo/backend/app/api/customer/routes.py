from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.auth.dependencies import require_csrf, require_customer
from app.core.database import get_db
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.order import CustomerOrderListResponse, CustomerOrderResponse
from app.schemas.ticket import TicketCreateRequest, TicketListResponse, TicketResponse
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
)
def create_ticket(
    payload: TicketCreateRequest,
    user: Annotated[User, Depends(require_customer)],
    _: Annotated[None, Depends(require_csrf)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
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

    return TicketResponse.model_validate(ticket)


@router.get("/tickets", response_model=TicketListResponse)
def list_tickets(
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> TicketListResponse:
    tickets = service.list_customer_tickets(customer_id_for(user), limit)
    return TicketListResponse(tickets=tickets)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: str,
    user: Annotated[User, Depends(require_customer)],
    service: Annotated[TicketService, Depends(get_ticket_service)],
) -> TicketResponse:
    ticket = service.get_customer_ticket(customer_id_for(user), ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return TicketResponse.model_validate(ticket)

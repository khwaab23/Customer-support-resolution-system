from dataclasses import dataclass

from app.models.user import User, UserRole


@dataclass(frozen=True, slots=True)
class CustomerInvestigationContext:
    """Trusted customer identity supplied by validated application authentication.

    Construct this context only in trusted application code after FastAPI's
    ``require_customer`` dependency has validated the authenticated user. The
    dataclass is immutable for accidental-mutation safety; it does not itself
    authenticate a caller.
    """

    customer_id: str

    @classmethod
    def from_authenticated_customer(cls, user: User) -> "CustomerInvestigationContext":
        """Create context from a customer user already validated by application code."""
        if user.role != UserRole.CUSTOMER or user.customer_id is None:
            raise ValueError("A validated customer user with customer_id is required")
        return cls(customer_id=user.customer_id)

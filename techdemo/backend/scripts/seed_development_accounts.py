import os

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.models.customer import Customer
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService


def required_environment_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} must be set before development seeding.")
    return value


def main() -> None:
    """Create development-only accounts without overwriting existing records."""
    settings = get_settings()
    if settings.app_environment != "development":
        raise SystemExit("Development account seeding is disabled outside development.")

    customer_password = required_environment_value("DEV_SEED_CUSTOMER_PASSWORD")
    admin_email = required_environment_value("DEV_SEED_ADMIN_EMAIL").strip().lower()
    admin_password = required_environment_value("DEV_SEED_ADMIN_PASSWORD")

    with get_session_factory()() as session:
        users = UserRepository(session)
        customers = list(
            session.scalars(
                select(Customer)
                .where(Customer.account_status == "ACTIVE")
                .order_by(Customer.customer_id.asc())
                .limit(3)
            )
        )
        if len(customers) < 3:
            raise SystemExit("At least three active customers are required for seeding.")

        created = 0
        for customer in customers:
            if (
                users.get_by_customer_id(customer.customer_id) is not None
                or users.get_by_email(customer.email) is not None
            ):
                continue
            users.add(
                User(
                    email=customer.email.strip().lower(),
                    password_hash=AuthService.hash_password(customer_password),
                    role=UserRole.CUSTOMER,
                    customer_id=customer.customer_id,
                    is_active=True,
                )
            )
            created += 1

        if users.get_by_email(admin_email) is None:
            users.add(
                User(
                    email=admin_email,
                    password_hash=AuthService.hash_password(admin_password),
                    role=UserRole.ADMIN,
                    customer_id=None,
                    is_active=True,
                )
            )
            created += 1

        if created:
            session.commit()
        print(f"Created {created} development account(s); existing accounts were not changed.")


if __name__ == "__main__":
    main()

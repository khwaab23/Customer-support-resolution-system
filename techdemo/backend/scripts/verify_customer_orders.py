"""Read-only verification of authenticated customer order endpoints."""

import os
import sys
from getpass import getpass
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.repositories.order_repository import OrderRepository

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_CUSTOMER_EMAIL = "customer001@example.test"
CSRF_HEADER_NAME = "X-CSRF-Token"


class VerificationFailure(Exception):
    """Raised after a failed verification has been reported."""


def report(step: str, response: httpx.Response, expected_status: int) -> None:
    passed = response.status_code == expected_status
    print(f"{'PASS' if passed else 'FAIL'}: {step} (HTTP {response.status_code})")
    if not passed:
        raise VerificationFailure(f"{step} expected HTTP {expected_status}.")


def report_check(step: str, condition: bool) -> None:
    print(f"{'PASS' if condition else 'FAIL'}: {step}")
    if not condition:
        raise VerificationFailure(step)


def cookie_value(client: httpx.Client, name: str) -> str | None:
    for cookie in client.cookies.jar:
        if cookie.name == name:
            return cookie.value
    return None


def request_origin(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VerificationFailure("AUTH_TEST_BASE_URL must be a complete HTTP(S) URL.")
    return f"{parsed.scheme}://{parsed.netloc}"


def customer_password(email: str) -> str:
    return os.getenv("AUTH_TEST_CUSTOMER_PASSWORD") or getpass(f"Password for {email}: ")


def verify_repository_ownership(customer_id: str, api_orders: list[dict[str, object]]) -> None:
    """Use the existing read-only repository instead of trusting API data alone."""
    with get_session_factory()() as session:
        repository = OrderRepository(session)
        for api_order in api_orders:
            order_id = api_order.get("order_id")
            report_check("API response includes an order ID", isinstance(order_id, str))
            database_order = repository.get_by_id(order_id)
            report_check("API order exists in the database", database_order is not None)
            report_check(
                "API order belongs to the authenticated customer",
                database_order.customer_id == customer_id,
            )


def main() -> int:
    base_url = os.getenv("AUTH_TEST_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    customer_email = os.getenv("AUTH_TEST_CUSTOMER_EMAIL", DEFAULT_CUSTOMER_EMAIL)
    origin = request_origin(base_url)
    password = customer_password(customer_email)
    settings = get_settings()

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            csrf_response = client.get("/v1/auth/csrf", headers={"Origin": origin})
            report("Initialize CSRF", csrf_response, httpx.codes.NO_CONTENT)
            csrf_token = cookie_value(client, settings.csrf_cookie_name)
            report_check("CSRF cookie exists", csrf_token is not None)

            login_response = client.post(
                "/v1/auth/login",
                headers={"Origin": origin, CSRF_HEADER_NAME: csrf_token},
                json={"email": customer_email, "password": password},
            )
            report("Customer login", login_response, httpx.codes.OK)
            report_check(
                "Session cookie exists",
                cookie_value(client, settings.session_cookie_name) is not None,
            )

            me_response = client.get("/v1/auth/me")
            report("Verify authenticated customer", me_response, httpx.codes.OK)
            identity = me_response.json()
            report_check("Authenticated identity is CUSTOMER", identity.get("role") == "CUSTOMER")
            customer_id = identity.get("customer_id")
            report_check("Authenticated identity has a customer ID", isinstance(customer_id, str))

            list_response = client.get("/v1/customer/orders")
            report("List customer orders", list_response, httpx.codes.OK)
            orders = list_response.json().get("orders")
            report_check("Order list is an array", isinstance(orders, list))
            verify_repository_ownership(customer_id, orders)
            report_check("Customer has at least one order to verify", bool(orders))

            first_order_id = orders[0].get("order_id")
            report_check("First order has an order ID", isinstance(first_order_id, str))
            detail_response = client.get(f"/v1/customer/orders/{first_order_id}")
            report("Retrieve customer order", detail_response, httpx.codes.OK)
            report_check(
                "Retrieved order matches requested order",
                detail_response.json().get("order_id") == first_order_id,
            )

            other_order_id = os.getenv("AUTH_TEST_OTHER_ORDER_ID")
            if other_order_id:
                other_response = client.get(f"/v1/customer/orders/{other_order_id}")
                report("Reject another customer's order", other_response, httpx.codes.NOT_FOUND)
            else:
                print("SKIP: Other-customer check (AUTH_TEST_OTHER_ORDER_ID is not set)")

            csrf_token = cookie_value(client, settings.csrf_cookie_name)
            report_check("Current CSRF cookie exists", csrf_token is not None)
            logout_response = client.post(
                "/v1/auth/logout",
                headers={"Origin": origin, CSRF_HEADER_NAME: csrf_token},
            )
            report("Logout", logout_response, httpx.codes.OK)
    except httpx.HTTPError as exc:
        print(f"FAIL: Could not reach {base_url}: {exc}", file=sys.stderr)
        return 1
    except VerificationFailure as exc:
        print(f"FAIL: Verification stopped: {exc}", file=sys.stderr)
        return 1

    print("PASS: Customer order API verification completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

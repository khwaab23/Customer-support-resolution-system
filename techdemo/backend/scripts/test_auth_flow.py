"""Exercise the local authentication flow without exposing credentials or tokens."""

import os
import sys
from getpass import getpass
from urllib.parse import urlsplit

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_CUSTOMER_EMAIL = "customer001@example.test"
CSRF_COOKIE_NAME = "techdemo_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_COOKIE_NAME = "techdemo_session"


class FlowFailure(Exception):
    """Raised after a failed verification step has been reported."""


def report(step: str, response: httpx.Response, expected_status: int) -> None:
    passed = response.status_code == expected_status
    outcome = "PASS" if passed else "FAIL"
    print(f"{outcome}: {step} (HTTP {response.status_code})")
    if not passed:
        raise FlowFailure(f"{step} expected HTTP {expected_status}.")


def report_check(step: str, condition: bool) -> None:
    outcome = "PASS" if condition else "FAIL"
    print(f"{outcome}: {step}")
    if not condition:
        raise FlowFailure(step)


def cookie_value(client: httpx.Client, cookie_name: str) -> str | None:
    for cookie in client.cookies.jar:
        if cookie.name == cookie_name:
            return cookie.value
    return None


def password_from_environment_or_prompt(variable_name: str, prompt: str) -> str:
    return os.getenv(variable_name) or getpass(prompt)


def origin_for(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FlowFailure(
            "AUTH_TEST_BASE_URL must include an http:// or https:// origin."
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def obtain_csrf_token(client: httpx.Client, origin: str, label: str) -> str:
    response = client.get("/v1/auth/csrf", headers={"Origin": origin})
    report(f"{label}: obtain CSRF cookie", response, httpx.codes.NO_CONTENT)
    csrf_token = cookie_value(client, CSRF_COOKIE_NAME)
    report_check(f"{label}: CSRF cookie exists", csrf_token is not None)
    return csrf_token


def run_login_flow(
    client: httpx.Client,
    origin: str,
    email: str,
    password: str,
    expected_role: str,
    expects_customer_id: bool,
    label: str,
) -> None:
    csrf_token = obtain_csrf_token(client, origin, label)
    login_response = client.post(
        "/v1/auth/login",
        headers={"Origin": origin, CSRF_HEADER_NAME: csrf_token},
        json={"email": email, "password": password},
    )
    report(f"{label}: login", login_response, httpx.codes.OK)

    session_token = cookie_value(client, SESSION_COOKIE_NAME)
    report_check(f"{label}: session cookie exists", session_token is not None)

    me_response = client.get("/v1/auth/me")
    report(f"{label}: authenticated session", me_response, httpx.codes.OK)
    identity = me_response.json()
    report_check(f"{label}: role is {expected_role}", identity.get("role") == expected_role)
    report_check(
        f"{label}: customer ownership matches role",
        (identity.get("customer_id") is not None) == expects_customer_id,
    )

    # Login does not rotate the CSRF token, but always read the current cookie.
    csrf_token = cookie_value(client, CSRF_COOKIE_NAME)
    report_check(f"{label}: current CSRF cookie exists", csrf_token is not None)
    logout_response = client.post(
        "/v1/auth/logout",
        headers={"Origin": origin, CSRF_HEADER_NAME: csrf_token},
    )
    report(f"{label}: logout", logout_response, httpx.codes.OK)

    # Send the pre-logout token explicitly to prove server-side revocation, not
    # merely browser-side cookie removal. Its value is never printed or stored.
    revoked_session_response = client.get(
        "/v1/auth/me",
        cookies={SESSION_COOKIE_NAME: session_token},
    )
    report(
        f"{label}: revoked session is unauthorized",
        revoked_session_response,
        httpx.codes.UNAUTHORIZED,
    )


def main() -> int:
    base_url = os.getenv("AUTH_TEST_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    customer_email = os.getenv("AUTH_TEST_CUSTOMER_EMAIL", DEFAULT_CUSTOMER_EMAIL)
    origin = origin_for(base_url)
    customer_password = password_from_environment_or_prompt(
        "AUTH_TEST_CUSTOMER_PASSWORD",
        f"Password for {customer_email}: ",
    )

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            run_login_flow(
                client=client,
                origin=origin,
                email=customer_email,
                password=customer_password,
                expected_role="CUSTOMER",
                expects_customer_id=True,
                label="Customer flow",
            )

            admin_email = os.getenv("AUTH_TEST_ADMIN_EMAIL")
            if admin_email:
                admin_password = password_from_environment_or_prompt(
                    "AUTH_TEST_ADMIN_PASSWORD",
                    f"Password for {admin_email}: ",
                )
                run_login_flow(
                    client=client,
                    origin=origin,
                    email=admin_email,
                    password=admin_password,
                    expected_role="ADMIN",
                    expects_customer_id=False,
                    label="Admin flow",
                )
            else:
                print("SKIP: Admin flow (AUTH_TEST_ADMIN_EMAIL is not set)")
    except httpx.HTTPError as exc:
        print(f"FAIL: Could not reach {base_url}: {exc}", file=sys.stderr)
        return 1
    except FlowFailure as exc:
        print(f"FAIL: Authentication flow stopped: {exc}", file=sys.stderr)
        return 1

    print("PASS: Authentication integration flow completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

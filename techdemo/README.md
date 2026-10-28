# TechDemo

TechDemo is a learning project for a production-minded Customer Support Resolution Agent. It is a modular monolith with a FastAPI backend, PostgreSQL, customer and admin React portals, policy-grounded investigation tools, and human review for durable support actions.

## What it does

- Customers can sign in, view their orders, create and track tickets, or start with AI Support Chat.
- Chat can use a customer-selected order to inspect authorized order, shipment, return, payment, and refund records.
- Policy-dependent questions use the local policy retrieval layer; the system does not promise refunds or invent eligibility.
- A support ticket and workflow are created only after the customer explicitly confirms an escalation.
- Administrators can review policy evidence and deterministic refund eligibility, then record an internal decision. An internal approval never transfers money or marks a refund as sent.

## Structure

- `backend/` — FastAPI application, SQLAlchemy models, Alembic migrations, tests, and verification scripts.
- `backend/app/api/` — authenticated customer, admin, and chat HTTP routes.
- `backend/app/agents/` — bounded AI investigation and customer-chat orchestration.
- `backend/app/tools/` — trusted, read-only customer-scoped business and policy tools.
- `backend/app/services/` — application workflows, ticketing, chat, review, and eligibility logic.
- `backend/app/workflows/` — LangGraph support workflow and PostgreSQL checkpoint integration.
- `frontend/customer/` — React/Vite customer portal, served locally on port 3000.
- `frontend/admin/` — React/Vite admin review portal, served locally on port 3001.
- `policies/` — versioned support-policy source documents used by retrieval.

## Local setup

Prerequisites: Python 3.11+, Node.js, PostgreSQL 17, and the project database configuration in `backend/.env`.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Review the migration chain before applying it. Migrations are never applied automatically:

```bash
cd backend
alembic history
alembic current
alembic upgrade head
```

Start the API:

```bash
cd backend
uvicorn app.main:app --reload --port 8001
```

Start the customer portal:

```bash
cd frontend/customer
npm install
npm run dev
```

Start the admin portal:

```bash
cd frontend/admin
npm install
npm run dev
```

The default local origins are `http://127.0.0.1:3000` for customers and `http://127.0.0.1:3001` for administrators. Keep those exact origins in `TRUSTED_ORIGINS` in `backend/.env`.

## Verification

```bash
cd backend
python -m pytest

cd ../frontend/customer
npm run typecheck && npm test && npm run build

cd ../admin
npm run typecheck && npm test && npm run build
```

## Safety boundaries

- Browser sessions are HttpOnly cookies; state-changing calls use origin and CSRF validation.
- Customer identity is derived from the authenticated session, never model-provided input.
- Investigation tools are read-only and enforce order ownership.
- Models can classify or summarize bounded evidence but cannot approve, execute, or transfer refunds.
- Ticket escalation requires customer confirmation; admin decisions require an authenticated admin, CSRF protection, and optimistic concurrency checks.
- Chat and review data do not store passwords, API keys, full prompts, chain-of-thought, or raw tool credentials.


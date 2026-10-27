# Human Review, Escalation & Audit

Policy ID: NTE-POL-05 | Version: 1.0 | Effective: 2026-10-01

## Purpose

Ensure that decisions with risk or uncertainty are reversible, attributable and auditable.

## Approval transitions

Proposal states: DRAFT -> PENDING_REVIEW -> APPROVED, REJECTED or EXPIRED. Only APPROVED proposals matching the current server-validated facts may reach the payment execution step.

## Review record

Save reviewer identity, decision, exact proposal payload, approved amount in minor units, timestamps, and any rejection reason. Never ask the LLM to supply reviewer identity.

## Escalation triggers

Escalate identity mismatch, missing evidence, unavailable external service with unresolved status, conflicting policy versions, return inspection failure, late-return exceptions, or suspected duplicate/ambiguous refunds.

## Policy grounding

Each proposed resolution must record applicable document ID, version and section references. Similarity score from RAG alone never establishes eligibility.

## Audit trail

Write immutable-style events for ticket creation, tool calls, proposal, review, execution request, provider confirmation, and ticket changes. Do not log real secrets, payment card details, or sensitive personal information.

## Resilience

Use structured tool errors, bounded retries for safe reads, and reconciliation for financial writes. Workflow checkpoints never replace transactional financial records.

## MVP limits

Single fictitious store and currency (USD); synthetic identities; mock payments, shipping and ticketing; customer messages stay within the project UI.

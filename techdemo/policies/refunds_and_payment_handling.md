# Refunds & Payment Handling

Policy ID: NTE-POL-02 | Version: 1.0 | Effective: 2026-10-01

## Purpose

Control refund proposals, required human approval, execution, verification and duplicate-prevention.

## Eligibility prerequisites

A refund proposal requires authenticated order ownership, a qualifying return under the applicable returns policy, RECEIVED return, PASSED inspection, captured payment, and no existing successful or unresolved refund for the same item/amount.

## Refund amount

Proposed refund amounts are calculated by server code in integer cents (minor currency units). Never exceed the captured and remaining refundable amount, and do not assume the model can select or edit the payable amount.

## Approval requirement

Every refund, without exceptions in this MVP, needs explicit approval from an authorized human reviewer for the exact order, amount, currency, return and proposal. Rejected or expired approvals prohibit execution.

## Execution

Create a unique idempotency key for the authorized refund. Execute only through MockPay with server-side credentials, never through a direct LLM-selected payment credential or reviewer identity.

## Verification

Mark a refund SUCCEEDED only when the payment provider confirms the result. A request timeout or ambiguous provider response must be UNKNOWN until reconciliation by provider reference or idempotency key; do not blindly send another refund.

## Customer messaging

A proposal or an approval is not proof of payment. Say "refund requested" or "approved, processing" unless provider confirmation shows success. Do not promise a banking settlement date.

## Timing

After confirmed issuance, describe the fictional standard expectation as 3-5 business days for settlement, subject to payment provider behavior; communicate uncertainty as appropriate.

## Examples

ORD-1001: eligible received return, no issued refund; prepare proposal for human approval. ORD-1002: provider already shows refund SUCCEEDED; explain existing outcome. ORD-1020: UNKNOWN mock provider outcome; reconcile before retry.

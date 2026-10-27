# Shipping & Order Status

Policy ID: NTE-POL-03 | Version: 1.0 | Effective: 2026-10-01

## Purpose

Answer order-status requests using verified order and shipping records, rather than invented tracking updates.

## Lookup

Authenticate the customer. Validate that the order belongs to that customer. Retrieve order status and mock carrier status separately.

## Status precedence

Use the most recently verified carrier status for physical shipment location. Order PROCESSING does not mean the package has shipped. Shipment IN_TRANSIT does not mean delivered.

## Delay handling

When estimated delivery is passed and current carrier status indicates DELAYED, explain the last verified update and recommend a ticket follow-up. Do not fabricate a new arrival date.

## Unavailable services

If the MockParcel API times out or is unavailable, acknowledge that shipment details could not be verified. Preserve known information with its timestamp; leave the ticket open or escalate as necessary.

## Ticket update

Write back the status category, actual carrier facts and next step. Never claim shipment status changed merely because a ticket was updated.

## Examples

ORD-1006 has DELAYED in synthetic carrier status. ORD-1008 simulates a carrier service outage. Both require uncertainty-aware explanations.

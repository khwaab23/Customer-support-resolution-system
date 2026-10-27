"""Dedicated workflow-ID registry; checkpoint contents are never authentication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import psycopg

from app.workflows.checkpoint import checkpoint_conninfo


@dataclass(frozen=True, slots=True)
class WorkflowRegistryEntry:
    workflow_id: str
    thread_id: str
    ticket_id: str
    customer_id: str
    review_consumed: bool = False


class WorkflowRegistry(Protocol):
    def create(self, entry: WorkflowRegistryEntry) -> None: ...
    def get(self, workflow_id: str) -> WorkflowRegistryEntry | None: ...
    def consume_review(self, workflow_id: str) -> bool: ...
    def active_for_ticket(self, ticket_id: str, customer_id: str) -> WorkflowRegistryEntry | None: ...


class PostgresWorkflowRegistry:
    """Registry stored only in the checkpoint schema, never in business tables."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo

    def create(self, entry: WorkflowRegistryEntry) -> None:
        with psycopg.connect(self._conninfo) as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workflow_registry (workflow_id, thread_id, ticket_id, customer_id) VALUES (%s, %s, %s, %s)",
                (entry.workflow_id, entry.thread_id, entry.ticket_id, entry.customer_id),
            )

    def get(self, workflow_id: str) -> WorkflowRegistryEntry | None:
        with psycopg.connect(self._conninfo) as connection, connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            row = cursor.execute(
                "SELECT workflow_id, thread_id, ticket_id, customer_id, review_consumed FROM workflow_registry WHERE workflow_id = %s",
                (workflow_id,),
            ).fetchone()
        return WorkflowRegistryEntry(**row) if row else None

    def active_for_ticket(self, ticket_id: str, customer_id: str) -> WorkflowRegistryEntry | None:
        with psycopg.connect(self._conninfo) as connection, connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            row = cursor.execute(
                "SELECT workflow_id, thread_id, ticket_id, customer_id, review_consumed FROM workflow_registry WHERE ticket_id = %s AND customer_id = %s AND review_consumed = FALSE ORDER BY created_at DESC LIMIT 1",
                (ticket_id, customer_id),
            ).fetchone()
        return WorkflowRegistryEntry(**row) if row else None

    def consume_review(self, workflow_id: str) -> bool:
        with psycopg.connect(self._conninfo) as connection, connection.cursor() as cursor:
            updated = cursor.execute(
                "UPDATE workflow_registry SET review_consumed = TRUE WHERE workflow_id = %s AND review_consumed = FALSE",
                (workflow_id,),
            ).rowcount
        return updated == 1

"""Isolated PostgreSQL configuration for LangGraph persistence."""

from __future__ import annotations

from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from app.core.config import Settings, get_settings


def checkpoint_conninfo(settings: Settings | None = None) -> str:
    """Build non-logged psycopg conninfo with an isolated search path."""
    configured = settings or get_settings()
    return psycopg.conninfo.make_conninfo(
        host=configured.db_host,
        port=configured.db_port,
        dbname=configured.db_name,
        user=configured.db_user,
        password=configured.db_password,
        options=f"-c search_path={configured.workflow_checkpoint_schema},public",
    )


@contextmanager
def postgres_checkpointer(settings: Settings | None = None):
    """Open a short-lived official PostgresSaver for one workflow operation."""
    with PostgresSaver.from_conn_string(checkpoint_conninfo(settings)) as saver:
        yield saver


def setup_workflow_persistence(settings: Settings | None = None) -> None:
    """Create only the dedicated schema, registry, and LangGraph tables.

    This explicit operation is intentionally never called during application import
    or a normal workflow start. It must be run by a trusted operator.
    """
    configured = settings or get_settings()
    schema = configured.workflow_checkpoint_schema
    with psycopg.connect(checkpoint_conninfo(configured), autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_registry (
                    workflow_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL UNIQUE,
                    ticket_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    review_consumed BOOLEAN NOT NULL DEFAULT FALSE
                )
                """
            )
        PostgresSaver(connection).setup()

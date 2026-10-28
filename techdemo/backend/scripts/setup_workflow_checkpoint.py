"""Explicit setup for the isolated LangGraph PostgreSQL persistence schema."""

import sys

from app.core.config import get_settings
from app.workflows.checkpoint import setup_workflow_persistence


def main() -> int:
    settings = get_settings()
    if settings.app_environment != "development":
        print("FAIL: workflow checkpoint setup is limited to development.", file=sys.stderr)
        return 1
    try:
        setup_workflow_persistence(settings)
    except Exception:
        print("FAIL: workflow persistence setup could not complete.", file=sys.stderr)
        return 1
    print(f"Created or verified dedicated checkpoint schema: {settings.workflow_checkpoint_schema}")
    print("Created or verified workflow_registry and LangGraph checkpoint tables only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

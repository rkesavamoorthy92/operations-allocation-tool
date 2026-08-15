"""Immutable audit event recording."""

from __future__ import annotations

import getpass
from typing import Any
import sqlite3

from operations_allocation.domain.models import RunState


class AuditService:
    def __init__(self, repository: Any, application_name: str = "Operations Allocation Tool") -> None:
        self.repository = repository
        self.application_name = application_name

    def record(self, *, run_id: str | None, program_id: str, action: str, previous_state: RunState | None = None, new_state: RunState | None = None, metadata: dict[str, Any] | None = None, connection: sqlite3.Connection | None = None) -> None:
        self.repository.add(run_id=run_id, program_id=program_id, os_username=getpass.getuser(), application_name=self.application_name, action=action, previous_state=previous_state, new_state=new_state, metadata=metadata or {}, connection=connection)

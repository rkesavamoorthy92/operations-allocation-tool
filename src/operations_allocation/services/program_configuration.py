"""Creation and versioning of mutable program configurations."""

from __future__ import annotations

from typing import Any
import re

from operations_allocation.config.program_config import validate_program_configuration
from operations_allocation.domain.exceptions import InvalidConfigurationError
from operations_allocation.domain.models import Program
from operations_allocation.utils.canonical import canonical_json, sha256_for


class ProgramConfigurationService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def create_program(self, program_id: str, name: str) -> Program:
        if not re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)*", program_id):
            raise InvalidConfigurationError("Program ID must use uppercase letters, digits, and internal hyphens only.")
        if not name.strip():
            raise InvalidConfigurationError("Program name must not be blank.")
        program = Program(program_id=program_id, name=name)
        self.repository.add(program)
        return program

    def save_version(self, configuration: dict[str, Any]) -> None:
        validate_program_configuration(configuration)
        self.repository.get(configuration["program_id"])
        self.repository.save_configuration(configuration["program_id"], configuration["version"], canonical_json(configuration), sha256_for(configuration))

    def archive_program(self, program_id: str) -> None:
        """Soft-delete: hides the Program from the Dashboard's default view.
        Nothing is erased -- Program row, configuration versions, and every
        Run underneath it stay on disk and are restorable.
        """
        self.repository.get(program_id)
        self.repository.set_active(program_id, False)

    def restore_program(self, program_id: str) -> None:
        self.repository.get(program_id)
        self.repository.set_active(program_id, True)

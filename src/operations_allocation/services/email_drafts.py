"""Coordinates Outlook draft generation (PROJECT_SPEC.md section 18):
individual per-associate drafts (with their work file attached) and one
consolidated team draft. Runs after Distribution.

Always persists a plain-text rendering of every draft as an artifact
first -- this is the manual-email fallback that keeps the workflow usable
when Outlook/COM is unavailable (AGENTS.md section 16). Outlook draft
creation is then attempted on a best-effort basis; if it fails, the
failure is recorded in the audit trail rather than raised, so a missing
Outlook installation never blocks the operator from getting a
send-ready email out (via the fallback text).

Never sends email -- only creates drafts (Outlook) or fallback text
(manual). AGENTS.md section 50.
"""

from __future__ import annotations

from typing import Any

from operations_allocation.core.email_content import build_consolidated_draft, build_individual_draft, render_draft_as_text
from operations_allocation.domain.exceptions import AssociateFileNotDistributedError, EmailTemplateError, OutlookUnavailableError
from operations_allocation.domain.models import ArtifactType


class EmailDraftService:
    def __init__(self, *, snapshots: Any, allocation_results: Any, file_artifacts: Any, audit: Any) -> None:
        self.snapshots, self.allocation_results = snapshots, allocation_results
        self.file_artifacts, self.audit = file_artifacts, audit

    def create_individual_drafts(self, *, run_id: str, outlook_adapter: Any = None) -> tuple[Any, ...]:
        configuration, templates = self._load_context(run_id)
        allocation_result = self.allocation_results.get(run_id)
        associates_by_id = {associate["associate_id"]: associate for associate in configuration["associates"]}
        due_date = self._require_due_date(configuration)
        subject_template, body_template = self._require_templates(templates, "individual_subject", "individual_body")

        associate_files = {
            artifact.associate_id: artifact
            for artifact in self.file_artifacts.list_for_run(run_id)
            if artifact.artifact_type is ArtifactType.ASSOCIATE_FILES
        }

        artifacts = []
        for assignment in allocation_result.assignments:
            if assignment.planned_count == 0:
                continue
            associate = associates_by_id[assignment.associate_id]
            work_file = associate_files.get(assignment.associate_id)
            if work_file is None:
                raise AssociateFileNotDistributedError(
                    f"Associate '{assignment.associate_id}' has no distributed work file yet. Run Distribution before creating drafts."
                )
            attachment_path = str(self.file_artifacts.run_directory(run_id) / work_file.relative_path)

            draft = build_individual_draft(
                associate_id=assignment.associate_id,
                associate_email=associate["email"],
                associate_name=associate["name"],
                program_name=configuration["program_configuration"]["program_name"],
                run_id=run_id,
                item_count=assignment.planned_count,
                due_date=due_date,
                subject_template=subject_template,
                body_template=body_template,
                attachment_paths=(attachment_path,),
            )
            artifacts.append(self._persist_and_dispatch(run_id=run_id, draft=draft, outlook_adapter=outlook_adapter))
        return tuple(artifacts)

    def create_consolidated_draft(self, *, run_id: str, outlook_adapter: Any = None) -> Any:
        configuration, templates = self._load_context(run_id)
        allocation_result = self.allocation_results.get(run_id)
        associates_by_id = {associate["associate_id"]: associate for associate in configuration["associates"]}
        due_date = self._require_due_date(configuration)
        subject_template, body_template = self._require_templates(templates, "consolidated_subject", "consolidated_body")

        recipients = sorted({associates_by_id[a.associate_id]["email"] for a in allocation_result.assignments if a.planned_count > 0})
        draft = build_consolidated_draft(
            recipient_emails=recipients,
            program_name=configuration["program_configuration"]["program_name"],
            run_id=run_id,
            total_item_count=allocation_result.sample_count,
            due_date=due_date,
            subject_template=subject_template,
            body_template=body_template,
        )
        return self._persist_and_dispatch(run_id=run_id, draft=draft, outlook_adapter=outlook_adapter)

    def _load_context(self, run_id: str) -> tuple[dict, dict]:
        snapshot = self.snapshots.get(run_id)
        return snapshot.configuration, snapshot.configuration["program_configuration"]["email"].get("templates", {})

    @staticmethod
    def _require_templates(templates: dict, subject_key: str, body_key: str) -> tuple[str, str]:
        missing = [key for key in (subject_key, body_key) if key not in templates]
        if missing:
            raise EmailTemplateError(f"Email configuration is missing required template(s): {', '.join(missing)}.")
        return templates[subject_key], templates[body_key]

    @staticmethod
    def _require_due_date(configuration: dict) -> str:
        due_date = configuration.get("due_date")
        if not due_date:
            raise EmailTemplateError("Run due date has not been set. Enter a due date before creating email drafts.")
        return due_date

    def _persist_and_dispatch(self, *, run_id: str, draft: Any, outlook_adapter: Any) -> Any:
        filename_suffix = draft.associate_id if draft.associate_id else "team"
        artifact = self.file_artifacts.write_bytes(
            run_id=run_id,
            artifact_type=ArtifactType.EMAIL_DRAFTS,
            filename=f"{draft.draft_type}_{filename_suffix}.txt",
            content=render_draft_as_text(draft).encode("utf-8"),
            associate_id=draft.associate_id,
        )
        outlook_created = False
        outlook_error: str | None = None
        if outlook_adapter is not None:
            try:
                outlook_adapter.create_draft(draft)
                outlook_created = True
            except OutlookUnavailableError as error:
                outlook_error = str(error)

        self.audit.record(
            run_id=run_id,
            program_id=run_id.rsplit("-", 2)[0],
            action="EMAIL_DRAFT_CREATED",
            metadata={
                "draft_type": draft.draft_type,
                "associate_id": draft.associate_id,
                "recipients": list(draft.recipients),
                "outlook_created": outlook_created,
                "outlook_error": outlook_error,
                "fallback_artifact_sha256": artifact.sha256,
            },
        )
        return artifact

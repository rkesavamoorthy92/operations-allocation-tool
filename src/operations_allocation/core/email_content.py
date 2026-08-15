"""Builds the content of Outlook email drafts (PROJECT_SPEC.md section 18):
one draft per associate (with their work file attached) and one
consolidated draft to the whole distributed team. Pure logic -- actual
Outlook/COM interaction lives in ``infrastructure.outlook_adapter``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from operations_allocation.core.email_templates import render_template


@dataclass(frozen=True, slots=True)
class EmailDraftContent:
    draft_type: str
    """'individual' or 'consolidated'."""

    associate_id: str | None
    recipients: tuple[str, ...]
    subject: str
    body: str
    attachment_paths: tuple[str, ...]


def build_individual_draft(
    *,
    associate_id: str,
    associate_email: str,
    associate_name: str,
    program_name: str,
    run_id: str,
    item_count: int,
    due_date: str,
    subject_template: str,
    body_template: str,
    attachment_paths: Sequence[str],
) -> EmailDraftContent:
    values = {"associate_name": associate_name, "program_name": program_name, "run_id": run_id, "item_count": str(item_count), "due_date": due_date}
    return EmailDraftContent(
        draft_type="individual",
        associate_id=associate_id,
        recipients=(associate_email,),
        subject=render_template(subject_template, values),
        body=render_template(body_template, values),
        attachment_paths=tuple(attachment_paths),
    )


def build_consolidated_draft(
    *,
    recipient_emails: Sequence[str],
    program_name: str,
    run_id: str,
    total_item_count: int,
    due_date: str,
    subject_template: str,
    body_template: str,
) -> EmailDraftContent:
    values = {"program_name": program_name, "run_id": run_id, "item_count": str(total_item_count), "due_date": due_date}
    return EmailDraftContent(
        draft_type="consolidated",
        associate_id=None,
        recipients=tuple(recipient_emails),
        subject=render_template(subject_template, values),
        body=render_template(body_template, values),
        attachment_paths=(),
    )


def render_draft_as_text(draft: EmailDraftContent) -> str:
    """Render a draft as plain text -- the manual-email fallback
    (PROJECT_SPEC.md section 18 / AGENTS.md section 16) used whenever
    Outlook/COM is unavailable, so the operator can copy this into any
    email client and send it themselves.
    """
    lines = [f"To: {'; '.join(draft.recipients)}", f"Subject: {draft.subject}"]
    if draft.attachment_paths:
        lines.append(f"Attachments: {'; '.join(draft.attachment_paths)}")
    lines.append("")
    lines.append(draft.body)
    return "\n".join(lines)

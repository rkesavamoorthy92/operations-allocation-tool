"""Outlook Platform Adapter (ARCHITECTURE.md section 4.7).

Isolates Classic desktop Outlook COM automation (PROJECT_SPEC.md section
18 / AGENTS.md section 16 -- v1 targets Windows Outlook via COM) behind a
narrow interface so core business logic never imports ``win32com``
directly. ``pywin32`` is imported lazily inside methods, not at module
level, so this module can be imported (and the rest of the application
can run) even on a machine where Outlook/pywin32 is unavailable --
ARCHITECTURE.md section 9.4, "Core engines and services must run without
Outlook installed."

Draft creation only. This adapter never sends email -- AGENTS.md section
50.
"""

from __future__ import annotations

from typing import Sequence

from operations_allocation.core.email_content import EmailDraftContent
from operations_allocation.domain.exceptions import OutlookUnavailableError


class OutlookComAdapter:
    """Creates Outlook drafts via COM automation against a running or
    launchable Classic desktop Outlook installation."""

    def is_available(self) -> bool:
        try:
            self._dispatch()
            return True
        except Exception:
            return False

    def create_draft(self, draft: EmailDraftContent) -> None:
        try:
            outlook = self._dispatch()
            mail_item = outlook.CreateItem(0)  # 0 == olMailItem
            mail_item.To = "; ".join(draft.recipients)
            mail_item.Subject = draft.subject
            mail_item.Body = draft.body
            for attachment_path in draft.attachment_paths:
                mail_item.Attachments.Add(str(attachment_path))
            mail_item.Save()  # Saves as a draft; deliberately never .Send()
        except Exception as error:
            raise OutlookUnavailableError(f"Could not create an Outlook draft via COM: {error}") from error

    @staticmethod
    def _dispatch() -> object:
        try:
            import win32com.client
        except ImportError as error:
            raise OutlookUnavailableError("pywin32 is not installed; Outlook COM automation is unavailable.") from error
        return win32com.client.Dispatch("Outlook.Application")

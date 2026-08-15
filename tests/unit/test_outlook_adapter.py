from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from operations_allocation.core.email_content import EmailDraftContent
from operations_allocation.domain.exceptions import OutlookUnavailableError
from operations_allocation.infrastructure.outlook_adapter import OutlookComAdapter


def _draft() -> EmailDraftContent:
    return EmailDraftContent(draft_type="individual", associate_id="A001", recipients=("jane@example.test",), subject="Subject", body="Body", attachment_paths=("C:/files/a.xlsx",))


class OutlookComAdapterTestCase(unittest.TestCase):
    def _install_fake_win32com(self, application_mock: MagicMock) -> None:
        fake_module = types.ModuleType("win32com")
        fake_client = types.ModuleType("win32com.client")
        fake_client.Dispatch = MagicMock(return_value=application_mock)
        fake_module.client = fake_client
        self._patcher = patch.dict(sys.modules, {"win32com": fake_module, "win32com.client": fake_client})
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_create_draft_saves_but_never_sends(self) -> None:
        mail_item = MagicMock()
        application = MagicMock()
        application.CreateItem.return_value = mail_item
        self._install_fake_win32com(application)

        OutlookComAdapter().create_draft(_draft())

        mail_item.Save.assert_called_once()
        mail_item.Send.assert_not_called()
        self.assertEqual(mail_item.To, "jane@example.test")
        self.assertEqual(mail_item.Subject, "Subject")
        self.assertEqual(mail_item.Body, "Body")
        mail_item.Attachments.Add.assert_called_once_with("C:/files/a.xlsx")

    def test_is_available_true_when_dispatch_succeeds(self) -> None:
        self._install_fake_win32com(MagicMock())
        self.assertTrue(OutlookComAdapter().is_available())

    def test_missing_pywin32_raises_outlook_unavailable(self) -> None:
        with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
            with self.assertRaises(OutlookUnavailableError):
                OutlookComAdapter().create_draft(_draft())

    def test_is_available_false_when_dispatch_fails(self) -> None:
        with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
            self.assertFalse(OutlookComAdapter().is_available())

    def test_com_failure_during_send_raises_outlook_unavailable_not_bare_exception(self) -> None:
        application = MagicMock()
        application.CreateItem.side_effect = RuntimeError("COM error")
        self._install_fake_win32com(application)
        with self.assertRaises(OutlookUnavailableError):
            OutlookComAdapter().create_draft(_draft())

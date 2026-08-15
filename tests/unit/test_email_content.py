from __future__ import annotations

import unittest

from operations_allocation.core.email_content import build_consolidated_draft, build_individual_draft, render_draft_as_text
from operations_allocation.core.email_templates import render_template
from operations_allocation.domain.exceptions import EmailTemplateError


class RenderTemplateTestCase(unittest.TestCase):
    def test_substitutes_supported_tokens(self) -> None:
        result = render_template("Hi {{associate_name}}, {{item_count}} items due {{due_date}}.", {"associate_name": "Jane", "item_count": "10", "due_date": "2026-08-20"})
        self.assertEqual(result, "Hi Jane, 10 items due 2026-08-20.")

    def test_unsupported_placeholder_raises(self) -> None:
        with self.assertRaises(EmailTemplateError):
            render_template("Hi {{secret_field}}", {})

    def test_missing_value_for_supported_token_raises(self) -> None:
        with self.assertRaises(EmailTemplateError):
            render_template("Hi {{associate_name}}", {})

    def test_template_with_no_placeholders_passes_through(self) -> None:
        self.assertEqual(render_template("Plain text, no tokens.", {}), "Plain text, no tokens.")

    def test_repeated_token_substituted_every_occurrence(self) -> None:
        result = render_template("{{run_id}} / {{run_id}}", {"run_id": "R1"})
        self.assertEqual(result, "R1 / R1")


class BuildIndividualDraftTestCase(unittest.TestCase):
    def test_builds_expected_content(self) -> None:
        draft = build_individual_draft(
            associate_id="A001", associate_email="jane@example.test", associate_name="Jane Doe",
            program_name="MX PT", run_id="MX-PT-20260815-01", item_count=25, due_date="2026-08-20",
            subject_template="{{program_name}} allocation for {{associate_name}}",
            body_template="You have {{item_count}} items due {{due_date}} (Run {{run_id}}).",
            attachment_paths=("C:/files/a.xlsx",),
        )
        self.assertEqual(draft.draft_type, "individual")
        self.assertEqual(draft.recipients, ("jane@example.test",))
        self.assertEqual(draft.subject, "MX PT allocation for Jane Doe")
        self.assertEqual(draft.body, "You have 25 items due 2026-08-20 (Run MX-PT-20260815-01).")
        self.assertEqual(draft.attachment_paths, ("C:/files/a.xlsx",))

    def test_consolidated_template_cannot_use_associate_name(self) -> None:
        with self.assertRaises(EmailTemplateError):
            build_consolidated_draft(
                recipient_emails=["a@example.test"], program_name="MX PT", run_id="R1", total_item_count=1, due_date="2026-08-20",
                subject_template="Hi {{associate_name}}", body_template="body",
            )


class BuildConsolidatedDraftTestCase(unittest.TestCase):
    def test_builds_expected_content(self) -> None:
        draft = build_consolidated_draft(
            recipient_emails=["a@example.test", "b@example.test"], program_name="MX PT", run_id="R1", total_item_count=40, due_date="2026-08-20",
            subject_template="{{program_name}} team allocation", body_template="{{item_count}} items total, due {{due_date}}.",
        )
        self.assertEqual(draft.draft_type, "consolidated")
        self.assertIsNone(draft.associate_id)
        self.assertEqual(draft.recipients, ("a@example.test", "b@example.test"))
        self.assertEqual(draft.subject, "MX PT team allocation")
        self.assertEqual(draft.body, "40 items total, due 2026-08-20.")
        self.assertEqual(draft.attachment_paths, ())


class RenderDraftAsTextTestCase(unittest.TestCase):
    def test_includes_recipients_subject_attachments_and_body(self) -> None:
        draft = build_individual_draft(
            associate_id="A001", associate_email="jane@example.test", associate_name="Jane Doe",
            program_name="MX PT", run_id="R1", item_count=5, due_date="2026-08-20",
            subject_template="Subject", body_template="Body text.", attachment_paths=("C:/files/a.xlsx",),
        )
        text = render_draft_as_text(draft)
        self.assertIn("To: jane@example.test", text)
        self.assertIn("Subject: Subject", text)
        self.assertIn("Attachments: C:/files/a.xlsx", text)
        self.assertIn("Body text.", text)

    def test_consolidated_draft_omits_attachments_line(self) -> None:
        draft = build_consolidated_draft(
            recipient_emails=["a@example.test"], program_name="MX PT", run_id="R1", total_item_count=1, due_date="2026-08-20",
            subject_template="Subject", body_template="Body.",
        )
        self.assertNotIn("Attachments:", render_draft_as_text(draft))

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from operations_allocation.ui.app_context import AppContext, default_data_directory


class AppContextTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_build_creates_data_directory_and_database(self) -> None:
        directory = Path(self.tempdir.name) / "app_data"
        context = AppContext.build(data_directory=directory)
        self.assertTrue(directory.exists())
        self.assertTrue((directory / "operations_allocation.db").exists())

    def test_default_data_directory_is_not_the_install_directory(self) -> None:
        directory = default_data_directory()
        self.assertNotIn("site-packages", str(directory))

    def test_wired_services_can_run_a_full_program_and_run_creation(self) -> None:
        context = AppContext.build(data_directory=Path(self.tempdir.name) / "app_data")
        context.program_configuration.create_program("MX-PT", "MX PT")
        self.assertEqual(len(context.programs.list_all()), 1)
        run = context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        self.assertEqual(len(context.runs.list_all()), 1)
        self.assertEqual(context.runs.get(run.run_id).run_id, run.run_id)

    def test_current_os_username_never_raises(self) -> None:
        self.assertIsInstance(AppContext.current_os_username(), str)

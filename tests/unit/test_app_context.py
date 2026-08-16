from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

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

    def test_default_data_directory_honors_explicit_override_env_var(self) -> None:
        # This is the deployment-time escape hatch for moving to a shared
        # location later (PROJECT_SPEC.md discussion: 'single-user local
        # now, shared DB later') without a code change or rebuild.
        with mock.patch.dict(os.environ, {"OPERATIONS_ALLOCATION_DATA_DIR": r"\\shared\OpsAllocation"}):
            self.assertEqual(default_data_directory(), Path(r"\\shared\OpsAllocation"))

    def test_default_data_directory_ignores_blank_override_env_var(self) -> None:
        with mock.patch.dict(os.environ, {"OPERATIONS_ALLOCATION_DATA_DIR": ""}):
            directory = default_data_directory()
        self.assertTrue(str(directory).endswith("OperationsAllocationTool"))

    def test_default_data_directory_strips_stray_whitespace_from_override(self) -> None:
        # A very easy real-world mistake: Windows' own "Edit environment
        # variables" GUI (and hand-written .bat wrappers) make it easy to
        # leave a trailing space, which sqlite3 then treats as a literal
        # path character and fails with a confusing "unable to open
        # database file" instead of anything pointing at the real cause.
        with mock.patch.dict(os.environ, {"OPERATIONS_ALLOCATION_DATA_DIR": "  C:\\Shared\\OpsAllocation  "}):
            self.assertEqual(default_data_directory(), Path("C:\\Shared\\OpsAllocation"))

    def test_wired_services_can_run_a_full_program_and_run_creation(self) -> None:
        context = AppContext.build(data_directory=Path(self.tempdir.name) / "app_data")
        context.program_configuration.create_program("MX-PT", "MX PT")
        self.assertEqual(len(context.programs.list_all()), 1)
        run = context.orchestration.create_run(program_id="MX-PT", created_by="tester", created_on=date(2026, 8, 15))
        self.assertEqual(len(context.runs.list_all()), 1)
        self.assertEqual(context.runs.get(run.run_id).run_id, run.run_id)

    def test_current_os_username_never_raises(self) -> None:
        self.assertIsInstance(AppContext.current_os_username(), str)

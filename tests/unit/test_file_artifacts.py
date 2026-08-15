from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from operations_allocation.domain.exceptions import ArtifactAlreadyExistsError, ArtifactSourceNotFoundError, InvalidArtifactFilenameError, PersistenceError
from operations_allocation.domain.models import ArtifactType
from operations_allocation.infrastructure.file_artifacts import FileArtifactManager, validate_artifact_filename
from operations_allocation.persistence.database import Database
from operations_allocation.persistence.repositories import ArtifactRepository, ProgramRepository, RunRepository
from operations_allocation.services.program_configuration import ProgramConfigurationService
from datetime import date


class ValidateArtifactFilenameTestCase(unittest.TestCase):
    def test_accepts_plain_filename(self) -> None:
        self.assertEqual(validate_artifact_filename("report.xlsx"), "report.xlsx")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(InvalidArtifactFilenameError):
            validate_artifact_filename("")

    def test_rejects_path_separators(self) -> None:
        with self.assertRaises(InvalidArtifactFilenameError):
            validate_artifact_filename("sub/report.xlsx")
        with self.assertRaises(InvalidArtifactFilenameError):
            validate_artifact_filename("sub\\report.xlsx")

    def test_rejects_traversal(self) -> None:
        with self.assertRaises(InvalidArtifactFilenameError):
            validate_artifact_filename("../report.xlsx")

    def test_rejects_absolute_path(self) -> None:
        with self.assertRaises(InvalidArtifactFilenameError):
            validate_artifact_filename("/etc/report.xlsx")


class FileArtifactManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.artifacts_root = Path(self.tempdir.name) / "artifacts"
        database = Database(Path(self.tempdir.name) / "artifacts.db")
        database.initialize_schema()
        self.artifacts_repo = ArtifactRepository(database)
        self.manager = FileArtifactManager(base_directory=self.artifacts_root, artifacts=self.artifacts_repo)
        programs = ProgramRepository(database)
        ProgramConfigurationService(programs).create_program("MX-PT", "MX PT")
        self.run = RunRepository(database).create_next("MX-PT", "user", None, date(2026, 8, 15))

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_write_bytes_creates_file_and_registers_artifact(self) -> None:
        artifact = self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="summary.txt", content=b"hello")
        expected_path = self.manager.run_directory(self.run.run_id) / "reports" / "summary.txt"
        self.assertTrue(expected_path.is_file())
        self.assertEqual(expected_path.read_bytes(), b"hello")
        self.assertEqual(artifact.byte_size, 5)
        self.assertEqual(len(artifact.sha256), 64)
        stored = self.artifacts_repo.list_for_run(self.run.run_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].original_filename, "summary.txt")

    def test_write_bytes_never_silently_overwrites(self) -> None:
        self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="summary.txt", content=b"one")
        with self.assertRaises(ArtifactAlreadyExistsError):
            self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="summary.txt", content=b"two")
        expected_path = self.manager.run_directory(self.run.run_id) / "reports" / "summary.txt"
        self.assertEqual(expected_path.read_bytes(), b"one")

    def test_write_bytes_rejects_unsafe_filename(self) -> None:
        with self.assertRaises(InvalidArtifactFilenameError):
            self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="../escape.txt", content=b"x")

    def test_no_temp_files_left_behind_after_write(self) -> None:
        self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="summary.txt", content=b"hello")
        remaining = list((self.manager.run_directory(self.run.run_id) / "reports").iterdir())
        self.assertEqual(remaining, [self.manager.run_directory(self.run.run_id) / "reports" / "summary.txt"])

    def test_import_file_copies_without_touching_source(self) -> None:
        source_dir = Path(self.tempdir.name) / "external"
        source_dir.mkdir()
        source_path = source_dir / "input.csv"
        source_path.write_bytes(b"a,b,c\n1,2,3\n")
        artifact = self.manager.import_file(run_id=self.run.run_id, artifact_type=ArtifactType.SOURCE, source_path=source_path)
        self.assertEqual(artifact.original_filename, "input.csv")
        self.assertTrue(source_path.is_file())
        self.assertEqual(source_path.read_bytes(), b"a,b,c\n1,2,3\n")
        self.assertEqual(self.manager.read_bytes(artifact), b"a,b,c\n1,2,3\n")

    def test_import_file_missing_source_raises(self) -> None:
        with self.assertRaises(ArtifactSourceNotFoundError):
            self.manager.import_file(run_id=self.run.run_id, artifact_type=ArtifactType.SOURCE, source_path=Path(self.tempdir.name) / "nope.csv")

    def test_ensure_run_directories_creates_all_artifact_type_folders(self) -> None:
        self.manager.ensure_run_directories(self.run.run_id)
        for artifact_type in ArtifactType:
            self.assertTrue((self.manager.run_directory(self.run.run_id) / artifact_type.value).is_dir())

    def test_artifacts_table_is_append_only(self) -> None:
        self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="summary.txt", content=b"hello")
        with self.assertRaises(PersistenceError):
            with self.artifacts_repo.database.transaction() as connection:
                connection.execute("UPDATE artifacts SET sha256 = 'x' WHERE run_id = ?", (self.run.run_id,))
        with self.assertRaises(PersistenceError):
            with self.artifacts_repo.database.transaction() as connection:
                connection.execute("DELETE FROM artifacts WHERE run_id = ?", (self.run.run_id,))

    def test_list_for_run_orders_by_creation(self) -> None:
        self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="first.txt", content=b"1")
        self.manager.write_bytes(run_id=self.run.run_id, artifact_type=ArtifactType.REPORTS, filename="second.txt", content=b"2")
        names = [artifact.original_filename for artifact in self.manager.list_for_run(self.run.run_id)]
        self.assertEqual(names, ["first.txt", "second.txt"])

"""
Tests for E2E artifact storage.

These tests validate the ArtifactStorage class which manages the
structured storage layout for E2E test artifacts.
"""

import json
import pytest
import tempfile
from pathlib import Path

from systemeval.e2e.storage import (
    ArtifactStorage,
    StorageError,
    RunNotFoundError,
    ArtifactNotFoundError,
)
from systemeval.e2e.types import ChangeSet, Change, ChangeType


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_dir):
    """Create an ArtifactStorage instance with a temp directory."""
    return ArtifactStorage(temp_dir)


@pytest.fixture
def sample_changeset(temp_dir):
    """Create a sample ChangeSet for testing."""
    return ChangeSet(
        base_ref="main",
        head_ref="feature-branch",
        changes=[
            Change(
                file_path="src/api/users.py",
                change_type=ChangeType.MODIFIED,
                additions=10,
                deletions=5,
            ),
            Change(
                file_path="src/api/auth.py",
                change_type=ChangeType.ADDED,
                additions=50,
                deletions=0,
            ),
        ],
        repository_root=temp_dir,
        metadata={"pr_number": 123},
    )


@pytest.fixture
def sample_metadata():
    """Create sample metadata for testing."""
    return {
        "status": "completed",
        "provider": "debuggai",
        "tests_count": 5,
        "started_at": "2024-01-15T10:00:00Z",
        "completed_at": "2024-01-15T10:05:00Z",
    }


# ============================================================================
# Initialization Tests
# ============================================================================


class TestArtifactStorageInit:
    """Test ArtifactStorage initialization."""

    def test_creates_base_directories(self, temp_dir):
        """Test that base directories are created on init."""
        storage = ArtifactStorage(temp_dir)

        runs_dir = temp_dir / "runs"
        assert runs_dir.exists()
        assert runs_dir.is_dir()

    def test_skips_directory_creation_when_disabled(self, temp_dir):
        """Test that directories are not created when disabled."""
        output_dir = temp_dir / "new_output"
        storage = ArtifactStorage(output_dir, create_directories=False)

        assert not (output_dir / "runs").exists()

    def test_handles_relative_path(self):
        """Test that relative paths are converted to absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a path relative to the temp dir
            storage = ArtifactStorage(Path(tmpdir) / "relative" / "path")
            assert storage.output_directory.is_absolute()

    def test_handles_string_path(self, temp_dir):
        """Test that string paths are converted to Path objects."""
        storage = ArtifactStorage(str(temp_dir))
        assert isinstance(storage.output_directory, Path)


# ============================================================================
# Run Management Tests
# ============================================================================


class TestRunManagement:
    """Test run directory management."""

    def test_get_run_directory_creates(self, storage):
        """Test get_run_directory creates the directory."""
        run_dir = storage.get_run_directory("run_001")

        assert run_dir.exists()
        assert run_dir.is_dir()
        assert run_dir.name == "run_001"
        assert (run_dir / "tests").exists()

    def test_get_run_directory_idempotent(self, storage):
        """Test get_run_directory is idempotent."""
        run_dir1 = storage.get_run_directory("run_001")
        run_dir2 = storage.get_run_directory("run_001")

        assert run_dir1 == run_dir2

    def test_get_run_directory_no_create_raises(self, storage):
        """Test get_run_directory raises when create=False and run doesn't exist."""
        with pytest.raises(RunNotFoundError) as exc:
            storage.get_run_directory("nonexistent", create=False)

        assert exc.value.run_id == "nonexistent"

    def test_run_exists(self, storage):
        """Test run_exists method."""
        assert not storage.run_exists("run_001")

        storage.get_run_directory("run_001")
        assert storage.run_exists("run_001")

    def test_list_runs_empty(self, storage):
        """Test list_runs returns empty list when no runs."""
        assert storage.list_runs() == []

    def test_list_runs_returns_sorted(self, storage):
        """Test list_runs returns runs sorted by modification time."""
        # Create runs in order
        storage.get_run_directory("run_001")
        storage.get_run_directory("run_002")
        storage.get_run_directory("run_003")

        runs = storage.list_runs()
        assert len(runs) == 3
        # Most recent first
        assert runs[0] == "run_003"

    def test_get_latest_run(self, storage):
        """Test get_latest_run returns most recent."""
        storage.get_run_directory("run_001")
        storage.get_run_directory("run_002")

        assert storage.get_latest_run() == "run_002"

    def test_get_latest_run_empty(self, storage):
        """Test get_latest_run returns None when no runs."""
        assert storage.get_latest_run() is None

    def test_delete_run(self, storage):
        """Test delete_run removes run directory."""
        storage.get_run_directory("run_001")
        assert storage.run_exists("run_001")

        result = storage.delete_run("run_001")
        assert result is True
        assert not storage.run_exists("run_001")

    def test_delete_run_nonexistent(self, storage):
        """Test delete_run returns False for nonexistent run."""
        result = storage.delete_run("nonexistent")
        assert result is False

    def test_cleanup_old_runs(self, storage):
        """Test cleanup_old_runs keeps only specified count."""
        # Create several runs
        for i in range(5):
            storage.get_run_directory(f"run_{i:03d}")

        deleted = storage.cleanup_old_runs(keep_count=2)

        assert len(deleted) == 3
        assert len(storage.list_runs()) == 2

    def test_cleanup_old_runs_keeps_all_when_under_limit(self, storage):
        """Test cleanup_old_runs keeps all when under limit."""
        storage.get_run_directory("run_001")
        storage.get_run_directory("run_002")

        deleted = storage.cleanup_old_runs(keep_count=5)

        assert len(deleted) == 0
        assert len(storage.list_runs()) == 2

    def test_cleanup_old_runs_invalid_count(self, storage):
        """Test cleanup_old_runs raises for negative count."""
        with pytest.raises(ValueError):
            storage.cleanup_old_runs(keep_count=-1)


# ============================================================================
# Metadata Tests
# ============================================================================


class TestMetadata:
    """Test metadata save/load operations."""

    def test_save_metadata(self, storage, sample_metadata):
        """Test save_metadata creates metadata file."""
        path = storage.save_metadata("run_001", sample_metadata)

        assert path.exists()
        assert path.name == "metadata.json"

    def test_save_metadata_adds_timestamp(self, storage):
        """Test save_metadata adds saved_at timestamp."""
        storage.save_metadata("run_001", {"status": "running"})

        metadata = storage.load_metadata("run_001")
        assert "saved_at" in metadata

    def test_save_metadata_preserves_existing_timestamp(self, storage):
        """Test save_metadata preserves existing saved_at."""
        original_timestamp = "2024-01-01T00:00:00Z"
        storage.save_metadata("run_001", {"saved_at": original_timestamp})

        metadata = storage.load_metadata("run_001")
        assert metadata["saved_at"] == original_timestamp

    def test_load_metadata(self, storage, sample_metadata):
        """Test load_metadata retrieves saved metadata."""
        storage.save_metadata("run_001", sample_metadata)

        loaded = storage.load_metadata("run_001")
        assert loaded["status"] == sample_metadata["status"]
        assert loaded["provider"] == sample_metadata["provider"]

    def test_load_metadata_run_not_found(self, storage):
        """Test load_metadata raises for nonexistent run."""
        with pytest.raises(RunNotFoundError):
            storage.load_metadata("nonexistent")

    def test_load_metadata_file_not_found(self, storage):
        """Test load_metadata raises when file doesn't exist."""
        storage.get_run_directory("run_001")

        with pytest.raises(FileNotFoundError):
            storage.load_metadata("run_001")

    def test_update_metadata(self, storage, sample_metadata):
        """Test update_metadata merges with existing."""
        storage.save_metadata("run_001", sample_metadata)

        updated = storage.update_metadata("run_001", {"status": "failed", "error": "timeout"})

        assert updated["status"] == "failed"
        assert updated["error"] == "timeout"
        assert updated["provider"] == sample_metadata["provider"]
        assert "updated_at" in updated

    def test_update_metadata_creates_if_missing(self, storage):
        """Test update_metadata creates metadata if it doesn't exist."""
        storage.get_run_directory("run_001")

        updated = storage.update_metadata("run_001", {"status": "running"})

        assert updated["status"] == "running"


# ============================================================================
# Changeset Tests
# ============================================================================


class TestChangeset:
    """Test changeset save/load operations."""

    def test_save_changeset(self, storage, sample_changeset):
        """Test save_changeset creates changeset file."""
        path = storage.save_changeset("run_001", sample_changeset)

        assert path.exists()
        assert path.name == "changeset.json"

    def test_load_changeset(self, storage, sample_changeset):
        """Test load_changeset retrieves saved changeset."""
        storage.save_changeset("run_001", sample_changeset)

        loaded = storage.load_changeset("run_001")

        assert loaded["base_ref"] == "main"
        assert loaded["head_ref"] == "feature-branch"
        assert len(loaded["changes"]) == 2
        assert loaded["metadata"]["pr_number"] == 123

    def test_load_changeset_run_not_found(self, storage):
        """Test load_changeset raises for nonexistent run."""
        with pytest.raises(RunNotFoundError):
            storage.load_changeset("nonexistent")

    def test_load_changeset_file_not_found(self, storage):
        """Test load_changeset raises when file doesn't exist."""
        storage.get_run_directory("run_001")

        with pytest.raises(FileNotFoundError):
            storage.load_changeset("run_001")


# ============================================================================
# Test Artifact Tests
# ============================================================================


class TestTestArtifacts:
    """Test artifact save/load operations."""

    def test_save_test_artifact_script(self, storage):
        """Test saving a test script artifact."""
        script_content = "test('login', async () => { /* test code */ });"

        path = storage.save_test_artifact(
            "run_001", "test_login", "script", script_content
        )

        assert path.exists()
        assert path.suffix == ".ts"
        assert "test_login" in path.stem

    def test_save_test_artifact_binary(self, storage):
        """Test saving a binary artifact (recording)."""
        # Fake GIF content
        gif_content = b"GIF89a\x01\x00\x01\x00"

        path = storage.save_test_artifact(
            "run_001", "test_login", "recording", gif_content
        )

        assert path.exists()
        assert path.suffix == ".gif"

    def test_save_test_artifact_custom_extension(self, storage):
        """Test saving artifact with custom extension."""
        path = storage.save_test_artifact(
            "run_001", "test_login", "custom", "data", extension=".custom"
        )

        assert path.suffix == ".custom"

    def test_load_test_artifact_text(self, storage):
        """Test loading text artifact."""
        content = "test content"
        storage.save_test_artifact("run_001", "test_login", "script", content)

        loaded = storage.load_test_artifact("run_001", "test_login", "script")
        assert loaded == content

    def test_load_test_artifact_binary(self, storage):
        """Test loading binary artifact."""
        content = b"\x00\x01\x02\x03"
        storage.save_test_artifact("run_001", "test_login", "recording", content)

        loaded = storage.load_test_artifact(
            "run_001", "test_login", "recording", as_bytes=True
        )
        assert loaded == content

    def test_load_test_artifact_not_found(self, storage):
        """Test load_test_artifact raises for nonexistent artifact."""
        storage.get_run_directory("run_001")

        with pytest.raises(ArtifactNotFoundError) as exc:
            storage.load_test_artifact("run_001", "test_login", "script")

        assert exc.value.run_id == "run_001"
        assert exc.value.test_name == "test_login"
        assert exc.value.artifact_type == "script"

    def test_save_test_details(self, storage):
        """Test saving test details."""
        details = {
            "name": "Login Test",
            "description": "Tests user login flow",
            "steps": ["navigate", "fill form", "submit"],
        }

        path = storage.save_test_details("run_001", "test_login", details)

        assert path.exists()
        assert path.name == "details.json"

    def test_load_test_details(self, storage):
        """Test loading test details."""
        details = {"name": "Test", "steps": ["step1", "step2"]}
        storage.save_test_details("run_001", "test_login", details)

        loaded = storage.load_test_details("run_001", "test_login")
        assert loaded == details

    def test_load_test_details_not_found(self, storage):
        """Test load_test_details raises when not found."""
        storage.get_run_directory("run_001")

        with pytest.raises(FileNotFoundError):
            storage.load_test_details("run_001", "nonexistent")

    def test_list_tests(self, storage):
        """Test list_tests returns all test names."""
        storage.save_test_artifact("run_001", "test_login", "script", "content")
        storage.save_test_artifact("run_001", "test_checkout", "script", "content")
        storage.save_test_artifact("run_001", "test_search", "script", "content")

        tests = storage.list_tests("run_001")

        assert len(tests) == 3
        assert "test_login" in tests
        assert "test_checkout" in tests
        assert "test_search" in tests

    def test_list_tests_empty(self, storage):
        """Test list_tests returns empty list for run without tests."""
        storage.get_run_directory("run_001")

        tests = storage.list_tests("run_001")
        assert tests == []

    def test_list_test_artifacts(self, storage):
        """Test list_test_artifacts returns all artifacts for a test."""
        storage.save_test_artifact("run_001", "test_login", "script", "content")
        storage.save_test_artifact("run_001", "test_login", "recording", b"gif")
        storage.save_test_details("run_001", "test_login", {"name": "test"})

        artifacts = storage.list_test_artifacts("run_001", "test_login")

        assert len(artifacts) == 3

    def test_list_test_artifacts_nonexistent(self, storage):
        """Test list_test_artifacts returns empty for nonexistent test."""
        storage.get_run_directory("run_001")

        artifacts = storage.list_test_artifacts("run_001", "nonexistent")
        assert artifacts == []


# ============================================================================
# Name Sanitization Tests
# ============================================================================


class TestNameSanitization:
    """Test name sanitization for file/directory names."""

    def test_sanitizes_spaces(self, storage):
        """Test that spaces are replaced with underscores."""
        path = storage.save_test_artifact(
            "run_001", "test with spaces", "script", "content"
        )

        assert " " not in str(path)
        assert "test_with_spaces" in str(path)

    def test_sanitizes_special_characters(self, storage):
        """Test that special characters are replaced."""
        path = storage.save_test_artifact(
            "run_001", "test:name/with*special", "script", "content"
        )

        # Check only the filename and its parent directory name (not full path)
        filename = path.name
        parent_name = path.parent.name
        for char in [':', '*', '?', '<', '>', '|']:
            assert char not in filename
            assert char not in parent_name

    def test_sanitizes_backslashes(self, storage):
        """Test that backslashes are replaced."""
        path = storage.save_test_artifact(
            "run_001", "test\\name", "script", "content"
        )

        assert "\\" not in str(path)


# ============================================================================
# Latest Symlink Tests
# ============================================================================


class TestLatestSymlink:
    """Test latest symlink management."""

    def test_save_metadata_updates_latest(self, storage):
        """Test that save_metadata updates latest symlink."""
        storage.save_metadata("run_001", {"status": "completed"})

        latest = storage.output_directory / "latest"
        assert latest.is_symlink()

    def test_latest_points_to_most_recent(self, storage):
        """Test latest symlink points to most recently saved run."""
        storage.save_metadata("run_001", {"status": "completed"})
        storage.save_metadata("run_002", {"status": "completed"})

        latest_path = storage.get_latest_path()
        assert latest_path is not None
        assert latest_path.name == "run_002"

    def test_get_latest_path_no_symlink(self, storage):
        """Test get_latest_path returns None when no symlink."""
        assert storage.get_latest_path() is None

    def test_delete_run_updates_latest(self, storage):
        """Test deleting the latest run updates symlink."""
        storage.save_metadata("run_001", {"status": "completed"})
        storage.save_metadata("run_002", {"status": "completed"})

        storage.delete_run("run_002")

        latest_path = storage.get_latest_path()
        assert latest_path is not None
        assert latest_path.name == "run_001"


# ============================================================================
# Utility Method Tests
# ============================================================================


class TestUtilityMethods:
    """Test utility methods."""

    def test_get_total_size(self, storage):
        """Test get_total_size returns correct size."""
        # Create some content
        storage.save_test_artifact("run_001", "test1", "script", "a" * 100)
        storage.save_test_artifact("run_001", "test2", "script", "b" * 200)
        storage.save_metadata("run_001", {"status": "completed"})

        total_size = storage.get_total_size("run_001")

        # Size should be at least the content we wrote
        assert total_size >= 300

    def test_get_total_size_nonexistent(self, storage):
        """Test get_total_size returns 0 for nonexistent run."""
        assert storage.get_total_size("nonexistent") == 0

    def test_get_run_info(self, storage, sample_metadata):
        """Test get_run_info returns comprehensive info."""
        storage.save_metadata("run_001", sample_metadata)
        storage.save_test_artifact("run_001", "test1", "script", "content")
        storage.save_test_artifact("run_001", "test2", "script", "content")

        info = storage.get_run_info("run_001")

        assert info["run_id"] == "run_001"
        assert info["tests_count"] == 2
        assert "test1" in info["tests"]
        assert "test2" in info["tests"]
        assert info["total_size_bytes"] > 0
        assert info["metadata"]["status"] == "completed"
        assert "created_at" in info
        assert "modified_at" in info

    def test_get_run_info_not_found(self, storage):
        """Test get_run_info raises for nonexistent run."""
        with pytest.raises(RunNotFoundError):
            storage.get_run_info("nonexistent")


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for full storage workflows."""

    def test_complete_run_workflow(self, storage, sample_changeset, sample_metadata):
        """Test complete workflow: create run, save artifacts, retrieve."""
        run_id = "run_integration_001"

        # Create run and save metadata
        storage.save_metadata(run_id, sample_metadata)
        storage.save_changeset(run_id, sample_changeset)

        # Save test artifacts
        tests = [
            ("test_login", "test('login', () => {});"),
            ("test_checkout", "test('checkout', () => {});"),
            ("test_search", "test('search', () => {});"),
        ]

        for test_name, script in tests:
            storage.save_test_artifact(run_id, test_name, "script", script)
            storage.save_test_artifact(run_id, test_name, "recording", b"fake-gif")
            storage.save_test_details(run_id, test_name, {
                "name": test_name,
                "passed": True,
            })

        # Verify everything is stored correctly
        info = storage.get_run_info(run_id)
        assert info["tests_count"] == 3

        loaded_metadata = storage.load_metadata(run_id)
        assert loaded_metadata["status"] == "completed"

        loaded_changeset = storage.load_changeset(run_id)
        assert len(loaded_changeset["changes"]) == 2

        for test_name, _ in tests:
            artifacts = storage.list_test_artifacts(run_id, test_name)
            assert len(artifacts) == 3  # script, recording, details

    def test_multiple_runs_cleanup(self, storage):
        """Test creating multiple runs and cleaning up old ones."""
        # Create 10 runs
        for i in range(10):
            run_id = f"run_{i:03d}"
            storage.save_metadata(run_id, {"index": i})

        assert len(storage.list_runs()) == 10

        # Cleanup, keeping only 3
        deleted = storage.cleanup_old_runs(keep_count=3)

        assert len(deleted) == 7
        assert len(storage.list_runs()) == 3

        # Latest symlink should still work
        latest = storage.get_latest_path()
        assert latest is not None
        assert latest.exists()

    def test_directory_structure(self, storage, sample_changeset):
        """Test that the directory structure matches the specification."""
        run_id = "run_structure_test"

        storage.save_metadata(run_id, {"status": "completed"})
        storage.save_changeset(run_id, sample_changeset)
        storage.save_test_artifact(run_id, "test_example", "script", "content")
        storage.save_test_details(run_id, "test_example", {"name": "test"})

        # Verify structure
        base = storage.output_directory

        # Check runs directory
        assert (base / "runs").is_dir()

        # Check run directory
        run_dir = base / "runs" / run_id
        assert run_dir.is_dir()

        # Check metadata and changeset
        assert (run_dir / "metadata.json").is_file()
        assert (run_dir / "changeset.json").is_file()

        # Check tests directory
        assert (run_dir / "tests").is_dir()

        # Check test directory
        test_dir = run_dir / "tests" / "test_example"
        assert test_dir.is_dir()
        assert (test_dir / "test_example.spec.ts").is_file()
        assert (test_dir / "details.json").is_file()

        # Check latest symlink
        assert (base / "latest").is_symlink()

"""
Artifact storage for E2E test generation.

This module provides test artifact management (test scripts, recordings, etc.).
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class RunNotFoundError(StorageError):
    """Raised when a requested run does not exist."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class ArtifactNotFoundError(StorageError):
    """Raised when a requested artifact does not exist."""

    def __init__(self, run_id: str, test_name: str, artifact_type: str):
        self.run_id = run_id
        self.test_name = test_name
        self.artifact_type = artifact_type
        super().__init__(
            f"Artifact not found: {artifact_type} for test '{test_name}' in run '{run_id}'"
        )


@dataclass
class ArtifactStorage:
    """
    Manages E2E test artifact storage with a structured directory layout.

    This class provides methods to create, read, and manage test artifacts
    including test scripts, recordings, and metadata files.

    Attributes:
        output_directory: Root directory for all storage operations.
        create_directories: Whether to create directories on initialization.
    """

    output_directory: Path
    create_directories: bool = True

    # File naming conventions
    METADATA_FILE: str = "metadata.json"
    CHANGESET_FILE: str = "changeset.json"
    DETAILS_FILE: str = "details.json"
    RUNS_DIR: str = "runs"
    TESTS_DIR: str = "tests"
    LATEST_LINK: str = "latest"

    # Default artifact file extensions
    ARTIFACT_EXTENSIONS: Dict[str, str] = field(default_factory=lambda: {
        "script": ".spec.ts",
        "recording": ".gif",
        "screenshot": ".png",
        "video": ".webm",
        "trace": ".json",
        "log": ".log",
    })

    def __post_init__(self) -> None:
        """Initialize storage and create directories if needed."""
        # Ensure output_directory is a Path
        if not isinstance(self.output_directory, Path):
            self.output_directory = Path(self.output_directory)

        # Make path absolute
        if not self.output_directory.is_absolute():
            self.output_directory = self.output_directory.resolve()

        # Create base directories if requested
        if self.create_directories:
            self._ensure_base_directories()

    def _ensure_base_directories(self) -> None:
        """Create the base directory structure."""
        runs_dir = self.output_directory / self.RUNS_DIR
        runs_dir.mkdir(parents=True, exist_ok=True)

    def _get_runs_directory(self) -> Path:
        """Get the runs directory path."""
        return self.output_directory / self.RUNS_DIR

    def _get_run_path(self, run_id: str) -> Path:
        """Get the path to a specific run directory."""
        return self._get_runs_directory() / run_id

    def _get_tests_directory(self, run_id: str) -> Path:
        """Get the tests directory path for a run."""
        return self._get_run_path(run_id) / self.TESTS_DIR

    def _get_test_directory(self, run_id: str, test_name: str) -> Path:
        """Get the directory path for a specific test."""
        return self._get_tests_directory(run_id) / test_name

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize a name for use as a directory or file name.

        Replaces problematic characters with underscores.
        """
        # Replace common problematic characters
        sanitized = name
        for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']:
            sanitized = sanitized.replace(char, '_')
        return sanitized

    def _get_artifact_filename(
        self, test_name: str, artifact_type: str, extension: Optional[str] = None
    ) -> str:
        """
        Get the filename for an artifact.

        Args:
            test_name: Name of the test
            artifact_type: Type of artifact (script, recording, etc.)
            extension: Optional custom extension

        Returns:
            Filename for the artifact
        """
        sanitized = self._sanitize_name(test_name)

        if extension is None:
            extension = self.ARTIFACT_EXTENSIONS.get(artifact_type, "")

        if artifact_type == "script":
            return f"{sanitized}{extension}"
        else:
            return f"{artifact_type}{extension}"

    # ========================================================================
    # Run Management
    # ========================================================================

    def get_run_directory(self, run_id: str, create: bool = True) -> Path:
        """
        Get or create the directory for a specific run.

        Args:
            run_id: Unique identifier for the run
            create: Whether to create the directory if it doesn't exist

        Returns:
            Path to the run directory

        Raises:
            RunNotFoundError: If create=False and run doesn't exist
        """
        run_path = self._get_run_path(run_id)

        if create:
            run_path.mkdir(parents=True, exist_ok=True)
            tests_dir = run_path / self.TESTS_DIR
            tests_dir.mkdir(exist_ok=True)
        elif not run_path.exists():
            raise RunNotFoundError(run_id)

        return run_path

    def run_exists(self, run_id: str) -> bool:
        """Check if a run directory exists."""
        return self._get_run_path(run_id).exists()

    def list_runs(self) -> List[str]:
        """
        List all run IDs in storage.

        Returns:
            List of run IDs sorted by modification time (newest first)
        """
        runs_dir = self._get_runs_directory()
        if not runs_dir.exists():
            return []

        # Get all directories in runs/
        runs = []
        for entry in runs_dir.iterdir():
            if entry.is_dir() and entry.name != self.LATEST_LINK:
                runs.append(entry)

        # Sort by modification time, newest first
        runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [r.name for r in runs]

    def get_latest_run(self) -> Optional[str]:
        """
        Get the most recent run ID.

        Returns:
            The most recent run ID, or None if no runs exist
        """
        runs = self.list_runs()
        return runs[0] if runs else None

    def delete_run(self, run_id: str) -> bool:
        """
        Delete a run and all its artifacts.

        Args:
            run_id: ID of the run to delete

        Returns:
            True if deleted, False if run didn't exist
        """
        run_path = self._get_run_path(run_id)
        if not run_path.exists():
            return False

        shutil.rmtree(run_path)

        # Update latest symlink if needed
        latest_path = self.output_directory / self.LATEST_LINK
        if latest_path.is_symlink():
            target = latest_path.resolve()
            if target == run_path or not target.exists():
                latest_path.unlink()
                # Point to new latest if available
                new_latest = self.get_latest_run()
                if new_latest:
                    self._update_latest_symlink(new_latest)

        return True

    def cleanup_old_runs(self, keep_count: int) -> List[str]:
        """
        Remove old runs, keeping only the most recent ones.

        Args:
            keep_count: Number of most recent runs to keep

        Returns:
            List of deleted run IDs
        """
        if keep_count < 0:
            raise ValueError("keep_count must be non-negative")

        runs = self.list_runs()
        deleted = []

        # Keep the first keep_count runs (already sorted newest first)
        for run_id in runs[keep_count:]:
            if self.delete_run(run_id):
                deleted.append(run_id)

        return deleted

    # ========================================================================
    # Test Artifact Management
    # ========================================================================

    def save_test_artifact(
        self,
        run_id: str,
        test_name: str,
        artifact_type: str,
        content: Union[bytes, str],
        extension: Optional[str] = None,
    ) -> Path:
        """
        Save a test artifact to storage.

        Args:
            run_id: ID of the run
            test_name: Name of the test
            artifact_type: Type of artifact (script, recording, screenshot, etc.)
            content: Artifact content (bytes or string)
            extension: Optional custom file extension

        Returns:
            Path to the saved artifact
        """
        sanitized_test_name = self._sanitize_name(test_name)
        test_dir = self._get_test_directory(run_id, sanitized_test_name)
        test_dir.mkdir(parents=True, exist_ok=True)

        filename = self._get_artifact_filename(test_name, artifact_type, extension)
        artifact_path = test_dir / filename

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"

        with open(artifact_path, mode, encoding=encoding) as f:
            f.write(content)

        return artifact_path

    def load_test_artifact(
        self,
        run_id: str,
        test_name: str,
        artifact_type: str,
        as_bytes: bool = False,
        extension: Optional[str] = None,
    ) -> Union[bytes, str]:
        """
        Load a test artifact from storage.

        Args:
            run_id: ID of the run
            test_name: Name of the test
            artifact_type: Type of artifact to load
            as_bytes: Whether to return content as bytes
            extension: Optional custom file extension

        Returns:
            Artifact content

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist
        """
        sanitized_test_name = self._sanitize_name(test_name)
        test_dir = self._get_test_directory(run_id, sanitized_test_name)
        filename = self._get_artifact_filename(test_name, artifact_type, extension)
        artifact_path = test_dir / filename

        if not artifact_path.exists():
            raise ArtifactNotFoundError(run_id, test_name, artifact_type)

        mode = "rb" if as_bytes else "r"
        encoding = None if as_bytes else "utf-8"

        with open(artifact_path, mode, encoding=encoding) as f:
            return f.read()

    def save_test_details(
        self, run_id: str, test_name: str, details: Dict[str, Any]
    ) -> Path:
        """
        Save test details to a JSON file.

        Args:
            run_id: ID of the run
            test_name: Name of the test
            details: Test details dictionary

        Returns:
            Path to the saved details file
        """
        sanitized_test_name = self._sanitize_name(test_name)
        test_dir = self._get_test_directory(run_id, sanitized_test_name)
        test_dir.mkdir(parents=True, exist_ok=True)

        details_path = test_dir / self.DETAILS_FILE

        with open(details_path, "w", encoding="utf-8") as f:
            json.dump(details, f, indent=2, default=str)

        return details_path

    def load_test_details(self, run_id: str, test_name: str) -> Dict[str, Any]:
        """
        Load test details from JSON file.

        Args:
            run_id: ID of the run
            test_name: Name of the test

        Returns:
            Test details dictionary

        Raises:
            FileNotFoundError: If details file doesn't exist
        """
        sanitized_test_name = self._sanitize_name(test_name)
        test_dir = self._get_test_directory(run_id, sanitized_test_name)
        details_path = test_dir / self.DETAILS_FILE

        if not details_path.exists():
            raise FileNotFoundError(
                f"Details file not found for test '{test_name}' in run '{run_id}'"
            )

        with open(details_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_tests(self, run_id: str) -> List[str]:
        """
        List all test names for a run.

        Args:
            run_id: ID of the run

        Returns:
            List of test names
        """
        tests_dir = self._get_tests_directory(run_id)
        if not tests_dir.exists():
            return []

        return [
            entry.name
            for entry in tests_dir.iterdir()
            if entry.is_dir()
        ]

    def list_test_artifacts(self, run_id: str, test_name: str) -> List[Path]:
        """
        List all artifacts for a specific test.

        Args:
            run_id: ID of the run
            test_name: Name of the test

        Returns:
            List of artifact file paths
        """
        sanitized_test_name = self._sanitize_name(test_name)
        test_dir = self._get_test_directory(run_id, sanitized_test_name)

        if not test_dir.exists():
            return []

        return [
            entry
            for entry in test_dir.iterdir()
            if entry.is_file()
        ]

    # ========================================================================
    # Latest Symlink Management
    # ========================================================================

    def _update_latest_symlink(self, run_id: str) -> None:
        """
        Update the 'latest' symlink to point to the specified run.

        Args:
            run_id: ID of the run to point to
        """
        latest_path = self.output_directory / self.LATEST_LINK
        run_path = self._get_run_path(run_id)

        # Remove existing symlink if present
        if latest_path.is_symlink() or latest_path.exists():
            latest_path.unlink()

        # Create relative symlink
        # The symlink target should be relative: runs/{run_id}
        relative_target = Path(self.RUNS_DIR) / run_id
        latest_path.symlink_to(relative_target)

    def get_latest_path(self) -> Optional[Path]:
        """
        Get the path that the 'latest' symlink points to.

        Returns:
            Path to the latest run, or None if no latest exists
        """
        latest_path = self.output_directory / self.LATEST_LINK

        if not latest_path.is_symlink():
            return None

        # Resolve relative to output_directory
        target = latest_path.resolve()
        if target.exists():
            return target

        return None

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def get_total_size(self, run_id: str) -> int:
        """
        Get the total size of all artifacts in a run.

        Args:
            run_id: ID of the run

        Returns:
            Total size in bytes
        """
        run_path = self._get_run_path(run_id)
        if not run_path.exists():
            return 0

        total_size = 0
        for entry in run_path.rglob("*"):
            if entry.is_file():
                total_size += entry.stat().st_size

        return total_size

    def get_run_info(self, run_id: str) -> Dict[str, Any]:
        """
        Get summary information about a run.

        Args:
            run_id: ID of the run

        Returns:
            Dictionary with run information
        """
        from .metadata_manager import MetadataManager

        run_path = self._get_run_path(run_id)

        if not run_path.exists():
            raise RunNotFoundError(run_id)

        tests = self.list_tests(run_id)
        total_size = self.get_total_size(run_id)

        # Get metadata if available
        metadata_mgr = MetadataManager(self.output_directory)
        try:
            metadata = metadata_mgr.load_metadata(run_id)
        except FileNotFoundError:
            metadata = {}

        return {
            "run_id": run_id,
            "path": str(run_path),
            "tests_count": len(tests),
            "tests": tests,
            "total_size_bytes": total_size,
            "metadata": metadata,
            "created_at": datetime.fromtimestamp(
                run_path.stat().st_ctime, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "modified_at": datetime.fromtimestamp(
                run_path.stat().st_mtime, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
        }

    # ========================================================================
    # Backward Compatibility Delegation Methods
    # ========================================================================
    # After Phase 2 reorganization, metadata and changeset operations were
    # moved to separate manager classes. These delegation methods maintain
    # backward compatibility for code expecting the old monolithic interface.

    def save_metadata(self, run_id: str, metadata: Dict[str, Any]) -> Path:
        """
        Save run metadata (delegates to MetadataManager).

        Backward compatibility method. New code should use MetadataManager directly.
        """
        from .metadata_manager import MetadataManager
        manager = MetadataManager(self.output_directory)
        return manager.save_metadata(run_id, metadata)

    def load_metadata(self, run_id: str) -> Dict[str, Any]:
        """
        Load run metadata (delegates to MetadataManager).

        Backward compatibility method. New code should use MetadataManager directly.
        """
        from .metadata_manager import MetadataManager
        manager = MetadataManager(self.output_directory)
        return manager.load_metadata(run_id)

    def update_metadata(self, run_id: str, updates: Dict[str, Any]) -> Path:
        """
        Update run metadata (delegates to MetadataManager).

        Backward compatibility method. New code should use MetadataManager directly.
        """
        from .metadata_manager import MetadataManager
        manager = MetadataManager(self.output_directory)
        return manager.update_metadata(run_id, updates)

    def save_changeset(self, run_id: str, changeset: Dict[str, Any]) -> Path:
        """
        Save changeset data (delegates to ChangesetManager).

        Backward compatibility method. New code should use ChangesetManager directly.
        """
        from .changeset_manager import ChangesetManager
        manager = ChangesetManager(self.output_directory)
        return manager.save_changeset(run_id, changeset)

    def load_changeset(self, run_id: str) -> Dict[str, Any]:
        """
        Load changeset data (delegates to ChangesetManager).

        Backward compatibility method. New code should use ChangesetManager directly.
        """
        from .changeset_manager import ChangesetManager
        manager = ChangesetManager(self.output_directory)
        return manager.load_changeset(run_id)


__all__ = [
    "ArtifactStorage",
    "StorageError",
    "RunNotFoundError",
    "ArtifactNotFoundError",
]

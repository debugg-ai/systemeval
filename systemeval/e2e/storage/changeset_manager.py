"""
Changeset management for E2E test runs.

This module handles changeset storage and retrieval.
"""

import json
from pathlib import Path
from typing import Any, Dict

from ..core.types import ChangeSet
from .artifact_storage import RunNotFoundError


class ChangesetManager:
    """
    Manages changesets for E2E test runs.

    Provides methods to save and load changeset information.
    """

    def __init__(self, output_directory: Path):
        """
        Initialize changeset manager.

        Args:
            output_directory: Root directory for storage operations
        """
        self.output_directory = Path(output_directory)
        self.CHANGESET_FILE = "changeset.json"
        self.RUNS_DIR = "runs"

    def _get_run_path(self, run_id: str) -> Path:
        """Get the path to a specific run directory."""
        return self.output_directory / self.RUNS_DIR / run_id

    def save_changeset(self, run_id: str, changeset: ChangeSet) -> Path:
        """
        Save changeset information to JSON file.

        Args:
            run_id: ID of the run
            changeset: ChangeSet object to save

        Returns:
            Path to the saved changeset file
        """
        run_dir = self._get_run_path(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        changeset_path = run_dir / self.CHANGESET_FILE

        with open(changeset_path, "w", encoding="utf-8") as f:
            json.dump(changeset.to_dict(), f, indent=2, default=str)

        return changeset_path

    def load_changeset(self, run_id: str) -> Dict[str, Any]:
        """
        Load changeset information from JSON file.

        Args:
            run_id: ID of the run

        Returns:
            Changeset dictionary

        Raises:
            RunNotFoundError: If run doesn't exist
            FileNotFoundError: If changeset file doesn't exist
        """
        run_dir = self._get_run_path(run_id)
        if not run_dir.exists():
            raise RunNotFoundError(run_id)

        changeset_path = run_dir / self.CHANGESET_FILE

        if not changeset_path.exists():
            raise FileNotFoundError(f"Changeset file not found for run: {run_id}")

        with open(changeset_path, "r", encoding="utf-8") as f:
            return json.load(f)


__all__ = ["ChangesetManager"]

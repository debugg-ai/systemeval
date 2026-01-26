"""
Metadata management for E2E test runs.

This module handles run metadata storage and retrieval.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .artifact_storage import RunNotFoundError


class MetadataManager:
    """
    Manages metadata for E2E test runs.

    Provides methods to save, load, and update run metadata.
    """

    def __init__(self, output_directory: Path):
        """
        Initialize metadata manager.

        Args:
            output_directory: Root directory for storage operations
        """
        self.output_directory = Path(output_directory)
        self.METADATA_FILE = "metadata.json"
        self.RUNS_DIR = "runs"
        self.LATEST_LINK = "latest"

    def _get_run_path(self, run_id: str) -> Path:
        """Get the path to a specific run directory."""
        return self.output_directory / self.RUNS_DIR / run_id

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
        relative_target = Path(self.RUNS_DIR) / run_id
        latest_path.symlink_to(relative_target)

    def save_metadata(self, run_id: str, metadata: Dict[str, Any]) -> Path:
        """
        Save run metadata to JSON file.

        Args:
            run_id: ID of the run
            metadata: Metadata dictionary to save

        Returns:
            Path to the saved metadata file
        """
        run_dir = self._get_run_path(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = run_dir / self.METADATA_FILE

        # Add timestamp if not present
        if "saved_at" not in metadata:
            metadata["saved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

        # Update latest symlink
        self._update_latest_symlink(run_id)

        return metadata_path

    def load_metadata(self, run_id: str) -> Dict[str, Any]:
        """
        Load run metadata from JSON file.

        Args:
            run_id: ID of the run

        Returns:
            Metadata dictionary

        Raises:
            RunNotFoundError: If run doesn't exist
            FileNotFoundError: If metadata file doesn't exist
        """
        run_dir = self._get_run_path(run_id)
        if not run_dir.exists():
            raise RunNotFoundError(run_id)

        metadata_path = run_dir / self.METADATA_FILE

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found for run: {run_id}")

        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_metadata(self, run_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update existing metadata with new values.

        Args:
            run_id: ID of the run
            updates: Dictionary of values to update

        Returns:
            Updated metadata dictionary
        """
        try:
            metadata = self.load_metadata(run_id)
        except FileNotFoundError:
            metadata = {}

        metadata.update(updates)
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.save_metadata(run_id, metadata)
        return metadata


__all__ = ["MetadataManager"]

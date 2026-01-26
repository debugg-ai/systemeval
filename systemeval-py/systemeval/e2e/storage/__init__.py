"""
Storage management for E2E test artifacts.

This module provides a structured storage layout for E2E test artifacts,
including test scripts, recordings, and metadata.

Storage Layout:
    output_directory/
    |-- runs/
    |   |-- {run_id}/
    |       |-- metadata.json        # Run info, status, timestamps
    |       |-- changeset.json       # Git changes that triggered generation
    |       |-- tests/
    |           |-- {test_name}/
    |               |-- {test_name}.spec.ts   # Test script
    |               |-- recording.gif          # Visual recording
    |               |-- details.json           # Test details
    |-- latest -> runs/{most_recent_run_id}   # Symlink to latest

Usage:
    from systemeval.e2e.storage import ArtifactStorage
    from pathlib import Path

    storage = ArtifactStorage(Path("/output"))
    run_dir = storage.get_run_directory("run_123")
    storage.save_metadata("run_123", {"status": "completed"})
"""

from .artifact_storage import (
    ArtifactStorage,
    StorageError,
    RunNotFoundError,
    ArtifactNotFoundError,
)
from .metadata_manager import MetadataManager
from .changeset_manager import ChangesetManager

__all__ = [
    "ArtifactStorage",
    "StorageError",
    "RunNotFoundError",
    "ArtifactNotFoundError",
    "MetadataManager",
    "ChangesetManager",
]

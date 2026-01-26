"""Base adapter for JavaScript test frameworks (Jest, Vitest, etc.)."""

import shutil
from pathlib import Path
from typing import List, Optional

from systemeval.adapters.base import BaseAdapter


class BaseJavaScriptAdapter(BaseAdapter):
    """
    Base class for JavaScript test framework adapters.

    Provides shared functionality for npm/npx-based test frameworks:
    - npx executable discovery and caching
    - Common command building patterns
    - Configuration file detection

    Subclasses should implement framework-specific logic:
    - _build_base_command(): Framework-specific command construction
    - discover(): Test discovery using framework APIs
    - execute(): Test execution with result parsing
    - _parse_results(): Parse framework-specific output
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize JavaScript adapter."""
        super().__init__(*args, **kwargs)
        self._npx_path: Optional[str] = None

    def _get_npx_path(self) -> str:
        """Get path to npx executable.

        Returns:
            Path to npx executable

        Raises:
            RuntimeError: If npx not found in PATH
        """
        if self._npx_path is None:
            self._npx_path = shutil.which("npx")
            if not self._npx_path:
                raise RuntimeError(
                    "npx not found in PATH. Install Node.js from https://nodejs.org/"
                )
        return self._npx_path

    def _build_base_command(self) -> List[str]:
        """Build base command for the test framework.

        This should be overridden by subclasses to provide framework-specific
        commands (e.g., ['npx', 'jest'] or ['npx', 'vitest', 'run']).

        Returns:
            List of command arguments
        """
        raise NotImplementedError("Subclasses must implement _build_base_command")

"""Pytest adapter implementation for test discovery and execution."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pytest
    from _pytest.config import Config
    from _pytest.main import Session
    from _pytest.nodes import Item
    from _pytest.python import Function

    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False

from .base import BaseAdapter, TestFailure, TestItem, TestResult
from systemeval.utils.django import detect_django_settings
from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


class PytestCollectPlugin:
    """Plugin to collect test items during pytest collection phase."""

    def __init__(self) -> None:
        self.items: List[Item] = []

    def pytest_collection_finish(self, session: Session) -> None:
        """Called after collection has been performed."""
        self.items = session.items


class PytestResultPlugin:
    """Plugin to capture test results during pytest execution."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.skipped = 0
        self.failures: List[TestFailure] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def pytest_sessionstart(self, session: Session) -> None:
        """Called at the start of the test session."""
        import time

        self.start_time = time.time()

    def pytest_sessionfinish(self, session: Session) -> None:
        """Called at the end of the test session."""
        import time

        self.end_time = time.time()

    def pytest_runtest_logreport(self, report: Any) -> None:
        """Called for each test run phase (setup, call, teardown)."""
        # Only process the 'call' phase
        if report.when != "call":
            return

        if report.passed:
            self.passed += 1
        elif report.failed:
            self.failed += 1
            self.failures.append(
                TestFailure(
                    test_id=report.nodeid,
                    test_name=report.nodeid.split("::")[-1],
                    message=str(report.longrepr) if hasattr(report, "longrepr") else "",
                    traceback=str(report.longrepr) if hasattr(report, "longrepr") else None,
                    duration=report.duration if hasattr(report, "duration") else 0.0,
                )
            )
        elif report.skipped:
            self.skipped += 1

    def pytest_internalerror(self, excrepr: Any) -> None:
        """Called for internal errors."""
        self.errors += 1

    def get_result(self, exit_code: int) -> TestResult:
        """Build TestResult from collected data.

        Args:
            exit_code: Pytest exit code

        Returns:
            TestResult object
        """
        duration = 0.0
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time

        return TestResult(
            passed=self.passed,
            failed=self.failed,
            errors=self.errors,
            skipped=self.skipped,
            duration=duration,
            failures=self.failures,
            exit_code=exit_code,
        )


class PytestAdapter(BaseAdapter):
    """Pytest framework adapter."""

    def __init__(self, project_root: str) -> None:
        """Initialize pytest adapter.

        Args:
            project_root: Absolute path to the project root directory
        """
        if not PYTEST_AVAILABLE:
            raise ImportError(
                "pytest is not installed. Install with: pip install systemeval[pytest]"
            )
        super().__init__(project_root)
        self._detect_django()

    def _detect_django(self) -> None:
        """Detect if this is a Django project and set DJANGO_SETTINGS_MODULE."""
        detect_django_settings(self.project_root, require_manage_py=True)

    def validate_environment(self) -> bool:
        """Validate that pytest is properly configured.

        Returns:
            True if environment is valid, False otherwise
        """
        if not PYTEST_AVAILABLE:
            return False

        # Check if pytest.ini or pyproject.toml exists
        pytest_ini = Path(self.project_root) / "pytest.ini"
        pyproject_toml = Path(self.project_root) / "pyproject.toml"
        setup_cfg = Path(self.project_root) / "setup.cfg"

        return any([pytest_ini.exists(), pyproject_toml.exists(), setup_cfg.exists()])

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover tests matching criteria.

        Args:
            category: Test marker to filter by (e.g., 'unit', 'integration')
            app: Application/module path to filter by
            file: Specific test file path to filter by

        Returns:
            List of discovered test items
        """
        args = ["--collect-only", "-q"]

        # Build pytest arguments based on filters
        if category:
            args.extend(["-m", category])

        if file:
            test_path = Path(self.project_root) / file
            if test_path.exists():
                args.append(str(test_path))
        elif app:
            app_path = Path(self.project_root) / app
            if app_path.exists():
                args.append(str(app_path))
        else:
            # Default to project root
            args.append(self.project_root)

        # Create collection plugin
        collect_plugin = PytestCollectPlugin()

        # Run pytest collection
        original_dir = os.getcwd()
        try:
            os.chdir(self.project_root)
            pytest.main(args, plugins=[collect_plugin])
        finally:
            os.chdir(original_dir)

        # Convert collected items to TestItem objects
        test_items = []
        for item in collect_plugin.items:
            if isinstance(item, Function):
                markers = [marker.name for marker in item.iter_markers()]
                test_items.append(
                    TestItem(
                        id=item.nodeid,
                        name=item.name,
                        path=str(Path(item.fspath).relative_to(self.project_root)),
                        markers=markers,
                        metadata={
                            "module": item.module.__name__ if hasattr(item, "module") else None,
                            "class": item.cls.__name__ if hasattr(item, "cls") and item.cls else None,
                        },
                    )
                )

        return test_items

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> TestResult:
        """Execute tests and return results.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Enable parallel test execution (requires pytest-xdist)
            coverage: Enable coverage reporting (requires pytest-cov)
            failfast: Stop on first failure
            verbose: Verbose output
            timeout: Timeout in seconds for entire test run

        Returns:
            Test execution results
        """
        args = []

        # Verbosity
        if verbose:
            args.append("-vv")
        else:
            args.append("-v")

        # Fail fast
        if failfast:
            args.append("-x")

        # Parallel execution
        if parallel:
            try:
                import xdist  # noqa: F401

                args.extend(["-n", "auto"])
            except ImportError:
                logger.warning("pytest-xdist not installed, running serially")

        # Coverage
        if coverage:
            try:
                import pytest_cov  # noqa: F401

                args.extend(["--cov", self.project_root, "--cov-report", "term-missing"])
            except ImportError:
                logger.warning("pytest-cov not installed, skipping coverage")

        # Timeout
        if timeout:
            args.append(f"--timeout={timeout}")

        # Use custom plugin to capture results
        result_plugin = PytestResultPlugin()

        # Specific tests or full suite
        if tests:
            for test in tests:
                args.append(f"{test.path}::{test.name}")
        else:
            args.append(self.project_root)

        # Execute pytest
        original_dir = os.getcwd()
        exit_code = 0
        try:
            os.chdir(self.project_root)
            exit_code = pytest.main(args, plugins=[result_plugin])
        finally:
            os.chdir(original_dir)

        # Build result from collected data
        return result_plugin.get_result(exit_code)

    def get_available_markers(self) -> List[str]:
        """Return available test markers/categories.

        Returns:
            List of marker names
        """
        args = ["--markers"]
        original_dir = os.getcwd()

        # Capture markers from pytest
        markers = []
        try:
            os.chdir(self.project_root)

            # Run pytest --markers and capture output
            import io
            import contextlib

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pytest.main(args)

            output_text = output.getvalue()

            # Parse markers from output
            # Format is typically: @pytest.mark.markername: description
            for line in output_text.split("\n"):
                if line.strip().startswith("@pytest.mark."):
                    marker_name = line.split("@pytest.mark.")[1].split(":")[0].strip()
                    if marker_name and marker_name not in ["parametrize", "skip", "skipif"]:
                        markers.append(marker_name)

        finally:
            os.chdir(original_dir)

        return sorted(set(markers))

"""
Surfer adapter for DebuggAI cloud E2E testing.

Triggers E2E tests via the DebuggAI API and polls for completion.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from systemeval.adapters.base import AdapterConfig, BaseAdapter, TestItem, TestResult, TestFailure

logger = logging.getLogger(__name__)


class SurferAdapter(BaseAdapter):
    """
    Adapter for running DebuggAI Surfer E2E tests in the cloud.

    Integrates with the DebuggAI platform to trigger AI-generated E2E tests
    against a target URL (typically an ngrok tunnel to local development).

    Supports initialization with either AdapterConfig or legacy parameters.

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(
            project_root="/path/to/project",
            timeout=600,
            extra={
                "project_slug": "my-project",
                "api_key": "your-api-key",
                "api_base_url": "https://api.debugg.ai",
                "poll_interval": 5,
            }
        )
        adapter = SurferAdapter(config)

        # Using legacy parameters (backward compatible)
        adapter = SurferAdapter(
            project_root="/path/to/project",
            project_slug="my-project",
            api_key="your-api-key",
        )
    """

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
        project_slug: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base_url: str = "https://api.debugg.ai",
        poll_interval: int = 5,
        timeout: int = 600,
    ) -> None:
        """Initialize Surfer adapter.

        Args:
            config_or_project_root: Either an AdapterConfig object or project root path.
            project_slug: DebuggAI project slug (used only if project_root is passed).
            api_key: DebuggAI API key.
            api_base_url: DebuggAI API base URL.
            poll_interval: Seconds between status checks.
            timeout: Default timeout in seconds.
        """
        super().__init__(config_or_project_root)

        # Extract Surfer-specific settings from config or use legacy params
        if isinstance(config_or_project_root, AdapterConfig):
            self.project_slug = self.config.get("project_slug", "")
            self.api_key = self.config.get("api_key") or os.environ.get("DEBUGGAI_API_KEY")
            self.api_base_url = self.config.get("api_base_url", "https://api.debugg.ai").rstrip("/")
            self.poll_interval = self.config.get("poll_interval", 5)
            self.surfer_timeout = self.config.timeout or self.config.get("timeout", 600)
        else:
            # Legacy initialization
            if project_slug is None:
                raise ValueError("project_slug is required when not using AdapterConfig")
            self.project_slug = project_slug
            self.api_key = api_key or os.environ.get("DEBUGGAI_API_KEY")
            self.api_base_url = api_base_url.rstrip("/")
            self.poll_interval = poll_interval
            self.surfer_timeout = timeout

        if not self.api_key:
            logger.warning("No DEBUGGAI_API_KEY found. Set it via env var or config.")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an authenticated API request."""
        url = f"{self.api_base_url}{endpoint}"
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        body = json.dumps(data).encode() if data else None
        request = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error(f"API error {e.code}: {error_body}")
            raise
        except URLError as e:
            logger.error(f"Network error: {e}")
            raise

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover available E2E tests from DebuggAI."""
        if not self.api_key:
            logger.error("Cannot discover tests without API key")
            return []

        try:
            endpoint = f"/api/v1/projects/{self.project_slug}/e2e-tests/"
            data = self._make_request("GET", endpoint)

            tests = []
            for test in data.get("results", data if isinstance(data, list) else []):
                tests.append(TestItem(
                    id=str(test.get("id", test.get("uid", ""))),
                    name=test.get("name", test.get("title", "")),
                    path=test.get("url", ""),
                    markers=["browser", "e2e", "surfer"],
                    metadata={
                        "status": test.get("status"),
                        "created": test.get("created_at", test.get("timestamp")),
                        "description": test.get("description", ""),
                    },
                ))

            return tests

        except (HTTPError, URLError) as e:
            logger.error(f"Failed to discover tests: {e}")
            return []

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
        target_url: Optional[str] = None,
    ) -> TestResult:
        """
        Execute E2E tests via DebuggAI Surfer.

        Args:
            tests: Optional list of specific tests to run
            parallel: Ignored (cloud handles parallelism)
            coverage: Ignored (not applicable to E2E)
            failfast: Stop on first failure
            verbose: Enable verbose output
            timeout: Override default timeout
            target_url: URL to test against (e.g., ngrok tunnel URL)
        """
        if not self.api_key:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
                failures=[TestFailure(
                    test_id="auth",
                    test_name="Authentication",
                    message="DEBUGGAI_API_KEY not configured",
                )],
            )

        start_time = time.time()
        exec_timeout = timeout or self.surfer_timeout

        try:
            # Trigger E2E test run
            run_id = self._trigger_test_run(target_url, tests)
            if not run_id:
                return TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=time.time() - start_time,
                    exit_code=2,
                    failures=[TestFailure(
                        test_id="trigger",
                        test_name="Test Trigger",
                        message="Failed to trigger E2E test run",
                    )],
                )

            logger.info(f"Triggered E2E test run: {run_id}")

            # Poll for completion
            result = self._poll_for_completion(run_id, exec_timeout, failfast)
            result.duration = time.time() - start_time
            return result

        except Exception as e:
            logger.error(f"E2E test execution failed: {e}")
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=time.time() - start_time,
                exit_code=2,
                failures=[TestFailure(
                    test_id="execution",
                    test_name="Test Execution",
                    message=str(e),
                )],
            )

    def _trigger_test_run(
        self,
        target_url: Optional[str],
        tests: Optional[List[TestItem]] = None,
    ) -> Optional[str]:
        """Trigger an E2E test run and return the run ID."""
        try:
            endpoint = "/api/v1/e2e-test-runs/"
            payload: Dict[str, Any] = {
                "project_slug": self.project_slug,
            }

            if target_url:
                payload["target_url"] = target_url

            if tests:
                payload["test_ids"] = [t.id for t in tests]

            data = self._make_request("POST", endpoint, payload)
            return str(data.get("id", data.get("uid", data.get("run_id", ""))))

        except (HTTPError, URLError) as e:
            logger.error(f"Failed to trigger test run: {e}")
            return None

    def _poll_for_completion(
        self,
        run_id: str,
        timeout: int,
        failfast: bool = False,
    ) -> TestResult:
        """Poll for test run completion and return results."""
        endpoint = f"/api/v1/e2e-test-runs/{run_id}/"
        start_time = time.time()
        last_status = ""

        while (time.time() - start_time) < timeout:
            try:
                data = self._make_request("GET", endpoint)
                status = data.get("status", "")

                if status != last_status:
                    logger.info(f"Test run status: {status}")
                    last_status = status

                # Check if complete
                if status in ("completed", "passed", "success"):
                    return self._parse_run_results(data)
                elif status in ("failed", "error"):
                    return self._parse_run_results(data)
                elif status == "cancelled":
                    return TestResult(
                        passed=0,
                        failed=0,
                        errors=0,
                        skipped=1,
                        duration=time.time() - start_time,
                        exit_code=0,
                    )

                # Check for failfast condition
                if failfast and status == "running":
                    failures = data.get("failures", [])
                    if failures:
                        return self._parse_run_results(data)

                time.sleep(self.poll_interval)

            except (HTTPError, URLError) as e:
                logger.warning(f"Error polling status: {e}")
                time.sleep(self.poll_interval)

        # Timeout
        return TestResult(
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            duration=timeout,
            exit_code=2,
            failures=[TestFailure(
                test_id=run_id,
                test_name="E2E Test Run",
                message=f"Test run timed out after {timeout}s",
            )],
        )

    def _parse_run_results(self, data: Dict[str, Any]) -> TestResult:
        """Parse E2E run results into TestResult."""
        # Extract stats from various possible response formats
        stats = data.get("stats", data.get("summary", {}))
        passed = stats.get("passed", data.get("tests_passed", 0))
        failed = stats.get("failed", data.get("tests_failed", 0))
        skipped = stats.get("skipped", data.get("tests_skipped", 0))
        errors = stats.get("errors", 0)

        # If no stats, try to count from test results
        if passed == 0 and failed == 0:
            test_results = data.get("test_results", data.get("results", []))
            for tr in test_results:
                status = tr.get("status", tr.get("verdict", "")).lower()
                if status in ("passed", "pass", "success"):
                    passed += 1
                elif status in ("failed", "fail"):
                    failed += 1
                elif status in ("skipped", "skip"):
                    skipped += 1
                elif status in ("error",):
                    errors += 1

        # Extract failures
        failures: List[TestFailure] = []
        for failure in data.get("failures", data.get("test_results", [])):
            if isinstance(failure, dict):
                status = failure.get("status", failure.get("verdict", "")).lower()
                if status in ("failed", "fail", "error"):
                    failures.append(TestFailure(
                        test_id=str(failure.get("id", failure.get("test_id", ""))),
                        test_name=failure.get("name", failure.get("test_name", "")),
                        message=failure.get("message", failure.get("error_message", "")),
                        traceback=failure.get("traceback", failure.get("stack_trace")),
                        duration=failure.get("duration", 0),
                    ))

        # Determine exit code
        exit_code = 0 if (failed == 0 and errors == 0) else 1
        status = data.get("status", "")
        if status in ("error",):
            exit_code = 2

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration=data.get("duration_seconds", data.get("duration", 0)),
            exit_code=exit_code,
            failures=failures,
            parsed_from="surfer",
        )

    def get_available_markers(self) -> List[str]:
        """Return available test markers/tags."""
        return ["browser", "e2e", "surfer", "cloud"]

    def validate_environment(self) -> bool:
        """Validate that API access is configured."""
        if not self.api_key:
            logger.error("DEBUGGAI_API_KEY not configured")
            return False

        if not self.project_slug:
            logger.error("project_slug not configured")
            return False

        # Try a lightweight API call to validate credentials
        try:
            endpoint = f"/api/v1/projects/{self.project_slug}/"
            self._make_request("GET", endpoint)
            return True
        except HTTPError as e:
            if e.code == 401:
                logger.error("Invalid API key")
            elif e.code == 404:
                logger.error(f"Project not found: {self.project_slug}")
            else:
                logger.error(f"API validation failed: {e}")
            return False
        except URLError as e:
            logger.error(f"Cannot connect to API: {e}")
            return False

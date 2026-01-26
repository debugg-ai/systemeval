"""
Tests for E2E reporting module.

Tests the conversion functions that transform E2E generation results
to systemeval's standard reporting formats (TestResult, EvaluationResult).
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from systemeval.types import TestResult, Verdict
from systemeval.core.evaluation import EvaluationResult
from systemeval.e2e.types import (
    E2EResult,
    E2EConfig,
    ChangeSet,
    Change,
    ChangeType,
    GenerationResult,
    StatusResult,
    CompletionResult,
    ArtifactResult,
    GenerationStatus,
)
from systemeval.e2e.reporting import (
    generation_status_to_verdict,
    e2e_result_to_test_result,
    status_result_to_test_result,
    e2e_to_evaluation_result,
    create_e2e_evaluation_context,
    render_e2e_result,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_changeset(tmp_path: Path) -> ChangeSet:
    """Create a sample changeset for testing."""
    return ChangeSet(
        base_ref="main",
        head_ref="feature-branch",
        changes=[
            Change(
                file_path="src/api/users.py",
                change_type=ChangeType.MODIFIED,
                additions=25,
                deletions=10,
            ),
            Change(
                file_path="src/api/auth.py",
                change_type=ChangeType.ADDED,
                additions=50,
                deletions=0,
            ),
        ],
        repository_root=tmp_path,
    )


@pytest.fixture
def sample_e2e_config(tmp_path: Path) -> E2EConfig:
    """Create a sample E2E config for testing."""
    return E2EConfig(
        provider_name="mock",
        project_root=tmp_path,
        api_key="test-api-key",
        api_base_url="https://api.example.com",
        project_slug="test-project",
        test_framework="playwright",
        programming_language="typescript",
        timeout_seconds=300,
    )


@pytest.fixture
def sample_generation_result() -> GenerationResult:
    """Create a sample generation result."""
    return GenerationResult(
        run_id="mock-run-123",
        status=GenerationStatus.IN_PROGRESS,
        message="E2E test generation started",
    )


@pytest.fixture
def completed_completion() -> CompletionResult:
    """Create a completed completion result."""
    return CompletionResult(
        run_id="mock-run-123",
        status=GenerationStatus.COMPLETED,
        completed=True,
        timed_out=False,
        duration_seconds=45.5,
        final_message="Generation completed successfully",
    )


@pytest.fixture
def failed_completion() -> CompletionResult:
    """Create a failed completion result."""
    return CompletionResult(
        run_id="mock-run-123",
        status=GenerationStatus.FAILED,
        completed=True,
        timed_out=False,
        duration_seconds=12.3,
        final_message="Generation failed",
        error="API error: Invalid project configuration",
    )


@pytest.fixture
def sample_artifacts(tmp_path: Path) -> ArtifactResult:
    """Create sample artifacts result."""
    test_file = tmp_path / "test_users.spec.ts"
    test_file.write_text("test('user login', async () => {});")

    return ArtifactResult(
        run_id="mock-run-123",
        output_directory=tmp_path,
        test_files=[test_file],
        total_tests=5,
        total_size_bytes=1024,
    )


@pytest.fixture
def successful_e2e_result(
    sample_changeset: ChangeSet,
    sample_e2e_config: E2EConfig,
    sample_generation_result: GenerationResult,
    completed_completion: CompletionResult,
    sample_artifacts: ArtifactResult,
) -> E2EResult:
    """Create a successful E2E result."""
    result = E2EResult(
        changeset=sample_changeset,
        config=sample_e2e_config,
        generation=sample_generation_result,
        completion=completed_completion,
        artifacts=sample_artifacts,
        success=True,
    )
    result.finalize(success=True)
    return result


@pytest.fixture
def failed_e2e_result(
    sample_changeset: ChangeSet,
    sample_e2e_config: E2EConfig,
    sample_generation_result: GenerationResult,
    failed_completion: CompletionResult,
) -> E2EResult:
    """Create a failed E2E result."""
    result = E2EResult(
        changeset=sample_changeset,
        config=sample_e2e_config,
        generation=sample_generation_result,
        completion=failed_completion,
        artifacts=None,
        success=False,
        error="API error: Invalid project configuration",
    )
    result.finalize(success=False, error="API error: Invalid project configuration")
    return result


# ============================================================================
# generation_status_to_verdict Tests
# ============================================================================


class TestGenerationStatusToVerdict:
    """Test generation_status_to_verdict mapping."""

    def test_completed_maps_to_pass(self):
        """COMPLETED status should map to PASS verdict."""
        assert generation_status_to_verdict(GenerationStatus.COMPLETED) == Verdict.PASS

    def test_failed_maps_to_fail(self):
        """FAILED status should map to FAIL verdict."""
        assert generation_status_to_verdict(GenerationStatus.FAILED) == Verdict.FAIL

    def test_cancelled_maps_to_error(self):
        """CANCELLED status should map to ERROR verdict."""
        assert generation_status_to_verdict(GenerationStatus.CANCELLED) == Verdict.ERROR

    def test_pending_maps_to_error(self):
        """PENDING status should map to ERROR verdict."""
        assert generation_status_to_verdict(GenerationStatus.PENDING) == Verdict.ERROR

    def test_in_progress_maps_to_error(self):
        """IN_PROGRESS status should map to ERROR verdict."""
        assert generation_status_to_verdict(GenerationStatus.IN_PROGRESS) == Verdict.ERROR


# ============================================================================
# e2e_result_to_test_result Tests
# ============================================================================


class TestE2EResultToTestResult:
    """Test e2e_result_to_test_result conversion."""

    def test_successful_result_converts_correctly(self, successful_e2e_result: E2EResult):
        """Successful E2E result should convert to passing TestResult."""
        test_result = e2e_result_to_test_result(successful_e2e_result)

        assert isinstance(test_result, TestResult)
        assert test_result.verdict == Verdict.PASS
        assert test_result.passed == 5  # From artifacts.total_tests
        assert test_result.failed == 0
        assert test_result.errors == 0
        assert test_result.exit_code == 0
        assert test_result.category == "e2e_generation"
        assert test_result.parsed_from == "e2e"

    def test_failed_result_converts_correctly(self, failed_e2e_result: E2EResult):
        """Failed E2E result should convert to failing TestResult."""
        test_result = e2e_result_to_test_result(failed_e2e_result)

        assert isinstance(test_result, TestResult)
        assert test_result.verdict == Verdict.FAIL
        assert test_result.passed == 0
        assert test_result.failed == 1
        assert test_result.errors == 0
        assert test_result.exit_code == 1
        assert len(test_result.failures) == 1
        assert "API error" in test_result.failures[0].message

    def test_custom_category(self, successful_e2e_result: E2EResult):
        """Custom category should be preserved."""
        test_result = e2e_result_to_test_result(successful_e2e_result, category="custom_e2e")

        assert test_result.category == "custom_e2e"

    def test_failure_includes_metadata(self, failed_e2e_result: E2EResult):
        """Failure should include relevant metadata."""
        test_result = e2e_result_to_test_result(failed_e2e_result)

        failure = test_result.failures[0]
        assert "run_id" in failure.metadata
        assert failure.metadata["run_id"] == "mock-run-123"
        assert failure.metadata["status"] == "failed"

    def test_duration_preserved(self, successful_e2e_result: E2EResult):
        """Duration should be preserved from E2E result."""
        test_result = e2e_result_to_test_result(successful_e2e_result)

        # Duration comes from total_duration_seconds which is set by finalize()
        assert test_result.duration >= 0


# ============================================================================
# status_result_to_test_result Tests
# ============================================================================


class TestStatusResultToTestResult:
    """Test status_result_to_test_result conversion."""

    def test_completed_status(self):
        """Completed status should convert to passing TestResult."""
        status = StatusResult(
            run_id="test-123",
            status=GenerationStatus.COMPLETED,
            tests_generated=10,
            progress_percent=100.0,
        )

        test_result = status_result_to_test_result(status)

        assert test_result.verdict == Verdict.PASS
        assert test_result.passed == 10
        assert test_result.failed == 0

    def test_failed_status(self):
        """Failed status should convert to failing TestResult."""
        status = StatusResult(
            run_id="test-123",
            status=GenerationStatus.FAILED,
            error="Generation failed: timeout",
            progress_percent=50.0,
        )

        test_result = status_result_to_test_result(status)

        assert test_result.verdict == Verdict.FAIL
        assert test_result.passed == 0
        assert test_result.failed == 1
        assert len(test_result.failures) == 1
        assert "timeout" in test_result.failures[0].message

    def test_in_progress_status(self):
        """In-progress status should convert to ERROR TestResult."""
        status = StatusResult(
            run_id="test-123",
            status=GenerationStatus.IN_PROGRESS,
            tests_generated=3,
            progress_percent=30.0,
        )

        test_result = status_result_to_test_result(status)

        assert test_result.verdict == Verdict.ERROR
        assert test_result.errors == 1


# ============================================================================
# e2e_to_evaluation_result Tests
# ============================================================================


class TestE2EToEvaluationResult:
    """Test e2e_to_evaluation_result conversion."""

    def test_successful_result_creates_valid_evaluation(self, successful_e2e_result: E2EResult):
        """Successful E2E result should create valid EvaluationResult."""
        evaluation = e2e_to_evaluation_result(successful_e2e_result)

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.verdict == Verdict.PASS
        assert evaluation.exit_code == 0
        assert len(evaluation.sessions) == 1

        # Check metadata
        assert evaluation.metadata.adapter_type == "e2e"
        assert evaluation.metadata.category == "e2e_generation"

    def test_failed_result_creates_failing_evaluation(self, failed_e2e_result: E2EResult):
        """Failed E2E result should create failing EvaluationResult."""
        evaluation = e2e_to_evaluation_result(failed_e2e_result)

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.verdict == Verdict.FAIL
        assert evaluation.exit_code == 1

    def test_project_name_preserved(self, successful_e2e_result: E2EResult):
        """Project name should be preserved in metadata."""
        evaluation = e2e_to_evaluation_result(successful_e2e_result, project_name="my-project")

        assert evaluation.metadata.project_name == "my-project"

    def test_session_contains_metrics(self, successful_e2e_result: E2EResult):
        """Session should contain expected metrics."""
        evaluation = e2e_to_evaluation_result(successful_e2e_result)
        session = evaluation.sessions[0]

        metric_names = [m.name for m in session.metrics]
        assert "generation_status" in metric_names
        assert "tests_generated" in metric_names
        assert "timed_out" in metric_names
        assert "duration_seconds" in metric_names

    def test_session_contains_changeset_metadata(self, successful_e2e_result: E2EResult):
        """Session metadata should include changeset info."""
        evaluation = e2e_to_evaluation_result(successful_e2e_result)
        session = evaluation.sessions[0]

        assert "changeset" in session.metadata
        assert session.metadata["changeset"]["base_ref"] == "main"
        assert session.metadata["changeset"]["head_ref"] == "feature-branch"

    def test_serializes_to_json(self, successful_e2e_result: E2EResult):
        """EvaluationResult should serialize to valid JSON."""
        evaluation = e2e_to_evaluation_result(successful_e2e_result)
        json_str = evaluation.to_json()

        assert isinstance(json_str, str)
        assert '"verdict": "PASS"' in json_str


# ============================================================================
# create_e2e_evaluation_context Tests
# ============================================================================


class TestCreateE2EEvaluationContext:
    """Test create_e2e_evaluation_context helper."""

    def test_context_contains_required_keys(self, successful_e2e_result: E2EResult):
        """Context should contain all required template keys."""
        context = create_e2e_evaluation_context(successful_e2e_result)

        required_keys = [
            "verdict",
            "exit_code",
            "run_id",
            "provider",
            "status",
            "tests_generated",
            "files_generated",
            "duration",
            "duration_seconds",
            "timestamp",
            "changeset",
            "config",
            "category",
            "failures",
        ]

        for key in required_keys:
            assert key in context, f"Missing required key: {key}"

    def test_successful_context_values(self, successful_e2e_result: E2EResult):
        """Successful result should have correct context values."""
        context = create_e2e_evaluation_context(successful_e2e_result)

        assert context["verdict"] == "PASS"
        assert context["exit_code"] == 0
        assert context["tests_generated"] == 5
        assert context["files_generated"] == 1
        assert context["passed"] == 5
        assert context["failed"] == 0
        assert context["errors"] == 0
        assert context["failures"] == []

    def test_failed_context_values(self, failed_e2e_result: E2EResult):
        """Failed result should have correct context values."""
        context = create_e2e_evaluation_context(failed_e2e_result)

        assert context["verdict"] == "FAIL"
        assert context["exit_code"] == 1
        assert context["tests_generated"] == 0
        assert context["passed"] == 0
        assert context["failed"] == 1
        assert len(context["failures"]) == 1

    def test_changeset_info_included(self, successful_e2e_result: E2EResult):
        """Changeset info should be included in context."""
        context = create_e2e_evaluation_context(successful_e2e_result)

        assert "changeset" in context
        assert context["changeset"]["base_ref"] == "main"
        assert context["changeset"]["head_ref"] == "feature-branch"
        assert context["changeset"]["total_changes"] == 2

    def test_config_info_included(self, successful_e2e_result: E2EResult):
        """Config info should be included in context."""
        context = create_e2e_evaluation_context(successful_e2e_result)

        assert "config" in context
        assert context["config"]["provider_name"] == "mock"
        assert context["config"]["test_framework"] == "playwright"


# ============================================================================
# render_e2e_result Tests
# ============================================================================


class TestRenderE2EResult:
    """Test render_e2e_result template rendering."""

    def test_render_e2e_summary(self, successful_e2e_result: E2EResult):
        """Should render e2e_summary template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_summary")

        assert isinstance(output, str)
        assert "[PASS]" in output
        assert "E2E Generation" in output
        assert "5 tests generated" in output

    def test_render_e2e_ci(self, successful_e2e_result: E2EResult):
        """Should render e2e_ci template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_ci")

        assert isinstance(output, str)
        assert "SYSTEMEVAL E2E GENERATION RESULTS" in output
        assert "Verdict:" in output
        assert "PASS" in output

    def test_render_e2e_github(self, successful_e2e_result: E2EResult):
        """Should render e2e_github template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_github")

        assert isinstance(output, str)
        assert "::notice::" in output
        assert "E2E generation succeeded" in output

    def test_render_e2e_markdown(self, successful_e2e_result: E2EResult):
        """Should render e2e_markdown template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_markdown")

        assert isinstance(output, str)
        assert "# E2E Test Generation Results" in output
        assert "| Metric | Value |" in output
        assert "**PASS**" in output

    def test_render_failed_result(self, failed_e2e_result: E2EResult):
        """Should render failed result correctly."""
        output = render_e2e_result(failed_e2e_result, template_name="e2e_summary")

        assert "[FAIL]" in output

    def test_render_e2e_table(self, successful_e2e_result: E2EResult):
        """Should render e2e_table template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_table")

        assert isinstance(output, str)
        assert "E2E TEST GENERATION RESULTS" in output
        assert "Tests Generated:" in output

    def test_render_e2e_slack(self, successful_e2e_result: E2EResult):
        """Should render e2e_slack template."""
        output = render_e2e_result(successful_e2e_result, template_name="e2e_slack")

        assert isinstance(output, str)
        assert "*PASS*" in output
        assert "E2E Generation" in output


# ============================================================================
# Integration Tests
# ============================================================================


class TestReportingIntegration:
    """Integration tests for the reporting module."""

    def test_full_conversion_pipeline(
        self,
        sample_changeset: ChangeSet,
        sample_e2e_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test full conversion from E2EResult through all formats."""
        # Create artifacts
        test_file = tmp_path / "test_api.spec.ts"
        test_file.write_text("test('api works', async () => {});")

        artifacts = ArtifactResult(
            run_id="integration-test-123",
            output_directory=tmp_path,
            test_files=[test_file],
            total_tests=3,
            total_size_bytes=512,
        )

        # Create E2E result
        e2e_result = E2EResult(
            changeset=sample_changeset,
            config=sample_e2e_config,
            generation=GenerationResult(
                run_id="integration-test-123",
                status=GenerationStatus.IN_PROGRESS,
            ),
            completion=CompletionResult(
                run_id="integration-test-123",
                status=GenerationStatus.COMPLETED,
                completed=True,
                timed_out=False,
                duration_seconds=30.0,
            ),
            artifacts=artifacts,
            success=True,
        )
        e2e_result.finalize(success=True)

        # Convert to TestResult
        test_result = e2e_result_to_test_result(e2e_result)
        assert test_result.verdict == Verdict.PASS
        assert test_result.passed == 3

        # Convert to EvaluationResult
        evaluation = e2e_to_evaluation_result(e2e_result)
        assert evaluation.verdict == Verdict.PASS
        assert len(evaluation.sessions) == 1

        # Create context and render
        context = create_e2e_evaluation_context(e2e_result)
        assert context["tests_generated"] == 3

        # Render to multiple formats
        summary = render_e2e_result(e2e_result, "e2e_summary")
        assert "[PASS]" in summary

        markdown = render_e2e_result(e2e_result, "e2e_markdown")
        assert "# E2E Test Generation Results" in markdown

    def test_error_handling_in_conversion(self, sample_changeset: ChangeSet, sample_e2e_config: E2EConfig):
        """Test that conversion handles edge cases gracefully."""
        # Create E2E result with no artifacts
        e2e_result = E2EResult(
            changeset=sample_changeset,
            config=sample_e2e_config,
            generation=GenerationResult(
                run_id="error-test",
                status=GenerationStatus.FAILED,
                message="Generation failed immediately",
            ),
            completion=CompletionResult(
                run_id="error-test",
                status=GenerationStatus.FAILED,
                completed=True,
                timed_out=False,
                duration_seconds=1.0,
                error="Authentication failed",
            ),
            artifacts=None,
            success=False,
            error="Authentication failed",
        )
        e2e_result.finalize(success=False, error="Authentication failed")

        # All conversions should work without exceptions
        test_result = e2e_result_to_test_result(e2e_result)
        assert test_result.verdict == Verdict.FAIL

        evaluation = e2e_to_evaluation_result(e2e_result)
        assert evaluation.verdict == Verdict.FAIL

        context = create_e2e_evaluation_context(e2e_result)
        assert context["error"] == "Authentication failed"

        summary = render_e2e_result(e2e_result, "e2e_summary")
        assert "[FAIL]" in summary

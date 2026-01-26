"""
E2E test generation reporting integration.

This module converts E2E generation results to systemeval's standard
reporting formats (TestResult, EvaluationResult) for consistent
output across different adapters and providers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from systemeval.types import TestResult, TestFailure, Verdict
from systemeval.core.evaluation import (
    EvaluationResult,
    create_evaluation,
    create_session,
    metric,
    Severity,
)
from ..core.types import (
    E2EResult,
    GenerationStatus,
    StatusResult,
    ArtifactResult,
)


# ============================================================================
# Status to Verdict Mapping
# ============================================================================

def generation_status_to_verdict(status: GenerationStatus) -> Verdict:
    """
    Map GenerationStatus to Verdict.

    Args:
        status: E2E generation status

    Returns:
        Corresponding Verdict value

    Mapping:
        - COMPLETED -> PASS (generation succeeded)
        - FAILED -> FAIL (generation failed)
        - CANCELLED -> ERROR (user/system cancellation)
        - PENDING -> ERROR (incomplete state)
        - IN_PROGRESS -> ERROR (incomplete state)
    """
    if status == GenerationStatus.COMPLETED:
        return Verdict.PASS
    elif status == GenerationStatus.FAILED:
        return Verdict.FAIL
    else:
        # PENDING, IN_PROGRESS, CANCELLED are all ERROR states
        # as they indicate the process did not complete normally
        return Verdict.ERROR


# ============================================================================
# E2E Result to TestResult Conversion
# ============================================================================

def e2e_result_to_test_result(
    e2e_result: E2EResult,
    category: Optional[str] = None,
) -> TestResult:
    """
    Convert an E2EResult to systemeval's standard TestResult format.

    This allows E2E generation results to be displayed using the same
    templates and output formats as test execution results.

    Args:
        e2e_result: Complete E2E generation result from orchestrator
        category: Optional category label for the result (default: "e2e_generation")

    Returns:
        TestResult with E2E metrics mapped to test counts

    Mapping:
        - passed: Number of tests successfully generated
        - failed: 1 if generation failed, 0 otherwise
        - errors: 1 if generation errored (cancelled/timeout), 0 otherwise
        - skipped: 0 (not applicable to E2E generation)
        - duration: Total generation duration
        - exit_code: 0=PASS, 1=FAIL, 2=ERROR
    """
    # Determine verdict from completion status
    verdict = generation_status_to_verdict(e2e_result.completion.status)

    # Calculate test counts based on outcome
    tests_generated = 0
    if e2e_result.artifacts:
        tests_generated = e2e_result.artifacts.total_tests

    # Map to passed/failed/error counts
    if verdict == Verdict.PASS:
        passed = tests_generated
        failed = 0
        errors = 0
        exit_code = 0
    elif verdict == Verdict.FAIL:
        passed = 0
        failed = 1
        errors = 0
        exit_code = 1
    else:  # ERROR
        passed = 0
        failed = 0
        errors = 1
        exit_code = 2

    # Build failures list if generation failed
    failures = []
    if verdict != Verdict.PASS and e2e_result.error:
        failures.append(TestFailure(
            test_id=f"e2e_generation:{e2e_result.generation.run_id}",
            test_name="E2E Test Generation",
            message=e2e_result.error,
            traceback=None,
            duration=e2e_result.total_duration_seconds,
            metadata={
                "run_id": e2e_result.generation.run_id,
                "status": e2e_result.completion.status.value,
                "provider": e2e_result.config.provider_name,
                "timed_out": e2e_result.completion.timed_out,
            },
        ))

    # Create TestResult
    result = TestResult(
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=0,
        duration=e2e_result.total_duration_seconds,
        failures=failures,
        total=max(tests_generated, 1),  # At least 1 for the generation attempt
        exit_code=exit_code,
        coverage_percent=None,
        category=category or "e2e_generation",
        timestamp=e2e_result.completed_at or e2e_result.started_at,
        parsed_from="e2e",
    )

    return result


def status_result_to_test_result(
    status: StatusResult,
    category: Optional[str] = None,
) -> TestResult:
    """
    Convert a StatusResult to TestResult for progress reporting.

    Useful for showing intermediate status during long-running generation.

    Args:
        status: Current status of E2E generation
        category: Optional category label

    Returns:
        TestResult representing current generation state
    """
    verdict = generation_status_to_verdict(status.status)

    if verdict == Verdict.PASS:
        passed = status.tests_generated
        failed = 0
        errors = 0
        exit_code = 0
    elif verdict == Verdict.FAIL:
        passed = 0
        failed = 1
        errors = 0
        exit_code = 1
    else:
        passed = 0
        failed = 0
        errors = 1
        exit_code = 2

    failures = []
    if status.error:
        failures.append(TestFailure(
            test_id=f"e2e_generation:{status.run_id}",
            test_name="E2E Test Generation",
            message=status.error,
            duration=0.0,
            metadata={
                "run_id": status.run_id,
                "status": status.status.value,
                "progress_percent": status.progress_percent,
            },
        ))

    return TestResult(
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=0,
        duration=0.0,  # Not available in StatusResult
        failures=failures,
        total=max(status.tests_generated, 1),
        exit_code=exit_code,
        category=category or "e2e_generation",
        timestamp=status.completed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        parsed_from="e2e",
    )


# ============================================================================
# E2E Result to EvaluationResult Conversion
# ============================================================================

def e2e_to_evaluation_result(
    e2e_result: E2EResult,
    project_name: Optional[str] = None,
) -> EvaluationResult:
    """
    Convert an E2EResult to EvaluationResult for detailed JSON output.

    The EvaluationResult provides a richer schema with:
    - Unique evaluation ID and timestamp
    - Multiple metrics with pass/fail conditions
    - Session-based organization
    - Environment context

    Args:
        e2e_result: Complete E2E generation result
        project_name: Optional project name for context

    Returns:
        EvaluationResult with detailed E2E metrics
    """
    # Create evaluation with metadata
    evaluation = create_evaluation(
        adapter_type="e2e",
        category="e2e_generation",
        project_name=project_name or e2e_result.config.project_slug,
        command=f"systemeval e2e run --provider {e2e_result.config.provider_name}",
        environment={
            "provider": e2e_result.config.provider_name,
            "test_framework": e2e_result.config.test_framework,
            "programming_language": e2e_result.config.programming_language,
        },
    )

    # Create session for generation
    session = create_session("e2e_generation")
    session.started_at = e2e_result.started_at
    session.completed_at = e2e_result.completed_at
    session.duration_seconds = e2e_result.total_duration_seconds

    # Add metrics

    # 1. Generation Status Metric
    generation_passed = e2e_result.completion.status == GenerationStatus.COMPLETED
    session.metrics.append(metric(
        name="generation_status",
        value=e2e_result.completion.status.value,
        expected="completed",
        condition=generation_passed,
        message=e2e_result.completion.final_message,
        severity=Severity.ERROR,
    ))

    # 2. Tests Generated Metric
    tests_generated = e2e_result.artifacts.total_tests if e2e_result.artifacts else 0
    session.metrics.append(metric(
        name="tests_generated",
        value=tests_generated,
        expected=">0",
        condition=tests_generated > 0 or not generation_passed,  # Allow 0 if failed
        message=f"{tests_generated} tests generated",
        severity=Severity.WARNING if generation_passed else Severity.INFO,
    ))

    # 3. Timeout Metric
    session.metrics.append(metric(
        name="timed_out",
        value=e2e_result.completion.timed_out,
        expected=False,
        condition=not e2e_result.completion.timed_out,
        message="Generation timed out" if e2e_result.completion.timed_out else None,
        severity=Severity.ERROR,
    ))

    # 4. Duration Metric
    session.metrics.append(metric(
        name="duration_seconds",
        value=round(e2e_result.total_duration_seconds, 2),
        expected=f"<{e2e_result.config.timeout_seconds}",
        condition=e2e_result.total_duration_seconds < e2e_result.config.timeout_seconds,
        message=f"Completed in {e2e_result.total_duration_seconds:.1f}s",
        severity=Severity.INFO,
    ))

    # 5. Files Generated Metric (if artifacts available)
    if e2e_result.artifacts:
        files_count = len(e2e_result.artifacts.test_files)
        session.metrics.append(metric(
            name="files_generated",
            value=files_count,
            expected=">0",
            condition=files_count > 0,
            message=f"{files_count} test files generated",
            severity=Severity.WARNING,
            output_directory=str(e2e_result.artifacts.output_directory),
        ))

    # Add changeset info to metadata
    session.metadata["changeset"] = {
        "base_ref": e2e_result.changeset.base_ref,
        "head_ref": e2e_result.changeset.head_ref,
        "total_changes": e2e_result.changeset.total_changes,
        "total_additions": e2e_result.changeset.total_additions,
        "total_deletions": e2e_result.changeset.total_deletions,
    }

    # Add run info
    session.metadata["run"] = {
        "run_id": e2e_result.generation.run_id,
        "provider": e2e_result.config.provider_name,
        "started_at": e2e_result.generation.started_at,
    }

    # Add error if present
    if e2e_result.error:
        session.metadata["error"] = e2e_result.error

    # Add warnings
    if e2e_result.warnings:
        session.metadata["warnings"] = e2e_result.warnings

    # Add artifacts info if available
    if e2e_result.artifacts:
        session.artifacts["test_files"] = ",".join(
            str(f) for f in e2e_result.artifacts.test_files[:10]  # Limit to 10
        )
        session.artifacts["output_directory"] = str(e2e_result.artifacts.output_directory)

    # Add session to evaluation
    evaluation.add_session(session)

    # Add any warnings from E2E result
    for warning in e2e_result.warnings:
        evaluation.add_warning(warning)

    # Finalize
    evaluation.metadata.duration_seconds = e2e_result.total_duration_seconds
    evaluation.finalize()

    return evaluation


def create_e2e_evaluation_context(
    e2e_result: E2EResult,
) -> Dict[str, Any]:
    """
    Create a template context dictionary from E2EResult.

    This context can be passed directly to TemplateRenderer.render()
    for custom output formats.

    Args:
        e2e_result: Complete E2E generation result

    Returns:
        Dictionary with template-friendly keys
    """
    verdict = generation_status_to_verdict(e2e_result.completion.status)
    tests_generated = e2e_result.artifacts.total_tests if e2e_result.artifacts else 0
    files_generated = len(e2e_result.artifacts.test_files) if e2e_result.artifacts else 0

    return {
        # Verdict and status
        "verdict": verdict.value,
        "exit_code": 0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),

        # Generation info
        "run_id": e2e_result.generation.run_id,
        "provider": e2e_result.config.provider_name,
        "status": e2e_result.completion.status.value,

        # Counts
        "tests_generated": tests_generated,
        "files_generated": files_generated,
        "total": tests_generated,
        "passed": tests_generated if verdict == Verdict.PASS else 0,
        "failed": 1 if verdict == Verdict.FAIL else 0,
        "errors": 1 if verdict == Verdict.ERROR else 0,
        "skipped": 0,

        # Timing
        "duration": e2e_result.total_duration_seconds,
        "duration_seconds": e2e_result.total_duration_seconds,
        "started_at": e2e_result.started_at,
        "completed_at": e2e_result.completed_at,
        "timestamp": e2e_result.completed_at or e2e_result.started_at,
        "timed_out": e2e_result.completion.timed_out,

        # Changeset info
        "changeset": {
            "base_ref": e2e_result.changeset.base_ref,
            "head_ref": e2e_result.changeset.head_ref,
            "total_changes": e2e_result.changeset.total_changes,
            "total_additions": e2e_result.changeset.total_additions,
            "total_deletions": e2e_result.changeset.total_deletions,
        },

        # Config info
        "config": {
            "provider_name": e2e_result.config.provider_name,
            "test_framework": e2e_result.config.test_framework,
            "programming_language": e2e_result.config.programming_language,
            "project_slug": e2e_result.config.project_slug,
            "output_directory": str(e2e_result.config.output_directory) if e2e_result.config.output_directory else None,
        },

        # Artifacts
        "artifacts": {
            "output_directory": str(e2e_result.artifacts.output_directory) if e2e_result.artifacts else None,
            "test_files": [str(f) for f in e2e_result.artifacts.test_files] if e2e_result.artifacts else [],
            "total_tests": tests_generated,
            "total_size_bytes": e2e_result.artifacts.total_size_bytes if e2e_result.artifacts else 0,
        } if e2e_result.artifacts else None,

        # Error/warnings
        "error": e2e_result.error,
        "warnings": e2e_result.warnings,

        # For template compatibility with standard TestResult
        "category": "e2e_generation",
        "failures": [{
            "test_id": f"e2e_generation:{e2e_result.generation.run_id}",
            "test_name": "E2E Test Generation",
            "message": e2e_result.error or "Generation did not complete",
            "duration": e2e_result.total_duration_seconds,
            "duration_seconds": e2e_result.total_duration_seconds,
            "metadata": {
                "run_id": e2e_result.generation.run_id,
                "status": e2e_result.completion.status.value,
            },
        }] if verdict != Verdict.PASS else [],
    }


def render_e2e_result(
    e2e_result: E2EResult,
    template_name: str = "e2e_summary",
) -> str:
    """
    Render E2E result using the template system.

    Args:
        e2e_result: Complete E2E generation result
        template_name: Name of template to use (e2e_summary, e2e_markdown, etc.)

    Returns:
        Rendered output string
    """
    from systemeval.templates import TemplateRenderer

    renderer = TemplateRenderer()
    context = create_e2e_evaluation_context(e2e_result)

    return renderer.render(template_name, context)

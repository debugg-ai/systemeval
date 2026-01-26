"""JSON formatter for machine-readable output."""

import json
from typing import TYPE_CHECKING, Optional

from systemeval.types import TestResult

if TYPE_CHECKING:
    from systemeval.config import MultiProjectResult


class JsonFormatter:
    """Formats test results as JSON.

    This formatter produces machine-readable JSON output suitable for
    CI/CD systems and automated processing.

    The output uses the EvaluationResult schema when available, falling
    back to TestResult.to_dict() for simple cases.

    Attributes:
        adapter_type: Test adapter type for evaluation context.
        project_name: Project name for evaluation context.
    """

    def __init__(
        self,
        adapter_type: str = "unknown",
        project_name: Optional[str] = None,
    ):
        """Initialize the JSON formatter.

        Args:
            adapter_type: Type of test adapter (pytest, jest, etc.).
            project_name: Project name for context.
        """
        self.adapter_type = adapter_type
        self.project_name = project_name

    def format_single_result(self, result: TestResult) -> str:
        """Format a single test result as JSON.

        Uses TestResult.to_evaluation() to produce the unified
        EvaluationResult schema with deterministic verdicts.

        Args:
            result: TestResult to format.

        Returns:
            JSON string with evaluation data.
        """
        # Check if this is a pipeline adapter result with detailed evaluation
        if (
            hasattr(result, "pipeline_adapter")
            and hasattr(result, "pipeline_tests")
            and result.pipeline_adapter is not None
        ):
            # Use pipeline adapter's detailed evaluation
            evaluation = result.pipeline_adapter.create_evaluation_result(
                tests=result.pipeline_tests,
                results_by_project=result.pipeline_metrics,
                duration=result.duration,
            )
        else:
            # Convert to unified EvaluationResult schema
            evaluation = result.to_evaluation(
                adapter_type=self.adapter_type,
                project_name=self.project_name,
            )
            evaluation.finalize()

        return evaluation.to_json()

    def format_multi_project_result(self, result: "MultiProjectResult") -> str:
        """Format multi-project results as JSON.

        Args:
            result: MultiProjectResult to format.

        Returns:
            JSON string with multi-project data.
        """
        return json.dumps(result.to_json_dict(), indent=2)

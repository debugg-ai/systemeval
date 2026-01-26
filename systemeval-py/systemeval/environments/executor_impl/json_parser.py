"""
JSON-based test result parsing.

Provides:
- JsonResultParser: Parses structured JSON output from test frameworks
- EmbeddedJsonParser: Extracts and parses JSON embedded in test output
"""
import json
import re
from typing import Optional

from systemeval.types import TestResult


class JsonResultParser:
    """
    Parser for structured JSON output from test reporters.

    Supports:
    - pytest-json-report format
    - Jest --json format
    - Playwright JSON reporter format
    """

    @property
    def name(self) -> str:
        return "json"

    def can_parse(self, json_str: str) -> bool:
        """Check if string is valid JSON."""
        try:
            json.loads(json_str)
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    def parse(self, json_output: str, exit_code: int) -> Optional[TestResult]:
        """Parse structured JSON output from test reporters."""
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError:
            return None

        # pytest-json-report format
        if "summary" in data and "tests" in data:
            summary = data.get("summary", {})
            return TestResult(
                passed=summary.get("passed", 0),
                failed=summary.get("failed", 0),
                errors=summary.get("error", 0),
                skipped=summary.get("skipped", 0),
                duration=data.get("duration", 0.0),
                exit_code=exit_code,
                parsed_from="json:pytest",
            )

        # Jest JSON format
        if "numPassedTests" in data:
            return TestResult(
                passed=data.get("numPassedTests", 0),
                failed=data.get("numFailedTests", 0),
                errors=0,
                skipped=data.get("numPendingTests", 0),
                duration=data.get("testResults", [{}])[0].get("perfStats", {}).get("runtime", 0) / 1000,
                exit_code=exit_code,
                parsed_from="json:jest",
            )

        # Playwright JSON format
        if "stats" in data and "expected" in data.get("stats", {}):
            stats = data["stats"]
            return TestResult(
                passed=stats.get("expected", 0),
                failed=stats.get("unexpected", 0),
                errors=0,
                skipped=stats.get("skipped", 0),
                duration=stats.get("duration", 0) / 1000,  # ms to seconds
                exit_code=exit_code,
                parsed_from="json:playwright",
            )

        return None


class EmbeddedJsonParser:
    """
    Parser for extracting JSON embedded in test output.

    Some test frameworks output JSON inline with other text.
    This parser finds and extracts that JSON.
    """

    @property
    def name(self) -> str:
        return "embedded_json"

    def can_parse(self, output: str) -> bool:
        """Check if output contains embedded JSON."""
        # Look for common JSON patterns
        patterns = [
            r'\{[^{}]*"summary"\s*:\s*\{[^}]+\}[^{}]*\}',
            r'\{[^{}]*"numPassedTests"\s*:\s*\d+[^{}]*\}',
        ]
        return any(re.search(pattern, output) for pattern in patterns)

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """Extract and parse embedded JSON from output."""
        # Look for common JSON patterns in output
        json_patterns = [
            # pytest-json-report inline
            r'\{[^{}]*"summary"\s*:\s*\{[^}]+\}[^{}]*\}',
            # Jest JSON output
            r'\{[^{}]*"numPassedTests"\s*:\s*\d+[^{}]*\}',
        ]

        json_parser = JsonResultParser()

        for pattern in json_patterns:
            match = re.search(pattern, output)
            if match:
                result = json_parser.parse(match.group(0), exit_code)
                if result:
                    return result

        return None

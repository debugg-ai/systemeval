"""
Flexible test executor for running various test commands and scripts.

Supports:
- Shell scripts (./scripts/run-e2e.sh)
- Multi-step command sequences
- Pytest/Jest with custom arguments
- Arbitrary shell commands
- Docker exec commands

Architecture:
- TestExecutorProtocol: Interface for command execution
- ResultParserProtocol: Interface for parsing test output
- Pattern classes: Framework-specific regex patterns
- Strategy pattern: Parsers are selected based on output format

This module now serves as a facade, delegating to specialized submodules:
- process_executor: Local command execution
- docker_executor: Docker container execution
- test_result_parser: Framework-specific parsing
- json_parser: JSON result parsing
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple, Union, runtime_checkable

from systemeval.types import TestResult
from systemeval.utils.logging import get_logger

# Import pattern classes for backward compatibility
from systemeval.environments.executor.patterns import (
    ParserFactory,
    PytestPatterns,
    JestPatterns,
    PlaywrightPatterns,
    MochaPatterns,
    GoTestPatterns,
    GenericPatterns,
)

# Import execution models
from systemeval.environments.executor.models import ExecutionConfig, ExecutionResult

# Import submodule components
from systemeval.environments.executor.impl.process_executor import LocalCommandExecutor
from systemeval.environments.executor.impl.docker_executor import DockerExecutor as _DockerExecutor
from systemeval.environments.executor.impl.test_result_parser import (
    PytestResultParser,
    JestResultParser,
    PlaywrightResultParser,
    MochaResultParser,
    GoTestResultParser,
    GenericResultParser,
    TestResultAggregator,
    DEFAULT_PARSERS,
)
from systemeval.environments.executor.impl.json_parser import (
    JsonResultParser,
    EmbeddedJsonParser,
)

logger = get_logger(__name__)


# ============================================================================
# Protocols (Interfaces)
# ============================================================================


@runtime_checkable
class TestExecutorProtocol(Protocol):
    """
    Protocol for test command execution.

    Defines the contract for executing test commands and scripts.
    Implementations may execute locally, in Docker, or remotely.

    Example implementations:
    - TestExecutor: Local execution
    - DockerExecutor: Execution inside Docker containers
    """

    def execute(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = True,
        shell: bool = True,
    ) -> ExecutionResult:
        """
        Execute a test command or script.

        Args:
            command: Command string, script path, or list of commands
            timeout: Timeout in seconds
            env: Additional environment variables
            stream: Stream output in real-time
            shell: Use shell for command interpretation

        Returns:
            ExecutionResult with output and exit code
        """
        ...

    def parse_test_results(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> TestResult:
        """
        Parse test output to extract results.

        Args:
            output: Test command stdout/stderr
            exit_code: Command exit code
            json_output: Optional JSON output from structured reporters

        Returns:
            TestResult with parsed counts and metadata
        """
        ...


@runtime_checkable
class ResultParserProtocol(Protocol):
    """
    Protocol for parsing test framework output.

    Defines the contract for framework-specific result parsing.
    Each parser knows how to extract test counts and metadata from
    a specific test framework's output format.

    Example implementations:
    - PytestParser
    - JestParser
    - PlaywrightParser
    - MochaParser
    - GoTestParser
    - GenericParser (fallback)
    """

    @property
    def name(self) -> str:
        """Parser name (e.g., 'pytest', 'jest')."""
        ...

    def can_parse(self, output: str) -> bool:
        """
        Check if this parser can handle the given output.

        Args:
            output: Test output to check

        Returns:
            True if this parser recognizes the output format
        """
        ...

    def parse(self, output: str, exit_code: int) -> Optional[TestResult]:
        """
        Parse test output and extract results.

        Args:
            output: Test command output
            exit_code: Command exit code

        Returns:
            TestResult if parsing succeeded, None otherwise
        """
        ...


# Backward compatibility aliases for existing code
# These map the old module-level names to the new class-based organization
PYTEST_FULL_PATTERN = PytestPatterns.FULL_SUMMARY
PYTEST_SHORT_SUMMARY = PytestPatterns.SHORT_SUMMARY
PYTEST_COLLECTION_ERROR = PytestPatterns.COLLECTION_ERROR
JEST_SUMMARY = JestPatterns.SUMMARY
JEST_TIME = JestPatterns.TIME
PLAYWRIGHT_SUMMARY = PlaywrightPatterns.SUMMARY
PLAYWRIGHT_FAILED = PlaywrightPatterns.FAILED
PLAYWRIGHT_SKIPPED = PlaywrightPatterns.SKIPPED
MOCHA_PASSING = MochaPatterns.PASSING
MOCHA_FAILING = MochaPatterns.FAILING
MOCHA_PENDING = MochaPatterns.PENDING
GO_TEST_PASS = GoTestPatterns.PASS
GO_TEST_FAIL = GoTestPatterns.FAIL
GO_TEST_SKIP = GoTestPatterns.SKIP
INDIVIDUAL_PASSED = GenericPatterns.PASSED
INDIVIDUAL_FAILED = GenericPatterns.FAILED
INDIVIDUAL_SKIPPED = GenericPatterns.SKIPPED
DURATION_PATTERN = GenericPatterns.DURATION


# ============================================================================
# Helper Functions (Backward Compatibility)
# ============================================================================


def get_parser_for_output(
    output: str,
    parsers: Optional[List[ResultParserProtocol]] = None,
) -> Optional[ResultParserProtocol]:
    """
    Find the appropriate parser for the given output.

    Args:
        output: Test output to parse
        parsers: Optional list of parsers to try (defaults to DEFAULT_PARSERS)

    Returns:
        First parser that can handle the output, or None
    """
    for parser in (parsers or DEFAULT_PARSERS):
        if parser.can_parse(output):
            return parser
    return None


# ============================================================================
# Main Executor Classes (Facades)
# ============================================================================


class TestExecutor:
    """
    Flexible executor for running test commands.

    This is now a facade that delegates to LocalCommandExecutor
    and TestResultAggregator for backward compatibility.

    Handles various test scenarios:
    - Simple commands: "pytest -v"
    - Shell scripts: "./scripts/run-e2e.sh"
    - Multi-step: ["npm run build", "npm test", "./scripts/validate.sh"]
    - Complex pipelines: "cd app && npm install && npm test"
    """

    def __init__(
        self,
        working_dir: str = ".",
        env: Optional[Dict[str, str]] = None,
        verbose: bool = False,
    ) -> None:
        # Delegate to LocalCommandExecutor
        self._executor = LocalCommandExecutor(
            working_dir=working_dir,
            env=env,
            verbose=verbose,
        )
        self._parser = TestResultAggregator()

        # Expose attributes for backward compatibility
        self.working_dir = self._executor.working_dir
        self.base_env = self._executor.base_env
        self.verbose = self._executor.verbose

    def execute(
        self,
        command: Union[str, List[str]],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        stream: bool = True,
        shell: bool = True,
    ) -> ExecutionResult:
        """
        Execute a test command or script.

        Args:
            command: Command string, script path, or list of commands
            timeout: Timeout in seconds
            env: Additional environment variables
            stream: Stream output in real-time
            shell: Use shell for command interpretation

        Returns:
            ExecutionResult with output and exit code
        """
        return self._executor.execute(command, timeout, env, stream, shell)

    def parse_test_results(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> TestResult:
        """
        Parse test output to extract results.

        Parsing priority:
        1. Structured JSON output (pytest-json-report, jest --json)
        2. Framework-specific regex patterns (pytest, jest, playwright, mocha, go)
        3. Generic patterns
        4. Fallback based on exit code (with warning)

        Args:
            output: Test command stdout/stderr
            exit_code: Command exit code
            json_output: Optional JSON output from structured reporters

        Returns:
            TestResult with parsed counts and metadata
        """
        return self._parser.parse(output, exit_code, json_output)

    # Expose internal methods for backward compatibility with tests
    def _execute_single(self, *args, **kwargs):
        return self._executor._execute_single(*args, **kwargs)

    def _execute_sequence(self, *args, **kwargs):
        return self._executor._execute_sequence(*args, **kwargs)

    def _execute_streaming(self, *args, **kwargs):
        return self._executor._execute_streaming(*args, **kwargs)

    def _execute_capture(self, *args, **kwargs):
        return self._executor._execute_capture(*args, **kwargs)

    def _stream_with_timeout(self, *args, **kwargs):
        return self._executor.stream_handler.stream_with_timeout(*args, **kwargs)

    @property
    def _output_buffer(self):
        return self._executor.stream_handler._output_buffer

    @_output_buffer.setter
    def _output_buffer(self, value):
        self._executor.stream_handler._output_buffer = value


class DockerExecutor(_DockerExecutor):
    """
    Executor for running commands inside Docker containers.

    This class extends the submodule's DockerExecutor to add
    the parse_test_results method for backward compatibility.
    """

    def parse_test_results(
        self,
        output: str,
        exit_code: int,
        json_output: Optional[str] = None,
    ) -> TestResult:
        """
        Parse test output to extract results.

        Delegates to TestResultAggregator for parsing logic.
        """
        parser = TestResultAggregator()
        return parser.parse(output, exit_code, json_output)

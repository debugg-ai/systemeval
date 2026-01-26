"""
Protocol definitions for E2E test generation providers.

This module defines the contracts that E2E providers must implement,
following Python's Protocol pattern for structural subtyping (duck typing
with type safety).

Protocols define WHAT providers must do, not HOW they do it. This allows
any implementation that satisfies the contract to be used interchangeably.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from .types import (
    ArtifactResult,
    ChangeSet,
    CompletionResult,
    E2EConfig,
    E2EResult,
    GenerationResult,
    StatusResult,
    ValidationResult,
)


@runtime_checkable
class E2EProvider(Protocol):
    """
    Protocol for E2E test generation providers.

    An E2E provider is responsible for generating end-to-end tests based on
    code changes. It handles the test generation lifecycle:
    1. Validate configuration
    2. Submit generation request
    3. Check generation status
    4. Download generated test artifacts

    This is a pure interface - no implementation details, no base class coupling.
    Any class that implements these methods can be used as an E2E provider.

    Example:
        class SurferProvider:
            def __init__(self, api_key: str, api_base_url: str) -> None:
                self.api_key = api_key
                self.api_base_url = api_base_url

            def generate_tests(
                self, changes: ChangeSet, config: E2EConfig
            ) -> GenerationResult:
                # Submit to Surfer API
                ...

            def get_status(self, run_id: str) -> StatusResult:
                # Check Surfer API status
                ...

            def download_artifacts(
                self, run_id: str, output_dir: Path
            ) -> ArtifactResult:
                # Download from Surfer API
                ...

            def validate_config(self, config: E2EConfig) -> ValidationResult:
                # Validate Surfer-specific config
                ...

        # Usage - no base class needed
        provider: E2EProvider = SurferProvider(api_key="...", api_base_url="...")
        result = provider.generate_tests(changes, config)
    """

    def generate_tests(self, changes: ChangeSet, config: E2EConfig) -> GenerationResult:
        """
        Generate E2E tests for the given code changes.

        This initiates the test generation process. It should:
        1. Submit the changes to the provider's backend
        2. Return immediately with a run_id for tracking
        3. Not block waiting for completion (use get_status for that)

        Args:
            changes: The code changes to generate tests for
            config: Configuration for test generation

        Returns:
            GenerationResult with run_id and initial status

        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If provider backend is unavailable
            TimeoutError: If submission times out

        Example:
            result = provider.generate_tests(changes, config)
            print(f"Generation started: {result.run_id}")
            # Later, check status with: provider.get_status(result.run_id)
        """
        ...

    def get_status(self, run_id: str) -> StatusResult:
        """
        Check the status of a test generation run.

        This queries the provider backend for the current status of a generation
        run. It should return immediately with the current state.

        Args:
            run_id: Unique identifier from generate_tests()

        Returns:
            StatusResult with current status, progress, and any errors

        Raises:
            KeyError: If run_id is not found
            RuntimeError: If provider backend is unavailable

        Example:
            status = provider.get_status("run_abc123")
            if status.status == GenerationStatus.COMPLETED:
                print(f"Generated {status.tests_generated} tests")
            elif status.status == GenerationStatus.FAILED:
                print(f"Failed: {status.error}")
        """
        ...

    def download_artifacts(self, run_id: str, output_dir: Path) -> ArtifactResult:
        """
        Download generated test artifacts.

        This downloads the generated test files from the provider backend
        to the specified output directory. Should only be called after
        generation is completed.

        Args:
            run_id: Unique identifier from generate_tests()
            output_dir: Where to write the test files (must exist)

        Returns:
            ArtifactResult with list of downloaded files and metadata

        Raises:
            KeyError: If run_id is not found
            ValueError: If generation is not completed yet
            RuntimeError: If provider backend is unavailable
            OSError: If output_dir doesn't exist or isn't writable

        Example:
            artifacts = provider.download_artifacts("run_abc123", Path("/tmp/tests"))
            print(f"Downloaded {len(artifacts.test_files)} test files")
            for test_file in artifacts.test_files:
                print(f"  - {test_file}")
        """
        ...

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        """
        Validate E2E configuration before generation.

        This performs provider-specific validation of the configuration.
        It should check:
        - Required fields are present
        - API credentials are valid
        - Project/URL is accessible
        - Framework/language combinations are supported

        This is a preflight check - it should not start generation.

        Args:
            config: Configuration to validate

        Returns:
            ValidationResult with validation status and any errors

        Example:
            validation = provider.validate_config(config)
            if not validation.valid:
                for error in validation.errors:
                    print(f"ERROR: {error}")
                for warning in validation.warnings:
                    print(f"WARNING: {warning}")
        """
        ...


@runtime_checkable
class E2EOrchestrator(Protocol):
    """
    Protocol for E2E test generation orchestration.

    An orchestrator coordinates the complete E2E test generation workflow:
    1. Analyze code changes from git
    2. Generate tests via a provider
    3. Wait for generation to complete
    4. Download test artifacts

    This is the high-level interface used by CLI commands and automation.
    It composes a provider with change analysis and completion polling.

    Example:
        class DefaultOrchestrator:
            def __init__(self, provider: E2EProvider) -> None:
                self.provider = provider

            def analyze_changes(
                self, repo_path: Path, base_ref: str, head_ref: str
            ) -> ChangeSet:
                # Run git diff and parse
                ...

            def run_e2e_flow(
                self, changes: ChangeSet, config: E2EConfig
            ) -> E2EResult:
                # Coordinate generation + polling + download
                ...

            def await_completion(
                self, run_id: str, timeout: int
            ) -> CompletionResult:
                # Poll until done or timeout
                ...

        # Usage
        orchestrator: E2EOrchestrator = DefaultOrchestrator(provider)
        changes = orchestrator.analyze_changes(
            Path("/repo"), "main", "feature-branch"
        )
        result = orchestrator.run_e2e_flow(changes, config)
    """

    def analyze_changes(
        self,
        repo_path: Path,
        base_ref: str,
        head_ref: str,
    ) -> ChangeSet:
        """
        Analyze code changes between two git references.

        This runs git diff and parses the results into a structured ChangeSet.
        It should:
        1. Validate that repo_path is a git repository
        2. Validate that base_ref and head_ref exist
        3. Run git diff between the refs
        4. Parse the diff into Change objects
        5. Return a complete ChangeSet

        Args:
            repo_path: Absolute path to git repository
            base_ref: Base git reference (commit SHA, branch, tag)
            head_ref: Head git reference (commit SHA, branch, tag)

        Returns:
            ChangeSet with all detected changes

        Raises:
            ValueError: If repo_path is not a git repo or refs don't exist
            RuntimeError: If git command fails

        Example:
            changes = orchestrator.analyze_changes(
                Path("/home/user/myproject"),
                "origin/main",
                "HEAD"
            )
            print(f"Found {changes.total_changes} changed files")
            print(f"  +{changes.total_additions} -{changes.total_deletions}")
        """
        ...

    def run_e2e_flow(self, changes: ChangeSet, config: E2EConfig) -> E2EResult:
        """
        Run the complete E2E test generation flow.

        This is the main entry point for E2E generation. It:
        1. Validates the configuration
        2. Generates tests via the provider
        3. Polls for completion (with timeout)
        4. Downloads artifacts if successful
        5. Returns comprehensive result

        This is a blocking operation that waits for generation to complete.

        Args:
            changes: Code changes to generate tests for
            config: Configuration for test generation

        Returns:
            E2EResult with complete generation outcome

        Example:
            result = orchestrator.run_e2e_flow(changes, config)
            if result.success:
                print(f"Generated {len(result.artifacts.test_files)} test files")
                for test_file in result.artifacts.test_files:
                    print(f"  - {test_file}")
            else:
                print(f"Failed: {result.error}")
        """
        ...

    def await_completion(self, run_id: str, timeout: int) -> CompletionResult:
        """
        Wait for test generation to complete.

        This polls the provider's get_status() until generation completes,
        fails, or the timeout is reached. It should:
        1. Poll at reasonable intervals (e.g., every 5 seconds)
        2. Return early if generation completes or fails
        3. Return with timed_out=True if timeout is reached
        4. Track total wait duration

        Args:
            run_id: Unique identifier from provider.generate_tests()
            timeout: Maximum seconds to wait (0 = no timeout)

        Returns:
            CompletionResult with final status and timing

        Example:
            completion = orchestrator.await_completion("run_abc123", timeout=300)
            if completion.completed and not completion.timed_out:
                print(f"Completed in {completion.duration_seconds:.1f}s")
            elif completion.timed_out:
                print(f"Timed out after {completion.duration_seconds:.1f}s")
            else:
                print(f"Failed: {completion.error}")
        """
        ...

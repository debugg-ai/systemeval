"""
Example implementations demonstrating the E2E provider interfaces.

These are reference implementations showing how to implement the protocols.
They serve as both documentation and starting points for real implementations.
"""

import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from .core.protocols import E2EOrchestrator, E2EProvider
from .core.types import (
    ArtifactResult,
    Change,
    ChangeSet,
    ChangeType,
    CompletionResult,
    E2EConfig,
    E2EResult,
    GenerationResult,
    GenerationStatus,
    StatusResult,
    ValidationResult,
)


# ============================================================================
# Example Provider Implementation
# ============================================================================


class MockE2EProvider:
    """
    Mock E2E provider for testing and demonstration.

    This is a complete implementation of the E2EProvider protocol that simulates
    test generation without calling real APIs. Useful for:
    - Testing orchestrator logic
    - Demonstrating the interface
    - Development without API dependencies
    - Integration testing
    """

    def __init__(
        self,
        api_key: str,
        api_base_url: str,
        simulate_delay: bool = True,
    ) -> None:
        """
        Initialize mock provider.

        Args:
            api_key: API key (validated but not used)
            api_base_url: Base URL (validated but not used)
            simulate_delay: Whether to simulate realistic delays
        """
        if not api_key:
            raise ValueError("api_key is required")
        if not api_base_url:
            raise ValueError("api_base_url is required")

        self.api_key = api_key
        self.api_base_url = api_base_url
        self.simulate_delay = simulate_delay

        # Track in-memory "runs"
        self._runs: Dict[str, Dict] = {}

    def generate_tests(self, changes: ChangeSet, config: E2EConfig) -> GenerationResult:
        """Simulate test generation."""
        # Validate config first
        validation = self.validate_config(config)
        if not validation.valid:
            raise ValueError(f"Invalid config: {validation.errors}")

        # Create run
        run_id = f"mock-{uuid.uuid4().hex[:12]}"

        # Calculate simulated test count based on changes
        test_count = len(changes.changes) * 2  # 2 tests per file

        # Store run state
        self._runs[run_id] = {
            "status": GenerationStatus.IN_PROGRESS,
            "changes": changes,
            "config": config,
            "tests_generated": 0,
            "target_tests": test_count,
            "created_at": time.time(),
        }

        return GenerationResult(
            run_id=run_id,
            status=GenerationStatus.IN_PROGRESS,
            message=f"Mock generation started for {changes.total_changes} changes",
            metadata={
                "provider": "mock",
                "target_tests": test_count,
            },
        )

    def get_status(self, run_id: str) -> StatusResult:
        """Check simulated generation status."""
        if run_id not in self._runs:
            raise KeyError(f"Run {run_id} not found")

        run = self._runs[run_id]
        current_status = run["status"]

        # Simulate progress over time
        if current_status == GenerationStatus.IN_PROGRESS:
            elapsed = time.time() - run["created_at"]

            # Complete after 10 seconds in simulation mode
            if self.simulate_delay and elapsed > 10:
                run["status"] = GenerationStatus.COMPLETED
                run["tests_generated"] = run["target_tests"]
                current_status = GenerationStatus.COMPLETED
            elif not self.simulate_delay:
                # Instant completion if delay disabled
                run["status"] = GenerationStatus.COMPLETED
                run["tests_generated"] = run["target_tests"]
                current_status = GenerationStatus.COMPLETED
            else:
                # Update progress
                progress = min(elapsed / 10.0, 0.99)
                run["tests_generated"] = int(run["target_tests"] * progress)

        # Build status result
        progress_percent = None
        if current_status == GenerationStatus.IN_PROGRESS:
            progress_percent = (run["tests_generated"] / run["target_tests"]) * 100

        completed_at = None
        if current_status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            completed_at = None  # Would be ISO timestamp in real implementation

        return StatusResult(
            run_id=run_id,
            status=current_status,
            message=f"Mock generation {current_status.value}",
            progress_percent=progress_percent,
            tests_generated=run["tests_generated"],
            completed_at=completed_at,
            metadata={
                "provider": "mock",
            },
        )

    def download_artifacts(self, run_id: str, output_dir: Path) -> ArtifactResult:
        """Simulate downloading test artifacts."""
        if run_id not in self._runs:
            raise KeyError(f"Run {run_id} not found")

        run = self._runs[run_id]

        # Check if completed
        if run["status"] != GenerationStatus.COMPLETED:
            raise ValueError(
                f"Cannot download artifacts: generation status is {run['status'].value}"
            )

        # Ensure output directory exists
        if not output_dir.exists():
            raise OSError(f"Output directory does not exist: {output_dir}")

        # Simulate creating test files
        test_files: list[Path] = []
        changes: ChangeSet = run["changes"]

        for i, change in enumerate(changes.changes):
            # Create mock test file
            test_file = output_dir / f"test_{Path(change.file_path).stem}_{i}.spec.ts"
            test_files.append(test_file)

            # Write mock test content
            mock_content = f"""// Mock E2E test generated for {change.file_path}
describe('{change.file_path}', () => {{
  it('should test change {change.change_type.value}', async () => {{
    // Mock test implementation
    expect(true).toBe(true);
  }});

  it('should test edge cases', async () => {{
    // Mock test implementation
    expect(true).toBe(true);
  }});
}});
"""
            test_file.write_text(mock_content)

        return ArtifactResult(
            run_id=run_id,
            output_directory=output_dir,
            test_files=test_files,
            total_tests=run["tests_generated"],
            total_size_bytes=sum(f.stat().st_size for f in test_files),
            metadata={
                "provider": "mock",
            },
        )

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        """Validate E2E configuration."""
        errors: list[str] = []
        warnings: list[str] = []

        # Check required fields
        if not config.project_url:
            errors.append("project_url is required")

        if not config.project_slug:
            warnings.append("project_slug not set, using default")

        # Check framework support
        supported_frameworks = ["playwright", "cypress", "selenium"]
        if config.test_framework not in supported_frameworks:
            errors.append(
                f"Unsupported test_framework: {config.test_framework}. "
                f"Supported: {supported_frameworks}"
            )

        # Check language support
        supported_languages = ["typescript", "javascript", "python"]
        if config.programming_language not in supported_languages:
            errors.append(
                f"Unsupported programming_language: {config.programming_language}. "
                f"Supported: {supported_languages}"
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metadata={
                "provider": "mock",
            },
        )


# ============================================================================
# Example Orchestrator Implementation
# ============================================================================


class BasicE2EOrchestrator:
    """
    Basic E2E orchestrator implementation.

    This orchestrator coordinates the full E2E workflow using a provider.
    It demonstrates the standard pattern for orchestration.
    """

    def __init__(self, provider: E2EProvider, poll_interval: int = 5) -> None:
        """
        Initialize orchestrator.

        Args:
            provider: E2E provider instance to use
            poll_interval: Seconds between status polls (default: 5)
        """
        self.provider = provider
        self.poll_interval = poll_interval

    def analyze_changes(
        self,
        repo_path: Path,
        base_ref: str,
        head_ref: str,
    ) -> ChangeSet:
        """
        Analyze changes between git refs.

        This is a simplified implementation. A real implementation would:
        1. Validate git repository
        2. Run git diff
        3. Parse diff output
        4. Handle binary files, renames, etc.
        """
        # Validate repository
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        git_dir = repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {repo_path}")

        # In a real implementation, we would run:
        # git diff --numstat base_ref..head_ref
        # and parse the output

        # For this example, create a mock changeset
        changes = [
            Change(
                file_path="src/api/users.py",
                change_type=ChangeType.MODIFIED,
                additions=15,
                deletions=3,
            ),
            Change(
                file_path="src/api/auth.py",
                change_type=ChangeType.MODIFIED,
                additions=8,
                deletions=2,
            ),
        ]

        return ChangeSet(
            base_ref=base_ref,
            head_ref=head_ref,
            changes=changes,
            repository_root=repo_path,
            metadata={
                "git_command": f"git diff {base_ref}..{head_ref}",
            },
        )

    def run_e2e_flow(self, changes: ChangeSet, config: E2EConfig) -> E2EResult:
        """
        Run complete E2E generation flow.

        This is the main orchestration method that coordinates all steps.
        """
        # Validate config
        validation = self.provider.validate_config(config)
        if not validation.valid:
            # Return early with validation errors
            error_msg = "; ".join(validation.errors)
            return E2EResult(
                changeset=changes,
                config=config,
                generation=GenerationResult(
                    run_id="",
                    status=GenerationStatus.FAILED,
                    message="Configuration validation failed",
                ),
                completion=CompletionResult(
                    run_id="",
                    status=GenerationStatus.FAILED,
                    completed=True,
                    timed_out=False,
                    error=error_msg,
                ),
                success=False,
                error=f"Configuration validation failed: {error_msg}",
                warnings=validation.warnings,
            )

        # Start generation
        try:
            generation = self.provider.generate_tests(changes, config)
        except Exception as e:
            return E2EResult(
                changeset=changes,
                config=config,
                generation=GenerationResult(
                    run_id="",
                    status=GenerationStatus.FAILED,
                    message=str(e),
                ),
                completion=CompletionResult(
                    run_id="",
                    status=GenerationStatus.FAILED,
                    completed=True,
                    timed_out=False,
                    error=str(e),
                ),
                success=False,
                error=f"Generation failed: {e}",
            )

        # Wait for completion
        completion = self.await_completion(
            generation.run_id,
            config.timeout_seconds,
        )

        # Download artifacts if successful
        artifacts: Optional[ArtifactResult] = None
        if completion.status == GenerationStatus.COMPLETED:
            try:
                # Ensure output directory exists
                output_dir = config.output_directory or config.project_root / "e2e_generated"
                output_dir.mkdir(parents=True, exist_ok=True)

                artifacts = self.provider.download_artifacts(
                    generation.run_id,
                    output_dir,
                )
            except Exception as e:
                completion.error = f"Artifact download failed: {e}"
                completion.status = GenerationStatus.FAILED

        # Build final result
        result = E2EResult(
            changeset=changes,
            config=config,
            generation=generation,
            completion=completion,
            artifacts=artifacts,
            warnings=validation.warnings,
        )

        # Finalize with success/failure
        success = (
            completion.status == GenerationStatus.COMPLETED
            and artifacts is not None
        )
        result.finalize(success=success, error=completion.error)

        return result

    def await_completion(self, run_id: str, timeout: int) -> CompletionResult:
        """
        Wait for generation to complete.

        Polls provider status until completion or timeout.
        """
        start_time = time.time()
        last_status: Optional[StatusResult] = None

        while True:
            # Check status
            try:
                last_status = self.provider.get_status(run_id)
            except Exception as e:
                # Status check failed
                return CompletionResult(
                    run_id=run_id,
                    status=GenerationStatus.FAILED,
                    completed=True,
                    timed_out=False,
                    duration_seconds=time.time() - start_time,
                    error=f"Status check failed: {e}",
                )

            # Check if completed
            if last_status.status in (
                GenerationStatus.COMPLETED,
                GenerationStatus.FAILED,
                GenerationStatus.CANCELLED,
            ):
                return CompletionResult(
                    run_id=run_id,
                    status=last_status.status,
                    completed=True,
                    timed_out=False,
                    duration_seconds=time.time() - start_time,
                    final_message=last_status.message,
                    error=last_status.error,
                    metadata=last_status.metadata,
                )

            # Check timeout
            elapsed = time.time() - start_time
            if timeout > 0 and elapsed >= timeout:
                return CompletionResult(
                    run_id=run_id,
                    status=last_status.status,
                    completed=False,
                    timed_out=True,
                    duration_seconds=elapsed,
                    final_message=f"Timed out after {elapsed:.1f}s",
                )

            # Wait before next poll
            time.sleep(self.poll_interval)


# ============================================================================
# Usage Examples
# ============================================================================


def example_usage() -> None:
    """
    Demonstrate how to use the E2E interfaces.

    This shows the complete workflow from provider creation to test generation.
    """
    # 1. Create provider instance with explicit configuration
    provider = MockE2EProvider(
        api_key="sk-test-key-12345",
        api_base_url="https://api.example.com",
        simulate_delay=False,  # Instant completion for example
    )

    # 2. Create orchestrator with provider
    orchestrator = BasicE2EOrchestrator(provider, poll_interval=2)

    # 3. Analyze changes from git
    repo_path = Path.cwd()
    changes = orchestrator.analyze_changes(
        repo_path=repo_path,
        base_ref="main",
        head_ref="HEAD",
    )

    print(f"Found {changes.total_changes} changes:")
    for change in changes.changes:
        print(f"  {change.change_type.value}: {change.file_path}")

    # 4. Configure E2E generation
    config = E2EConfig(
        provider_name="mock",
        project_root=repo_path,
        project_url="http://localhost:3000",
        project_slug="my-project",
        test_framework="playwright",
        programming_language="typescript",
        timeout_seconds=60,
    )

    # 5. Run E2E flow
    result = orchestrator.run_e2e_flow(changes, config)

    # 6. Check results
    if result.success:
        print(f"\nSuccess! Generated {len(result.artifacts.test_files)} test files:")
        for test_file in result.artifacts.test_files:
            print(f"  - {test_file}")
    else:
        print(f"\nFailed: {result.error}")


if __name__ == "__main__":
    example_usage()

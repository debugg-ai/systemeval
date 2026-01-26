"""
E2E Configuration Usage Examples

This module demonstrates correct usage of the E2E configuration system.

Design Principles:
------------------
1. No config discovery - config passed explicitly
2. No cascading fallbacks - single source of truth
3. No magic values - all values explicit
4. Fail fast - invalid config raises ValueError
"""
import yaml
from pathlib import Path
from typing import Dict, Any

from systemeval.e2e_config import (
    E2EConfig,
    DebuggAIProviderConfig,
    LocalProviderConfig,
    load_e2e_config_from_dict,
)
from systemeval.e2e_types import (
    E2EResult,
    GenerationResult,
    StatusResult,
    ArtifactResult,
    E2EFailure,
    Verdict,
)


# ============================================================================
# Example 1: Creating E2EConfig Programmatically
# ============================================================================


def example_create_debuggai_config() -> E2EConfig:
    """
    Example: Create DebuggAI E2E config programmatically.

    Best practice: Use factory method for type safety.
    """
    config = E2EConfig.for_debuggai(
        api_key="sk_live_your_api_key_here",
        api_url="https://api.debugg.ai",
        output_dir=Path("/tmp/e2e-output"),
        project_id="my-project",
        timeout_seconds=300,
        poll_interval_seconds=5,
    )

    # Validate provider config
    provider_config = config.get_provider_config()
    assert isinstance(provider_config, DebuggAIProviderConfig)

    print(f"Created DebuggAI config: {config.provider}")
    print(f"  API URL: {provider_config.api_url}")
    print(f"  Project: {provider_config.project_id}")
    print(f"  Output: {config.output_dir}")

    return config


def example_create_local_config() -> E2EConfig:
    """
    Example: Create local E2E config programmatically.

    Best practice: Use factory method for type safety.
    """
    config = E2EConfig.for_local(
        base_url="http://localhost:3000",
        output_dir=Path("/tmp/e2e-output"),
        timeout_seconds=60,
        poll_interval_seconds=2,
    )

    # Validate provider config
    provider_config = config.get_provider_config()
    assert isinstance(provider_config, LocalProviderConfig)

    print(f"Created local config: {config.provider}")
    print(f"  Base URL: {provider_config.base_url}")
    print(f"  Output: {config.output_dir}")

    return config


# ============================================================================
# Example 2: Loading E2EConfig from YAML
# ============================================================================


def example_load_from_yaml(config_path: Path) -> E2EConfig:
    """
    Example: Load E2E config from YAML file.

    CRITICAL: No config discovery. Caller must pass explicit path.

    Args:
        config_path: ABSOLUTE path to config file

    Best practice:
    - Caller explicitly reads config file
    - Caller is responsible for resolving config path
    - No searching cwd, no env vars, no magic
    """
    if not config_path.is_absolute():
        raise ValueError(f"Config path must be absolute: {config_path}")

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Caller explicitly reads config file
    with open(config_path) as f:
        raw_config = yaml.safe_load(f)

    # Then passes to loader
    config = load_e2e_config_from_dict(raw_config)

    print(f"Loaded config from: {config_path}")
    print(f"  Provider: {config.provider}")
    print(f"  Output: {config.output_dir}")

    return config


# ============================================================================
# Example 3: Creating E2EResult Objects
# ============================================================================


def example_create_successful_result() -> E2EResult:
    """
    Example: Create successful E2E test result.

    This demonstrates the full lifecycle of E2E test execution:
    1. Generation (submit test to provider)
    2. Status Polling (wait for completion)
    3. Artifact Collection (download results)
    4. Result Aggregation (compute verdict)
    """
    # Stage 1: Generation
    generation = GenerationResult(
        status="success",
        test_run_id="run_abc123",
        message="Test run created successfully",
        duration_seconds=0.5,
        metadata={"project_id": "my-project"},
    )

    # Stage 2: Status Polling
    status = StatusResult(
        status="completed",
        poll_count=5,
        duration_seconds=45.0,
        metadata={"execution_time": 43.2},
    )

    # Stage 3: Artifact Collection
    artifacts = ArtifactResult(
        status="success",
        artifacts_collected=[
            "/tmp/e2e/screenshot_1.png",
            "/tmp/e2e/video_1.webm",
            "/tmp/e2e/trace_1.json",
        ],
        total_size_bytes=1024 * 1024 * 5,  # 5MB
        duration_seconds=2.5,
    )

    # Aggregate into E2EResult
    result = E2EResult(
        test_run_id="run_abc123",
        provider="debuggai",
        passed=8,
        failed=0,
        errors=0,
        skipped=0,
        duration_seconds=48.0,
        generation=generation,
        status=status,
        artifacts=artifacts,
    )

    # Check verdict
    assert result.verdict == Verdict.PASS
    assert result.total == 8

    print(f"E2E Result: {result.verdict}")
    print(f"  Passed: {result.passed}/{result.total}")
    print(f"  Duration: {result.duration_seconds}s")

    return result


def example_create_failed_result() -> E2EResult:
    """
    Example: Create failed E2E test result with failures.

    Demonstrates how to capture test failures with E2E-specific details.
    """
    # Create failure with E2E-specific metadata
    failure = E2EFailure(
        test_id="e2e_login_test",
        test_name="User can log in successfully",
        message="Timeout waiting for login button",
        traceback="...",
        duration=30.0,
        screenshot_path="/tmp/e2e/screenshot_login_failed.png",
        video_path="/tmp/e2e/video_login_failed.webm",
        trace_path="/tmp/e2e/trace_login_failed.json",
        console_logs=[
            "ERROR: Failed to load authentication module",
            "WARNING: Token expired",
        ],
    )

    # Create result with failures
    result = E2EResult(
        test_run_id="run_xyz789",
        provider="debuggai",
        passed=5,
        failed=2,
        errors=0,
        skipped=1,
        duration_seconds=120.0,
        failures=[failure],
        generation=GenerationResult(status="success", test_run_id="run_xyz789"),
        status=StatusResult(status="completed", poll_count=10),
        artifacts=ArtifactResult(
            status="success",
            artifacts_collected=["/tmp/e2e/screenshot_login_failed.png"],
        ),
    )

    # Check verdict
    assert result.verdict == Verdict.FAIL
    assert len(result.failures) == 1

    print(f"E2E Result: {result.verdict}")
    print(f"  Passed: {result.passed}/{result.total}")
    print(f"  Failed: {result.failed}")
    print(f"  Failures:")
    for f in result.failures:
        print(f"    - {f.test_name}: {f.message}")

    return result


def example_create_error_result() -> E2EResult:
    """
    Example: Create error E2E result (generation failed).

    Use this factory for fatal errors that prevent test execution.
    """
    result = E2EResult.from_error(
        error_message="DebuggAI API authentication failed: Invalid API key",
        provider="debuggai",
    )

    # Check verdict
    assert result.verdict == Verdict.ERROR
    assert result.errors == 1

    print(f"E2E Result: {result.verdict}")
    print(f"  Error: {result.metadata['error']}")

    return result


def example_create_timeout_result() -> E2EResult:
    """
    Example: Create error E2E result (timeout during polling).

    Demonstrates handling of timeout scenarios.
    """
    generation = GenerationResult(
        status="success",
        test_run_id="run_timeout123",
    )

    status = StatusResult(
        status="running",
        poll_count=60,
        duration_seconds=300.0,
        timeout_exceeded=True,
        error="Timeout waiting for test completion after 300s",
    )

    result = E2EResult(
        test_run_id="run_timeout123",
        provider="debuggai",
        passed=0,
        failed=0,
        errors=1,
        skipped=0,
        duration_seconds=300.0,
        exit_code=2,
        generation=generation,
        status=status,
    )

    # Check verdict
    assert result.verdict == Verdict.ERROR

    print(f"E2E Result: {result.verdict}")
    print(f"  Timeout: {status.timeout_exceeded}")
    print(f"  Duration: {result.duration_seconds}s")

    return result


# ============================================================================
# Example 4: Converting to JSON
# ============================================================================


def example_serialize_to_json(result: E2EResult) -> Dict[str, Any]:
    """
    Example: Serialize E2EResult to JSON for CI/CD integration.

    Output format matches TestResult.to_dict() for consistency.
    """
    json_dict = result.to_dict()

    print("JSON Output:")
    print(f"  verdict: {json_dict['verdict']}")
    print(f"  total: {json_dict['total']}")
    print(f"  passed: {json_dict['passed']}")
    print(f"  failed: {json_dict['failed']}")
    print(f"  duration_seconds: {json_dict['duration_seconds']}")

    if "generation" in json_dict:
        print(f"  generation.status: {json_dict['generation']['status']}")

    if "status" in json_dict:
        print(f"  status.status: {json_dict['status']['status']}")

    if "artifacts" in json_dict:
        print(f"  artifacts.status: {json_dict['artifacts']['status']}")

    return json_dict


# ============================================================================
# Example 5: Validation Examples
# ============================================================================


def example_invalid_relative_path():
    """
    Example: Demonstrate validation failure for relative paths.

    CRITICAL: E2E config requires absolute paths - no cwd assumptions.
    """
    try:
        config = E2EConfig.for_debuggai(
            api_key="sk_live_key",
            api_url="https://api.debugg.ai",
            output_dir=Path("./output"),  # INVALID - relative path
        )
        print("ERROR: Should have raised ValueError")
    except ValueError as e:
        print(f"Validation correctly failed: {e}")
        assert "absolute path" in str(e).lower()


def example_invalid_api_url():
    """
    Example: Demonstrate validation failure for invalid API URL.

    CRITICAL: API URLs must be explicit HTTP/HTTPS - no magic values.
    """
    try:
        config = DebuggAIProviderConfig(
            api_key="sk_live_key",
            api_url="debugg.ai",  # INVALID - no http:// prefix
        )
        print("ERROR: Should have raised ValueError")
    except ValueError as e:
        print(f"Validation correctly failed: {e}")
        assert "http://" in str(e).lower()


def example_invalid_empty_api_key():
    """
    Example: Demonstrate validation failure for empty API key.

    CRITICAL: API keys must be non-empty strings.
    """
    try:
        config = DebuggAIProviderConfig(
            api_key="",  # INVALID - empty string
            api_url="https://api.debugg.ai",
        )
        print("ERROR: Should have raised ValueError")
    except Exception as e:
        print(f"Validation correctly failed: {e}")
        # Pydantic raises ValidationError with "at least 1 character" message
        assert "at least 1 character" in str(e).lower() or "cannot be empty" in str(e).lower()


# ============================================================================
# Main: Run All Examples
# ============================================================================


def main():
    """Run all examples."""
    print("=" * 70)
    print("E2E Configuration Examples")
    print("=" * 70)

    print("\n--- Example 1: Creating E2EConfig Programmatically ---")
    example_create_debuggai_config()
    example_create_local_config()

    print("\n--- Example 2: Loading E2EConfig from YAML ---")
    # Note: This requires actual config files to exist
    # example_load_from_yaml(Path("/path/to/e2e_config_debuggai.yaml"))

    print("\n--- Example 3: Creating E2EResult Objects ---")
    example_create_successful_result()
    example_create_failed_result()
    example_create_error_result()
    example_create_timeout_result()

    print("\n--- Example 4: Converting to JSON ---")
    result = example_create_successful_result()
    example_serialize_to_json(result)

    print("\n--- Example 5: Validation Examples ---")
    example_invalid_relative_path()
    example_invalid_api_url()
    example_invalid_empty_api_key()

    print("\n" + "=" * 70)
    print("All examples completed successfully")
    print("=" * 70)


if __name__ == "__main__":
    main()

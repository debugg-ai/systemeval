"""
Multi-project configuration models for systemeval v2.0.

This module contains Pydantic models for multi-project test orchestration:
- DefaultsConfig: Global default configuration values applied to all subprojects
- SubprojectConfig: Configuration for a single subproject in multi-project mode
- SubprojectResult: Result from running a single subproject's tests
- MultiProjectResult: Aggregated result from running multiple subprojects

V2.0 Multi-Project Support:
---------------------------
The v2.0 configuration adds hierarchical multi-project support where each
subproject represents an independent test suite that can use a different
test framework (pytest, vitest, playwright, jest).

Config Resolution Order (v2.0):
1. Subproject's own systemeval.yaml (if exists in subproject path)
2. Root config's subprojects[name] settings
3. Root config's defaults
"""
import re
import warnings
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DefaultsConfig(BaseModel):
    """
    Global default configuration values applied to all subprojects.

    These defaults are inherited by subprojects unless explicitly overridden
    in the subproject's own configuration.
    """
    timeout: int = Field(default=300, description="Default timeout in seconds for test execution")
    parallel: bool = Field(default=False, description="Run tests in parallel by default")
    coverage: bool = Field(default=False, description="Collect coverage by default")
    verbose: bool = Field(default=False, description="Verbose output by default")
    failfast: bool = Field(default=False, description="Stop on first failure by default")


class SubprojectConfig(BaseModel):
    """
    Configuration for a single subproject in multi-project mode.

    Each subproject represents an independent test suite that can use
    a different test framework (pytest, vitest, playwright, jest).

    Example:
        subprojects:
          - name: backend
            path: backend
            adapter: pytest
            env:
              DJANGO_SETTINGS_MODULE: config.settings.test
          - name: app
            path: app
            adapter: vitest
            pre_commands:
              - npm install
    """
    name: str = Field(..., description="Unique identifier for this subproject")
    path: str = Field(..., description="Relative path from project_root to subproject directory")
    adapter: str = Field(default="pytest", description="Test adapter to use (pytest, vitest, playwright, jest)")
    test_directory: Optional[str] = Field(default=None, description="Relative path to tests from subproject path")
    config_file: Optional[str] = Field(default=None, description="Path to adapter-specific config (vitest.config.ts, etc.)")
    enabled: bool = Field(default=True, description="Whether to run this subproject")
    tags: List[str] = Field(default_factory=list, description="Tags for filtering (unit, e2e, integration)")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables to set")
    pre_commands: List[str] = Field(default_factory=list, description="Commands to run before tests (npm install, etc.)")
    options: Dict[str, Any] = Field(default_factory=dict, description="Adapter-specific options (ignore paths, markers, etc.)")
    timeout: Optional[int] = Field(default=None, description="Override default timeout for this subproject")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate subproject name is a valid identifier."""
        if not v or not v.strip():
            raise ValueError("Subproject name cannot be empty")
        # Allow alphanumeric, hyphens, underscores
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', v):
            raise ValueError(
                f"Subproject name '{v}' must start with a letter and contain only "
                "letters, numbers, hyphens, and underscores"
            )
        return v

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, v: str) -> str:
        """Validate adapter name against known adapters."""
        # Known adapters (both current and planned)
        known_adapters = {
            "pytest", "pytest-django", "vitest", "jest",
            "playwright", "pipeline", "surfer"
        }
        if v not in known_adapters:
            # Don't fail hard - allow for future adapters
            warnings.warn(f"Unknown adapter '{v}'. Known adapters: {known_adapters}")
        return v


class SubprojectResult(BaseModel):
    """
    Result from running a single subproject's tests.

    Used for aggregated reporting in multi-project mode.
    """
    name: str = Field(..., description="Subproject name")
    adapter: str = Field(..., description="Adapter used")
    passed: int = Field(default=0, description="Number of passed tests")
    failed: int = Field(default=0, description="Number of failed tests")
    errors: int = Field(default=0, description="Number of test errors")
    skipped: int = Field(default=0, description="Number of skipped tests")
    status: Literal["PASS", "FAIL", "ERROR", "SKIP"] = Field(default="SKIP", description="Overall status")
    duration: float = Field(default=0.0, description="Duration in seconds")
    failures: List[Dict[str, Any]] = Field(default_factory=list, description="Failure details")
    error_message: Optional[str] = Field(default=None, description="Error message if status is ERROR")


class MultiProjectResult(BaseModel):
    """
    Aggregated result from running multiple subprojects.

    Provides unified summary for CI/CD integration.
    """
    verdict: Literal["PASS", "FAIL", "ERROR"] = Field(default="PASS", description="Overall verdict")
    subprojects: List[SubprojectResult] = Field(default_factory=list, description="Per-subproject results")
    total_passed: int = Field(default=0, description="Total passed tests across all subprojects")
    total_failed: int = Field(default=0, description="Total failed tests across all subprojects")
    total_errors: int = Field(default=0, description="Total errors across all subprojects")
    total_skipped: int = Field(default=0, description="Total skipped tests across all subprojects")
    total_duration: float = Field(default=0.0, description="Total duration in seconds")

    def calculate_totals(self) -> None:
        """Calculate totals from subproject results."""
        self.total_passed = sum(s.passed for s in self.subprojects)
        self.total_failed = sum(s.failed for s in self.subprojects)
        self.total_errors = sum(s.errors for s in self.subprojects)
        self.total_skipped = sum(s.skipped for s in self.subprojects)
        self.total_duration = sum(s.duration for s in self.subprojects)

        # Determine overall verdict
        if any(s.status == "ERROR" for s in self.subprojects):
            self.verdict = "ERROR"
        elif any(s.status == "FAIL" for s in self.subprojects):
            self.verdict = "FAIL"
        else:
            self.verdict = "PASS"

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary for CI output."""
        return {
            "verdict": self.verdict,
            "total_passed": self.total_passed,
            "total_failed": self.total_failed,
            "total_errors": self.total_errors,
            "total_skipped": self.total_skipped,
            "total_duration_seconds": round(self.total_duration, 3),
            "subprojects": [
                {
                    "name": s.name,
                    "adapter": s.adapter,
                    "passed": s.passed,
                    "failed": s.failed,
                    "errors": s.errors,
                    "skipped": s.skipped,
                    "status": s.status,
                    "duration_seconds": round(s.duration, 3),
                    "failures": s.failures if s.failures else None,
                    "error_message": s.error_message,
                }
                for s in self.subprojects
            ],
        }

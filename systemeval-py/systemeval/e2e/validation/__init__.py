"""
E2E configuration validation.

This module provides comprehensive validation for E2E configurations,
following systemeval's strict architectural principles:
- No magic values - all validation explicit
- Fail fast - return all errors, not just the first
- Clear error messages - actionable feedback
- Provider-specific validation - different providers have different requirements
"""

from ..core.types import E2EConfig, ValidationResult
from .base import (
    SUPPORTED_TEST_FRAMEWORKS,
    SUPPORTED_LANGUAGES,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    PROVIDERS_REQUIRING_API_KEY,
)
from .composite_validator import E2EConfigValidator


# ============================================================================
# Convenience Functions
# ============================================================================


def validate_e2e_config(
    config: E2EConfig,
    strict_mode: bool = False,
    check_paths: bool = True,
) -> ValidationResult:
    """
    Convenience function to validate an E2E configuration.

    Args:
        config: E2E configuration to validate
        strict_mode: If True, treat warnings as errors
        check_paths: If True, verify paths exist and are writable

    Returns:
        ValidationResult with validation status and any errors/warnings

    Example:
        result = validate_e2e_config(config)
        if not result.valid:
            raise ValueError(f"Invalid config: {result.errors}")
    """
    validator = E2EConfigValidator(
        strict_mode=strict_mode,
        check_paths=check_paths,
    )
    return validator.validate(config)


def quick_validate(config: E2EConfig) -> bool:
    """
    Quick validation that returns True/False only.

    Useful for simple checks where you don't need detailed errors.

    Args:
        config: E2E configuration to validate

    Returns:
        True if configuration is valid, False otherwise
    """
    result = validate_e2e_config(config, strict_mode=False, check_paths=False)
    return result.valid


__all__ = [
    "E2EConfigValidator",
    "validate_e2e_config",
    "quick_validate",
    "SUPPORTED_TEST_FRAMEWORKS",
    "SUPPORTED_LANGUAGES",
    "PROVIDERS_REQUIRING_API_KEY",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
]

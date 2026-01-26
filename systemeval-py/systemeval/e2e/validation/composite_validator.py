"""
Composite E2E configuration validator.

This module provides the main E2EConfigValidator that orchestrates
all validation checks.
"""

from typing import List

from ..core.types import E2EConfig, ValidationResult
from .base import BaseE2EValidator, PROVIDERS_REQUIRING_API_KEY
from .debuggai_validator import DebuggAIValidator


class E2EConfigValidator:
    """
    Validates E2E configurations comprehensively.

    This validator checks:
    - Required fields (provider_name, project_root)
    - Provider-specific requirements (api_key for debuggai)
    - Path validation (project_root exists, output_directory writable)
    - URL validation (api_base_url, project_url formats)
    - Timeout bounds (reasonable ranges)
    - Test framework compatibility

    Usage:
        validator = E2EConfigValidator()
        result = validator.validate(config)
        if not result.valid:
            for error in result.errors:
                print(f"ERROR: {error}")
            for warning in result.warnings:
                print(f"WARNING: {warning}")
    """

    def __init__(
        self,
        strict_mode: bool = False,
        check_paths: bool = True,
        check_connectivity: bool = False,
    ) -> None:
        """
        Initialize the validator.

        Args:
            strict_mode: If True, treat warnings as errors
            check_paths: If True, verify paths exist and are writable
            check_connectivity: If True, attempt to verify API connectivity
        """
        self._strict_mode = strict_mode
        self._check_paths = check_paths
        self._check_connectivity = check_connectivity
        self._base_validator = BaseE2EValidator(strict_mode, check_paths)
        self._debuggai_validator = DebuggAIValidator()

    def validate(self, config: E2EConfig) -> ValidationResult:
        """
        Perform full validation on E2E configuration.

        This runs all validation checks and returns a comprehensive result.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Run all validation methods
        required_result = self._base_validator.validate_required_fields(config)
        errors.extend(required_result.errors)
        warnings.extend(required_result.warnings)

        provider_result = self.validate_provider_config(config)
        errors.extend(provider_result.errors)
        warnings.extend(provider_result.warnings)

        paths_result = self._base_validator.validate_paths(config)
        errors.extend(paths_result.errors)
        warnings.extend(paths_result.warnings)

        urls_result = self._base_validator.validate_urls(config)
        errors.extend(urls_result.errors)
        warnings.extend(urls_result.warnings)

        timeout_result = self._base_validator.validate_timeouts(config)
        errors.extend(timeout_result.errors)
        warnings.extend(timeout_result.warnings)

        framework_result = self._base_validator.validate_test_framework(config)
        errors.extend(framework_result.errors)
        warnings.extend(framework_result.warnings)

        # In strict mode, warnings become errors
        if self._strict_mode:
            errors.extend(warnings)
            warnings = []

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            metadata={
                "strict_mode": self._strict_mode,
                "check_paths": self._check_paths,
                "check_connectivity": self._check_connectivity,
            },
        )

    def validate_provider_config(self, config: E2EConfig) -> ValidationResult:
        """
        Validate provider-specific configuration requirements.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for provider-specific checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        provider = config.provider_name.lower() if config.provider_name else ""

        # Check API key requirement for specific providers
        if provider in PROVIDERS_REQUIRING_API_KEY:
            if not config.api_key:
                errors.append(
                    f"api_key is required for provider '{config.provider_name}'"
                )
            elif not config.api_key.strip():
                errors.append("api_key cannot be whitespace only")

        # Provider-specific validations
        if provider == "debuggai":
            result = self._debuggai_validator.validate(config)
            errors.extend(result.errors)
            warnings.extend(result.warnings)
        elif provider == "surfer":
            result = self._validate_surfer_config(config)
            errors.extend(result.errors)
            warnings.extend(result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_surfer_config(self, config: E2EConfig) -> ValidationResult:
        """Validate Surfer-specific configuration."""
        errors: List[str] = []
        warnings: List[str] = []

        # api_base_url is required for Surfer
        if not config.api_base_url:
            errors.append("api_base_url is required for Surfer provider")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ========================================================================
    # Backward Compatibility Delegation Methods
    # ========================================================================
    # After Phase 2 reorganization, validation methods were moved to
    # BaseE2EValidator. These delegation methods maintain backward
    # compatibility for tests expecting direct method access.

    def validate_required_fields(self, config: E2EConfig) -> ValidationResult:
        """Delegate to base validator (backward compatibility)."""
        return self._base_validator.validate_required_fields(config)

    def validate_paths(self, config: E2EConfig) -> ValidationResult:
        """Delegate to base validator (backward compatibility)."""
        return self._base_validator.validate_paths(config)

    def validate_urls(self, config: E2EConfig) -> ValidationResult:
        """Delegate to base validator (backward compatibility)."""
        return self._base_validator.validate_urls(config)

    def validate_timeouts(self, config: E2EConfig) -> ValidationResult:
        """Delegate to base validator (backward compatibility)."""
        return self._base_validator.validate_timeouts(config)

    def validate_test_framework(self, config: E2EConfig) -> ValidationResult:
        """Delegate to base validator (backward compatibility)."""
        return self._base_validator.validate_test_framework(config)


__all__ = ["E2EConfigValidator"]

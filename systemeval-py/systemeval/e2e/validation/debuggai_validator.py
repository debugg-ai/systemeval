"""
DebuggAI-specific validation for E2E configurations.

This module provides validation logic specific to the DebuggAI provider.
"""

from typing import List

from ..core.types import E2EConfig, ValidationResult


class DebuggAIValidator:
    """
    Validator for DebuggAI-specific configuration.

    Checks DebuggAI requirements and compatibility.
    """

    def validate(self, config: E2EConfig) -> ValidationResult:
        """
        Validate DebuggAI-specific configuration.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult with DebuggAI-specific checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        # project_url is required for DebuggAI
        if not config.project_url:
            errors.append("project_url is required for DebuggAI provider")

        # Warn about unsupported frameworks
        if config.test_framework not in {"playwright", "cypress", "selenium"}:
            warnings.append(
                f"test_framework '{config.test_framework}' may not be fully supported "
                f"by DebuggAI. Recommended: playwright, cypress, selenium"
            )

        # Warn about unsupported languages
        if config.programming_language not in {"typescript", "javascript", "python"}:
            warnings.append(
                f"programming_language '{config.programming_language}' may not be fully "
                f"supported by DebuggAI. Recommended: typescript, javascript, python"
            )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


__all__ = ["DebuggAIValidator"]

"""
Base validation for E2E configurations.

This module provides base validation logic and constants.
"""

import os
import re
from pathlib import Path
from typing import List, Set, Tuple

from ..core.types import E2EConfig, ValidationResult


# ============================================================================
# Constants
# ============================================================================

# Supported test frameworks
SUPPORTED_TEST_FRAMEWORKS: Set[str] = {
    "playwright",
    "cypress",
    "selenium",
    "puppeteer",
    "webdriverio",
}

# Supported programming languages
SUPPORTED_LANGUAGES: Set[str] = {
    "typescript",
    "javascript",
    "python",
    "java",
    "csharp",
}

# Timeout bounds (in seconds)
MIN_TIMEOUT_SECONDS: int = 1
MAX_TIMEOUT_SECONDS: int = 3600  # 1 hour

# Providers that require API keys
PROVIDERS_REQUIRING_API_KEY: Set[str] = {
    "debuggai",
    "surfer",
}

# URL regex pattern for validation
URL_PATTERN = re.compile(
    r"^https?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
    r"localhost|"  # localhost
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)?$",  # path
    re.IGNORECASE,
)


# ============================================================================
# Base Validator
# ============================================================================


class BaseE2EValidator:
    """
    Base validator for E2E configurations.

    Provides common validation methods used by specific validators.
    """

    def __init__(
        self,
        strict_mode: bool = False,
        check_paths: bool = True,
    ) -> None:
        """
        Initialize the validator.

        Args:
            strict_mode: If True, treat warnings as errors
            check_paths: If True, verify paths exist and are writable
        """
        self._strict_mode = strict_mode
        self._check_paths = check_paths

    def validate_required_fields(self, config: E2EConfig) -> ValidationResult:
        """
        Validate required fields are present and non-empty.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for required fields check
        """
        errors: List[str] = []
        warnings: List[str] = []

        # provider_name is required
        if not config.provider_name:
            errors.append("provider_name is required and cannot be empty")
        elif not config.provider_name.strip():
            errors.append("provider_name cannot be whitespace only")

        # project_root is validated at dataclass level (must be absolute)
        # We just check it exists if path checking is enabled
        if self._check_paths and not config.project_root.exists():
            errors.append(f"project_root does not exist: {config.project_root}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_paths(self, config: E2EConfig) -> ValidationResult:
        """
        Validate path configuration.

        Checks:
        - project_root exists and is a directory
        - output_directory is writable (parent exists)

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for path checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not self._check_paths:
            return ValidationResult(valid=True, errors=[], warnings=[])

        # Validate project_root
        if not config.project_root.exists():
            errors.append(f"project_root does not exist: {config.project_root}")
        elif not config.project_root.is_dir():
            errors.append(f"project_root is not a directory: {config.project_root}")

        # Validate output_directory
        if config.output_directory:
            if config.output_directory.exists():
                if not config.output_directory.is_dir():
                    errors.append(
                        f"output_directory exists but is not a directory: "
                        f"{config.output_directory}"
                    )
                elif not self._is_writable(config.output_directory):
                    errors.append(
                        f"output_directory is not writable: {config.output_directory}"
                    )
            else:
                # Check if parent directory exists and is writable
                parent = config.output_directory.parent
                if not parent.exists():
                    warnings.append(
                        f"output_directory parent does not exist: {parent}. "
                        f"It will be created during test generation."
                    )
                elif not self._is_writable(parent):
                    errors.append(
                        f"output_directory parent is not writable: {parent}"
                    )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _is_writable(self, path: Path) -> bool:
        """Check if a path is writable."""
        try:
            return os.access(path, os.W_OK)
        except (OSError, PermissionError):
            return False

    def validate_urls(self, config: E2EConfig) -> ValidationResult:
        """
        Validate URL configuration.

        Checks:
        - api_base_url format (if provided)
        - project_url format (if provided)

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for URL checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Validate api_base_url
        if config.api_base_url:
            if not self._is_valid_url(config.api_base_url):
                errors.append(
                    f"api_base_url is not a valid URL: {config.api_base_url}. "
                    f"Must start with http:// or https://"
                )
            elif config.api_base_url.endswith("/"):
                warnings.append(
                    "api_base_url has trailing slash which may cause issues"
                )

        # Validate project_url
        if config.project_url:
            if not self._is_valid_url(config.project_url):
                errors.append(
                    f"project_url is not a valid URL: {config.project_url}. "
                    f"Must start with http:// or https://"
                )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _is_valid_url(self, url: str) -> bool:
        """Check if a string is a valid URL."""
        if not url:
            return False
        return bool(URL_PATTERN.match(url))

    def validate_timeouts(self, config: E2EConfig) -> ValidationResult:
        """
        Validate timeout configuration.

        Checks:
        - timeout_seconds is within reasonable bounds

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for timeout checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        # timeout_seconds bounds
        if config.timeout_seconds < MIN_TIMEOUT_SECONDS:
            errors.append(
                f"timeout_seconds must be at least {MIN_TIMEOUT_SECONDS}, "
                f"got {config.timeout_seconds}"
            )
        elif config.timeout_seconds > MAX_TIMEOUT_SECONDS:
            errors.append(
                f"timeout_seconds must be at most {MAX_TIMEOUT_SECONDS}, "
                f"got {config.timeout_seconds}"
            )
        elif config.timeout_seconds < 30:
            warnings.append(
                f"timeout_seconds of {config.timeout_seconds} is very short. "
                f"E2E test generation typically takes 1-5 minutes."
            )
        elif config.timeout_seconds > 1800:
            warnings.append(
                f"timeout_seconds of {config.timeout_seconds} is very long (> 30 min). "
                f"Consider if this is intentional."
            )

        # max_tests validation
        if config.max_tests is not None:
            if config.max_tests <= 0:
                errors.append(f"max_tests must be positive, got {config.max_tests}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_test_framework(self, config: E2EConfig) -> ValidationResult:
        """
        Validate test framework and language compatibility.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult for framework checks
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Check if test_framework is supported
        if config.test_framework not in SUPPORTED_TEST_FRAMEWORKS:
            warnings.append(
                f"test_framework '{config.test_framework}' is not in the standard list. "
                f"Supported: {', '.join(sorted(SUPPORTED_TEST_FRAMEWORKS))}"
            )

        # Check if programming_language is supported
        if config.programming_language not in SUPPORTED_LANGUAGES:
            warnings.append(
                f"programming_language '{config.programming_language}' is not in the "
                f"standard list. Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )

        # Check framework/language compatibility
        compatible, reason = self._check_framework_language_compatibility(
            config.test_framework, config.programming_language
        )
        if not compatible:
            warnings.append(reason)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _check_framework_language_compatibility(
        self, framework: str, language: str
    ) -> Tuple[bool, str]:
        """
        Check if test framework and programming language are compatible.

        Returns:
            Tuple of (is_compatible, reason_if_not)
        """
        # Define common compatibility rules
        compatibility_matrix = {
            "playwright": {"typescript", "javascript", "python", "java", "csharp"},
            "cypress": {"typescript", "javascript"},
            "selenium": {"python", "java", "csharp", "javascript"},
            "puppeteer": {"typescript", "javascript"},
            "webdriverio": {"typescript", "javascript"},
        }

        if framework not in compatibility_matrix:
            # Unknown framework, assume compatible
            return True, ""

        supported_languages = compatibility_matrix[framework]
        if language not in supported_languages:
            return (
                False,
                f"test_framework '{framework}' does not typically support "
                f"'{language}'. Supported languages: {', '.join(sorted(supported_languages))}"
            )

        return True, ""


__all__ = [
    "BaseE2EValidator",
    "SUPPORTED_TEST_FRAMEWORKS",
    "SUPPORTED_LANGUAGES",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "PROVIDERS_REQUIRING_API_KEY",
]

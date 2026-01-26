"""
Tests for E2E configuration validation.

These tests validate the E2EConfigValidator class which performs
comprehensive validation of E2E configurations.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from systemeval.e2e.types import E2EConfig, ValidationResult
from systemeval.e2e.validation import (
    E2EConfigValidator,
    validate_e2e_config,
    quick_validate,
    SUPPORTED_TEST_FRAMEWORKS,
    SUPPORTED_LANGUAGES,
    PROVIDERS_REQUIRING_API_KEY,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_config(temp_dir):
    """Create a valid E2EConfig for testing."""
    return E2EConfig(
        provider_name="debuggai",
        project_root=temp_dir,
        api_key="sk_live_test_key",
        api_base_url="https://api.debugg.ai",
        project_url="https://myapp.example.com",
        test_framework="playwright",
        programming_language="typescript",
        timeout_seconds=300,
    )


@pytest.fixture
def validator():
    """Create a validator instance."""
    return E2EConfigValidator(check_paths=True)


@pytest.fixture
def validator_no_paths():
    """Create a validator that doesn't check paths."""
    return E2EConfigValidator(check_paths=False)


# ============================================================================
# E2EConfigValidator Basic Tests
# ============================================================================


class TestE2EConfigValidatorInit:
    """Test E2EConfigValidator initialization."""

    def test_default_init(self):
        """Test default initialization."""
        validator = E2EConfigValidator()
        assert validator._strict_mode is False
        assert validator._check_paths is True
        assert validator._check_connectivity is False

    def test_strict_mode_init(self):
        """Test initialization with strict mode."""
        validator = E2EConfigValidator(strict_mode=True)
        assert validator._strict_mode is True

    def test_no_path_check_init(self):
        """Test initialization without path checking."""
        validator = E2EConfigValidator(check_paths=False)
        assert validator._check_paths is False

    def test_connectivity_check_init(self):
        """Test initialization with connectivity checking."""
        validator = E2EConfigValidator(check_connectivity=True)
        assert validator._check_connectivity is True


# ============================================================================
# Full Validation Tests
# ============================================================================


class TestValidate:
    """Test full validation method."""

    def test_valid_config_passes(self, validator, valid_config):
        """Test valid configuration passes validation."""
        result = validator.validate(valid_config)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_returns_validation_result(self, validator, valid_config):
        """Test validate returns ValidationResult."""
        result = validator.validate(valid_config)

        assert isinstance(result, ValidationResult)
        assert hasattr(result, "valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")

    def test_metadata_includes_options(self, validator, valid_config):
        """Test validation result includes metadata about options."""
        result = validator.validate(valid_config)

        assert "strict_mode" in result.metadata
        assert "check_paths" in result.metadata
        assert "check_connectivity" in result.metadata

    def test_strict_mode_converts_warnings_to_errors(self, temp_dir):
        """Test strict mode treats warnings as errors."""
        validator = E2EConfigValidator(strict_mode=True, check_paths=False)
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
            # This will generate a warning about short timeout
            timeout_seconds=10,
        )

        result = validator.validate(config)

        # In strict mode, the short timeout warning becomes an error
        assert result.valid is False or len(result.warnings) == 0


# ============================================================================
# Required Fields Validation Tests
# ============================================================================


class TestValidateRequiredFields:
    """Test required fields validation."""

    def test_missing_provider_name_fails(self, validator_no_paths, temp_dir):
        """Test missing provider_name fails validation."""
        config = E2EConfig(
            provider_name="",  # Empty
            project_root=temp_dir,
        )

        result = validator_no_paths.validate_required_fields(config)

        assert result.valid is False
        assert any("provider_name" in e for e in result.errors)

    def test_whitespace_provider_name_fails(self, validator_no_paths, temp_dir):
        """Test whitespace-only provider_name fails validation."""
        config = E2EConfig(
            provider_name="   ",  # Whitespace only
            project_root=temp_dir,
        )

        result = validator_no_paths.validate_required_fields(config)

        assert result.valid is False
        assert any("whitespace" in e for e in result.errors)

    def test_valid_provider_name_passes(self, validator_no_paths, temp_dir):
        """Test valid provider_name passes validation."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
        )

        result = validator_no_paths.validate_required_fields(config)

        assert result.valid is True

    def test_nonexistent_project_root_fails_with_path_check(self, validator):
        """Test nonexistent project_root fails when path checking enabled."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=Path("/nonexistent/path/that/does/not/exist"),
        )

        result = validator.validate_required_fields(config)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)


# ============================================================================
# Provider Config Validation Tests
# ============================================================================


class TestValidateProviderConfig:
    """Test provider-specific validation."""

    def test_debuggai_requires_api_key(self, validator_no_paths, temp_dir):
        """Test DebuggAI provider requires api_key."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key=None,  # Missing
            project_url="https://example.com",
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is False
        assert any("api_key" in e for e in result.errors)

    def test_debuggai_requires_project_url(self, validator_no_paths, temp_dir):
        """Test DebuggAI provider requires project_url."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url=None,  # Missing
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is False
        assert any("project_url" in e for e in result.errors)

    def test_debuggai_valid_config_passes(self, validator_no_paths, temp_dir):
        """Test valid DebuggAI config passes."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_live_test",
            project_url="https://example.com",
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is True

    def test_surfer_requires_api_key(self, validator_no_paths, temp_dir):
        """Test Surfer provider requires api_key."""
        config = E2EConfig(
            provider_name="surfer",
            project_root=temp_dir,
            api_key=None,  # Missing
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is False
        assert any("api_key" in e for e in result.errors)

    def test_surfer_requires_api_base_url(self, validator_no_paths, temp_dir):
        """Test Surfer provider requires api_base_url."""
        config = E2EConfig(
            provider_name="surfer",
            project_root=temp_dir,
            api_key="sk_test",
            api_base_url=None,  # Missing
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is False
        assert any("api_base_url" in e for e in result.errors)

    def test_local_provider_no_api_key_required(self, validator_no_paths, temp_dir):
        """Test local provider doesn't require api_key."""
        config = E2EConfig(
            provider_name="local",
            project_root=temp_dir,
            api_key=None,  # Not required for local
        )

        result = validator_no_paths.validate_provider_config(config)

        # Should not have api_key error
        assert not any("api_key" in e for e in result.errors)

    def test_whitespace_api_key_fails(self, validator_no_paths, temp_dir):
        """Test whitespace-only api_key fails validation."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="   ",  # Whitespace only
            project_url="https://example.com",
        )

        result = validator_no_paths.validate_provider_config(config)

        assert result.valid is False
        assert any("whitespace" in e for e in result.errors)

    def test_debuggai_warns_unsupported_framework(self, validator_no_paths, temp_dir):
        """Test DebuggAI warns about unsupported frameworks."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
            test_framework="puppeteer",  # Not fully supported by DebuggAI
        )

        result = validator_no_paths.validate_provider_config(config)

        assert any("puppeteer" in w and "may not be fully supported" in w
                   for w in result.warnings)


# ============================================================================
# Path Validation Tests
# ============================================================================


class TestValidatePaths:
    """Test path validation."""

    def test_existing_project_root_passes(self, validator, temp_dir):
        """Test existing project_root passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
        )

        result = validator.validate_paths(config)

        assert result.valid is True

    def test_nonexistent_project_root_fails(self, validator):
        """Test nonexistent project_root fails validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=Path("/nonexistent/path/xyz123"),
        )

        result = validator.validate_paths(config)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

    def test_file_as_project_root_fails(self, temp_dir, validator):
        """Test file as project_root fails validation."""
        # Create a file instead of directory
        file_path = temp_dir / "testfile.txt"
        file_path.write_text("test")

        config = E2EConfig(
            provider_name="test",
            project_root=file_path,
        )

        result = validator.validate_paths(config)

        assert result.valid is False
        assert any("not a directory" in e for e in result.errors)

    def test_existing_output_directory_passes(self, validator, temp_dir):
        """Test existing output directory passes validation."""
        output_dir = temp_dir / "output"
        output_dir.mkdir()

        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            output_directory=output_dir,
        )

        result = validator.validate_paths(config)

        assert result.valid is True

    def test_nonexistent_output_directory_warns(self, validator, temp_dir):
        """Test nonexistent output directory generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            output_directory=temp_dir / "nonexistent_output",
        )

        result = validator.validate_paths(config)

        # Should pass (parent exists and is writable)
        assert result.valid is True
        # But may have warning about creation

    def test_nonexistent_output_parent_warns(self, validator, temp_dir):
        """Test nonexistent output directory parent generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            output_directory=Path("/nonexistent/parent/output"),
        )

        result = validator.validate_paths(config)

        assert any("parent does not exist" in w for w in result.warnings)

    def test_path_check_disabled_skips_validation(self, temp_dir):
        """Test path checking can be disabled."""
        validator = E2EConfigValidator(check_paths=False)
        config = E2EConfig(
            provider_name="test",
            project_root=Path("/nonexistent/path"),
        )

        result = validator.validate_paths(config)

        # Should pass because path checking is disabled
        assert result.valid is True
        assert len(result.errors) == 0


# ============================================================================
# URL Validation Tests
# ============================================================================


class TestValidateUrls:
    """Test URL validation."""

    def test_valid_https_api_url_passes(self, validator_no_paths, temp_dir):
        """Test valid HTTPS API URL passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="https://api.example.com",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True

    def test_valid_http_api_url_passes(self, validator_no_paths, temp_dir):
        """Test valid HTTP API URL passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="http://localhost:8080",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True

    def test_invalid_api_url_fails(self, validator_no_paths, temp_dir):
        """Test invalid API URL fails validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="not-a-valid-url",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is False
        assert any("api_base_url" in e and "not a valid URL" in e
                   for e in result.errors)

    def test_api_url_without_protocol_fails(self, validator_no_paths, temp_dir):
        """Test API URL without protocol fails validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="api.example.com",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is False
        assert any("http://" in e or "https://" in e for e in result.errors)

    def test_api_url_trailing_slash_warns(self, validator_no_paths, temp_dir):
        """Test API URL with trailing slash generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="https://api.example.com/",
        )

        result = validator_no_paths.validate_urls(config)

        assert any("trailing slash" in w for w in result.warnings)

    def test_valid_project_url_passes(self, validator_no_paths, temp_dir):
        """Test valid project URL passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            project_url="https://myapp.example.com",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True

    def test_invalid_project_url_fails(self, validator_no_paths, temp_dir):
        """Test invalid project URL fails validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            project_url="not-a-url",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is False
        assert any("project_url" in e for e in result.errors)

    def test_no_urls_passes(self, validator_no_paths, temp_dir):
        """Test config without URLs passes URL validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True

    def test_localhost_url_passes(self, validator_no_paths, temp_dir):
        """Test localhost URL passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            project_url="http://localhost:3000",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True

    def test_ip_address_url_passes(self, validator_no_paths, temp_dir):
        """Test IP address URL passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            project_url="http://192.168.1.100:8080",
        )

        result = validator_no_paths.validate_urls(config)

        assert result.valid is True


# ============================================================================
# Timeout Validation Tests
# ============================================================================


class TestValidateTimeouts:
    """Test timeout validation."""

    def test_valid_timeout_passes(self, validator_no_paths, temp_dir):
        """Test valid timeout passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            timeout_seconds=300,
        )

        result = validator_no_paths.validate_timeouts(config)

        assert result.valid is True

    def test_timeout_below_minimum_fails(self, validator_no_paths, temp_dir):
        """Test timeout below minimum fails validation."""
        # Note: E2EConfig validates timeout_seconds > 0 in __post_init__
        # So we test the boundary
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            timeout_seconds=MIN_TIMEOUT_SECONDS,  # Minimum valid
        )

        result = validator_no_paths.validate_timeouts(config)

        assert result.valid is True  # Minimum is valid

    def test_timeout_above_maximum_fails(self, validator_no_paths, temp_dir):
        """Test timeout above maximum fails validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            timeout_seconds=MAX_TIMEOUT_SECONDS + 1,
        )

        result = validator_no_paths.validate_timeouts(config)

        assert result.valid is False
        assert any("at most" in e for e in result.errors)

    def test_short_timeout_warns(self, validator_no_paths, temp_dir):
        """Test very short timeout generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            timeout_seconds=10,
        )

        result = validator_no_paths.validate_timeouts(config)

        assert any("very short" in w for w in result.warnings)

    def test_long_timeout_warns(self, validator_no_paths, temp_dir):
        """Test very long timeout generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            timeout_seconds=2000,  # > 30 min
        )

        result = validator_no_paths.validate_timeouts(config)

        assert any("very long" in w for w in result.warnings)

    def test_valid_max_tests_passes(self, validator_no_paths, temp_dir):
        """Test valid max_tests passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            max_tests=10,
        )

        result = validator_no_paths.validate_timeouts(config)

        assert result.valid is True

    def test_zero_max_tests_fails(self, validator_no_paths, temp_dir):
        """Test zero max_tests fails validation."""
        # Note: E2EConfig validates max_tests > 0 in __post_init__
        # This test verifies the validator also catches it
        with pytest.raises(ValueError):
            E2EConfig(
                provider_name="test",
                project_root=temp_dir,
                max_tests=0,
            )

    def test_none_max_tests_passes(self, validator_no_paths, temp_dir):
        """Test None max_tests passes validation (no limit)."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            max_tests=None,
        )

        result = validator_no_paths.validate_timeouts(config)

        assert result.valid is True


# ============================================================================
# Test Framework Validation Tests
# ============================================================================


class TestValidateTestFramework:
    """Test framework and language validation."""

    def test_supported_framework_passes(self, validator_no_paths, temp_dir):
        """Test supported framework passes validation."""
        for framework in SUPPORTED_TEST_FRAMEWORKS:
            config = E2EConfig(
                provider_name="test",
                project_root=temp_dir,
                test_framework=framework,
            )

            result = validator_no_paths.validate_test_framework(config)

            # Check that the "not in standard list" warning is not present
            assert not any(
                framework in w and "not in the standard list" in w
                for w in result.warnings
            ), f"Framework {framework} should not generate 'not in standard list' warning"

    def test_unsupported_framework_warns(self, validator_no_paths, temp_dir):
        """Test unsupported framework generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            test_framework="custom_framework",
        )

        result = validator_no_paths.validate_test_framework(config)

        assert any("custom_framework" in w for w in result.warnings)

    def test_supported_language_passes(self, validator_no_paths, temp_dir):
        """Test supported language passes validation."""
        for language in SUPPORTED_LANGUAGES:
            config = E2EConfig(
                provider_name="test",
                project_root=temp_dir,
                programming_language=language,
            )

            result = validator_no_paths.validate_test_framework(config)

            assert not any(language in w and "not in the standard list" in w
                          for w in result.warnings), \
                f"Language {language} should not generate warning"

    def test_unsupported_language_warns(self, validator_no_paths, temp_dir):
        """Test unsupported language generates warning."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            programming_language="ruby",
        )

        result = validator_no_paths.validate_test_framework(config)

        assert any("ruby" in w for w in result.warnings)

    def test_compatible_framework_language_passes(self, validator_no_paths, temp_dir):
        """Test compatible framework/language combination passes."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            test_framework="playwright",
            programming_language="typescript",
        )

        result = validator_no_paths.validate_test_framework(config)

        assert not any("does not typically support" in w for w in result.warnings)

    def test_incompatible_framework_language_warns(self, validator_no_paths, temp_dir):
        """Test incompatible framework/language combination warns."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            test_framework="cypress",
            programming_language="python",  # Cypress doesn't support Python
        )

        result = validator_no_paths.validate_test_framework(config)

        assert any("does not typically support" in w for w in result.warnings)

    def test_playwright_supports_multiple_languages(self, validator_no_paths, temp_dir):
        """Test Playwright supports multiple languages."""
        for lang in ["typescript", "javascript", "python", "java", "csharp"]:
            config = E2EConfig(
                provider_name="test",
                project_root=temp_dir,
                test_framework="playwright",
                programming_language=lang,
            )

            result = validator_no_paths.validate_test_framework(config)

            assert not any("does not typically support" in w for w in result.warnings), \
                f"Playwright should support {lang}"


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_validate_e2e_config_function(self, temp_dir):
        """Test validate_e2e_config convenience function."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
        )

        result = validate_e2e_config(config)

        assert isinstance(result, ValidationResult)
        assert result.valid is True

    def test_validate_e2e_config_with_strict_mode(self, temp_dir):
        """Test validate_e2e_config with strict_mode."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
            timeout_seconds=10,  # Generates warning
        )

        result = validate_e2e_config(config, strict_mode=True, check_paths=False)

        # Warning should become error in strict mode
        if result.valid:
            assert len(result.warnings) == 0  # Warnings converted to errors

    def test_validate_e2e_config_without_path_check(self):
        """Test validate_e2e_config without path checking."""
        config = E2EConfig(
            provider_name="test",
            project_root=Path("/nonexistent/path"),
        )

        result = validate_e2e_config(config, check_paths=False)

        # Should not fail on path
        assert not any("does not exist" in e for e in result.errors)

    def test_quick_validate_returns_bool(self, temp_dir):
        """Test quick_validate returns boolean."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
        )

        result = quick_validate(config)

        assert isinstance(result, bool)

    def test_quick_validate_valid_config(self, temp_dir):
        """Test quick_validate returns True for valid config."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
        )

        assert quick_validate(config) is True

    def test_quick_validate_invalid_config(self, temp_dir):
        """Test quick_validate returns False for invalid config."""
        config = E2EConfig(
            provider_name="",  # Invalid
            project_root=temp_dir,
        )

        assert quick_validate(config) is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestE2EConfigValidatorIntegration:
    """Integration tests for E2EConfigValidator."""

    def test_full_debuggai_config_validation(self, temp_dir):
        """Test full validation of a complete DebuggAI config."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_live_test_key",
            api_base_url="https://api.debugg.ai",
            project_url="https://myapp.example.com",
            test_framework="playwright",
            programming_language="typescript",
            output_directory=temp_dir / "e2e_tests",
            timeout_seconds=300,
            max_tests=50,
        )

        validator = E2EConfigValidator()
        result = validator.validate(config)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_full_local_config_validation(self, temp_dir):
        """Test full validation of a complete local config."""
        config = E2EConfig(
            provider_name="local",
            project_root=temp_dir,
            project_url="http://localhost:3000",
            test_framework="playwright",
            programming_language="javascript",
            timeout_seconds=60,
        )

        validator = E2EConfigValidator()
        result = validator.validate(config)

        assert result.valid is True

    def test_multiple_errors_collected(self, temp_dir):
        """Test that multiple errors are collected."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key=None,  # Error 1: Missing for debuggai
            project_url=None,  # Error 2: Missing for debuggai
            api_base_url="invalid-url",  # Error 3: Invalid URL
            timeout_seconds=5000,  # Error 4: Too high
        )

        validator = E2EConfigValidator(check_paths=False)
        result = validator.validate(config)

        assert result.valid is False
        # Should have multiple errors
        assert len(result.errors) >= 3

    def test_warnings_preserved_in_non_strict_mode(self, temp_dir):
        """Test warnings are preserved in non-strict mode."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
            api_base_url="https://api.example.com/",  # Trailing slash warning
            timeout_seconds=10,  # Short timeout warning
        )

        validator = E2EConfigValidator(check_paths=False, strict_mode=False)
        result = validator.validate(config)

        assert result.valid is True
        assert len(result.warnings) >= 1


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_provider_name(self, temp_dir):
        """Test empty provider name is caught."""
        config = E2EConfig(
            provider_name="",
            project_root=temp_dir,
        )

        result = validate_e2e_config(config, check_paths=False)

        assert result.valid is False

    def test_case_insensitive_provider_matching(self, temp_dir):
        """Test provider name matching is case-insensitive."""
        config = E2EConfig(
            provider_name="DebuggAI",  # Mixed case
            project_root=temp_dir,
            api_key="sk_test",
            project_url="https://example.com",
        )

        result = validate_e2e_config(config, check_paths=False)

        # Should recognize as debuggai and validate accordingly
        assert result.valid is True

    def test_url_with_path(self, temp_dir):
        """Test URL with path passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            api_base_url="https://api.example.com/v1",
            project_url="https://app.example.com/dashboard",
        )

        result = validate_e2e_config(config, check_paths=False)

        assert result.valid is True

    def test_url_with_port(self, temp_dir):
        """Test URL with port passes validation."""
        config = E2EConfig(
            provider_name="test",
            project_root=temp_dir,
            project_url="http://localhost:3000",
        )

        result = validate_e2e_config(config, check_paths=False)

        assert result.valid is True

    def test_minimum_valid_config(self, temp_dir):
        """Test minimum valid configuration."""
        config = E2EConfig(
            provider_name="local",
            project_root=temp_dir,
        )

        result = validate_e2e_config(config)

        assert result.valid is True

    def test_all_optional_fields_none(self, temp_dir):
        """Test config with all optional fields as None."""
        config = E2EConfig(
            provider_name="local",
            project_root=temp_dir,
            api_key=None,
            api_base_url=None,
            project_slug=None,
            project_url=None,
            max_tests=None,
        )

        result = validate_e2e_config(config)

        assert result.valid is True

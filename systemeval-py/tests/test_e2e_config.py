"""
Tests for E2E configuration models.

These tests validate the strict configuration principles:
1. No config discovery - explicit paths only
2. No cascading fallbacks - single source of truth
3. No magic values - all values validated
4. Fail fast - invalid config raises ValueError
"""
import pytest
from pathlib import Path
from typing import Dict, Any

from systemeval.e2e_config import (
    E2EConfig,
    DebuggAIProviderConfig,
    LocalProviderConfig,
    load_e2e_config_from_dict,
    validate_e2e_config,
)


# ============================================================================
# DebuggAIProviderConfig Tests
# ============================================================================


class TestDebuggAIProviderConfig:
    """Test DebuggAI provider configuration validation."""

    def test_valid_config(self):
        """Test valid DebuggAI config creation."""
        config = DebuggAIProviderConfig(
            api_key="sk_live_test_key",
            api_url="https://api.debugg.ai",
            project_id="test-project",
        )

        assert config.api_key == "sk_live_test_key"
        assert config.api_url == "https://api.debugg.ai"
        assert config.project_id == "test-project"

    def test_valid_config_without_project_id(self):
        """Test valid DebuggAI config without project_id."""
        config = DebuggAIProviderConfig(
            api_key="sk_live_test_key",
            api_url="https://api.debugg.ai",
        )

        assert config.project_id is None

    def test_api_url_trailing_slash_stripped(self):
        """Test API URL trailing slash is stripped."""
        config = DebuggAIProviderConfig(
            api_key="sk_live_test_key",
            api_url="https://api.debugg.ai/",
        )

        assert config.api_url == "https://api.debugg.ai"

    def test_api_key_whitespace_stripped(self):
        """Test API key whitespace is stripped."""
        config = DebuggAIProviderConfig(
            api_key="  sk_live_test_key  ",
            api_url="https://api.debugg.ai",
        )

        assert config.api_key == "sk_live_test_key"

    def test_empty_api_key_fails(self):
        """Test empty API key raises ValidationError."""
        with pytest.raises(Exception, match="string_too_short|at least 1 character"):
            DebuggAIProviderConfig(
                api_key="",
                api_url="https://api.debugg.ai",
            )

    def test_whitespace_api_key_fails(self):
        """Test whitespace-only API key raises ValueError."""
        with pytest.raises(ValueError, match="api_key cannot be empty"):
            DebuggAIProviderConfig(
                api_key="   ",
                api_url="https://api.debugg.ai",
            )

    def test_empty_api_url_fails(self):
        """Test empty API URL raises ValidationError."""
        with pytest.raises(Exception, match="string_too_short|at least 1 character"):
            DebuggAIProviderConfig(
                api_key="sk_live_test_key",
                api_url="",
            )

    def test_invalid_api_url_no_protocol_fails(self):
        """Test API URL without http/https fails."""
        with pytest.raises(ValueError, match="must start with http://"):
            DebuggAIProviderConfig(
                api_key="sk_live_test_key",
                api_url="api.debugg.ai",
            )

    def test_empty_project_id_fails(self):
        """Test empty project_id raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            DebuggAIProviderConfig(
                api_key="sk_live_test_key",
                api_url="https://api.debugg.ai",
                project_id="",
            )


# ============================================================================
# LocalProviderConfig Tests
# ============================================================================


class TestLocalProviderConfig:
    """Test local provider configuration validation."""

    def test_valid_config(self):
        """Test valid local config creation."""
        config = LocalProviderConfig(
            base_url="http://localhost:3000",
            timeout_seconds=60,
        )

        assert config.base_url == "http://localhost:3000"
        assert config.timeout_seconds == 60

    def test_base_url_trailing_slash_stripped(self):
        """Test base URL trailing slash is stripped."""
        config = LocalProviderConfig(
            base_url="http://localhost:3000/",
        )

        assert config.base_url == "http://localhost:3000"

    def test_empty_base_url_fails(self):
        """Test empty base URL raises ValidationError."""
        with pytest.raises(Exception, match="string_too_short|at least 1 character"):
            LocalProviderConfig(base_url="")

    def test_invalid_base_url_no_protocol_fails(self):
        """Test base URL without http/https fails."""
        with pytest.raises(ValueError, match="must start with http://"):
            LocalProviderConfig(base_url="localhost:3000")

    def test_timeout_too_small_fails(self):
        """Test timeout < 1 raises ValueError."""
        with pytest.raises(ValueError):
            LocalProviderConfig(
                base_url="http://localhost:3000",
                timeout_seconds=0,
            )

    def test_timeout_too_large_fails(self):
        """Test timeout > 600 raises ValueError."""
        with pytest.raises(ValueError):
            LocalProviderConfig(
                base_url="http://localhost:3000",
                timeout_seconds=601,
            )


# ============================================================================
# E2EConfig Tests
# ============================================================================


class TestE2EConfig:
    """Test top-level E2E configuration."""

    def test_valid_debuggai_config(self):
        """Test valid DebuggAI E2E config."""
        config = E2EConfig(
            provider="debuggai",
            provider_config={
                "api_key": "sk_live_test",
                "api_url": "https://api.debugg.ai",
                "project_id": "test",
            },
            output_dir=Path("/tmp/e2e"),
            timeout_seconds=300,
            poll_interval_seconds=5,
        )

        assert config.provider == "debuggai"
        assert config.output_dir == Path("/tmp/e2e")
        assert config.timeout_seconds == 300
        assert config.poll_interval_seconds == 5

        # Test typed provider config
        provider = config.get_provider_config()
        assert isinstance(provider, DebuggAIProviderConfig)
        assert provider.api_key == "sk_live_test"

    def test_valid_local_config(self):
        """Test valid local E2E config."""
        config = E2EConfig(
            provider="local",
            provider_config={
                "base_url": "http://localhost:3000",
                "timeout_seconds": 60,
            },
            output_dir=Path("/tmp/e2e"),
            timeout_seconds=60,
            poll_interval_seconds=2,
        )

        assert config.provider == "local"

        # Test typed provider config
        provider = config.get_provider_config()
        assert isinstance(provider, LocalProviderConfig)
        assert provider.base_url == "http://localhost:3000"

    def test_factory_for_debuggai(self):
        """Test E2EConfig.for_debuggai() factory method."""
        config = E2EConfig.for_debuggai(
            api_key="sk_live_test",
            api_url="https://api.debugg.ai",
            output_dir=Path("/tmp/e2e"),
            project_id="test",
        )

        assert config.provider == "debuggai"
        assert config.output_dir == Path("/tmp/e2e")

        provider = config.get_provider_config()
        assert isinstance(provider, DebuggAIProviderConfig)
        assert provider.api_key == "sk_live_test"
        assert provider.project_id == "test"

    def test_factory_for_local(self):
        """Test E2EConfig.for_local() factory method."""
        config = E2EConfig.for_local(
            base_url="http://localhost:3000",
            output_dir=Path("/tmp/e2e"),
        )

        assert config.provider == "local"

        provider = config.get_provider_config()
        assert isinstance(provider, LocalProviderConfig)
        assert provider.base_url == "http://localhost:3000"

    def test_relative_output_dir_fails(self):
        """Test relative output_dir raises ValueError."""
        with pytest.raises(ValueError, match="absolute path"):
            E2EConfig(
                provider="local",
                provider_config={
                    "base_url": "http://localhost:3000",
                },
                output_dir=Path("./output"),  # INVALID - relative
            )

    def test_output_dir_string_converted_to_path(self):
        """Test output_dir as string is converted to Path."""
        config = E2EConfig(
            provider="local",
            provider_config={
                "base_url": "http://localhost:3000",
            },
            output_dir="/tmp/e2e",  # String instead of Path
        )

        assert isinstance(config.output_dir, Path)
        assert config.output_dir == Path("/tmp/e2e")

    def test_empty_provider_config_fails(self):
        """Test empty provider_config raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            E2EConfig(
                provider="debuggai",
                provider_config={},  # INVALID - empty
                output_dir=Path("/tmp/e2e"),
            )

    def test_invalid_provider_config_for_provider_fails(self):
        """Test invalid provider_config for selected provider fails."""
        config = E2EConfig(
            provider="debuggai",
            provider_config={
                "base_url": "http://localhost:3000",  # Wrong fields for debuggai
            },
            output_dir=Path("/tmp/e2e"),
        )

        # Should fail when trying to get typed config
        with pytest.raises(ValueError):
            config.get_provider_config()

    def test_timeout_too_small_fails(self):
        """Test timeout < 1 raises ValueError."""
        with pytest.raises(ValueError):
            E2EConfig(
                provider="local",
                provider_config={"base_url": "http://localhost:3000"},
                output_dir=Path("/tmp/e2e"),
                timeout_seconds=0,
            )

    def test_timeout_too_large_fails(self):
        """Test timeout > 3600 raises ValueError."""
        with pytest.raises(ValueError):
            E2EConfig(
                provider="local",
                provider_config={"base_url": "http://localhost:3000"},
                output_dir=Path("/tmp/e2e"),
                timeout_seconds=3601,
            )

    def test_poll_interval_too_small_fails(self):
        """Test poll_interval < 1 raises ValueError."""
        with pytest.raises(ValueError):
            E2EConfig(
                provider="local",
                provider_config={"base_url": "http://localhost:3000"},
                output_dir=Path("/tmp/e2e"),
                poll_interval_seconds=0,
            )

    def test_poll_interval_too_large_fails(self):
        """Test poll_interval > 60 raises ValueError."""
        with pytest.raises(ValueError):
            E2EConfig(
                provider="local",
                provider_config={"base_url": "http://localhost:3000"},
                output_dir=Path("/tmp/e2e"),
                poll_interval_seconds=61,
            )


# ============================================================================
# Config Loading Tests
# ============================================================================


class TestConfigLoading:
    """Test E2E config loading functions."""

    def test_load_debuggai_config_from_dict(self):
        """Test loading DebuggAI config from dict."""
        config_dict = {
            "provider": "debuggai",
            "provider_config": {
                "api_key": "sk_live_test",
                "api_url": "https://api.debugg.ai",
                "project_id": "test",
            },
            "output_dir": "/tmp/e2e",
            "timeout_seconds": 300,
            "poll_interval_seconds": 5,
        }

        config = load_e2e_config_from_dict(config_dict)

        assert config.provider == "debuggai"
        assert config.output_dir == Path("/tmp/e2e")

    def test_load_local_config_from_dict(self):
        """Test loading local config from dict."""
        config_dict = {
            "provider": "local",
            "provider_config": {
                "base_url": "http://localhost:3000",
            },
            "output_dir": "/tmp/e2e",
        }

        config = load_e2e_config_from_dict(config_dict)

        assert config.provider == "local"

    def test_validate_e2e_config(self):
        """Test validate_e2e_config function."""
        config_dict = {
            "provider": "debuggai",
            "provider_config": {
                "api_key": "sk_live_test",
                "api_url": "https://api.debugg.ai",
            },
            "output_dir": "/tmp/e2e",
        }

        config = validate_e2e_config(config_dict)

        assert isinstance(config, E2EConfig)
        assert config.provider == "debuggai"

    def test_load_invalid_config_fails(self):
        """Test loading invalid config raises ValueError."""
        config_dict = {
            "provider": "debuggai",
            "provider_config": {},  # INVALID - empty
            "output_dir": "/tmp/e2e",
        }

        with pytest.raises(ValueError):
            load_e2e_config_from_dict(config_dict)


# ============================================================================
# Integration Tests
# ============================================================================


class TestE2EConfigIntegration:
    """Integration tests for E2E config system."""

    def test_end_to_end_debuggai_workflow(self):
        """Test complete workflow: create config, validate, use."""
        # Step 1: Create config
        config = E2EConfig.for_debuggai(
            api_key="sk_live_test_key",
            api_url="https://api.debugg.ai",
            output_dir=Path("/tmp/e2e-test"),
            project_id="integration-test",
            timeout_seconds=180,
        )

        # Step 2: Validate config
        assert config.provider == "debuggai"
        assert config.timeout_seconds == 180

        # Step 3: Get typed provider config
        provider = config.get_provider_config()
        assert isinstance(provider, DebuggAIProviderConfig)
        assert provider.api_key == "sk_live_test_key"
        assert provider.api_url == "https://api.debugg.ai"
        assert provider.project_id == "integration-test"

        # Step 4: Serialize to dict (for passing to runner)
        config_dict = {
            "provider": config.provider,
            "provider_config": config.provider_config,
            "output_dir": str(config.output_dir),
            "timeout_seconds": config.timeout_seconds,
            "poll_interval_seconds": config.poll_interval_seconds,
        }

        # Step 5: Reload from dict
        reloaded = load_e2e_config_from_dict(config_dict)
        assert reloaded.provider == config.provider
        assert reloaded.timeout_seconds == config.timeout_seconds

    def test_end_to_end_local_workflow(self):
        """Test complete workflow: create config, validate, use."""
        # Step 1: Create config
        config = E2EConfig.for_local(
            base_url="http://localhost:3000",
            output_dir=Path("/tmp/e2e-test"),
            timeout_seconds=30,
        )

        # Step 2: Validate config
        assert config.provider == "local"
        assert config.timeout_seconds == 30

        # Step 3: Get typed provider config
        provider = config.get_provider_config()
        assert isinstance(provider, LocalProviderConfig)
        assert provider.base_url == "http://localhost:3000"

        # Step 4: Use config (simulate runner)
        assert config.output_dir.is_absolute()
        assert config.poll_interval_seconds > 0

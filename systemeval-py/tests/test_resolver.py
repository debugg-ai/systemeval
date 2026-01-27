"""Tests for EnvironmentResolver in systemeval.environments.resolver."""

import pytest
from unittest.mock import MagicMock, patch

from systemeval.environments.resolver import EnvironmentResolver
from systemeval.environments.base import Environment, EnvironmentType
from systemeval.environments.implementations.standalone import StandaloneEnvironment
from systemeval.environments.implementations.docker_compose import DockerComposeEnvironment
from systemeval.environments.implementations.composite import CompositeEnvironment
from systemeval.environments.implementations.ngrok import NgrokEnvironment
from systemeval.environments.implementations.browser import BrowserEnvironment


class TestEnvironmentResolverInit:
    """Tests for EnvironmentResolver initialization."""

    def test_init_with_empty_config(self):
        """Test initialization with empty configuration."""
        resolver = EnvironmentResolver({})

        assert resolver.config == {}
        assert resolver._cache == {}

    def test_init_with_environments(self):
        """Test initialization with environment configurations."""
        config = {
            "backend": {"type": "standalone", "command": "python app.py"},
            "frontend": {"type": "standalone", "command": "npm start"},
        }
        resolver = EnvironmentResolver(config)

        assert resolver.config == config
        assert "backend" in resolver.config
        assert "frontend" in resolver.config
        assert resolver._cache == {}

    def test_init_preserves_config_reference(self):
        """Test that config is stored as reference."""
        config = {"test": {"type": "standalone"}}
        resolver = EnvironmentResolver(config)

        assert resolver.config is config


class TestEnvironmentResolverResolve:
    """Tests for EnvironmentResolver.resolve() method."""

    def test_resolve_standalone_environment(self):
        """Test resolving a standalone environment."""
        config = {
            "backend": {
                "type": "standalone",
                "command": "python app.py",
                "ready_pattern": "Server started",
                "port": 8000,
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("backend")

        assert isinstance(env, StandaloneEnvironment)
        assert env.name == "backend"
        assert env.command == "python app.py"
        assert env.ready_pattern == "Server started"
        assert env.port == 8000
        assert env.env_type == EnvironmentType.STANDALONE

    def test_resolve_standalone_default_type(self):
        """Test that missing type defaults to standalone."""
        config = {
            "simple": {
                "command": "echo hello",
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("simple")

        assert isinstance(env, StandaloneEnvironment)
        assert env.env_type == EnvironmentType.STANDALONE

    def test_resolve_docker_compose_environment(self):
        """Test resolving a docker-compose environment."""
        config = {
            "docker-backend": {
                "type": "docker-compose",
                "compose_file": "docker-compose.yml",
                "services": ["api", "db"],
                "test_service": "api",
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("docker-backend")

        assert isinstance(env, DockerComposeEnvironment)
        assert env.name == "docker-backend"
        assert env.compose_file == "docker-compose.yml"
        assert env.services == ["api", "db"]
        assert env.test_service == "api"
        assert env.env_type == EnvironmentType.DOCKER_COMPOSE

    def test_resolve_composite_environment(self):
        """Test resolving a composite environment with dependencies."""
        config = {
            "backend": {"type": "standalone", "command": "python app.py"},
            "frontend": {"type": "standalone", "command": "npm start"},
            "full-stack": {
                "type": "composite",
                "depends_on": ["backend", "frontend"],
                "test_command": "npm run e2e",
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("full-stack")

        assert isinstance(env, CompositeEnvironment)
        assert env.name == "full-stack"
        assert len(env.children) == 2
        assert env.test_command == "npm run e2e"
        assert env.env_type == EnvironmentType.COMPOSITE

        # Verify children are resolved
        assert isinstance(env.children[0], StandaloneEnvironment)
        assert isinstance(env.children[1], StandaloneEnvironment)
        assert env.children[0].name == "backend"
        assert env.children[1].name == "frontend"

    def test_resolve_composite_empty_depends_on(self):
        """Test resolving composite with empty depends_on."""
        config = {
            "empty-composite": {
                "type": "composite",
                "depends_on": [],
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("empty-composite")

        assert isinstance(env, CompositeEnvironment)
        assert env.children == []

    def test_resolve_composite_nested(self):
        """Test resolving nested composite environments."""
        config = {
            "db": {"type": "standalone", "command": "docker start db"},
            "api": {"type": "standalone", "command": "python app.py"},
            "backend": {
                "type": "composite",
                "depends_on": ["db", "api"],
            },
            "frontend": {"type": "standalone", "command": "npm start"},
            "full-stack": {
                "type": "composite",
                "depends_on": ["backend", "frontend"],
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("full-stack")

        assert isinstance(env, CompositeEnvironment)
        assert len(env.children) == 2

        # First child is nested composite
        backend = env.children[0]
        assert isinstance(backend, CompositeEnvironment)
        assert len(backend.children) == 2

        # Second child is standalone
        frontend = env.children[1]
        assert isinstance(frontend, StandaloneEnvironment)

    def test_resolve_ngrok_environment(self):
        """Test resolving an ngrok environment."""
        config = {
            "tunnel": {
                "type": "ngrok",
                "port": 3000,
                "region": "us",
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("tunnel")

        assert isinstance(env, NgrokEnvironment)
        assert env.name == "tunnel"
        assert env.env_type == EnvironmentType.NGROK

    def test_resolve_browser_environment(self):
        """Test resolving a browser environment."""
        config = {
            "chrome": {
                "type": "browser",
                "browser": "chromium",
                "headless": True,
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("chrome")

        assert isinstance(env, BrowserEnvironment)
        assert env.name == "chrome"
        assert env.env_type == EnvironmentType.BROWSER

    def test_resolve_unknown_environment_raises_key_error(self):
        """Test that resolving unknown environment raises KeyError."""
        config = {"backend": {"type": "standalone"}}
        resolver = EnvironmentResolver(config)

        with pytest.raises(KeyError) as exc_info:
            resolver.resolve("nonexistent")

        assert "nonexistent" in str(exc_info.value)
        assert "not found in configuration" in str(exc_info.value)

    def test_resolve_unknown_type_raises_value_error(self):
        """Test that unknown environment type raises ValueError."""
        config = {
            "invalid": {
                "type": "unknown-type",
            }
        }
        resolver = EnvironmentResolver(config)

        with pytest.raises(ValueError) as exc_info:
            resolver.resolve("invalid")

        assert "Unknown environment type" in str(exc_info.value)
        assert "unknown-type" in str(exc_info.value)

    def test_resolve_caches_environment(self):
        """Test that resolved environments are cached."""
        config = {
            "backend": {"type": "standalone", "command": "python app.py"}
        }
        resolver = EnvironmentResolver(config)

        # First resolution
        env1 = resolver.resolve("backend")
        assert "backend" in resolver._cache

        # Second resolution returns same instance
        env2 = resolver.resolve("backend")
        assert env1 is env2

    def test_resolve_cache_prevents_duplicate_construction(self):
        """Test that cache prevents creating duplicate instances."""
        config = {
            "backend": {"type": "standalone"},
            "frontend": {"type": "standalone"},
            "full": {"type": "composite", "depends_on": ["backend", "frontend"]}
        }
        resolver = EnvironmentResolver(config)

        # Resolve backend first
        backend = resolver.resolve("backend")

        # Now resolve composite, backend should be reused
        full = resolver.resolve("full")

        # The child should be the same instance as the one we resolved earlier
        assert full.children[0] is backend

    def test_resolve_composite_caches_children(self):
        """Test that resolving composite also caches its children."""
        config = {
            "backend": {"type": "standalone"},
            "frontend": {"type": "standalone"},
            "full": {"type": "composite", "depends_on": ["backend", "frontend"]}
        }
        resolver = EnvironmentResolver(config)

        # Resolve composite
        resolver.resolve("full")

        # Children should be in cache
        assert "backend" in resolver._cache
        assert "frontend" in resolver._cache


class TestEnvironmentResolverListEnvironments:
    """Tests for EnvironmentResolver.list_environments() method."""

    def test_list_environments_empty(self):
        """Test listing environments when none configured."""
        resolver = EnvironmentResolver({})

        result = resolver.list_environments()

        assert result == {}

    def test_list_environments_single(self):
        """Test listing single environment."""
        config = {"backend": {"type": "standalone"}}
        resolver = EnvironmentResolver(config)

        result = resolver.list_environments()

        assert result == {"backend": "standalone"}

    def test_list_environments_multiple(self):
        """Test listing multiple environments."""
        config = {
            "backend": {"type": "standalone"},
            "docker": {"type": "docker-compose"},
            "full": {"type": "composite", "depends_on": []},
            "tunnel": {"type": "ngrok"},
            "browser": {"type": "browser"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.list_environments()

        assert result == {
            "backend": "standalone",
            "docker": "docker-compose",
            "full": "composite",
            "tunnel": "ngrok",
            "browser": "browser",
        }

    def test_list_environments_defaults_to_standalone(self):
        """Test that missing type defaults to standalone in listing."""
        config = {
            "simple": {"command": "echo hello"},
            "explicit": {"type": "docker-compose"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.list_environments()

        assert result == {
            "simple": "standalone",
            "explicit": "docker-compose",
        }

    def test_list_environments_preserves_order(self):
        """Test that environment order is preserved (Python 3.7+ dict order)."""
        config = {
            "alpha": {"type": "standalone"},
            "beta": {"type": "docker-compose"},
            "gamma": {"type": "composite"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.list_environments()

        assert list(result.keys()) == ["alpha", "beta", "gamma"]


class TestEnvironmentResolverGetDefaultEnvironment:
    """Tests for EnvironmentResolver.get_default_environment() method."""

    def test_get_default_empty_config(self):
        """Test getting default when no environments configured."""
        resolver = EnvironmentResolver({})

        result = resolver.get_default_environment()

        assert result is None

    def test_get_default_explicit_default(self):
        """Test getting environment with explicit default flag."""
        config = {
            "backend": {"type": "standalone"},
            "frontend": {"type": "standalone", "default": True},
            "docker": {"type": "docker-compose"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        assert result == "frontend"

    def test_get_default_first_explicit_wins(self):
        """Test that first environment with default=true wins."""
        config = {
            "first": {"type": "standalone", "default": True},
            "second": {"type": "standalone", "default": True},
            "third": {"type": "standalone"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        assert result == "first"

    def test_get_default_prefers_non_composite(self):
        """Test that non-composite is preferred when no explicit default."""
        config = {
            "full": {"type": "composite", "depends_on": []},
            "backend": {"type": "standalone"},
            "docker": {"type": "docker-compose"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        # Should return first non-composite (backend)
        assert result == "backend"

    def test_get_default_falls_back_to_first(self):
        """Test that first environment is returned as fallback."""
        config = {
            "composite-only": {"type": "composite", "depends_on": []},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        # Should return first (composite) as fallback
        assert result == "composite-only"

    def test_get_default_with_all_composites(self):
        """Test default selection when all environments are composite."""
        config = {
            "first-composite": {"type": "composite", "depends_on": []},
            "second-composite": {"type": "composite", "depends_on": []},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        assert result == "first-composite"

    def test_get_default_explicit_overrides_type_preference(self):
        """Test that explicit default overrides type preference."""
        config = {
            "backend": {"type": "standalone"},
            "full": {"type": "composite", "depends_on": [], "default": True},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        # Explicit default wins even though composite is usually deprioritized
        assert result == "full"

    def test_get_default_false_not_selected(self):
        """Test that default: false is not treated as default."""
        config = {
            "first": {"type": "standalone", "default": False},
            "second": {"type": "standalone"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        # first has default=False, so it shouldn't be chosen via explicit default
        # Should fall through to first non-composite
        assert result == "first"

    def test_get_default_single_environment(self):
        """Test getting default with single environment."""
        config = {
            "only": {"type": "docker-compose"},
        }
        resolver = EnvironmentResolver(config)

        result = resolver.get_default_environment()

        assert result == "only"


class TestEnvironmentResolverEdgeCases:
    """Edge case tests for EnvironmentResolver."""

    def test_resolve_with_empty_config_dict(self):
        """Test resolving environment with empty config dict."""
        config = {
            "empty": {}
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("empty")

        # Should default to standalone
        assert isinstance(env, StandaloneEnvironment)

    def test_resolve_preserves_extra_config(self):
        """Test that extra config fields are passed through."""
        config = {
            "backend": {
                "type": "standalone",
                "command": "python app.py",
                "custom_field": "custom_value",
                "env": {"DEBUG": "true"},
            }
        }
        resolver = EnvironmentResolver(config)

        env = resolver.resolve("backend")

        # Environment should have access to full config
        assert env.config.get("custom_field") == "custom_value"
        assert env.env_vars.get("DEBUG") == "true"

    def test_resolve_composite_missing_dependency(self):
        """Test that resolving composite with missing dependency raises error."""
        config = {
            "full": {
                "type": "composite",
                "depends_on": ["backend", "nonexistent"],
            },
            "backend": {"type": "standalone"},
        }
        resolver = EnvironmentResolver(config)

        with pytest.raises(KeyError) as exc_info:
            resolver.resolve("full")

        assert "nonexistent" in str(exc_info.value)

    def test_resolve_multiple_environments_independently(self):
        """Test resolving multiple environments independently."""
        config = {
            "backend": {"type": "standalone", "port": 8000},
            "frontend": {"type": "standalone", "port": 3000},
            "docker": {"type": "docker-compose"},
        }
        resolver = EnvironmentResolver(config)

        backend = resolver.resolve("backend")
        frontend = resolver.resolve("frontend")
        docker = resolver.resolve("docker")

        assert backend.port == 8000
        assert frontend.port == 3000
        assert isinstance(docker, DockerComposeEnvironment)

        # All should be cached
        assert len(resolver._cache) == 3

    def test_list_environments_does_not_resolve(self):
        """Test that list_environments doesn't resolve/cache environments."""
        config = {
            "backend": {"type": "standalone"},
            "frontend": {"type": "standalone"},
        }
        resolver = EnvironmentResolver(config)

        resolver.list_environments()

        # Cache should still be empty
        assert resolver._cache == {}

    def test_get_default_does_not_resolve(self):
        """Test that get_default_environment doesn't resolve/cache environments."""
        config = {
            "backend": {"type": "standalone", "default": True},
        }
        resolver = EnvironmentResolver(config)

        resolver.get_default_environment()

        # Cache should still be empty
        assert resolver._cache == {}


class TestEnvironmentResolverIntegration:
    """Integration tests for EnvironmentResolver."""

    def test_full_workflow(self):
        """Test complete workflow: list, get default, resolve."""
        config = {
            "db": {"type": "standalone", "command": "docker start postgres"},
            "backend": {"type": "standalone", "command": "python app.py", "default": True},
            "frontend": {"type": "standalone", "command": "npm start"},
            "full-stack": {
                "type": "composite",
                "depends_on": ["backend", "frontend"],
            },
        }
        resolver = EnvironmentResolver(config)

        # List all environments
        envs = resolver.list_environments()
        assert len(envs) == 4

        # Get default
        default = resolver.get_default_environment()
        assert default == "backend"

        # Resolve specific environment
        backend = resolver.resolve("backend")
        assert isinstance(backend, StandaloneEnvironment)

        # Resolve composite (should reuse cached backend)
        full = resolver.resolve("full-stack")
        assert full.children[0] is backend

    def test_resolve_all_environment_types(self):
        """Test resolving all supported environment types."""
        config = {
            "standalone-env": {"type": "standalone", "command": "echo test"},
            "docker-env": {"type": "docker-compose", "compose_file": "local.yml"},
            "composite-env": {"type": "composite", "depends_on": ["standalone-env"]},
            "ngrok-env": {"type": "ngrok", "port": 3000},
            "browser-env": {"type": "browser", "browser": "chromium"},
        }
        resolver = EnvironmentResolver(config)

        standalone = resolver.resolve("standalone-env")
        docker = resolver.resolve("docker-env")
        composite = resolver.resolve("composite-env")
        ngrok = resolver.resolve("ngrok-env")
        browser = resolver.resolve("browser-env")

        assert isinstance(standalone, StandaloneEnvironment)
        assert isinstance(docker, DockerComposeEnvironment)
        assert isinstance(composite, CompositeEnvironment)
        assert isinstance(ngrok, NgrokEnvironment)
        assert isinstance(browser, BrowserEnvironment)

        # Verify all are cached
        assert len(resolver._cache) == 5

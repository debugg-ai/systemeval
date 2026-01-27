"""
Environment resolver for loading and instantiating environments from config.
"""
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from systemeval.config import (
    AnyEnvironmentConfig,
    CompositeEnvConfig,
)
from systemeval.environments.base import Environment, EnvironmentType
from systemeval.environments.implementations import (
    StandaloneEnvironment,
    DockerComposeEnvironment,
    CompositeEnvironment,
    NgrokEnvironment,
    BrowserEnvironment,
)


def _config_to_dict(config: Union[AnyEnvironmentConfig, Dict[str, Any]]) -> Dict[str, Any]:
    """Convert a typed config or dict to a dict for environment classes."""
    if isinstance(config, BaseModel):
        return config.model_dump()
    return config


class EnvironmentResolver:
    """
    Resolves environment names to Environment instances.

    Handles dependency resolution for composite environments.
    """

    def __init__(
        self, environments_config: Dict[str, Union[AnyEnvironmentConfig, Dict[str, Any]]]
    ) -> None:
        """
        Initialize resolver with environment configurations.

        Args:
            environments_config: Dict mapping env names to their configs (typed or dict)
        """
        self.config = environments_config
        self._cache: Dict[str, Environment] = {}

    def resolve(self, name: str) -> Environment:
        """
        Resolve an environment name to an Environment instance.

        Args:
            name: Environment name (e.g., 'backend', 'frontend', 'full-stack')

        Returns:
            Environment instance

        Raises:
            KeyError: If environment not found in config
            ValueError: If environment type is invalid
        """
        if name in self._cache:
            return self._cache[name]

        if name not in self.config:
            raise KeyError(f"Environment '{name}' not found in configuration")

        env_config = self.config[name]
        # Get type from typed model or dict
        if isinstance(env_config, BaseModel):
            env_type = env_config.type
        else:
            env_type = env_config.get("type", "standalone")

        # Convert to dict for environment class constructors
        config_dict = _config_to_dict(env_config)

        if env_type == EnvironmentType.STANDALONE.value:
            env = StandaloneEnvironment(name, config_dict)
        elif env_type == EnvironmentType.DOCKER_COMPOSE.value:
            env = DockerComposeEnvironment(name, config_dict)
        elif env_type == EnvironmentType.COMPOSITE.value:
            # Resolve dependencies first
            if isinstance(env_config, CompositeEnvConfig):
                depends_on = env_config.depends_on
            else:
                depends_on = env_config.get("depends_on", [])
            children = [self.resolve(dep_name) for dep_name in depends_on]
            env = CompositeEnvironment(name, config_dict, children)
        elif env_type == EnvironmentType.NGROK.value:
            env = NgrokEnvironment(name, config_dict)
        elif env_type == EnvironmentType.BROWSER.value:
            env = BrowserEnvironment(name, config_dict)
        else:
            raise ValueError(f"Unknown environment type: {env_type}")

        self._cache[name] = env
        return env

    def list_environments(self) -> Dict[str, str]:
        """
        List available environments and their types.

        Returns:
            Dict mapping env names to their types
        """
        result = {}
        for name, config in self.config.items():
            if isinstance(config, BaseModel):
                result[name] = config.type
            else:
                result[name] = config.get("type", "standalone")
        return result

    def get_default_environment(self) -> Optional[str]:
        """
        Get the default environment name.

        Priority:
        1. Environment with 'default: true'
        2. First non-composite environment
        3. First environment

        Returns:
            Default environment name, or None if no environments
        """
        if not self.config:
            return None

        # Check for explicit default
        for name, config in self.config.items():
            if isinstance(config, BaseModel):
                if config.default:
                    return name
            elif config.get("default", False):
                return name

        # Prefer non-composite
        for name, config in self.config.items():
            if isinstance(config, BaseModel):
                env_type = config.type
            else:
                env_type = config.get("type", "standalone")
            if env_type != EnvironmentType.COMPOSITE.value:
                return name

        # Fall back to first
        return next(iter(self.config.keys()))

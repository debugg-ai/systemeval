"""
Environment resolver for loading and instantiating environments from config.
"""
from typing import Any, Dict, Optional

from systemeval.environments.base import Environment, EnvironmentType
from systemeval.environments.standalone import StandaloneEnvironment
from systemeval.environments.docker_compose import DockerComposeEnvironment
from systemeval.environments.composite import CompositeEnvironment


class EnvironmentResolver:
    """
    Resolves environment names to Environment instances.

    Handles dependency resolution for composite environments.
    """

    def __init__(self, environments_config: Dict[str, Dict[str, Any]]) -> None:
        """
        Initialize resolver with environment configurations.

        Args:
            environments_config: Dict mapping env names to their configs
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
        env_type = env_config.get("type", "standalone")

        if env_type == EnvironmentType.STANDALONE.value:
            env = StandaloneEnvironment(name, env_config)
        elif env_type == EnvironmentType.DOCKER_COMPOSE.value:
            env = DockerComposeEnvironment(name, env_config)
        elif env_type == EnvironmentType.COMPOSITE.value:
            # Resolve dependencies first
            depends_on = env_config.get("depends_on", [])
            children = [self.resolve(dep_name) for dep_name in depends_on]
            env = CompositeEnvironment(name, env_config, children)
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
        return {
            name: config.get("type", "standalone")
            for name, config in self.config.items()
        }

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
            if config.get("default", False):
                return name

        # Prefer non-composite
        for name, config in self.config.items():
            if config.get("type", "standalone") != EnvironmentType.COMPOSITE.value:
                return name

        # Fall back to first
        return next(iter(self.config.keys()))

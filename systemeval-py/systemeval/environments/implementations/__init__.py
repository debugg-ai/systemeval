"""
Environment implementations for different execution contexts.

This module contains concrete environment implementations:
- StandaloneEnvironment: Local execution
- DockerComposeEnvironment: Docker Compose orchestration
- CompositeEnvironment: Multi-environment coordination
- NgrokEnvironment: Ngrok tunnel management
- BrowserEnvironment: Browser testing with Playwright/Surfer
"""

from .standalone import StandaloneEnvironment
from .docker_compose import DockerComposeEnvironment
from .composite import CompositeEnvironment
from .ngrok import NgrokEnvironment
from .browser import BrowserEnvironment

__all__ = [
    "StandaloneEnvironment",
    "DockerComposeEnvironment",
    "CompositeEnvironment",
    "NgrokEnvironment",
    "BrowserEnvironment",
]

"""Django settings detection utilities.

This module provides shared functions for detecting Django settings modules
across different adapters (pytest, pipeline, etc.).
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default settings module candidates ordered by preference
DEFAULT_SETTINGS_CANDIDATES: List[str] = [
    "config.settings.local",
    "config.settings",
    "backend.settings.local",
    "backend.settings",
    "settings.local",
    "settings",
]


def detect_django_settings(
    project_root: str,
    settings_candidates: Optional[List[str]] = None,
    require_manage_py: bool = False,
) -> Optional[str]:
    """Detect Django settings module for a project.

    Searches for Django settings files in the project and sets
    DJANGO_SETTINGS_MODULE environment variable if not already set.

    Args:
        project_root: Absolute path to the project root directory.
        settings_candidates: Optional list of settings module paths to check.
            Defaults to DEFAULT_SETTINGS_CANDIDATES.
        require_manage_py: If True, only detect settings if manage.py exists.
            Useful for pytest adapter to avoid false positives.

    Returns:
        The detected settings module name, or None if:
        - DJANGO_SETTINGS_MODULE was already set (returns the existing value)
        - require_manage_py=True and manage.py doesn't exist
        - No settings file was found

    Example:
        >>> from systemeval.utils.django import detect_django_settings
        >>> settings = detect_django_settings('/path/to/django/project')
        >>> print(settings)
        'config.settings.local'
    """
    project_path = Path(project_root)

    # Check for manage.py if required
    if require_manage_py:
        manage_py = project_path / "manage.py"
        if not manage_py.exists():
            return None

    # Don't override existing setting
    if "DJANGO_SETTINGS_MODULE" in os.environ:
        return os.environ["DJANGO_SETTINGS_MODULE"]

    # Use default candidates if none provided
    candidates = settings_candidates or DEFAULT_SETTINGS_CANDIDATES

    # Try to find settings module
    for candidate in candidates:
        settings_path = project_path / (candidate.replace(".", "/") + ".py")
        if settings_path.exists():
            os.environ["DJANGO_SETTINGS_MODULE"] = candidate
            logger.debug(f"Detected Django settings: {candidate}")
            return candidate

    return None


def setup_django(
    project_root: str,
    settings_candidates: Optional[List[str]] = None,
    fallback_settings: str = "config.settings.local",
) -> bool:
    """Configure Django environment for a project.

    This function:
    1. Adds project root to sys.path if not present
    2. Detects and sets DJANGO_SETTINGS_MODULE
    3. Calls django.setup() if Django is available and not already initialized

    Args:
        project_root: Absolute path to the project root directory.
        settings_candidates: Optional list of settings module paths to check.
        fallback_settings: Settings module to use if detection fails.

    Returns:
        True if Django was successfully configured, False otherwise.

    Example:
        >>> from systemeval.utils.django import setup_django
        >>> success = setup_django('/path/to/django/project')
        >>> print(success)
        True
    """
    # Add project root to Python path
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Detect settings module
    detected = detect_django_settings(
        project_root,
        settings_candidates=settings_candidates,
        require_manage_py=False,
    )

    # Use fallback if detection failed and env var not set
    if detected is None and "DJANGO_SETTINGS_MODULE" not in os.environ:
        os.environ["DJANGO_SETTINGS_MODULE"] = fallback_settings
        logger.debug(f"Using fallback Django settings: {fallback_settings}")

    # Initialize Django if not already done
    try:
        import django

        # Check if Django apps registry is ready
        try:
            from django.apps import apps

            if not apps.ready:
                django.setup()
                logger.debug("Django initialized successfully")
        except (ImportError, RuntimeError):
            # Apps not initialized yet, run setup
            django.setup()
            logger.debug("Django initialized successfully")

        return True

    except ImportError as e:
        logger.warning(f"Django import failed: {e}")
        return False
    except RuntimeError as e:
        logger.warning(f"Django setup failed: {e}")
        return False

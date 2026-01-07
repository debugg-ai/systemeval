"""SystemEval - Unified test runner CLI with framework-agnostic adapters."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("systemeval")
except PackageNotFoundError:
    # Package not installed, fallback to pyproject.toml version
    __version__ = "0.2.0"

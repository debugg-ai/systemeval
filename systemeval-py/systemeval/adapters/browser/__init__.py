"""Browser-based E2E test framework adapters (Playwright, Surfer)."""

from .playwright_adapter import PlaywrightAdapter
from .surfer_adapter import SurferAdapter

__all__ = ["PlaywrightAdapter", "SurferAdapter"]

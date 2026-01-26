"""
Adapter configuration models for systemeval.

This module contains Pydantic models for test adapter configurations:
- TestCategory: Test categorization (unit, integration, api, browser, pipeline)
- PytestConfig: Pytest adapter specific configuration
- PipelineConfig: Pipeline adapter specific configuration
- PlaywrightConfig: Playwright adapter configuration
- SurferConfig: DebuggAI Surfer adapter configuration
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TestCategory(BaseModel):
    """Test category configuration."""
    description: Optional[str] = None
    markers: List[str] = Field(default_factory=list)
    test_match: List[str] = Field(default_factory=list)
    paths: List[str] = Field(default_factory=list)
    requires: List[str] = Field(default_factory=list)


class PytestConfig(BaseModel):
    """Pytest adapter specific configuration."""
    config_file: Optional[str] = None
    base_path: str = "."
    default_category: str = "unit"


class PipelineConfig(BaseModel):
    """Pipeline adapter specific configuration."""
    projects: List[str] = Field(default_factory=lambda: ["crochet-patterns"])
    timeout: int = Field(default=600, description="Max time to wait per project (seconds)")
    poll_interval: int = Field(default=15, description="Seconds between status checks")
    sync_mode: bool = Field(default=False, description="Run webhooks synchronously")
    skip_build: bool = Field(default=False, description="Skip build, use existing containers")


class PlaywrightConfig(BaseModel):
    """Playwright adapter configuration."""
    config_file: str = Field(default="playwright.config.ts", description="Playwright config file")
    project: Optional[str] = Field(default=None, description="Playwright project (chromium, firefox, webkit)")
    headed: bool = Field(default=False, description="Run in headed mode")
    timeout: int = Field(default=30000, description="Test timeout in milliseconds")


class SurferConfig(BaseModel):
    """DebuggAI Surfer adapter configuration."""
    project_slug: str = Field(..., description="DebuggAI project slug")
    api_key: Optional[str] = Field(default=None, description="DebuggAI API key (or use DEBUGGAI_API_KEY env var)")
    api_base_url: str = Field(default="https://api.debugg.ai", description="DebuggAI API base URL")
    poll_interval: int = Field(default=5, description="Seconds between status checks")
    timeout: int = Field(default=600, description="Max time to wait for test completion")

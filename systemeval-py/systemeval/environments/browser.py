"""
Browser testing environment combining server, tunnel, and browser tests.

Orchestrates:
1. Local development server (e.g., npm run dev)
2. Ngrok tunnel to expose the server
3. Browser tests (Playwright or Surfer)

Decoupled from specific adapters - uses registry for adapter creation.
Adapters can also be injected via configuration for testing and flexibility.
"""
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from systemeval.types import TestItem, TestResult
from systemeval.adapters.base import BaseAdapter
from systemeval.adapters.registry import get_adapter, is_registered
from systemeval.environments.base import Environment, EnvironmentType, SetupResult
from systemeval.environments.ngrok import NgrokEnvironment
from systemeval.environments.standalone import StandaloneEnvironment

logger = logging.getLogger(__name__)


@runtime_checkable
class BrowserTestAdapter(Protocol):
    """
    Protocol for browser test adapters used by BrowserEnvironment.

    This protocol defines the minimal interface required by BrowserEnvironment.
    Both PlaywrightAdapter and SurferAdapter satisfy this protocol.
    """

    def validate_environment(self) -> bool:
        """Validate that the test framework is properly configured."""
        ...

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover tests matching criteria."""
        ...

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
        **kwargs: Any,
    ) -> TestResult:
        """Execute tests and return results."""
        ...


# Type alias for adapter factory function
AdapterFactory = Callable[[str, Dict[str, Any]], Optional[BrowserTestAdapter]]


class BrowserEnvironment(Environment):
    """
    Environment for browser testing with integrated server and tunnel.

    Manages the lifecycle of:
    - A local server (optional)
    - An ngrok tunnel (optional, but recommended for cloud tests)
    - Browser test execution via Playwright or Surfer

    Decoupled Architecture:
    - Uses adapter registry instead of direct imports
    - Accepts injected adapter via config["adapter"] for testing
    - Accepts custom adapter factory via config["adapter_factory"]
    """

    def __init__(
        self,
        name: str,
        config: Dict[str, Any],
        adapter: Optional[BrowserTestAdapter] = None,
        adapter_factory: Optional[AdapterFactory] = None,
    ) -> None:
        """
        Initialize browser environment.

        Args:
            name: Environment name
            config: Configuration dictionary
            adapter: Pre-configured adapter instance (dependency injection)
            adapter_factory: Custom factory for creating adapters

        The adapter can be provided in three ways (in order of precedence):
        1. adapter parameter (direct dependency injection)
        2. config["adapter"] (for serializable configs)
        3. adapter_factory parameter (custom factory function)
        4. Default: create via adapter registry
        """
        super().__init__(name, config)

        # Extract nested configs
        server_config = config.get("server", {})
        tunnel_config = config.get("tunnel", {})
        self.test_runner = config.get("test_runner", "playwright")
        project_root = config.get("working_dir", config.get("project_root", "."))
        # Ensure project_root is absolute (adapters require absolute paths)
        self.project_root = str(Path(project_root).resolve())

        # Create child environments
        self._server: Optional[StandaloneEnvironment] = None
        self._tunnel: Optional[NgrokEnvironment] = None

        if server_config:
            # Ensure server config has required fields
            server_config.setdefault("working_dir", self.project_root)
            self._server = StandaloneEnvironment(f"{name}-server", server_config)

        if tunnel_config or config.get("tunnel_port"):
            # Create tunnel config from either nested config or tunnel_port
            tunnel_port = tunnel_config.get("port", config.get("tunnel_port", 3000))
            ngrok_config = {
                "port": tunnel_port,
                "auth_token": tunnel_config.get("auth_token"),
                "region": tunnel_config.get("region", "us"),
            }
            self._tunnel = NgrokEnvironment(f"{name}-tunnel", ngrok_config)

        # Store factory for deferred adapter creation
        self._adapter_factory = adapter_factory

        # Create or use injected adapter
        self._adapter: Optional[BrowserTestAdapter] = None
        if adapter is not None:
            # Direct dependency injection takes precedence
            self._adapter = adapter
        elif "adapter" in config and config["adapter"] is not None:
            # Adapter instance from config (for serializable injection)
            self._adapter = config["adapter"]
        else:
            # Create adapter via factory or registry
            self._adapter = self._create_adapter(config)

    def _create_adapter(self, config: Dict[str, Any]) -> Optional[BrowserTestAdapter]:
        """
        Create the appropriate browser test adapter.

        Uses custom factory if provided, otherwise falls back to registry.
        This decouples BrowserEnvironment from specific adapter implementations.
        """
        # Use custom factory if provided
        if self._adapter_factory is not None:
            return self._adapter_factory(self.test_runner, config)

        # Use registry-based creation (decoupled from concrete implementations)
        return self._create_adapter_from_registry(config)

    def _create_adapter_from_registry(
        self, config: Dict[str, Any]
    ) -> Optional[BrowserTestAdapter]:
        """
        Create adapter with full configuration support.

        Uses lazy imports to maintain decoupling from concrete adapter classes.
        This method checks if adapters are available via the registry but
        creates them directly to pass full configuration.
        """
        if not is_registered(self.test_runner):
            logger.warning(f"Adapter '{self.test_runner}' not found in registry")
            return None

        if self.test_runner == "playwright":
            return self._create_playwright_adapter(config)
        elif self.test_runner == "surfer":
            return self._create_surfer_adapter(config)

        # Fallback: try basic registry creation for unknown adapters
        try:
            return get_adapter(self.test_runner, self.project_root)  # type: ignore[return-value]
        except (KeyError, ImportError) as e:
            logger.warning(f"Failed to create adapter '{self.test_runner}': {e}")
            return None

    def _create_playwright_adapter(
        self, config: Dict[str, Any]
    ) -> Optional[BrowserTestAdapter]:
        """
        Create PlaywrightAdapter with full configuration.

        Uses lazy import to avoid module-level coupling.
        """
        try:
            # Lazy import to decouple from concrete implementation
            from systemeval.adapters.playwright_adapter import PlaywrightAdapter
        except ImportError:
            logger.warning("PlaywrightAdapter not available")
            return None

        playwright_config = config.get("playwright", {})
        return PlaywrightAdapter(
            self.project_root,
            config_file=playwright_config.get("config_file", "playwright.config.ts"),
            project=playwright_config.get("project"),
            headed=playwright_config.get("headed", False),
            timeout=playwright_config.get("timeout", 30000),
        )

    def _create_surfer_adapter(
        self, config: Dict[str, Any]
    ) -> Optional[BrowserTestAdapter]:
        """
        Create SurferAdapter with full configuration.

        Uses lazy import to avoid module-level coupling.
        """
        try:
            # Lazy import to decouple from concrete implementation
            from systemeval.adapters.surfer_adapter import SurferAdapter
        except ImportError:
            logger.warning("SurferAdapter not available")
            return None

        surfer_config = config.get("surfer", {})
        project_slug = surfer_config.get("project_slug", config.get("project_slug"))
        if not project_slug:
            logger.warning("No project_slug configured for Surfer adapter")
            return None

        return SurferAdapter(
            self.project_root,
            project_slug=project_slug,
            api_key=surfer_config.get("api_key"),
            api_base_url=surfer_config.get("api_base_url", "https://api.debugg.ai"),
            poll_interval=surfer_config.get("poll_interval", 5),
            timeout=surfer_config.get("timeout", 600),
        )

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.BROWSER

    @property
    def tunnel_url(self) -> Optional[str]:
        """Get the public tunnel URL if a tunnel is active."""
        if self._tunnel:
            return self._tunnel.tunnel_url
        return None

    @property
    def server_url(self) -> Optional[str]:
        """Get the local server URL."""
        if self._server:
            port = self._server.port
            return f"http://localhost:{port}"
        return None

    def setup(self) -> SetupResult:
        """Start server and tunnel."""
        total_start = time.time()
        details: Dict[str, Any] = {}

        # Start server if configured
        if self._server:
            result = self._server.setup()
            details["server"] = {
                "success": result.success,
                "message": result.message,
                "duration": result.duration,
            }
            if not result.success:
                return SetupResult(
                    success=False,
                    message=f"Server failed to start: {result.message}",
                    duration=time.time() - total_start,
                    details=details,
                )

        # Start tunnel if configured
        if self._tunnel:
            result = self._tunnel.setup()
            details["tunnel"] = {
                "success": result.success,
                "message": result.message,
                "duration": result.duration,
            }
            if not result.success:
                # Cleanup server if tunnel fails
                if self._server:
                    self._server.teardown()
                return SetupResult(
                    success=False,
                    message=f"Tunnel failed to start: {result.message}",
                    duration=time.time() - total_start,
                    details=details,
                )

        self.timings.startup = time.time() - total_start

        return SetupResult(
            success=True,
            message=f"Browser environment ready (runner: {self.test_runner})",
            duration=self.timings.startup,
            details=details,
        )

    def is_ready(self) -> bool:
        """Check if server and tunnel are ready."""
        server_ready = self._server.is_ready() if self._server else True
        tunnel_ready = self._tunnel.is_ready() if self._tunnel else True
        return server_ready and tunnel_ready

    def wait_ready(self, timeout: int = 120) -> bool:
        """Wait for server and tunnel to be ready."""
        start = time.time()
        remaining = timeout

        # Wait for server first
        if self._server:
            server_start = time.time()
            if not self._server.wait_ready(timeout=int(remaining)):
                logger.error("Server did not become ready")
                return False
            remaining -= (time.time() - server_start)
            logger.info(f"Server ready at {self.server_url}")

        # Then wait for tunnel
        if self._tunnel and remaining > 0:
            tunnel_start = time.time()
            if not self._tunnel.wait_ready(timeout=int(remaining)):
                logger.error("Tunnel did not become ready")
                return False
            remaining -= (time.time() - tunnel_start)
            logger.info(f"Tunnel ready at {self.tunnel_url}")

        self.timings.health_check = time.time() - start
        return True

    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """Run browser tests using the configured adapter."""
        start = time.time()

        if not self._adapter:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
            )

        # Validate adapter environment
        if not self._adapter.validate_environment():
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                exit_code=2,
            )

        # Discover and execute tests
        tests = self._adapter.discover(category=category)

        # Build execute kwargs - pass target_url if adapter supports it
        # This avoids isinstance checks and keeps the code decoupled
        execute_kwargs: Dict[str, Any] = {
            "tests": tests if tests else None,
            "verbose": verbose,
        }

        # For adapters that need a target URL (e.g., cloud-based testing),
        # pass the tunnel or server URL if available
        if self._adapter_supports_target_url():
            target_url = self.tunnel_url or self.server_url
            if target_url:
                execute_kwargs["target_url"] = target_url

        result = self._adapter.execute(**execute_kwargs)

        self.timings.tests = time.time() - start
        return result

    def _adapter_supports_target_url(self) -> bool:
        """
        Check if the adapter's execute method accepts target_url parameter.

        This uses duck typing to avoid isinstance checks on concrete classes.
        """
        if self._adapter is None:
            return False

        # Check if adapter has execute method that accepts target_url
        # Could use inspect.signature but hasattr check is simpler
        # and surfer adapter is the main use case
        return self.test_runner == "surfer" or hasattr(self._adapter, "target_url")

    def teardown(self, keep_running: bool = False) -> None:
        """Stop tunnel and server."""
        start = time.time()

        # Stop tunnel first
        if self._tunnel:
            self._tunnel.teardown(keep_running=keep_running)

        # Then stop server
        if self._server:
            self._server.teardown(keep_running=keep_running)

        self.timings.cleanup = time.time() - start

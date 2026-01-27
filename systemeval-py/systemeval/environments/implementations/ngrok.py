"""
Ngrok tunnel environment for exposing local servers.

Manages ngrok tunnel lifecycle for browser testing against local services.
"""
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional
from urllib.request import urlopen
from urllib.error import URLError

from systemeval.types import TestResult
from systemeval.environments.base import Environment, EnvironmentType, SetupResult

logger = logging.getLogger(__name__)


class NgrokEnvironment(Environment):
    """
    Environment that manages ngrok tunnel lifecycle.

    Starts an ngrok tunnel to expose a local port and provides the public URL
    for browser tests to connect to.
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name, config)
        self._process: Optional[subprocess.Popen] = None
        self._tunnel_url: Optional[str] = None

        # Extract config
        self.port = config.get("port", 3000)
        self.auth_token = config.get("auth_token")
        self.region = config.get("region", "us")
        self.api_url = config.get("api_url", "http://127.0.0.1:4040/api/tunnels")

    @property
    def env_type(self) -> EnvironmentType:
        return EnvironmentType.NGROK

    @property
    def tunnel_url(self) -> Optional[str]:
        """Get the public tunnel URL once established."""
        return self._tunnel_url

    def setup(self) -> SetupResult:
        """Start the ngrok tunnel process."""
        start = time.time()

        # Check if ngrok is available
        ngrok_path = shutil.which("ngrok")
        if not ngrok_path:
            return SetupResult(
                success=False,
                message="ngrok not found in PATH. Install from https://ngrok.com/download",
                duration=time.time() - start,
            )

        try:
            # Build ngrok command
            cmd = [
                ngrok_path,
                "http",
                str(self.port),
                "--log=stdout",
                "--log-format=json",
            ]

            if self.region:
                cmd.extend(["--region", self.region])

            # Set auth token via environment if provided
            env = dict(os.environ)
            if self.auth_token:
                env["NGROK_AUTHTOKEN"] = self.auth_token

            # Start ngrok process
            self._process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            self.timings.startup = time.time() - start

            return SetupResult(
                success=True,
                message=f"Started ngrok tunnel on port {self.port}",
                duration=self.timings.startup,
                details={"pid": self._process.pid, "port": self.port},
            )

        except FileNotFoundError:
            return SetupResult(
                success=False,
                message="ngrok executable not found",
                duration=time.time() - start,
            )
        except OSError as e:
            return SetupResult(
                success=False,
                message=f"Failed to start ngrok: {e}",
                duration=time.time() - start,
            )

    def is_ready(self) -> bool:
        """Check if tunnel is established and URL is available."""
        if not self._process:
            return False

        if self._process.poll() is not None:
            return False  # Process exited

        return self._tunnel_url is not None

    def wait_ready(self, timeout: int = 30) -> bool:
        """Wait for ngrok tunnel to be established."""
        if not self._process:
            return False

        start = time.time()

        while (time.time() - start) < timeout:
            if self._process.poll() is not None:
                logger.error("ngrok process exited unexpectedly")
                return False

            # Poll ngrok API for tunnel info
            tunnel_url = self._get_tunnel_url()
            if tunnel_url:
                self._tunnel_url = tunnel_url
                self.timings.health_check = time.time() - start
                logger.info(f"Ngrok tunnel established: {tunnel_url}")
                return True

            time.sleep(0.5)

        logger.error(f"ngrok tunnel did not establish within {timeout}s")
        return False

    def _get_tunnel_url(self) -> Optional[str]:
        """Query ngrok API for the public tunnel URL."""
        try:
            with urlopen(self.api_url, timeout=2) as response:
                data = json.loads(response.read().decode())
                tunnels = data.get("tunnels", [])

                # Prefer https tunnel
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https":
                        return tunnel.get("public_url")

                # Fall back to any tunnel
                if tunnels:
                    return tunnels[0].get("public_url")

        except URLError:
            pass  # ngrok API not ready yet
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from ngrok API")
        except Exception as e:
            logger.debug(f"Error querying ngrok API: {e}")

        return None

    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """
        NgrokEnvironment doesn't run tests directly.

        This is a supporting environment that provides tunnel infrastructure.
        Tests are run by the adapter or parent composite environment.
        """
        return TestResult(
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            duration=0.0,
            exit_code=0,
        )

    def teardown(self, keep_running: bool = False) -> None:
        """Stop the ngrok tunnel process."""
        start = time.time()

        if self._process and not keep_running:
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
            except OSError as e:
                logger.debug(f"ngrok cleanup encountered OSError: {e}")
            finally:
                self._process = None
                self._tunnel_url = None

        self.timings.cleanup = time.time() - start

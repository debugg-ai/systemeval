"""Base formatter protocol and CLI progress callback."""

from typing import Any, Callable, Dict, Optional, Protocol
from rich.console import Console

from systemeval.types import TestResult
from systemeval.config import MultiProjectResult


class OutputFormatter(Protocol):
    """Protocol for output formatters.

    All formatters must implement this protocol to provide consistent
    output formatting across different result types.
    """

    def format_single_result(self, result: TestResult) -> str:
        """Format a single test result.

        Args:
            result: TestResult to format.

        Returns:
            Formatted string output.
        """
        ...

    def format_multi_project_result(self, result: "MultiProjectResult") -> str:
        """Format multi-project test results.

        Args:
            result: MultiProjectResult to format.

        Returns:
            Formatted string output.
        """
        ...


class CLIProgressCallback:
    """Progress callback that wraps console.print calls.

    This class provides progress reporting during test execution,
    using Rich console for formatted output. It can be suppressed
    when using non-interactive output modes (JSON, templates).

    Attributes:
        console: Rich Console instance for output.
        enabled: Whether progress messages should be printed.
    """

    def __init__(self, console: Console, enabled: bool = True):
        """Initialize the progress callback.

        Args:
            console: Rich Console instance.
            enabled: Whether to enable progress output (default: True).
        """
        self.console = console
        self.enabled = enabled

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Print a message if enabled.

        Args:
            *args: Positional arguments to pass to console.print.
            **kwargs: Keyword arguments to pass to console.print.
        """
        if self.enabled:
            self.console.print(*args, **kwargs)

    def print_subproject_header(self, name: str, adapter: str) -> None:
        """Print subproject execution header.

        Args:
            name: Subproject name.
            adapter: Adapter type.
        """
        self.print(f"[bold]▶ {name}[/bold] ({adapter})")

    def print_subproject_result(
        self,
        status: str,
        passed: int,
        failed: int,
        duration: float,
    ) -> None:
        """Print subproject execution result.

        Args:
            status: Test status (PASS, FAIL, ERROR).
            passed: Number of passed tests.
            failed: Number of failed tests.
            duration: Execution duration in seconds.
        """
        status_icon = "✓" if status == "PASS" else "✗"
        status_color = "green" if status == "PASS" else "red"
        self.print(
            f"  [{status_color}]{status_icon}[/{status_color}] "
            f"{passed} passed, {failed} failed ({duration:.1f}s)"
        )

    def print_error(self, message: str) -> None:
        """Print an error message.

        Args:
            message: Error message to display.
        """
        self.print(f"[red]✗ {message}[/red]")

    def print_pre_command(self, command: str) -> None:
        """Print pre-command execution message.

        Args:
            command: Command being executed.
        """
        self.print(f"  [dim]Running: {command}[/dim]")

    def print_environment_setup(self, env_name: str, env_type: str) -> None:
        """Print environment setup message.

        Args:
            env_name: Environment name.
            env_type: Environment type.
        """
        self.print(
            f"[bold cyan]Running tests in '{env_name}' environment ({env_type})[/bold cyan]"
        )

    def print_suite_info(self, suite: str) -> None:
        """Print test suite information.

        Args:
            suite: Test suite name.
        """
        self.print(f"[dim]Suite: {suite}[/dim]")

    def print_status(self, message: str) -> None:
        """Print a status message.

        Args:
            message: Status message to display.
        """
        self.print(f"[dim]{message}[/dim]")

    def print_success(self, message: str, duration: Optional[float] = None) -> None:
        """Print a success message.

        Args:
            message: Success message to display.
            duration: Optional duration in seconds to append.
        """
        if duration is not None:
            self.print(f"[green]{message}[/green] ({duration:.1f}s)")
        else:
            self.print(f"[green]{message}[/green]")

    def print_warning(self, message: str) -> None:
        """Print a warning message.

        Args:
            message: Warning message to display.
        """
        self.print(f"[yellow]{message}[/yellow]")

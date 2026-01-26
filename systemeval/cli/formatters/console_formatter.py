"""Console formatter using Rich for formatted output."""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from systemeval.types import TestResult, Verdict

if TYPE_CHECKING:
    from systemeval.config import MultiProjectResult


class ConsoleFormatter:
    """Formats test results for Rich console output.

    This formatter produces human-readable output with colors, tables,
    and formatting using the Rich library.

    Attributes:
        console: Rich Console instance for output.
    """

    def __init__(self, console: Console):
        """Initialize the console formatter.

        Args:
            console: Rich Console instance to use for output.
        """
        self.console = console

    def format_single_result(self, result: TestResult) -> str:
        """Format a single test result as a Rich table.

        Args:
            result: TestResult to format.

        Returns:
            Empty string (output is printed directly to console).
        """
        self._display_results(result)
        return ""

    def format_multi_project_result(self, result: "MultiProjectResult") -> str:
        """Format multi-project results as a Rich table.

        Args:
            result: MultiProjectResult to format.

        Returns:
            Empty string (output is printed directly to console).
        """
        self._display_multi_project_table(result)
        return ""

    def _display_results(self, results: TestResult) -> None:
        """Display test results in a formatted table.

        Args:
            results: TestResult object with test execution data.
        """
        # Summary table
        table = Table(title="Test Results Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")

        # Verdict first - most important
        verdict = results.verdict
        if verdict == Verdict.PASS:
            table.add_row("Verdict", "[green bold]PASS[/green bold]")
        elif verdict == Verdict.FAIL:
            table.add_row("Verdict", "[red bold]FAIL[/red bold]")
        else:
            table.add_row("Verdict", "[yellow bold]ERROR[/yellow bold]")

        table.add_row("Category", results.category or "default")
        table.add_row("Total", str(results.total))
        table.add_row("Passed", f"[green]{results.passed}[/green]")
        table.add_row(
            "Failed",
            f"[red]{results.failed}[/red]" if results.failed > 0 else "0"
        )
        table.add_row("Skipped", str(results.skipped))
        table.add_row(
            "Errors",
            f"[red]{results.errors}[/red]" if results.errors > 0 else "0"
        )

        if results.duration:
            table.add_row("Duration", f"{results.duration:.2f}s")

        if results.coverage_percent is not None:
            coverage_color = "green" if results.coverage_percent >= 80 else "yellow"
            table.add_row(
                "Coverage",
                f"[{coverage_color}]{results.coverage_percent:.1f}%[/{coverage_color}]"
            )

        table.add_row("Exit Code", str(results.exit_code))

        self.console.print(table)

        # Overall result banner
        if verdict == Verdict.ERROR:
            self.console.print("\n[yellow bold]======== ERROR ========[/yellow bold]")
        elif verdict == Verdict.FAIL:
            self.console.print("\n[red bold]======== FAILED ========[/red bold]")
        else:
            self.console.print("\n[green bold]======== PASSED ========[/green bold]")

    def _display_multi_project_table(self, result: "MultiProjectResult") -> None:
        """Display multi-project results as a Rich table.

        Args:
            result: Aggregated multi-project results.
        """
        self.console.print()

        # Create table
        table = Table(
            title="Multi-Project Test Results",
            show_header=True,
            header_style="bold"
        )
        table.add_column("Subproject", style="cyan")
        table.add_column("Adapter", style="dim")
        table.add_column("Passed", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Status", justify="center")

        for sp in result.subprojects:
            status_style = (
                "green" if sp.status == "PASS"
                else "yellow" if sp.status == "SKIP"
                else "red"
            )
            table.add_row(
                sp.name,
                sp.adapter,
                str(sp.passed) if sp.status != "SKIP" else "--",
                str(sp.failed) if sp.status != "SKIP" else "--",
                f"[{status_style}]{sp.status}[/{status_style}]",
            )

        # Add totals row
        table.add_section()
        verdict_style = "green" if result.verdict == "PASS" else "red"
        table.add_row(
            "[bold]TOTAL[/bold]",
            "",
            f"[bold]{result.total_passed}[/bold]",
            f"[bold]{result.total_failed}[/bold]",
            f"[bold {verdict_style}]{result.verdict}[/bold {verdict_style}]",
        )

        self.console.print(table)
        self.console.print()

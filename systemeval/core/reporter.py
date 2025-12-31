"""
Unified output formatting and reporting.

Uses rich library for beautiful terminal output with color-coded results.
Supports multiple output formats: table, json, junit.

SCHEMA HIERARCHY:
- Reporter uses EvaluationResult (from evaluation.py) as the primary schema
- EvaluationResult is the SINGULAR output format for all evaluations
- Legacy SequenceResult/SessionResult from result.py are DEPRECATED
"""

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .evaluation import EvaluationResult, Verdict


class Reporter:
    """
    Unified reporter for test results.

    Supports multiple output formats with consistent styling.
    """

    def __init__(
        self,
        format: str = "table",
        verbose: bool = False,
        colors: bool = True,
        show_passed: bool = False,
        show_metrics: bool = True,
    ):
        """
        Initialize reporter.

        Args:
            format: Output format (table, json, junit)
            verbose: Show detailed output
            colors: Enable color output
            show_passed: Show passed sessions (default: only failures)
            show_metrics: Show metric details
        """
        self.format = format
        self.verbose = verbose
        self.show_passed = show_passed
        self.show_metrics = show_metrics
        self.console = Console(force_terminal=colors, no_color=not colors)

    def report(self, result: EvaluationResult, output_file: Optional[Path] = None) -> None:
        """
        Generate and output test report.

        Args:
            result: EvaluationResult to report
            output_file: Optional file to write output to
        """
        if self.format == "json":
            self._report_json(result, output_file)
        elif self.format == "junit":
            self._report_junit(result, output_file)
        else:
            self._report_table(result, output_file)

    def _report_table(self, result: EvaluationResult, output_file: Optional[Path] = None) -> None:
        """Generate table format output using rich."""
        # Header
        verdict_color = "green" if result.verdict == Verdict.PASS else "red"
        header = Text(f"\n{'='*70}\n", style="bold")
        evaluation_name = result.metadata.project_name or result.metadata.adapter_type or "Evaluation"
        header.append(f" {evaluation_name.upper()}\n", style=f"bold {verdict_color}")
        header.append(f"{'='*70}\n", style="bold")
        self.console.print(header)

        # Summary
        duration = result.metadata.duration_seconds or 0
        summary = result.summary
        summary_lines = [
            f"Verdict: {result.verdict.value}",
            f"Duration: {duration:.1f}s",
            f"Sessions: {summary['passed_sessions']}/{summary['total_sessions']} passed",
        ]

        if result.verdict == Verdict.PASS:
            self.console.print(Panel("\n".join(summary_lines), style="green", title="PASS"))
        else:
            self.console.print(Panel("\n".join(summary_lines), style="red", title="FAIL"))

        # Sessions table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Session", style="cyan", width=30)
        table.add_column("Verdict", justify="center", width=10)
        table.add_column("Duration", justify="right", width=10)

        if self.show_metrics:
            table.add_column("Metrics", justify="right", width=10)
            table.add_column("Failed", width=40)

        for session in result.sessions:
            # Skip passed sessions if not verbose
            if not self.show_passed and session.verdict == Verdict.PASS:
                continue

            verdict_text = Text(
                session.verdict.value,
                style="green" if session.verdict == Verdict.PASS else "red"
            )

            duration_text = f"{session.duration_seconds:.1f}s" if session.duration_seconds else "N/A"

            if self.show_metrics:
                metrics_text = f"{len([m for m in session.metrics if m.passed])}/{len(session.metrics)}"
                failed_text = ", ".join([m.name for m in session.failed_metrics][:3])
                if len(session.failed_metrics) > 3:
                    failed_text += f" +{len(session.failed_metrics) - 3} more"

                table.add_row(
                    session.session_name,
                    verdict_text,
                    duration_text,
                    metrics_text,
                    failed_text or "-"
                )
            else:
                table.add_row(
                    session.session_name,
                    verdict_text,
                    duration_text,
                )

        self.console.print(table)

        # Detailed failures (if verbose)
        if self.verbose and result.failed_sessions:
            self.console.print("\n[bold red]Failed Sessions Details:[/bold red]\n")
            for session in result.failed_sessions:
                self._print_session_details(session)

        # Footer
        self.console.print(f"\n{'='*70}")
        self.console.print(f"Exit code: {result.exit_code}", style="bold")
        self.console.print(f"{'='*70}\n")

    def _print_session_details(self, session) -> None:
        """Print detailed metrics for a failed session."""
        self.console.print(f"\n[bold cyan]{session.session_name}[/bold cyan]")

        for metric in session.failed_metrics:
            self.console.print(f"  [red]✗[/red] {metric.name}: {metric.value}")
            if metric.message:
                self.console.print(f"    {metric.message}", style="dim")

    def _report_json(self, result: EvaluationResult, output_file: Optional[Path] = None) -> None:
        """Generate JSON format output."""
        output = result.to_json(indent=2)

        if output_file:
            output_file.write_text(output)
            self.console.print(f"JSON report written to: {output_file}")
        else:
            self.console.print(output)

    def _report_junit(self, result: EvaluationResult, output_file: Optional[Path] = None) -> None:
        """Generate JUnit XML format output."""
        # JUnit XML structure
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']

        summary = result.summary
        failures = summary['failed_sessions'] + summary['error_sessions']
        tests = summary['total_sessions']
        duration = result.metadata.duration_seconds or 0
        suite_name = result.metadata.project_name or result.metadata.adapter_type or "Evaluation"

        xml_lines.append(
            f'<testsuites name="{suite_name}" '
            f'tests="{tests}" failures="{failures}" time="{duration:.3f}">'
        )

        for session in result.sessions:
            session_duration = session.duration_seconds or 0
            status = "failure" if session.verdict != Verdict.PASS else "success"

            xml_lines.append(
                f'  <testsuite name="{session.session_name}" '
                f'tests="{len(session.metrics)}" failures="{len(session.failed_metrics)}" '
                f'time="{session_duration:.3f}">'
            )

            for metric in session.metrics:
                xml_lines.append(f'    <testcase name="{metric.name}" status="{status}">')

                if not metric.passed:
                    xml_lines.append(
                        f'      <failure message="{metric.message or "Failed"}">'
                    )
                    xml_lines.append(f'Value: {metric.value}')
                    xml_lines.append('      </failure>')

                xml_lines.append('    </testcase>')

            xml_lines.append('  </testsuite>')

        xml_lines.append('</testsuites>')

        output = "\n".join(xml_lines)

        if output_file:
            output_file.write_text(output)
            self.console.print(f"JUnit XML report written to: {output_file}")
        else:
            self.console.print(output)

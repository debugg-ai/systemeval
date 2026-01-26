"""
SystemEval CLI - Unified test runner with framework-agnostic adapters.
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from systemeval.config import (
    SystemEvalConfig,
    load_config,
    find_config_file,
    SubprojectConfig,
    SubprojectResult,
    MultiProjectResult,
    get_subproject_absolute_path,
)
from systemeval.adapters import get_adapter
from systemeval.types import (
    AdapterConfig,
    TestResult,
    TestCommandOptions,
)
from systemeval.utils.docker import get_environment_type
from systemeval.cli_helpers import run_browser_tests, run_multi_project_tests

# Import modular command registration functions
from systemeval.cli.commands import (
    register_config_commands,
    register_list_commands,
    e2e,
)
from systemeval.cli.formatters import create_formatter

console = Console()

def _run_single_subproject(
    root_config: "SystemEvalConfig",
    subproject: "SubprojectConfig",
    opts: TestCommandOptions,
) -> "SubprojectResult":
    """Run tests for a single subproject.

    Args:
        root_config: Root SystemEval configuration.
        subproject: The subproject configuration to run.
        opts: Grouped CLI options.

    Returns:
        SubprojectResult with test results for this subproject.
    """
    verbose = opts.execution.verbose
    json_output = opts.output.json_output
    failfast = opts.execution.failfast
    parallel = opts.execution.parallel
    coverage = opts.execution.coverage

    sp_path = get_subproject_absolute_path(root_config, subproject)

    if not json_output:
        console.print(f"[bold]▶ {subproject.name}[/bold] ({subproject.adapter})")

    # Check if subproject path exists
    if not sp_path.exists():
        if not json_output:
            console.print(f"  [red]✗ Path not found: {sp_path}[/red]")
        return SubprojectResult(
            name=subproject.name,
            adapter=subproject.adapter,
            status="ERROR",
            error_message=f"Subproject path not found: {sp_path}",
        )

    # Run pre_commands if defined
    if subproject.pre_commands:
        for cmd in subproject.pre_commands:
            if verbose and not json_output:
                console.print(f"  [dim]Running: {cmd}[/dim]")
            try:
                subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(sp_path),
                    check=True,
                    capture_output=not verbose,
                    env={**os.environ, **subproject.env},
                )
            except subprocess.CalledProcessError as e:
                if not json_output:
                    console.print(f"  [red]✗ Pre-command failed: {cmd}[/red]")
                return SubprojectResult(
                    name=subproject.name,
                    adapter=subproject.adapter,
                    status="ERROR",
                    error_message=f"Pre-command failed: {cmd}",
                )

    # Get adapter for this subproject
    try:
        # Create adapter config with subproject settings
        adapter_config = AdapterConfig(
            project_root=str(sp_path),
            test_directory=subproject.test_directory,
            parallel=parallel,
            coverage=coverage,
            timeout=root_config.get_effective_timeout(subproject),
            extra={
                "config_file": subproject.config_file,
                **subproject.options,
            },
        )

        # Get adapter - handle special cases
        adapter_name = subproject.adapter
        if adapter_name == "pytest-django":
            adapter_name = "pytest"  # pytest-django uses pytest adapter with Django settings

        adapter = get_adapter(adapter_name, str(sp_path))

    except (KeyError, ValueError) as e:
        if not json_output:
            console.print(f"  [red]✗ Adapter error: {e}[/red]")
        return SubprojectResult(
            name=subproject.name,
            adapter=subproject.adapter,
            status="ERROR",
            error_message=f"Adapter error: {e}",
        )

    # Set up environment variables
    env_backup = {}
    for key, value in subproject.env.items():
        env_backup[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        # Run tests
        start_time = time.time()
        test_result = adapter.execute(
            tests=None,
            parallel=parallel,
            coverage=coverage,
            failfast=failfast,
            verbose=verbose,
        )
        duration = time.time() - start_time

        # Convert TestResult to SubprojectResult
        sp_result = SubprojectResult(
            name=subproject.name,
            adapter=subproject.adapter,
            passed=test_result.passed,
            failed=test_result.failed,
            errors=test_result.errors,
            skipped=test_result.skipped,
            duration=duration,
            status="PASS" if test_result.verdict.value == "PASS" else (
                "ERROR" if test_result.verdict.value == "ERROR" else "FAIL"
            ),
            failures=[
                {
                    "test": f.test_id,
                    "name": f.test_name,
                    "message": f.message,
                }
                for f in test_result.failures
            ],
        )

        # Display result
        if not json_output:
            status_icon = "✓" if sp_result.status == "PASS" else "✗"
            status_color = "green" if sp_result.status == "PASS" else "red"
            console.print(
                f"  [{status_color}]{status_icon}[/{status_color}] "
                f"{sp_result.passed} passed, {sp_result.failed} failed "
                f"({sp_result.duration:.1f}s)"
            )

        return sp_result

    except Exception as e:
        if not json_output:
            console.print(f"  [red]✗ Execution error: {e}[/red]")
        return SubprojectResult(
            name=subproject.name,
            adapter=subproject.adapter,
            status="ERROR",
            error_message=str(e),
        )

    finally:
        # Restore environment variables
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _output_multi_project_results(
    result: "MultiProjectResult",
    opts: TestCommandOptions,
) -> None:
    """Output multi-project results in the appropriate format.

    Args:
        result: Aggregated multi-project results.
        opts: CLI options including output format.
    """
    json_output = opts.output.json_output
    template = opts.output.template

    if json_output:
        # Output JSON for CI
        console.print(json.dumps(result.to_json_dict(), indent=2))
    elif template:
        # Template output - could be extended for multi-project templates
        console.print(f"[yellow]Template output not yet implemented for multi-project mode[/yellow]")
        _display_multi_project_table(result)
    else:
        # Default: Rich table output
        _display_multi_project_table(result)


def _display_multi_project_table(result: "MultiProjectResult") -> None:
    """Display multi-project results as a Rich table.

    Args:
        result: Aggregated multi-project results.
    """
    console.print()

    # Create table
    table = Table(title="Multi-Project Test Results", show_header=True, header_style="bold")
    table.add_column("Subproject", style="cyan")
    table.add_column("Adapter", style="dim")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Status", justify="center")

    for sp in result.subprojects:
        status_style = "green" if sp.status == "PASS" else ("yellow" if sp.status == "SKIP" else "red")
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

    console.print(table)
    console.print()


def _run_with_environment(
    test_config: "SystemEvalConfig",
    opts: TestCommandOptions,
) -> "TestResult":
    """Run tests using environment orchestration.

    Args:
        test_config: Loaded SystemEval configuration.
        opts: Grouped CLI options for the test command.
    """
    from systemeval.environments import EnvironmentResolver

    # Extract options from grouped dataclasses
    env_name = opts.environment.env_name
    suite = opts.selection.suite
    category = opts.selection.category
    verbose = opts.execution.verbose
    keep_running = opts.environment.keep_running
    skip_build = opts.pipeline.skip_build
    json_output = opts.output.json_output

    # Resolve environment
    resolver = EnvironmentResolver(test_config.environments)

    if not test_config.environments:
        console.print("[red]Error:[/red] No environments configured in systemeval.yaml")
        console.print("Add an 'environments' section to your configuration")
        sys.exit(2)

    # Get environment name
    if not env_name:
        env_name = resolver.get_default_environment()
        if not env_name:
            console.print("[red]Error:[/red] No default environment found")
            sys.exit(2)

    try:
        env = resolver.resolve(env_name)
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e}")
        available = ", ".join(resolver.list_environments().keys())
        console.print(f"Available environments: {available}")
        sys.exit(2)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)

    # Inject skip_build if applicable
    if skip_build and hasattr(env, 'skip_build'):
        env.skip_build = skip_build

    if not json_output:
        console.print(f"[bold cyan]Running tests in '{env_name}' environment ({env.env_type.value})[/bold cyan]")
        if suite:
            console.print(f"[dim]Suite: {suite}[/dim]")
        console.print()

    # Run with context manager for clean setup/teardown
    try:
        if not json_output:
            console.print("[dim]Setting up environment...[/dim]")

        setup_result = env.setup()
        if not setup_result.success:
            console.print(f"[red]Setup failed:[/red] {setup_result.message}")
            from systemeval.adapters import TestResult
            return TestResult(
                passed=0, failed=0, errors=1, skipped=0,
                duration=setup_result.duration, exit_code=2
            )

        if not json_output:
            console.print(f"[green]Environment started[/green] ({setup_result.duration:.1f}s)")
            console.print("[dim]Waiting for services to be ready...[/dim]")

        if not env.wait_ready():
            console.print("[red]Error:[/red] Environment did not become ready within timeout")
            env.teardown()
            from systemeval.adapters import TestResult
            return TestResult(
                passed=0, failed=0, errors=1, skipped=0,
                duration=env.timings.startup + env.timings.health_check,
                exit_code=2
            )

        if not json_output:
            console.print(f"[green]Services ready[/green] ({env.timings.health_check:.1f}s)")
            console.print("[dim]Running tests...[/dim]")
            console.print()

        # Run tests
        results = env.run_tests(suite=suite, category=category, verbose=verbose)

        return results

    finally:
        if not keep_running:
            if not json_output:
                console.print()
                console.print("[dim]Tearing down environment...[/dim]")
            env.teardown(keep_running=keep_running)
            if not json_output:
                console.print(f"[dim]Cleanup complete ({env.timings.cleanup:.1f}s)[/dim]")
        else:
            if not json_output:
                console.print()
                console.print("[yellow]Keeping environment running (--keep-running)[/yellow]")


@click.group()
@click.version_option(version=None, package_name="systemeval")
def main() -> None:
    """SystemEval - Unified test runner CLI."""
    pass


# Register modular command groups
register_config_commands(main, console)
register_list_commands(main, console)
main.add_command(e2e)


def _execute_test_command(
    test_config: "SystemEvalConfig",
    opts: TestCommandOptions,
    config_path: Path,
) -> None:
    """Execute the test command with grouped options.

    This is the internal implementation that receives grouped options.
    The public test() function handles CLI argument parsing and conversion.

    Args:
        test_config: Loaded SystemEval configuration.
        opts: Grouped CLI options for the test command.
        config_path: Path to the configuration file.
    """
    # Extract commonly used options
    verbose = opts.execution.verbose
    json_output = opts.output.json_output
    category = opts.selection.category
    template = opts.output.template

    # Determine execution environment based on env_mode
    env_mode = opts.environment.env_mode
    if env_mode == 'docker':
        environment = "docker"
    elif env_mode == 'local':
        environment = "local"
    else:  # 'auto' (default)
        environment = get_environment_type()

    if verbose:
        console.print(f"[dim]Environment: {environment}[/dim]")
        console.print(f"[dim]Config: {config_path}[/dim]")

    # Check for multi-project mode (v2.0)
    if test_config.is_multi_project:
        multi_result = run_multi_project_tests(test_config=test_config, opts=opts)
        _output_multi_project_results(multi_result, opts)
        # Exit with appropriate code based on verdict
        if multi_result.verdict == "PASS":
            sys.exit(0)
        elif multi_result.verdict == "ERROR":
            sys.exit(2)
        else:
            sys.exit(1)

    # Handle browser testing mode
    if opts.browser_opts.browser or opts.browser_opts.surfer:
        results = run_browser_tests(test_config=test_config, opts=opts)
    # Check if using environment-based testing
    elif opts.environment.env_name or test_config.environments:
        results = _run_with_environment(test_config=test_config, opts=opts)
    else:
        # Legacy adapter-based testing
        results = _run_legacy_adapter_tests(test_config=test_config, opts=opts)

    # Set category on results for output
    results.category = category or "default"

    # Output results
    if json_output:
        # Check for pipeline adapter's detailed evaluation
        if hasattr(results, 'pipeline_adapter') and hasattr(results, 'pipeline_tests'):
            evaluation = results.pipeline_adapter.create_evaluation_result(
                tests=results.pipeline_tests,
                results_by_project=results.pipeline_metrics,
                duration=results.duration,
            )
        else:
            # Convert to unified EvaluationResult schema
            evaluation = results.to_evaluation(
                adapter_type=test_config.adapter,
                project_name=test_config.project_root.name if test_config.project_root else None,
            )
            evaluation.finalize()
        console.print(evaluation.to_json())
    elif template:
        from systemeval.templates import render_results
        output = render_results(results, template_name=template)
        console.print(output)
    else:
        _display_results(results)

    # Exit with appropriate code
    sys.exit(results.exit_code)


def _run_legacy_adapter_tests(
    test_config: "SystemEvalConfig",
    opts: TestCommandOptions,
) -> "TestResult":
    """Run tests using legacy adapter-based testing.

    Args:
        test_config: Loaded SystemEval configuration.
        opts: Grouped CLI options for the test command.
    """
    # Extract options
    category = opts.selection.category
    app = opts.selection.app
    file_path = opts.selection.file_path
    parallel = opts.execution.parallel
    coverage = opts.execution.coverage
    failfast = opts.execution.failfast
    verbose = opts.execution.verbose
    json_output = opts.output.json_output
    projects = opts.pipeline.projects
    timeout = opts.pipeline.timeout
    poll_interval = opts.pipeline.poll_interval
    sync = opts.pipeline.sync
    skip_build = opts.pipeline.skip_build

    # Get adapter
    try:
        adapter = get_adapter(test_config.adapter, str(test_config.project_root.absolute()))
    except (KeyError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)

    # Validate environment
    if not adapter.validate_environment():
        console.print("[yellow]Warning:[/yellow] Test environment validation failed")

    # Run tests
    if not json_output:
        console.print(f"[bold cyan]Running tests with {test_config.adapter} adapter[/bold cyan]")
        if category:
            console.print(f"[dim]Category: {category}[/dim]")
        if app:
            console.print(f"[dim]App: {app}[/dim]")
        if file_path:
            console.print(f"[dim]File: {file_path}[/dim]")
        console.print()

    # Build execution kwargs
    exec_kwargs = {
        "tests": None,  # Will use category/app/file filters in future
        "parallel": parallel,
        "coverage": coverage,
        "failfast": failfast,
        "verbose": verbose,
    }

    # Add pipeline-specific options if using pipeline adapter
    if test_config.adapter == "pipeline":
        if projects:
            exec_kwargs["projects"] = list(projects)
        if timeout:
            exec_kwargs["timeout"] = timeout
        if poll_interval:
            exec_kwargs["poll_interval"] = poll_interval
        exec_kwargs["sync_mode"] = sync
        exec_kwargs["skip_build"] = skip_build

    # Execute tests using adapter
    return adapter.execute(**exec_kwargs)


@main.command()
@click.option('--category', '-c', help='Test category to run (unit, integration, api, pipeline)')
@click.option('--app', '-a', help='Specific app/module to test')
@click.option('--file', '-f', 'file_path', help='Specific test file to run')
@click.option('--parallel', '-p', is_flag=True, help='Run tests in parallel')
@click.option('--coverage', is_flag=True, help='Collect coverage data')
@click.option('--failfast', '-x', is_flag=True, help='Stop on first failure')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--json', 'json_output', is_flag=True, help='Output results as JSON')
@click.option('--template', '-t', help='Output template (summary, markdown, ci, github, junit, slack, table, pipeline_*)')
@click.option(
    '--env-mode',
    type=click.Choice(['auto', 'docker', 'local'], case_sensitive=False),
    default='auto',
    help='Execution environment: auto (detect), docker (force Docker), local (force local host)'
)
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
# Environment orchestration options
@click.option('--env', '-e', 'env_name', help='Environment to run tests in (backend, frontend, full-stack)')
@click.option('--suite', '-s', help='Test suite to run (e2e, integration, unit)')
@click.option('--keep-running', is_flag=True, help='Keep containers/services running after tests')
# Pipeline adapter specific options
@click.option('--projects', multiple=True, help='Project slugs to evaluate (pipeline adapter)')
@click.option('--timeout', type=int, help='Max wait time per project in seconds (pipeline adapter)')
@click.option('--poll-interval', type=int, help='Seconds between status checks (pipeline adapter)')
@click.option('--sync', is_flag=True, help='Run webhooks synchronously (pipeline adapter)')
@click.option('--skip-build', is_flag=True, help='Skip build, use existing containers (pipeline adapter)')
# Browser testing options
@click.option('--browser', is_flag=True, help='Run Playwright browser tests')
@click.option('--surfer', is_flag=True, help='Run DebuggAI Surfer cloud E2E tests')
@click.option('--tunnel-port', type=int, help='Port to expose via ngrok tunnel for browser tests')
@click.option('--headed', is_flag=True, help='Run browser tests in headed mode (Playwright only)')
# Multi-project options (v2.0)
@click.option('--project', 'subprojects', multiple=True, help='Specific subproject(s) to run (v2.0 multi-project mode)')
@click.option('--tags', multiple=True, help='Only run subprojects with these tags (v2.0)')
@click.option('--exclude-tags', multiple=True, help='Exclude subprojects with these tags (v2.0)')
def test(
    category: Optional[str],
    app: Optional[str],
    file_path: Optional[str],
    parallel: bool,
    coverage: bool,
    failfast: bool,
    verbose: bool,
    json_output: bool,
    template: Optional[str],
    env_mode: str,
    config: Optional[str],
    # Environment options
    env_name: Optional[str],
    suite: Optional[str],
    keep_running: bool,
    # Pipeline options
    projects: tuple,
    timeout: Optional[int],
    poll_interval: Optional[int],
    sync: bool,
    skip_build: bool,
    # Browser testing options
    browser: bool,
    surfer: bool,
    tunnel_port: Optional[int],
    headed: bool,
    # Multi-project options
    subprojects: tuple,
    tags: tuple,
    exclude_tags: tuple,
) -> None:
    """Run tests using the configured adapter or environment.

    This function serves as the CLI entry point, receiving individual parameters
    from Click decorators. It converts them to grouped TestCommandOptions and
    delegates to the internal implementation.
    """
    try:
        # Load configuration
        config_path = Path(config) if config else find_config_file()
        if not config_path:
            console.print("[red]Error:[/red] No systemeval.yaml found in current or parent directories")
            console.print("Run 'systemeval init' to create a configuration file")
            sys.exit(2)

        try:
            test_config = load_config(config_path)
        except Exception as e:
            console.print(f"[red]Error loading config:[/red] {e}")
            sys.exit(2)

        # Convert CLI arguments to grouped options
        opts = TestCommandOptions.from_cli_args(
            # Test selection
            category=category,
            app=app,
            file_path=file_path,
            suite=suite,
            # Execution
            parallel=parallel,
            failfast=failfast,
            verbose=verbose,
            coverage=coverage,
            # Output
            json_output=json_output,
            template=template,
            # Environment
            env_mode=env_mode,
            env_name=env_name,
            config=config,
            keep_running=keep_running,
            # Pipeline
            projects=projects,
            timeout=timeout,
            poll_interval=poll_interval,
            sync=sync,
            skip_build=skip_build,
            # Browser
            browser=browser,
            surfer=surfer,
            tunnel_port=tunnel_port,
            headed=headed,
            # Multi-project
            subprojects=subprojects,
            tags=tags,
            exclude_tags=exclude_tags,
        )

        # Delegate to internal implementation
        _execute_test_command(test_config, opts, config_path)

    except KeyboardInterrupt:
        console.print("\n[yellow]Test run interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(2)


# Config and list commands are now registered via modular functions above


def _display_results(results: TestResult) -> None:
    """Display test results in a formatted table."""
    from systemeval.adapters import Verdict

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
    table.add_row("Failed", f"[red]{results.failed}[/red]" if results.failed > 0 else "0")
    table.add_row("Skipped", str(results.skipped))
    table.add_row("Errors", f"[red]{results.errors}[/red]" if results.errors > 0 else "0")

    if results.duration:
        table.add_row("Duration", f"{results.duration:.2f}s")

    if results.coverage_percent is not None:
        coverage_color = "green" if results.coverage_percent >= 80 else "yellow"
        table.add_row("Coverage", f"[{coverage_color}]{results.coverage_percent:.1f}%[/{coverage_color}]")

    table.add_row("Exit Code", str(results.exit_code))

    console.print(table)

    # Overall result banner
    if verdict == Verdict.ERROR:
        console.print(f"\n[yellow bold]======== ERROR ========[/yellow bold]")
    elif verdict == Verdict.FAIL:
        console.print(f"\n[red bold]======== FAILED ========[/red bold]")
    else:
        console.print(f"\n[green bold]======== PASSED ========[/green bold]")


# E2E commands are registered via the modular e2e command group above


if __name__ == '__main__':
    main()

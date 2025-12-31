"""
SystemEval CLI - Unified test runner with framework-agnostic adapters.
"""
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console
from rich.table import Table

from systemeval.config import SystemEvalConfig, load_config, find_config_file
from systemeval.adapters import get_adapter, list_adapters as get_available_adapters, TestResult
from systemeval.plugins.docker import get_environment_type, is_docker_environment

console = Console()


def _run_with_environment(
    test_config: "SystemEvalConfig",
    env_name: Optional[str],
    suite: Optional[str],
    category: Optional[str],
    verbose: bool,
    keep_running: bool,
    skip_build: bool,
    json_output: bool,
) -> "TestResult":
    """Run tests using environment orchestration."""
    from systemeval.environments import EnvironmentResolver

    # Resolve environment
    resolver = EnvironmentResolver(test_config.environments)

    if not test_config.environments:
        console.print("[red]Error:[/red] No environments configured in systemeval.yaml")
        console.print("Add an 'environments' section to your configuration")
        import sys
        sys.exit(2)

    # Get environment name
    if not env_name:
        env_name = resolver.get_default_environment()
        if not env_name:
            console.print("[red]Error:[/red] No default environment found")
            import sys
            sys.exit(2)

    try:
        env = resolver.resolve(env_name)
    except KeyError as e:
        console.print(f"[red]Error:[/red] {e}")
        available = ", ".join(resolver.list_environments().keys())
        console.print(f"Available environments: {available}")
        import sys
        sys.exit(2)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        import sys
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
@click.version_option(version="0.1.4")
def main() -> None:
    """SystemEval - Unified test runner CLI."""
    pass


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
@click.option('--docker', is_flag=True, help='Force Docker environment')
@click.option('--no-docker', is_flag=True, help='Force local environment')
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
    docker: bool,
    no_docker: bool,
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
) -> None:
    """Run tests using the configured adapter or environment."""
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

        # Determine environment
        if docker and no_docker:
            console.print("[red]Error:[/red] Cannot specify both --docker and --no-docker")
            sys.exit(2)

        if docker:
            environment = "docker"
        elif no_docker:
            environment = "local"
        else:
            environment = get_environment_type()

        if verbose:
            console.print(f"[dim]Environment: {environment}[/dim]")
            console.print(f"[dim]Config: {config_path}[/dim]")

        # Check if using environment-based testing
        if env_name or test_config.environments:
            results = _run_with_environment(
                test_config=test_config,
                env_name=env_name,
                suite=suite,
                category=category,
                verbose=verbose,
                keep_running=keep_running,
                skip_build=skip_build,
                json_output=json_output,
            )
        else:
            # Legacy adapter-based testing
            # Get adapter
            try:
                adapter = get_adapter(test_config.adapter, str(test_config.project_root.absolute()))
            except (KeyError, ValueError) as e:
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(2)

            # Validate environment
            if not adapter.validate_environment():
                console.print(f"[yellow]Warning:[/yellow] Test environment validation failed")

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
            results = adapter.execute(**exec_kwargs)

        # Set category on results for output
        results.category = category or "default"

        # Output results
        if json_output:
            # Check for pipeline adapter's detailed evaluation
            if hasattr(results, '_pipeline_adapter') and hasattr(results, '_pipeline_tests'):
                evaluation = results._pipeline_adapter.create_evaluation_result(
                    tests=results._pipeline_tests,
                    results_by_project=results._pipeline_metrics,
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

    except KeyboardInterrupt:
        console.print("\n[yellow]Test run interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        sys.exit(2)


@main.command()
@click.option('--force', is_flag=True, help='Overwrite existing config')
def init(force: bool) -> None:
    """Initialize systemeval.yaml configuration file."""
    config_path = Path("systemeval.yaml")

    if config_path.exists() and not force:
        console.print(f"[yellow]Warning:[/yellow] {config_path} already exists")
        console.print("Use --force to overwrite")
        sys.exit(1)

    # Detect project type
    project_type = _detect_project_type()

    if not project_type:
        console.print("[yellow]Could not auto-detect project type[/yellow]")
        console.print("Creating generic configuration")
        project_type = "generic"

    # Create default config based on project type
    config = _create_default_config(project_type)

    # Write config file
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Created {config_path}[/green]")
    console.print(f"Detected project type: [cyan]{project_type}[/cyan]")
    console.print("\nNext steps:")
    console.print("  1. Review and customize systemeval.yaml")
    console.print("  2. Run 'systemeval validate' to check configuration")
    console.print("  3. Run 'systemeval test' to execute tests")


@main.command()
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
def validate(config: Optional[str]) -> None:
    """Validate the configuration file."""
    try:
        config_path = Path(config) if config else find_config_file()
        if not config_path:
            console.print("[red]Error:[/red] No systemeval.yaml found")
            sys.exit(2)

        console.print(f"Validating [cyan]{config_path}[/cyan]...")

        # Load and validate
        test_config = load_config(config_path)

        # Validate adapter exists
        try:
            adapter = get_adapter(test_config.adapter, str(test_config.project_root.absolute()))
            if not adapter.validate_environment():
                console.print("[yellow]Warning:[/yellow] Environment validation failed")
        except (KeyError, ValueError) as e:
            console.print(f"[red]Adapter error:[/red] {e}")
            sys.exit(1)

        # Display config summary
        table = Table(title="Configuration Summary")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Adapter", test_config.adapter)
        table.add_row("Project Root", str(test_config.project_root))
        table.add_row("Test Directory", str(test_config.test_directory))

        if test_config.categories:
            categories = ", ".join(test_config.categories.keys())
            table.add_row("Categories", categories)

        console.print(table)
        console.print("\n[green]Configuration is valid![/green]")

    except Exception as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        sys.exit(1)


@main.group()
def list_cmd() -> None:
    """List available items."""
    pass


@list_cmd.command('categories')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
def list_categories(config: Optional[str]) -> None:
    """List available test categories."""
    try:
        config_path = Path(config) if config else find_config_file()
        if not config_path:
            console.print("[red]Error:[/red] No systemeval.yaml found")
            sys.exit(2)

        test_config = load_config(config_path)

        if not test_config.categories:
            console.print("[yellow]No categories defined in configuration[/yellow]")
            return

        table = Table(title="Available Test Categories")
        table.add_column("Category", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Markers", style="dim")

        for name, category in test_config.categories.items():
            markers = ", ".join(category.markers) if category.markers else "-"
            description = category.description or "-"
            table.add_row(name, description, markers)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)


@list_cmd.command('environments')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
def list_environments_cmd(config: Optional[str]) -> None:
    """List available test environments."""
    try:
        config_path = Path(config) if config else find_config_file()
        if not config_path:
            console.print("[red]Error:[/red] No systemeval.yaml found")
            sys.exit(2)

        test_config = load_config(config_path)

        if not test_config.environments:
            console.print("[yellow]No environments defined in configuration[/yellow]")
            console.print("\nAdd an 'environments' section to your systemeval.yaml:")
            console.print("""
[dim]environments:
  backend:
    type: docker-compose
    compose_file: local.yml
    test_command: pytest
  frontend:
    type: standalone
    command: npm run dev
    test_command: npm test[/dim]
""")
            return

        table = Table(title="Available Environments")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="white")
        table.add_column("Default", style="dim")
        table.add_column("Details", style="dim")

        for name, env_config in test_config.environments.items():
            env_type = env_config.get("type", "standalone")
            is_default = "Yes" if env_config.get("default", False) else ""

            # Build details string
            if env_type == "docker-compose":
                compose_file = env_config.get("compose_file", "docker-compose.yml")
                services = env_config.get("services", [])
                details = f"file: {compose_file}"
                if services:
                    details += f", services: {len(services)}"
            elif env_type == "composite":
                deps = env_config.get("depends_on", [])
                details = f"depends: {', '.join(deps)}"
            else:
                cmd = env_config.get("command", "")
                details = cmd[:40] + "..." if len(cmd) > 40 else cmd

            table.add_row(name, env_type, is_default, details)

        console.print(table)
        console.print("\n[dim]Usage: systemeval test --env <name>[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)


@list_cmd.command('adapters')
def list_adapters_cmd() -> None:
    """List available test adapters."""
    table = Table(title="Available Adapters")
    table.add_column("Adapter", style="cyan")
    table.add_column("Status", style="white")

    adapters = get_available_adapters()

    if not adapters:
        console.print("[yellow]No adapters registered[/yellow]")
        return

    # Map adapter names to descriptions
    adapter_info = {
        "pytest": "Python test framework (pytest)",
        "jest": "JavaScript test framework (jest)",
        "pipeline": "DebuggAI pipeline evaluation (Django)",
    }

    for name in adapters:
        description = adapter_info.get(name, "Test framework adapter")
        table.add_row(name, f"[green]Available[/green] - {description}")

    console.print(table)


@list_cmd.command('templates')
def list_templates_cmd() -> None:
    """List available output templates."""
    from systemeval.templates import TemplateRenderer

    renderer = TemplateRenderer()
    templates = renderer.list_templates()

    table = Table(title="Available Output Templates")
    table.add_column("Template", style="cyan")
    table.add_column("Description", style="white")

    for name, description in sorted(templates.items()):
        table.add_row(name, description)

    console.print(table)
    console.print("\n[dim]Usage: systemeval test --template <name>[/dim]")


def _detect_project_type() -> Optional[str]:
    """Detect project type from common files."""
    cwd = Path.cwd()

    # Django
    if (cwd / "manage.py").exists():
        return "django"

    # Next.js / Node.js
    if (cwd / "package.json").exists():
        try:
            import json
            with open(cwd / "package.json") as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "next" in deps:
                    return "nextjs"
                if "jest" in deps:
                    return "jest"
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            # Failed to read or parse package.json - fall through to nodejs
            pass
        return "nodejs"

    # Python
    if (cwd / "pytest.ini").exists() or (cwd / "pyproject.toml").exists():
        return "python-pytest"

    return None


def _create_default_config(project_type: str) -> dict:
    """Create default configuration based on project type."""
    base_config = {
        "adapter": "pytest",
        "project_root": ".",
        "test_directory": "tests",
        "categories": {},
    }

    if project_type == "django":
        base_config.update({
            "adapter": "pytest",
            "test_directory": "backend",
            "categories": {
                "unit": {
                    "description": "Fast isolated unit tests",
                    "markers": ["unit"],
                },
                "integration": {
                    "description": "Integration tests with database",
                    "markers": ["integration"],
                },
                "api": {
                    "description": "API endpoint tests",
                    "markers": ["api"],
                },
            },
        })
    elif project_type in ("nextjs", "nodejs", "jest"):
        base_config.update({
            "adapter": "jest",
            "test_directory": ".",
            "categories": {
                "unit": {
                    "description": "Unit tests",
                    "test_match": ["**/*.test.js", "**/*.test.ts"],
                },
                "integration": {
                    "description": "Integration tests",
                    "test_match": ["**/*.integration.test.js"],
                },
            },
        })
    elif project_type == "python-pytest":
        base_config.update({
            "adapter": "pytest",
            "categories": {
                "unit": {"markers": ["unit"]},
                "integration": {"markers": ["integration"]},
            },
        })

    return base_config


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


if __name__ == '__main__':
    main()

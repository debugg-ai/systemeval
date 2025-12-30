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


@click.group()
@click.version_option(version="0.1.2")
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
@click.option('--docker', is_flag=True, help='Force Docker environment')
@click.option('--no-docker', is_flag=True, help='Force local environment')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
def test(
    category: Optional[str],
    app: Optional[str],
    file_path: Optional[str],
    parallel: bool,
    coverage: bool,
    failfast: bool,
    verbose: bool,
    json_output: bool,
    docker: bool,
    no_docker: bool,
    config: Optional[str],
) -> None:
    """Run tests using the configured adapter."""
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

        # Execute tests using adapter
        results = adapter.execute(
            tests=None,  # Will use category/app/file filters in future
            parallel=parallel,
            coverage=coverage,
            failfast=failfast,
            verbose=verbose,
        )

        # Set category on results for output
        results.category = category or "default"

        # Output results
        if json_output:
            import json
            console.print(json.dumps(results.to_dict(), indent=2))
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
def list() -> None:
    """List available items."""
    pass


@list.command('categories')
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


@list.command('adapters')
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
    }

    for name in adapters:
        description = adapter_info.get(name, "Test framework adapter")
        table.add_row(name, f"[green]Available[/green] - {description}")

    console.print(table)


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
        except:
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

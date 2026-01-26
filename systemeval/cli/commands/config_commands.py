"""Configuration-related CLI commands for SystemEval.

This module provides commands for initializing, validating, and discovering
test configurations.
"""
import json
import sys
from pathlib import Path
from typing import Optional
from dataclasses import asdict

import click
import yaml
from rich.console import Console
from rich.table import Table

from systemeval.config import load_config, find_config_file
from systemeval.adapters import get_adapter


def _detect_project_type() -> Optional[str]:
    """Detect project type from common files.

    Returns:
        Project type identifier or None if not detected.
    """
    cwd = Path.cwd()

    # Django
    if (cwd / "manage.py").exists():
        return "django"

    # Next.js / Node.js
    if (cwd / "package.json").exists():
        try:
            import json as json_module
            with open(cwd / "package.json") as f:
                pkg = json_module.load(f)
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
    """Create default configuration based on project type.

    Args:
        project_type: Detected project type identifier.

    Returns:
        Dictionary containing default configuration.
    """
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


def register_config_commands(cli_group: click.Group, console: Console) -> None:
    """Register all configuration commands with the CLI group.

    Args:
        cli_group: Click group to register commands with.
        console: Rich Console instance for output.
    """

    @cli_group.command()
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

    @cli_group.command()
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

    @cli_group.command()
    @click.option('--category', '-c', help='Test category to filter by')
    @click.option('--app', '-a', help='Specific app/module to filter by')
    @click.option('--file', '-f', 'file_path', help='Specific test file to filter by')
    @click.option('--config', type=click.Path(exists=True), help='Path to config file')
    @click.option('--json', 'json_output', is_flag=True, help='Output results as JSON')
    def discover(
        category: Optional[str],
        app: Optional[str],
        file_path: Optional[str],
        config: Optional[str],
        json_output: bool,
    ) -> None:
        """Discover available tests.

        Lists all tests that can be run, optionally filtered by category, app, or file.
        """
        import json as json_module

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

            # Get adapter
            try:
                adapter = get_adapter(test_config.adapter, str(test_config.project_root.absolute()))
            except (KeyError, ValueError) as e:
                console.print(f"[red]Error:[/red] {e}")
                sys.exit(2)

            # Discover tests
            tests = adapter.discover(
                category=category,
                app=app,
                file=file_path,
            )

            # Output results
            if json_output:
                # Convert TestItem dataclasses to dicts for JSON serialization
                tests_as_dicts = [asdict(t) for t in tests]
                console.print(json_module.dumps(tests_as_dicts, indent=2))
            else:
                console.print(f"Found {len(tests)} tests:")
                for test in tests:
                    console.print(f"  {test.path}::{test.name}")

        except KeyboardInterrupt:
            console.print("\n[yellow]Discovery interrupted[/yellow]")
            sys.exit(130)
        except Exception as e:
            console.print(f"[red]Discovery failed:[/red] {e}")
            sys.exit(2)

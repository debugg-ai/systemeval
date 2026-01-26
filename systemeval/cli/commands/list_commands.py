"""List commands for SystemEval CLI.

This module provides commands for listing available items such as categories,
environments, adapters, and templates.
"""
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from systemeval.config import (
    load_config,
    find_config_file,
    DockerComposeEnvConfig,
    CompositeEnvConfig,
    StandaloneEnvConfig,
)
from systemeval.adapters import list_adapters as get_available_adapters
from systemeval.templates import TemplateRenderer


def register_list_commands(cli_group: click.Group, console: Console) -> None:
    """Register all list commands with the CLI group.

    Args:
        cli_group: Click group to register commands with.
        console: Rich Console instance for output.
    """

    @cli_group.group()
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
                env_type = env_config.type
                is_default = "Yes" if env_config.default else ""

                # Build details string based on typed config
                if isinstance(env_config, DockerComposeEnvConfig):
                    compose_file = env_config.compose_file
                    services = env_config.services
                    details = f"file: {compose_file}"
                    if services:
                        details += f", services: {len(services)}"
                elif isinstance(env_config, CompositeEnvConfig):
                    deps = env_config.depends_on
                    details = f"depends: {', '.join(deps)}"
                elif isinstance(env_config, StandaloneEnvConfig):
                    cmd = env_config.command
                    details = cmd[:40] + "..." if len(cmd) > 40 else cmd
                else:
                    details = ""

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
            "vitest": "Vite-powered test framework (vitest)",
            "playwright": "Browser automation framework (playwright)",
            "pipeline": "DebuggAI pipeline evaluation (Django)",
        }

        for name in adapters:
            description = adapter_info.get(name, "Test framework adapter")
            table.add_row(name, f"[green]Available[/green] - {description}")

        console.print(table)

    @list_cmd.command('templates')
    def list_templates_cmd() -> None:
        """List available output templates."""
        renderer = TemplateRenderer()
        templates = renderer.list_templates()

        table = Table(title="Available Output Templates")
        table.add_column("Template", style="cyan")
        table.add_column("Description", style="white")

        for name, description in sorted(templates.items()):
            table.add_row(name, description)

        console.print(table)
        console.print("\n[dim]Usage: systemeval test --template <name>[/dim]")

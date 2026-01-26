"""E2E test generation commands for SystemEval CLI.

This module contains all E2E-related Click commands:
- e2e run: Run E2E test generation for current changes
- e2e status: Check status of an E2E generation run
- e2e download: Download artifacts from a completed E2E run
- e2e init: Add E2E configuration to systemeval.yaml
"""

import json
import sys
import time as time_module
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console

from systemeval.config import find_config_file, load_config

console = Console()


@click.group()
def e2e():
    """E2E test generation commands."""
    pass


@e2e.command("run")
@click.option('--api-key', envvar='DEBUGGAI_API_KEY', help='DebuggAI API key (or DEBUGGAI_API_KEY env)')
@click.option('--provider', type=click.Choice(['debuggai', 'local', 'mock']), help='E2E provider to use')
@click.option('--project-url', help='URL of the application to test')
@click.option('--output-dir', type=click.Path(), help='Directory for generated tests')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
@click.option('--timeout', type=int, default=600, help='Max time to wait for generation (seconds)')
@click.option('--download/--no-download', default=True, help='Download generated test artifacts')
@click.option('--json', 'json_output', is_flag=True, help='Output results as JSON (EvaluationResult schema)')
@click.option('--template', '-t', help='Output template (e2e_summary, e2e_markdown, e2e_ci, e2e_github, e2e_table, e2e_slack)')
@click.option('--verbose', '-v', is_flag=True, help='Show verbose output')
@click.option('--base-ref', help='Base git reference (branch/commit) for comparison')
@click.option('--head-ref', help='Head git reference (branch/commit) for comparison')
@click.option('--working-changes', is_flag=True, help='Analyze uncommitted working directory changes')
def e2e_run(
    api_key: Optional[str],
    provider: Optional[str],
    project_url: Optional[str],
    output_dir: Optional[str],
    config: Optional[str],
    timeout: int,
    download: bool,
    json_output: bool,
    template: Optional[str],
    verbose: bool,
    base_ref: Optional[str],
    head_ref: Optional[str],
    working_changes: bool,
) -> None:
    """Run E2E test generation for current changes.

    Analyzes git changes and generates E2E tests using the configured provider.

    Examples:

        # Use config from systemeval.yaml
        systemeval e2e run

        # Override API key from CLI
        systemeval e2e run --api-key sk_live_...

        # Use specific provider
        systemeval e2e run --provider mock

        # Specify output directory
        systemeval e2e run --output-dir tests/e2e

        # Analyze uncommitted working directory changes
        systemeval e2e run --working-changes

        # Compare specific git refs
        systemeval e2e run --base-ref main --head-ref feature-branch
    """
    try:
        # Load configuration
        config_path = Path(config) if config else find_config_file()
        if not config_path:
            console.print("[red]Error:[/red] No systemeval.yaml found. Run 'systemeval init' first.")
            sys.exit(2)

        test_config = load_config(config_path)

        # Check if E2E is configured
        if not test_config.has_e2e_config() and not api_key:
            console.print("[red]Error:[/red] E2E not configured in systemeval.yaml and no --api-key provided.")
            console.print("Add an 'e2e' section to your config or pass --api-key")
            sys.exit(2)

        # Get E2E config with CLI overrides
        try:
            e2e_config = test_config.get_e2e_config(api_key_override=api_key)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(2)

        # Apply CLI overrides
        if e2e_config is None:
            # Create minimal config from CLI args
            from systemeval.e2e.types import E2EConfig as E2ETypesConfig
            e2e_config = E2ETypesConfig(
                provider_name=provider or "debuggai",
                project_root=test_config.project_root,
                api_key=api_key,
                project_url=project_url,
                output_directory=Path(output_dir) if output_dir else test_config.project_root / "tests/e2e_generated",
                timeout_seconds=timeout,
            )
        else:
            # Override with CLI args if provided
            if provider:
                e2e_config.provider_name = provider
            if project_url:
                e2e_config.project_url = project_url
            if output_dir:
                e2e_config.output_directory = test_config.project_root / output_dir

        if verbose:
            console.print(f"[dim]Provider: {e2e_config.provider_name}[/dim]")
            console.print(f"[dim]Project root: {e2e_config.project_root}[/dim]")
            console.print(f"[dim]Output: {e2e_config.output_directory}[/dim]")
            console.print()

        # Initialize E2E module
        from systemeval.e2e import initialize, E2EProviderFactory
        from systemeval.e2e.types import ChangeSet

        initialize(e2e_config)

        # Create provider using factory
        factory = E2EProviderFactory()
        try:
            e2e_provider = factory.create_provider(e2e_config)
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e}")
            console.print(f"Available providers: {', '.join(factory.list_providers())}")
            sys.exit(2)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(2)

        # Validate config
        validation = e2e_provider.validate_config(e2e_config)
        if not validation.valid:
            console.print("[red]Config validation failed:[/red]")
            for error in validation.errors:
                console.print(f"  - {error}")
            sys.exit(2)

        for warning in validation.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")

        if not json_output:
            console.print("[bold cyan]Starting E2E test generation...[/bold cyan]")

        # Analyze git changes using GitAnalyzer
        changes: Optional[ChangeSet] = None

        try:
            from systemeval.e2e.git_analyzer import (
                GitAnalysisError,
                analyze_working_changes,
                analyze_pr_changes,
                analyze_range,
            )

            if working_changes:
                # Analyze uncommitted working directory changes
                if verbose:
                    console.print("[dim]Analyzing working directory changes...[/dim]")
                changes = analyze_working_changes(
                    repo_path=test_config.project_root,
                    include_staged=True,
                    include_unstaged=True,
                    include_diff=True,
                )
            elif base_ref and head_ref:
                # Compare specific git refs
                if verbose:
                    console.print(f"[dim]Analyzing changes: {base_ref}...{head_ref}[/dim]")
                changes = analyze_range(
                    repo_path=test_config.project_root,
                    base_ref=base_ref,
                    head_ref=head_ref,
                    include_diff=True,
                )
            else:
                # Default: analyze PR-style changes (current branch vs default branch)
                if verbose:
                    console.print("[dim]Analyzing PR changes...[/dim]")
                changes = analyze_pr_changes(
                    repo_path=test_config.project_root,
                    include_diff=True,
                )

            if verbose:
                console.print(f"[dim]Found {len(changes.changes)} changed files[/dim]")

        except GitAnalysisError as git_error:
            # Git analysis failed - fall back to mock data with warning
            console.print(f"[yellow]Warning:[/yellow] Git analysis failed: {git_error}")
            console.print("[yellow]Using mock changeset for testing[/yellow]")

            from systemeval.e2e.types import Change, ChangeType
            changes = ChangeSet(
                base_ref="main",
                head_ref="HEAD",
                changes=[
                    Change("src/example.py", ChangeType.MODIFIED, additions=10, deletions=5),
                ],
                repository_root=test_config.project_root,
            )

        # Generate tests
        generation = e2e_provider.generate_tests(changes, e2e_config)

        if generation.status.value == "failed":
            console.print(f"[red]Generation failed:[/red] {generation.message}")
            sys.exit(1)

        if not json_output:
            console.print(f"[green]Generation started:[/green] {generation.run_id}")
            console.print("[dim]Waiting for completion...[/dim]")

        # Poll for completion
        start_time = time_module.time()
        while True:
            status = e2e_provider.get_status(generation.run_id)

            if verbose and not json_output:
                console.print(f"[dim]Status: {status.status.value} ({status.progress_percent:.0f}%)[/dim]")

            if status.status.value in ("completed", "failed", "cancelled"):
                break

            if time_module.time() - start_time > timeout:
                console.print("[red]Error:[/red] Generation timed out")
                sys.exit(1)

            time_module.sleep(5)

        # Build E2EResult for reporting
        from systemeval.e2e.types import E2EResult, CompletionResult, GenerationStatus
        from systemeval.e2e.reporting import (
            e2e_to_evaluation_result,
            e2e_result_to_test_result,
            create_e2e_evaluation_context,
            render_e2e_result,
        )

        # Calculate duration
        total_duration = time_module.time() - start_time

        # Create completion result
        completion = CompletionResult(
            run_id=generation.run_id,
            status=GenerationStatus(status.status.value),
            completed=status.status.value in ("completed", "failed"),
            timed_out=status.status.value not in ("completed", "failed", "cancelled"),
            duration_seconds=total_duration,
            final_message=status.message,
            error=status.error if hasattr(status, 'error') else None,
        )

        # Download artifacts if completed and requested
        artifacts = None
        if status.status.value == "completed" and download:
            if not json_output and not template:
                console.print("[dim]Downloading artifacts...[/dim]")

            e2e_config.output_directory.mkdir(parents=True, exist_ok=True)
            artifacts = e2e_provider.download_artifacts(generation.run_id, e2e_config.output_directory)

            if not json_output and not template:
                console.print(f"[green]Downloaded {len(artifacts.test_files)} files to {artifacts.output_directory}[/green]")

        # Create complete E2EResult
        e2e_result = E2EResult(
            changeset=changes,
            config=e2e_config,
            generation=generation,
            completion=completion,
            artifacts=artifacts,
            started_at=generation.started_at,
            success=status.status.value == "completed",
            error=status.error if hasattr(status, 'error') and status.status.value != "completed" else None,
            warnings=validation.warnings if hasattr(validation, 'warnings') else [],
        )
        e2e_result.finalize(
            success=status.status.value == "completed",
            error=status.error if hasattr(status, 'error') and status.status.value != "completed" else None,
        )

        # Output results based on format
        if json_output:
            # Full EvaluationResult JSON output
            evaluation = e2e_to_evaluation_result(
                e2e_result,
                project_name=test_config.project_root.name if test_config.project_root else None,
            )
            console.print(evaluation.to_json())
        elif template:
            # Template-based output
            output = render_e2e_result(e2e_result, template_name=template)
            console.print(output)
        else:
            # Default: Human-readable output
            if status.status.value == "completed":
                console.print(f"[green]Generation complete![/green] {status.tests_generated} tests generated")
            else:
                console.print(f"[red]Generation {status.status.value}:[/red] {status.message or 'No details available'}")

        # Exit with appropriate code
        if status.status.value == "completed":
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        if json_output:
            console.print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        elif template:
            # For template output, print error in a consistent format
            console.print(f"[{{ verdict_emoji }}] E2E Generation ERROR: {e}")
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)


@e2e.command("status")
@click.argument('run_id')
@click.option('--api-key', envvar='DEBUGGAI_API_KEY', help='DebuggAI API key')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def e2e_status(run_id: str, api_key: Optional[str], config: Optional[str], json_output: bool) -> None:
    """Check status of an E2E generation run.

    Examples:

        systemeval e2e status debuggai-abc123

        systemeval e2e status debuggai-abc123 --json
    """
    console.print(f"[yellow]Status check for {run_id} not yet implemented[/yellow]")
    console.print("The provider would need to track run state across CLI invocations.")
    sys.exit(0)


@e2e.command("download")
@click.argument('run_id')
@click.option('--api-key', envvar='DEBUGGAI_API_KEY', help='DebuggAI API key (or DEBUGGAI_API_KEY env)')
@click.option('--output-dir', type=click.Path(), help='Directory to download artifacts to')
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
@click.option('--json', 'json_output', is_flag=True, help='Output results as JSON')
def e2e_download(
    run_id: str,
    api_key: Optional[str],
    output_dir: Optional[str],
    config: Optional[str],
    json_output: bool,
) -> None:
    """Download artifacts from a completed E2E run.

    Downloads test scripts, recordings, and details from a completed E2E
    test generation run to the specified output directory.

    Examples:

        # Download to default output directory from config
        systemeval e2e download debuggai-abc123

        # Download to specific directory
        systemeval e2e download debuggai-abc123 --output-dir tests/e2e

        # Output JSON for CI integration
        systemeval e2e download debuggai-abc123 --json
    """
    try:
        # Load configuration
        config_path = Path(config) if config else find_config_file()
        test_config = None
        e2e_config = None

        if config_path:
            try:
                test_config = load_config(config_path)
                if test_config.has_e2e_config():
                    e2e_config = test_config.get_e2e_config(api_key_override=api_key)
            except Exception:
                # Config loading failed, continue with CLI args only
                pass

        # Determine API key
        effective_api_key = api_key
        if not effective_api_key and e2e_config:
            effective_api_key = e2e_config.api_key

        if not effective_api_key:
            if json_output:
                console.print(json.dumps({
                    "status": "error",
                    "error": "API key required. Provide --api-key or set DEBUGGAI_API_KEY env.",
                }, indent=2))
            else:
                console.print("[red]Error:[/red] API key required.")
                console.print("Provide --api-key or set DEBUGGAI_API_KEY environment variable.")
            sys.exit(2)

        # Determine output directory
        if output_dir:
            effective_output_dir = Path(output_dir)
        elif e2e_config and e2e_config.output_directory:
            effective_output_dir = e2e_config.output_directory
        elif test_config:
            effective_output_dir = test_config.project_root / "tests/e2e_generated"
        else:
            effective_output_dir = Path.cwd() / "e2e_artifacts"

        # Determine API base URL
        api_base_url = "https://api.debugg.ai"
        if e2e_config and e2e_config.api_base_url:
            api_base_url = e2e_config.api_base_url

        # Initialize provider
        from systemeval.e2e import DebuggAIProvider

        provider = DebuggAIProvider(
            api_key=effective_api_key,
            api_base_url=api_base_url,
        )

        if not json_output:
            console.print(f"[bold cyan]Downloading artifacts for run: {run_id}[/bold cyan]")
            console.print(f"[dim]Output directory: {effective_output_dir}[/dim]")
            console.print()

        # First, we need to get the run status to verify it exists and is completed
        # The provider needs the run tracked internally, so we need to fetch status first
        try:
            # Extract suite_uuid from run_id (format: debuggai-<uuid>)
            if run_id.startswith("debuggai-"):
                # Try to get suite status directly via API
                suite_uuid = run_id.replace("debuggai-", "")

                # Make direct API call to get suite info
                response = provider._api_request("GET", f"/cli/e2e/suites/{suite_uuid}")
                suite = response.get("suite", response)
                status_str = suite.get("status", "unknown").lower()

                if status_str not in ("completed", "complete"):
                    if json_output:
                        console.print(json.dumps({
                            "status": "error",
                            "error": f"Run '{run_id}' is not completed (status: {status_str}). Cannot download artifacts.",
                            "run_status": status_str,
                        }, indent=2))
                    else:
                        console.print(f"[red]Error:[/red] Run '{run_id}' is not completed (status: {status_str}).")
                        console.print("Artifacts can only be downloaded from completed runs.")
                    sys.exit(1)

                # Register the run in provider's internal tracking
                from systemeval.e2e.types import GenerationStatus, ChangeSet, Change, ChangeType

                # Create a minimal changeset for tracking
                dummy_changeset = ChangeSet(
                    base_ref="main",
                    head_ref="HEAD",
                    changes=[],
                    repository_root=Path.cwd(),
                )

                # Create a minimal E2E config for tracking
                from systemeval.e2e.types import E2EConfig as E2ETypesConfig
                dummy_e2e_config = E2ETypesConfig(
                    provider_name="debuggai",
                    project_root=Path.cwd(),
                )

                # Register the run internally
                from systemeval.e2e.providers.debuggai import DebuggAIRun
                provider._runs[run_id] = DebuggAIRun(
                    run_id=run_id,
                    suite_uuid=suite_uuid,
                    status=GenerationStatus.COMPLETED,
                    changes=dummy_changeset,
                    config=dummy_e2e_config,
                    suite_data=suite,
                )

            else:
                if json_output:
                    console.print(json.dumps({
                        "status": "error",
                        "error": f"Invalid run_id format: {run_id}. Expected format: debuggai-<suite_uuid>",
                    }, indent=2))
                else:
                    console.print(f"[red]Error:[/red] Invalid run_id format: {run_id}")
                    console.print("Expected format: debuggai-<suite_uuid>")
                sys.exit(2)

        except ValueError as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                if json_output:
                    console.print(json.dumps({
                        "status": "error",
                        "error": f"Run '{run_id}' not found.",
                    }, indent=2))
                else:
                    console.print(f"[red]Error:[/red] Run '{run_id}' not found.")
                sys.exit(1)
            raise

        # Download artifacts
        if not json_output:
            console.print("[dim]Downloading test artifacts...[/dim]")

        effective_output_dir.mkdir(parents=True, exist_ok=True)
        artifacts = provider.download_artifacts(run_id, effective_output_dir)

        # Output results
        if json_output:
            result = {
                "status": "success",
                "run_id": run_id,
                "artifacts": {
                    "total_tests": artifacts.total_tests,
                    "files_downloaded": len(artifacts.test_files),
                    "files": [str(f) for f in artifacts.test_files],
                    "output_directory": str(artifacts.output_directory),
                },
            }
            console.print(json.dumps(result, indent=2))
        else:
            console.print(f"[green]Downloaded {len(artifacts.test_files)} files[/green]")
            console.print(f"[dim]Total tests: {artifacts.total_tests}[/dim]")
            console.print(f"[dim]Output: {artifacts.output_directory}[/dim]")

            if artifacts.test_files:
                console.print("\n[bold]Downloaded files:[/bold]")
                for file_path in artifacts.test_files[:10]:  # Show first 10
                    console.print(f"  - {file_path.name}")
                if len(artifacts.test_files) > 10:
                    console.print(f"  ... and {len(artifacts.test_files) - 10} more")

        sys.exit(0)

    except KeyError as e:
        if json_output:
            console.print(json.dumps({
                "status": "error",
                "error": f"Run not found: {e}",
            }, indent=2))
        else:
            console.print(f"[red]Error:[/red] Run not found: {e}")
        sys.exit(1)

    except ValueError as e:
        if json_output:
            console.print(json.dumps({
                "status": "error",
                "error": str(e),
            }, indent=2))
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    except Exception as e:
        if json_output:
            console.print(json.dumps({
                "status": "error",
                "error": str(e),
            }, indent=2))
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(2)


@e2e.command("init")
@click.option('--provider', type=click.Choice(['debuggai', 'local', 'mock']), default='debuggai', help='E2E provider')
@click.option('--force', is_flag=True, help='Overwrite existing e2e config')
def e2e_init(provider: str, force: bool) -> None:
    """Add E2E configuration to systemeval.yaml.

    Examples:

        # Add E2E config with DebuggAI provider
        systemeval e2e init

        # Use local provider for development
        systemeval e2e init --provider local
    """
    config_path = find_config_file()

    if not config_path:
        console.print("[red]Error:[/red] No systemeval.yaml found. Run 'systemeval init' first.")
        sys.exit(2)

    # Load existing config
    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f) or {}

    if "e2e" in raw_config and not force:
        console.print("[yellow]Warning:[/yellow] E2E config already exists. Use --force to overwrite.")
        sys.exit(1)

    # Add E2E config section
    e2e_config = {
        "provider": {
            "provider": provider,
        },
        "output": {
            "directory": "tests/e2e_generated",
            "test_framework": "playwright",
        },
    }

    if provider == "debuggai":
        e2e_config["provider"]["api_key"] = "# Set your API key here or use DEBUGGAI_API_KEY env"
        console.print("[yellow]Note:[/yellow] Set your DebuggAI API key in the config or DEBUGGAI_API_KEY env")

    raw_config["e2e"] = e2e_config

    # Write back
    with open(config_path, "w") as f:
        yaml.dump(raw_config, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]E2E config added to {config_path}[/green]")


# Export the e2e group for registration in main CLI
__all__ = ["e2e"]

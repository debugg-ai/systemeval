"""
Helper functions for the SystemEval CLI.

These functions encapsulate the logic for running browser-focused tests and
multi-project sequences so that `systemeval/cli.py` can remain focused on
command wiring and option parsing.

Break larger helpers apart to keep files under ~600 lines and respect
single-responsibility principles.
"""
from typing import List

from rich.console import Console

from systemeval.adapters import TestResult
from systemeval.config import MultiProjectResult, SystemEvalConfig
from systemeval.types import TestCommandOptions
from systemeval.environments import BrowserEnvironment

console = Console()


def run_browser_tests(test_config: SystemEvalConfig, opts: TestCommandOptions) -> TestResult:
    """Run browser tests (Playwright or Surfer) for a single environment."""
    from systemeval.adapters import TestResult as AdapterTestResult  # noqa

    browser = opts.browser_opts.browser
    surfer = opts.browser_opts.surfer
    tunnel_port = opts.browser_opts.tunnel_port
    headed = opts.browser_opts.headed
    category = opts.selection.category
    verbose = opts.execution.verbose
    keep_running = opts.environment.keep_running
    timeout = opts.pipeline.timeout
    json_output = opts.output.json_output

    test_runner = "surfer" if surfer else "playwright"
    browser_config = {"test_runner": test_runner, "working_dir": str(test_config.project_root.absolute())}
    if tunnel_port:
        browser_config["tunnel"] = {"port": tunnel_port}

    if browser:
        playwright_conf = test_config.playwright_config
        if playwright_conf:
            browser_config["playwright"] = {
                "config_file": playwright_conf.config_file,
                "project": playwright_conf.project,
                "headed": headed or playwright_conf.headed,
                "timeout": playwright_conf.timeout,
            }
        elif headed:
            browser_config["playwright"] = {"headed": True}

    if surfer:
        surfer_conf = test_config.surfer_config
        if surfer_conf:
            browser_config["surfer"] = {
                "project_slug": surfer_conf.project_slug,
                "api_key": surfer_conf.api_key,
                "api_base_url": surfer_conf.api_base_url,
                "poll_interval": surfer_conf.poll_interval,
                "timeout": timeout or surfer_conf.timeout,
            }
        else:
            console.print("[red]Error:[/red] surfer_config not found in systemeval.yaml")
            console.print("Add a 'surfer:' section with project_slug")
            return TestResult(passed=0, failed=0, errors=1, skipped=0, duration=0.0, exit_code=2)

    env = BrowserEnvironment("browser-tests", browser_config)

    if not json_output:
        console.print(f"[bold cyan]Running {test_runner} browser tests[/bold cyan]")
        if tunnel_port:
            console.print(f"[dim]Tunnel port: {tunnel_port}[/dim]")
        console.print()

    try:
        if tunnel_port:
            if not json_output:
                console.print("[dim]Starting ngrok tunnel...[/dim]")
            setup_result = env.setup()
            if not setup_result.success:
                console.print(f"[red]Setup failed:[/red] {setup_result.message}")
                return TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=setup_result.duration,
                    exit_code=2,
                )
            if not env.wait_ready(timeout=60):
                console.print("[red]Error:[/red] Tunnel did not become ready")
                env.teardown()
                return TestResult(
                    passed=0,
                    failed=0,
                    errors=1,
                    skipped=0,
                    duration=env.timings.startup,
                    exit_code=2,
                )
            if not json_output and env.tunnel_url:
                console.print(f"[green]Tunnel ready:[/green] {env.tunnel_url}")

        if not json_output:
            console.print("[dim]Running browser tests...[/dim]")

        results = env.run_tests(category=category, verbose=verbose)
        return results

    finally:
        if not keep_running:
            env.teardown()


def run_multi_project_tests(test_config: SystemEvalConfig, opts: TestCommandOptions) -> MultiProjectResult:
    """Run all enabled subprojects for multi-project configurations."""
    verbose = opts.execution.verbose
    json_output = opts.output.json_output

    subproject_names = list(opts.multi_project.subprojects) if opts.multi_project.subprojects else None
    tags = list(opts.multi_project.tags) if opts.multi_project.tags else None
    exclude_tags = list(opts.multi_project.exclude_tags) if opts.multi_project.exclude_tags else None

    subprojects = test_config.get_enabled_subprojects(tags=tags, names=subproject_names)
    if exclude_tags:
        subprojects = [sp for sp in subprojects if not any(tag in sp.tags for tag in exclude_tags)]

    if not subprojects:
        console.print("[yellow]Warning:[/yellow] No subprojects matched the filters")
        return MultiProjectResult(verdict="PASS")

    if not json_output:
        console.print(f"[bold cyan]Running {len(subprojects)} subproject(s)[/bold cyan]")
        console.print()

    result = MultiProjectResult()
    for sp in subprojects:
        session_result = sp.run()
        result.sessions.append(session_result)

    return result

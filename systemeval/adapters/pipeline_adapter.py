"""Pipeline adapter implementation for Django pipeline evaluation.

This adapter integrates DebuggAI's full pipeline testing (build → deploy → health → crawl → E2E)
with the systemeval framework.

Usage:
    adapter = PipelineAdapter('/path/to/sentinal/backend')
    tests = adapter.discover(category='pipeline')
    result = adapter.execute(tests, timeout=600)
"""

import hashlib
import json
import logging
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAdapter, TestFailure, TestItem, TestResult

logger = logging.getLogger(__name__)


class PipelineAdapter(BaseAdapter):
    """Adapter for Django pipeline evaluation.

    Triggers full pipeline workflows (GitHub webhook → build → deploy → health → crawl → E2E tests)
    and evaluates success based on PIPELINE_CRITERIA:
    - build_status == "succeeded"
    - container_healthy == True
    - kg_exists == True
    - kg_pages > 0
    - e2e_error_rate == 0
    """

    # Hardcoded pipeline criteria (matches PIPELINE_CRITERIA from backend.core.testing)
    CRITERIA = {
        "build_status": lambda v: v == "succeeded",
        "container_healthy": lambda v: v is True,
        "kg_exists": lambda v: v is True,
        "kg_pages": lambda v: v is not None and v > 0,
        "e2e_error_rate": lambda v: v == 0 or v == 0.0,
    }

    def __init__(self, project_root: str) -> None:
        """Initialize pipeline adapter.

        Args:
            project_root: Absolute path to the Django backend directory
        """
        super().__init__(project_root)
        self._setup_django()

    def _setup_django(self) -> None:
        """Ensure Django is configured."""
        # Add project root to Python path
        if self.project_root not in sys.path:
            sys.path.insert(0, self.project_root)

        # Set Django settings module if not already set
        if "DJANGO_SETTINGS_MODULE" not in os.environ:
            # Try to detect settings module
            settings_candidates = [
                "config.settings.local",
                "config.settings",
                "backend.settings.local",
                "backend.settings",
                "settings.local",
                "settings",
            ]

            for candidate in settings_candidates:
                settings_path = Path(self.project_root) / (
                    candidate.replace(".", "/") + ".py"
                )
                if settings_path.exists():
                    os.environ["DJANGO_SETTINGS_MODULE"] = candidate
                    break
            else:
                # Default fallback
                os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.local"

        # Initialize Django if not already done
        try:
            import django

            # Check if Django apps registry is ready
            try:
                from django.apps import apps
                if not apps.ready:
                    django.setup()
            except Exception:
                # Apps not initialized yet, run setup
                django.setup()
        except Exception as e:
            logger.warning(f"Django setup failed: {e}")

    def validate_environment(self) -> bool:
        """Validate that Django is properly configured.

        Returns:
            True if environment is valid, False otherwise
        """
        try:
            import django
            from django.conf import settings

            # Check if Django is configured
            if not settings.configured:
                return False

            # Check for required Django apps
            required_apps = [
                "backend.projects",
                "backend.builds",
                "backend.containers",
                "backend.graphs",
                "backend.e2es",
            ]

            installed_apps = settings.INSTALLED_APPS
            for app in required_apps:
                if app not in installed_apps:
                    logger.warning(f"Required app not installed: {app}")
                    return False

            return True

        except ImportError:
            logger.error("Django is not installed")
            return False
        except Exception as e:
            logger.error(f"Environment validation failed: {e}")
            return False

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover projects to test.

        Args:
            category: Test marker to filter by (e.g., 'pipeline', 'build')
            app: Unused for pipeline adapter
            file: Unused for pipeline adapter

        Returns:
            List of test items (one per project)
        """
        try:
            from backend.projects.models import Project

            # Get all projects (or filter based on configuration)
            projects = Project.objects.all()

            test_items = []
            for project in projects:
                test_items.append(
                    TestItem(
                        id=str(project.id),
                        name=project.name,
                        path=project.slug,
                        markers=["pipeline", "build", "health", "crawl", "e2e"],
                        metadata={
                            "project_id": project.id,
                            "project_slug": project.slug,
                            "repo_url": project.repo.url if project.repo else None,
                        },
                    )
                )

            return test_items

        except Exception as e:
            logger.error(f"Project discovery failed: {e}")
            return []

    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
        # Pipeline-specific options
        projects: Optional[List[str]] = None,
        poll_interval: Optional[int] = None,
        sync_mode: bool = False,
        skip_build: bool = False,
    ) -> TestResult:
        """Execute pipeline tests and return results.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Unused for pipeline adapter (always sequential)
            coverage: Unused for pipeline adapter
            failfast: Stop on first failure
            verbose: Verbose output
            timeout: Max time to wait per project in seconds (default: 600)
            projects: List of project slugs to evaluate
            poll_interval: Seconds between status checks (default: 15)
            sync_mode: Run webhooks synchronously
            skip_build: Skip build, use existing containers

        Returns:
            Test execution results
        """
        import time

        from backend.projects.models import Project

        # Configuration with defaults
        timeout = timeout or 600
        poll_interval = poll_interval or 15

        # Discover tests if not provided
        if tests is None:
            tests = self.discover()

        # Filter tests by project slugs if specified
        if projects:
            tests = [
                t for t in tests
                if t.metadata.get("project_slug") in projects
                or t.name.lower() in [p.lower() for p in projects]
                or any(p.lower() in t.name.lower() for p in projects)
            ]

        if not tests:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                failures=[
                    TestFailure(
                        test_id="discovery",
                        test_name="discovery",
                        message="No projects found to test",
                    )
                ],
                exit_code=2,
            )

        # Execute each test (project evaluation)
        start_time = time.time()
        passed = 0
        failed = 0
        errors = 0
        failures = []

        for test in tests:
            if verbose:
                print(f"\n--- Evaluating: {test.name} ---")

            try:
                # Find project
                project = Project.objects.get(id=int(test.id))

                # Evaluate project through full pipeline
                session_start = time.time()
                metrics = self._evaluate_project(
                    project=project,
                    timeout=timeout,
                    poll_interval=poll_interval,
                    sync_mode=sync_mode,
                    skip_build=skip_build,
                    verbose=verbose,
                )
                session_duration = time.time() - session_start

                # Check if metrics pass criteria
                if self._metrics_pass(metrics):
                    passed += 1
                    if verbose:
                        print(f"  -> PASS ({session_duration:.1f}s)")
                else:
                    failed += 1
                    failure_msg = self._get_failure_message(metrics)
                    failures.append(
                        TestFailure(
                            test_id=test.id,
                            test_name=test.name,
                            message=failure_msg,
                            duration=session_duration,
                            metadata=metrics,
                        )
                    )
                    if verbose:
                        print(f"  -> FAIL: {failure_msg}")

                    if failfast:
                        break

            except Exception as e:
                errors += 1
                failures.append(
                    TestFailure(
                        test_id=test.id,
                        test_name=test.name,
                        message=f"Evaluation error: {str(e)}",
                        metadata={
                            "build_status": "error",
                            "container_healthy": False,
                            "kg_pages": 0,
                            "e2e_passed": 0,
                            "e2e_failed": 0,
                            "e2e_error": 0,
                        },
                    )
                )
                logger.exception(f"Evaluation failed for {test.name}")

                if failfast:
                    break

        duration = time.time() - start_time

        return TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=0,
            duration=duration,
            failures=failures,
            exit_code=0 if errors == 0 and failed == 0 else 1,
        )

    def get_available_markers(self) -> List[str]:
        """Return available test markers/categories.

        Returns:
            List of marker names
        """
        return ["pipeline", "build", "health", "crawl", "e2e"]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _find_project(self, slug: str):
        """Find a project by slug or name."""
        from backend.projects.models import Project

        project = Project.objects.filter(slug__icontains=slug).first()
        if project:
            return project
        project = Project.objects.filter(name__icontains=slug).first()
        return project

    def _trigger_webhook(
        self, project, sync_mode: bool = False, verbose: bool = False
    ) -> bool:
        """Trigger GitHub push webhook for a project.

        Args:
            project: Project instance
            sync_mode: Run synchronously (blocking) if True
            verbose: Print verbose output

        Returns:
            True if webhook was triggered successfully
        """
        try:
            from backend.repos.models import RepositoryInstallation
            from backend.repos.tasks import process_push_webhook
            from backend.pipelines.models import PipelineExecution

            repo = project.repo
            if not repo:
                if verbose:
                    print("  No repository associated with project")
                return False

            repo_install = RepositoryInstallation.objects.filter(repo=repo).first()
            if not repo_install:
                if verbose:
                    print("  No GitHub installation found")
                return False

            # Get latest commit SHA from existing execution
            latest_exec = (
                PipelineExecution.objects.filter(project=project)
                .exclude(metadata={})
                .order_by("-timestamp")
                .first()
            )

            commit_sha = (
                latest_exec.metadata.get("commit_sha")
                if latest_exec and latest_exec.metadata.get("commit_sha")
                else secrets.token_hex(20)
            )

            # Build webhook payload
            if "/" in repo.name:
                owner, repo_name = repo.name.split("/", 1)
            else:
                url_parts = repo.url.rstrip("/").split("/")
                owner = url_parts[-2]
                repo_name = url_parts[-1].replace(".git", "")

            payload = {
                "ref": "refs/heads/main",
                "before": "0" * 40,
                "after": commit_sha,
                "repository": {
                    "id": repo_install.github_repo_id or 0,
                    "name": repo_name,
                    "full_name": f"{owner}/{repo_name}",
                    "html_url": repo.url,
                },
                "pusher": {"name": "systemeval", "email": "eval@debugg.ai"},
                "sender": {"login": "systemeval", "id": 0},
                "commits": [
                    {
                        "id": commit_sha,
                        "message": "System eval",
                        "modified": ["README.md"],
                    }
                ],
                "head_commit": {"id": commit_sha, "message": "System eval"},
            }

            payload_str = (
                json.dumps(payload, sort_keys=True) + f"_eval_{secrets.token_hex(4)}"
            )
            payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()

            if sync_mode:
                process_push_webhook(payload_hash, payload, repo.id)
            else:
                task = process_push_webhook.delay(payload_hash, payload, repo.id)
                if verbose:
                    print(f"  Task queued: {task.id}")

            return True

        except Exception as e:
            logger.exception(f"Failed to trigger webhook for {project.name}")
            if verbose:
                print(f"  Webhook trigger failed: {e}")
            return False

    def _poll_for_completion(
        self,
        project,
        timeout: int,
        poll_interval: int,
        session_start: float,
        skip_build: bool,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Poll for pipeline completion and collect metrics.

        Args:
            project: Project instance
            timeout: Max time to wait in seconds
            poll_interval: Seconds between status checks
            session_start: Start time of this session (Unix timestamp)
            skip_build: Skip build phase if True
            verbose: Print verbose output

        Returns:
            Dictionary of collected metrics
        """
        from datetime import datetime, timezone as dt_timezone
        from django.db.models import Avg, Q
        from django.utils import timezone
        from backend.builds.models import Build
        from backend.containers.models import Container
        from backend.e2es.models import E2eRun, E2eRunMetrics
        from backend.graphs.models import GraphPage, KnowledgeGraph
        from backend.pipelines.models import PipelineExecution

        metrics = {}
        start_wait = time.time()
        session_start_dt = datetime.fromtimestamp(
            session_start, tz=dt_timezone.utc
        )

        while time.time() - start_wait < timeout:
            # Check pipeline execution
            pe = (
                PipelineExecution.objects.filter(project=project)
                .order_by("-timestamp")
                .first()
            )

            if pe:
                metrics["pipeline_status"] = pe.status

            # Check build
            build = Build.objects.filter(project=project).order_by("-timestamp").first()
            if build:
                metrics["build_status"] = build.status
                if build.completed_at and build.timestamp:
                    metrics["build_duration_seconds"] = (
                        build.completed_at - build.timestamp
                    ).total_seconds()

            # Check container
            container = (
                Container.objects.filter(project=project).order_by("-timestamp").first()
            )
            if container:
                metrics["container_healthy"] = container.is_healthy
                metrics["health_checks_passed"] = container.health_checks_passed

            # Check knowledge graph
            kg = KnowledgeGraph.objects.filter(environment__project=project).first()
            if kg:
                metrics["kg_exists"] = True
                metrics["kg_pages"] = GraphPage.objects.filter(graph=kg).count()
            else:
                metrics["kg_exists"] = False
                metrics["kg_pages"] = 0

            # Check E2E metrics - ONLY count runs from this evaluation session
            if pe:
                # Include runs tied to this pipeline execution
                session_runs = E2eRun.objects.filter(
                    Q(project=project, timestamp__gte=session_start_dt)
                    | Q(pipeline_execution=pe)
                )
            else:
                session_runs = E2eRun.objects.filter(
                    project=project, timestamp__gte=session_start_dt
                )

            metrics["e2e_runs"] = session_runs.count()
            metrics["e2e_passed"] = session_runs.filter(outcome="pass").count()
            metrics["e2e_failed"] = session_runs.filter(outcome="fail").count()
            metrics["e2e_error"] = session_runs.filter(outcome="error").count()

            if metrics["e2e_runs"] > 0:
                metrics["e2e_error_rate"] = (
                    metrics["e2e_error"] / metrics["e2e_runs"]
                ) * 100
            else:
                metrics["e2e_error_rate"] = 0.0

            # Get average actions from E2eRunMetrics
            session_run_ids = list(session_runs.values_list("id", flat=True))
            avg_result = E2eRunMetrics.objects.filter(
                run_id__in=session_run_ids
            ).aggregate(avg_steps=Avg("num_steps"))
            metrics["e2e_avg_actions"] = avg_result["avg_steps"] or 0.0

            # Count completed E2E runs
            completed_runs = session_runs.filter(
                status__in=["completed", "error"]
            ).count()
            pending_runs = session_runs.filter(status__in=["pending", "running"]).count()

            # Print progress
            if verbose:
                elapsed = int(time.time() - start_wait)
                build_status = metrics.get("build_status", "none")
                container_status = (
                    "healthy" if metrics.get("container_healthy") else "pending"
                )
                print(
                    f"  [+{elapsed}s] "
                    f"build={build_status} "
                    f"container={container_status} "
                    f"e2e={completed_runs}/{metrics['e2e_runs']} (pending={pending_runs})"
                )

            # Check if we have enough to call it done
            if metrics.get("build_status") == "succeeded" and metrics.get(
                "container_healthy"
            ):
                if skip_build:
                    # In skip_build mode, just check container health
                    break
                elif metrics.get("pipeline_status") in ["completed", "failed"]:
                    # Pipeline done - wait a bit for any in-flight E2E runs
                    if pending_runs == 0 or metrics["e2e_runs"] == 0:
                        break
                elif metrics["e2e_runs"] > 0 and pending_runs == 0:
                    # All E2E runs completed
                    break

            time.sleep(poll_interval)

        return metrics

    def _collect_metrics(
        self, project, session_start: float, verbose: bool = False
    ) -> Dict[str, Any]:
        """Collect comprehensive metrics for a project.

        Args:
            project: Project instance
            session_start: Start time of this session (Unix timestamp)
            verbose: Print verbose output

        Returns:
            Dictionary of metrics including diagnostics
        """
        from datetime import datetime, timezone as dt_timezone
        from django.db.models import Avg, Q
        from django.utils import timezone
        from backend.builds.models import Build
        from backend.containers.models import Container
        from backend.e2es.models import E2eRun, E2eRunMetrics
        from backend.graphs.models import GraphPage, KnowledgeGraph
        from backend.pipelines.models import PipelineExecution, StageExecution
        from backend.surfers.models import Surfer

        session_start_dt = datetime.fromtimestamp(
            session_start, tz=dt_timezone.utc
        )

        metrics = {}
        diagnostics = []

        # =====================================================================
        # BUILD METRICS
        # =====================================================================
        build = Build.objects.filter(project=project).order_by("-timestamp").first()
        if build:
            metrics["build_status"] = build.status
            metrics["build_id"] = str(build.id)
            if build.completed_at and build.timestamp:
                metrics["build_duration"] = (
                    build.completed_at - build.timestamp
                ).total_seconds()
            else:
                metrics["build_duration"] = None
            if build.status != "succeeded":
                diagnostics.append(f"Build {build.status}: check CodeBuild logs")
        else:
            metrics["build_status"] = "not_triggered"
            metrics["build_id"] = None
            metrics["build_duration"] = None
            diagnostics.append("No build found for project")

        # =====================================================================
        # CONTAINER METRICS
        # =====================================================================
        container = (
            Container.objects.filter(project=project).order_by("-timestamp").first()
        )
        if container:
            metrics["container_healthy"] = container.is_healthy
            metrics["health_checks_passed"] = container.health_checks_passed
            metrics["container_id"] = str(container.id)
            if container.started_at and container.timestamp:
                metrics["container_startup_time"] = (
                    container.started_at - container.timestamp
                ).total_seconds()
            else:
                metrics["container_startup_time"] = None
            if not container.is_healthy:
                diagnostics.append(
                    f"Container unhealthy: {container.health_checks_passed} checks passed"
                )
        else:
            metrics["container_healthy"] = False
            metrics["health_checks_passed"] = 0
            metrics["container_id"] = None
            metrics["container_startup_time"] = None
            diagnostics.append("No container found for project")

        # =====================================================================
        # PIPELINE EXECUTION METRICS
        # =====================================================================
        pe = (
            PipelineExecution.objects.filter(project=project)
            .order_by("-timestamp")
            .first()
        )
        if pe:
            metrics["pipeline_status"] = pe.status
            metrics["pipeline_id"] = str(pe.id)
            metrics["pipeline_name"] = pe.pipeline.name if pe.pipeline else None
            if pe.error_message:
                diagnostics.append(f"Pipeline error: {pe.error_message[:100]}")

            # Collect stage breakdown
            stages = StageExecution.objects.filter(
                pipeline_execution=pe
            ).order_by("order")
            stage_details = []
            for stage in stages:
                stage_info = {
                    "name": stage.stage_name,
                    "status": stage.status,
                    "order": stage.order,
                }
                if stage.started_at and stage.completed_at:
                    stage_info["duration"] = (
                        stage.completed_at - stage.started_at
                    ).total_seconds()
                else:
                    stage_info["duration"] = None
                if stage.error_message:
                    stage_info["error"] = stage.error_message[:100]
                    diagnostics.append(
                        f"Stage '{stage.stage_name}' failed: {stage.error_message[:50]}"
                    )
                stage_details.append(stage_info)
            metrics["pipeline_stages"] = stage_details
        else:
            metrics["pipeline_status"] = None
            metrics["pipeline_id"] = None
            metrics["pipeline_name"] = None
            metrics["pipeline_stages"] = []

        # =====================================================================
        # KNOWLEDGE GRAPH METRICS
        # =====================================================================
        kg = KnowledgeGraph.objects.filter(environment__project=project).first()
        if kg:
            metrics["kg_exists"] = True
            metrics["kg_id"] = str(kg.id)
            metrics["kg_pages"] = GraphPage.objects.filter(graph=kg).count()
            if metrics["kg_pages"] == 0:
                diagnostics.append("Knowledge graph exists but has 0 pages - crawl failed")
        else:
            metrics["kg_exists"] = False
            metrics["kg_id"] = None
            metrics["kg_pages"] = 0
            diagnostics.append("No knowledge graph found")

        # =====================================================================
        # SURFER/CRAWLER METRICS
        # =====================================================================
        session_surfers = Surfer.objects.filter(
            project=project,
            timestamp__gte=session_start_dt
        ).order_by("-timestamp")

        surfer_summary = {
            "total": session_surfers.count(),
            "completed": 0,
            "failed": 0,
            "running": 0,
            "errors": [],
        }

        for surfer in session_surfers[:10]:  # Check last 10 surfers
            goal_status = surfer.goal_status
            if goal_status == "DONE":
                surfer_summary["completed"] += 1
            elif goal_status == "FAILED":
                surfer_summary["failed"] += 1
                # Extract error from metadata
                if surfer.metadata and surfer.metadata.get("error"):
                    error_msg = surfer.metadata["error"][:100]
                    if error_msg not in surfer_summary["errors"]:
                        surfer_summary["errors"].append(error_msg)
                        diagnostics.append(f"Surfer error: {error_msg[:60]}")
            elif goal_status is None:
                surfer_summary["running"] += 1

        metrics["surfers"] = surfer_summary

        if surfer_summary["failed"] > 0 and surfer_summary["completed"] == 0:
            diagnostics.append(
                f"All {surfer_summary['failed']} surfers failed - browser issues likely"
            )

        # =====================================================================
        # E2E TEST METRICS (session-scoped)
        # =====================================================================
        if pe:
            session_runs = E2eRun.objects.filter(
                Q(project=project, timestamp__gte=session_start_dt)
                | Q(pipeline_execution=pe)
            )
        else:
            session_runs = E2eRun.objects.filter(
                project=project, timestamp__gte=session_start_dt
            )

        metrics["e2e_runs"] = session_runs.count()
        metrics["e2e_passed"] = session_runs.filter(outcome="pass").count()
        metrics["e2e_failed"] = session_runs.filter(outcome="fail").count()
        metrics["e2e_error"] = session_runs.filter(outcome="error").count()
        metrics["e2e_pending"] = session_runs.filter(
            status__in=["pending", "running"]
        ).count()

        if metrics["e2e_runs"] > 0:
            metrics["e2e_error_rate"] = round(
                (metrics["e2e_error"] / metrics["e2e_runs"]) * 100, 1
            )
            metrics["e2e_pass_rate"] = round(
                (metrics["e2e_passed"] / metrics["e2e_runs"]) * 100, 1
            )
        else:
            metrics["e2e_error_rate"] = 0.0
            metrics["e2e_pass_rate"] = 0.0

        # Get average steps per run
        session_run_ids = list(session_runs.values_list("id", flat=True))
        if session_run_ids:
            avg_result = E2eRunMetrics.objects.filter(
                run_id__in=session_run_ids
            ).aggregate(avg_steps=Avg("num_steps"))
            metrics["e2e_avg_steps"] = round(avg_result["avg_steps"] or 0, 1)
        else:
            metrics["e2e_avg_steps"] = 0.0

        # Check for error runs
        if metrics["e2e_error"] > 0:
            diagnostics.append(
                f"{metrics['e2e_error']} E2E runs errored - this is a system bug!"
            )

        # =====================================================================
        # DIAGNOSTICS SUMMARY
        # =====================================================================
        metrics["diagnostics"] = diagnostics
        metrics["diagnostic_count"] = len(diagnostics)

        return metrics

    def _metrics_pass(self, metrics: Dict[str, Any]) -> bool:
        """Check if metrics pass all criteria.

        Args:
            metrics: Dictionary of collected metrics

        Returns:
            True if all criteria pass
        """
        for metric_name, evaluator in self.CRITERIA.items():
            value = metrics.get(metric_name)
            if not evaluator(value):
                return False
        return True

    def _get_failure_message(self, metrics: Dict[str, Any]) -> str:
        """Generate failure message from metrics.

        Args:
            metrics: Dictionary of collected metrics

        Returns:
            Human-readable failure message
        """
        failures = []

        for metric_name, evaluator in self.CRITERIA.items():
            value = metrics.get(metric_name)
            if not evaluator(value):
                if metric_name == "build_status":
                    failures.append(f"Build failed: {value}")
                elif metric_name == "container_healthy":
                    failures.append("Container not healthy")
                elif metric_name == "kg_exists":
                    failures.append("Knowledge graph does not exist")
                elif metric_name == "kg_pages":
                    failures.append(f"Knowledge graph has {value} pages (required: > 0)")
                elif metric_name == "e2e_error_rate":
                    failures.append(f"E2E error rate: {value:.1f}% (required: 0%)")

        return "; ".join(failures) if failures else "Unknown failure"

    def _evaluate_project(
        self,
        project,
        timeout: int,
        poll_interval: int,
        sync_mode: bool,
        skip_build: bool,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Evaluate a single project through the full pipeline.

        Args:
            project: Project instance
            timeout: Max time to wait in seconds
            poll_interval: Seconds between status checks
            sync_mode: Run synchronously (blocking) if True
            skip_build: Skip build phase if True
            verbose: Print verbose output

        Returns:
            Dictionary of collected metrics
        """
        session_start = time.time()

        # Trigger webhook (unless skip_build)
        if not skip_build:
            triggered = self._trigger_webhook(
                project, sync_mode=sync_mode, verbose=verbose
            )
            if not triggered:
                return {
                    "build_status": "not_triggered",
                    "container_healthy": False,
                    "kg_exists": False,
                    "kg_pages": 0,
                    "e2e_error_rate": 0.0,
                }

        # Poll for completion
        poll_metrics = self._poll_for_completion(
            project=project,
            timeout=timeout,
            poll_interval=poll_interval,
            session_start=session_start,
            skip_build=skip_build,
            verbose=verbose,
        )

        # Collect comprehensive metrics for reporting
        metrics = self._collect_metrics(
            project=project,
            session_start=session_start,
            verbose=verbose,
        )

        return metrics

"""Pipeline adapter implementation for Django pipeline evaluation."""

import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from systemeval.adapters.base import AdapterConfig, BaseAdapter, TestFailure, TestItem, TestResult
from systemeval.adapters.repositories import DjangoProjectRepository, ProjectRepository
from systemeval.core.evaluation import (
    EvaluationResult,
    create_evaluation,
    create_session,
    metric,
)
from systemeval.utils.django import setup_django
from systemeval.utils.logging import get_logger
from systemeval.utils.retry import RetryConfig, retry_with_backoff

logger = get_logger(__name__)


class PipelineAdapter(BaseAdapter):
    """Adapter for Django pipeline evaluation.

    Supports initialization with either AdapterConfig or legacy parameters.

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(
            project_root="/path/to/project",
            timeout=600,
            extra={
                "repository": my_repository,
                "retry_config": RetryConfig(...),
            }
        )
        adapter = PipelineAdapter(config)

        # Using legacy parameters (backward compatible)
        adapter = PipelineAdapter(
            project_root="/path/to/project",
            repository=my_repository,
        )
    """

    # Hardcoded pipeline criteria (matches PIPELINE_CRITERIA from backend.core.testing)
    CRITERIA = {
        "build_status": lambda v: v == "succeeded",
        "container_healthy": lambda v: v is True,
        "kg_exists": lambda v: v is True,
        "kg_pages": lambda v: v is not None and v > 0,
        "e2e_error_rate": lambda v: v == 0 or v == 0.0,
    }

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
        repository: Optional[ProjectRepository] = None,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        """Initialize pipeline adapter with configuration.

        Args:
            config_or_project_root: Either an AdapterConfig object or project root path.
            repository: Project repository (used only if project_root is passed).
            retry_config: Retry configuration for transient failures.
        """
        super().__init__(config_or_project_root)

        # Extract Pipeline-specific settings from config or use legacy params
        if isinstance(config_or_project_root, AdapterConfig):
            self._repository = self.config.get("repository")
            retry_cfg = self.config.get("retry_config")
        else:
            # Legacy initialization
            self._repository = repository
            retry_cfg = retry_config

        # Setup retry configuration with sensible defaults
        self._retry_config = retry_cfg or RetryConfig(
            max_attempts=3,
            initial_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0,
            exceptions=(Exception,),
        )

        # Only setup Django if no repository is provided (backward compatibility)
        if self._repository is None:
            self._setup_django()
            try:
                self._repository = DjangoProjectRepository()
            except (ImportError, RuntimeError) as e:
                logger.warning(
                    f"Failed to create Django repository: {e}. "
                    "Adapter will not be functional without a repository."
                )

    def _setup_django(self) -> None:
        """Ensure Django is configured."""
        setup_django(self.project_root)

    def validate_environment(self) -> bool:
        """Validate that the repository is available."""
        if self._repository is None:
            logger.error("No repository configured")
            return False

        # Try a simple repository operation
        try:
            self._repository.get_all_projects()
            return True
        except Exception as e:
            logger.error(f"Repository validation failed: {e}")
            return False

    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover projects to test."""
        if self._repository is None:
            logger.error("No repository configured for discovery")
            return []

        try:
            # Get all projects from repository
            projects = self._repository.get_all_projects()

            test_items = []
            for project in projects:
                test_items.append(
                    TestItem(
                        id=project["id"],
                        name=project["name"],
                        path=project["slug"],
                        markers=["pipeline", "build", "health", "crawl", "e2e"],
                        metadata={
                            "project_id": project["id"],
                            "project_slug": project["slug"],
                            "repo_url": project.get("repo_url"),
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
        """Execute pipeline tests and return results."""
        import time

        if self._repository is None:
            return TestResult(
                passed=0,
                failed=0,
                errors=1,
                skipped=0,
                duration=0.0,
                failures=[
                    TestFailure(
                        test_id="config",
                        test_name="config",
                        message="No repository configured",
                    )
                ],
                exit_code=2,
            )

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
        results_by_project = {}  # Store metrics for detailed evaluation

        for test in tests:
            if verbose:
                logger.info(f"\n--- Evaluating: {test.name} ---")

            try:
                # Get project data
                project_data = self._repository.get_project_by_id(test.id)
                if not project_data:
                    raise ValueError(f"Project {test.id} not found")

                # For Django repository, extract the instance
                project = project_data.get("_instance")
                if project is None:
                    raise ValueError(
                        "Mock repository does not support full pipeline execution. "
                        "Use DjangoProjectRepository for actual pipeline tests."
                    )

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

                # Store metrics for detailed evaluation
                results_by_project[test.id] = metrics

                # Check if metrics pass criteria
                if self._metrics_pass(metrics):
                    passed += 1
                    if verbose:
                        logger.info(f"  -> PASS ({session_duration:.1f}s)")
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
                        logger.info(f"  -> FAIL: {failure_msg}")

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

        result = TestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=0,
            duration=duration,
            failures=failures,
            exit_code=0 if errors == 0 and failed == 0 else 1,
            # Store tests and metrics for detailed evaluation result generation
            pipeline_tests=tests,
            pipeline_metrics=results_by_project,
            pipeline_adapter=self,
        )

        return result

    def get_available_markers(self) -> List[str]:
        """Return available test markers/categories."""
        return ["pipeline", "build", "health", "crawl", "e2e"]

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _find_project(self, slug: str):
        """Find a project by slug or name.

        Args:
            slug: Project slug or name to search for

        Returns:
            Project instance (Django model) if using DjangoProjectRepository, None otherwise
        """
        if self._repository is None:
            return None

        project_data = self._repository.find_project(slug)
        if project_data:
            # Return the Django instance if available
            return project_data.get("_instance")
        return None

    def _trigger_webhook(
        self, project, sync_mode: bool = False, verbose: bool = False
    ) -> bool:
        """Trigger GitHub push webhook for a project.

        This method uses retry logic to handle transient failures in webhook triggering,
        such as temporary network issues or service unavailability.

        Args:
            project: Project instance (Django model)
            sync_mode: Run synchronously (blocking) if True
            verbose: Print verbose output

        Returns:
            True if webhook was triggered successfully
        """
        @retry_with_backoff(
            max_attempts=self._retry_config.max_attempts,
            initial_delay=self._retry_config.initial_delay,
            max_delay=self._retry_config.max_delay,
            exponential_base=self._retry_config.exponential_base,
            exceptions=(ConnectionError, TimeoutError, OSError),
            logger_instance=logger,
        )
        def _trigger_with_retry():
            """Inner function that performs the webhook trigger with retry."""
            # Import Django-specific modules only when needed
            from backend.repos.tasks import process_push_webhook

            repo = project.repo
            if not repo:
                if verbose:
                    logger.warning("  No repository associated with project")
                return False

            # Use repository abstraction to get installation
            if self._repository:
                installation_data = self._repository.get_repository_installation(repo.id)
            else:
                installation_data = None

            if not installation_data:
                if verbose:
                    logger.warning("  No GitHub installation found")
                return False

            # Get installation instance for Django-specific operations
            repo_install = installation_data.get("_instance")
            if not repo_install:
                if verbose:
                    logger.warning("  Repository installation not available")
                return False

            # Get latest commit SHA from existing execution
            if self._repository:
                latest_exec_data = self._repository.get_latest_pipeline_execution(
                    str(project.id)
                )
                commit_sha = (
                    latest_exec_data.get("metadata", {}).get("commit_sha")
                    if latest_exec_data
                    else secrets.token_hex(20)
                )
            else:
                commit_sha = secrets.token_hex(20)

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
                    logger.debug(f"  Task queued: {task.id}")

            return True

        try:
            return _trigger_with_retry()
        except Exception as e:
            logger.exception(f"Failed to trigger webhook for {project.name} after retries")
            if verbose:
                logger.error(f"  Webhook trigger failed after retries: {e}")
            return False

    def _check_run_status(
        self,
        project,
        session_start_dt,
    ) -> Dict[str, Any]:
        """Check pipeline run status via database queries.

        Fetches current status of build, container, pipeline execution,
        knowledge graph, and E2E runs for the given project.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start datetime (timezone-aware)

        Returns:
            Dictionary of current metrics with internal tracking data
        """
        from django.db.models import Avg, Q
        from backend.builds.models import Build
        from backend.containers.models import Container
        from backend.e2es.models import E2eRun, E2eRunMetrics
        from backend.graphs.models import GraphPage, KnowledgeGraph
        from backend.pipelines.models import PipelineExecution

        current_metrics: Dict[str, Any] = {}

        # Check pipeline execution - filter by session start time to avoid race conditions
        pe = (
            PipelineExecution.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
        )

        if pe:
            current_metrics["pipeline_status"] = pe.status
            current_metrics["_pe_obj"] = pe
            current_metrics["_pe_id"] = str(pe.id)
        else:
            current_metrics["_pe_obj"] = None
            current_metrics["_pe_id"] = None

        # Check build - filter by session start time
        build = (
            Build.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
        )
        if build:
            current_metrics["build_status"] = build.status
            current_metrics["_build_id"] = str(build.id)
            if build.completed_at and build.timestamp:
                current_metrics["build_duration_seconds"] = (
                    build.completed_at - build.timestamp
                ).total_seconds()

        # Check container - filter by session start time
        container = (
            Container.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
        )
        if container:
            current_metrics["container_healthy"] = container.is_healthy
            current_metrics["health_checks_passed"] = container.health_checks_passed
            current_metrics["_container_id"] = str(container.id)

        # Check knowledge graph - use the one from the latest container's environment if available
        # This prevents race conditions where multiple executions might share a KG
        if container and hasattr(container, 'environment'):
            kg = KnowledgeGraph.objects.filter(environment=container.environment).first()
        else:
            kg = KnowledgeGraph.objects.filter(environment__project=project).first()

        if kg:
            current_metrics["kg_exists"] = True
            current_metrics["kg_pages"] = GraphPage.objects.filter(graph=kg).count()
            current_metrics["_kg_id"] = str(kg.id)
        else:
            current_metrics["kg_exists"] = False
            current_metrics["kg_pages"] = 0
            current_metrics["_kg_id"] = None

        # Check E2E metrics - ONLY count runs from this evaluation session
        # Use pipeline execution correlation when available for stronger guarantees
        pe = current_metrics.get("_pe_obj")
        if pe:
            # Include runs tied to this specific pipeline execution OR created after session start
            # The pipeline_execution FK is the strongest correlation
            session_runs = E2eRun.objects.filter(
                Q(pipeline_execution=pe) | Q(project=project, timestamp__gte=session_start_dt)
            ).distinct()
        else:
            # Fallback to timestamp-based filtering
            session_runs = E2eRun.objects.filter(
                project=project, timestamp__gte=session_start_dt
            )

        current_metrics["e2e_runs"] = session_runs.count()
        current_metrics["e2e_passed"] = session_runs.filter(outcome="pass").count()
        current_metrics["e2e_failed"] = session_runs.filter(outcome="fail").count()
        current_metrics["e2e_error"] = session_runs.filter(outcome="error").count()

        if current_metrics["e2e_runs"] > 0:
            current_metrics["e2e_error_rate"] = (
                current_metrics["e2e_error"] / current_metrics["e2e_runs"]
            ) * 100
        else:
            current_metrics["e2e_error_rate"] = 0.0

        # Get average actions from E2eRunMetrics
        session_run_ids = list(session_runs.values_list("id", flat=True))
        avg_result = E2eRunMetrics.objects.filter(
            run_id__in=session_run_ids
        ).aggregate(avg_steps=Avg("num_steps"))
        current_metrics["e2e_avg_actions"] = avg_result["avg_steps"] or 0.0

        # Count completed E2E runs
        current_metrics["_completed_runs"] = session_runs.filter(
            status__in=["completed", "error"]
        ).count()
        current_metrics["_pending_runs"] = session_runs.filter(
            status__in=["pending", "running"]
        ).count()

        return current_metrics

    def _handle_completion(
        self,
        metrics: Dict[str, Any],
        skip_build: bool,
    ) -> bool:
        """Check if pipeline run is complete based on metrics.

        Determines whether polling should stop based on build status,
        container health, pipeline status, and E2E run completion.

        Args:
            metrics: Current metrics dictionary
            skip_build: Whether build phase was skipped

        Returns:
            True if polling should stop (completion detected), False otherwise
        """
        pending_runs = metrics.get("_pending_runs", 0)
        e2e_runs = metrics.get("e2e_runs", 0)

        # Check if we have enough to call it done
        if metrics.get("build_status") == "succeeded" and metrics.get("container_healthy"):
            if skip_build:
                # In skip_build mode, just check container health
                return True
            elif metrics.get("pipeline_status") in ["completed", "failed"]:
                # Pipeline done - wait a bit for any in-flight E2E runs
                if pending_runs == 0 or e2e_runs == 0:
                    return True
            elif e2e_runs > 0 and pending_runs == 0:
                # All E2E runs completed
                return True

        return False

    def _calculate_backoff(
        self,
        attempt: int,
        base_interval: int,
    ) -> float:
        """Calculate polling interval with optional backoff.

        Currently returns a constant interval, but can be extended
        to implement exponential backoff if needed.

        Args:
            attempt: Current polling attempt number (0-indexed)
            base_interval: Base polling interval in seconds

        Returns:
            Sleep duration in seconds
        """
        # For now, use constant polling interval
        # Can be extended to implement exponential backoff if needed
        return float(base_interval)

    def _log_polling_progress(
        self,
        metrics: Dict[str, Any],
        start_wait: float,
    ) -> None:
        """Log polling progress for verbose output.

        Args:
            metrics: Current metrics dictionary
            start_wait: Timestamp when polling started
        """
        elapsed = int(time.time() - start_wait)
        build_status = metrics.get("build_status", "none")
        container_status = "healthy" if metrics.get("container_healthy") else "pending"
        completed_runs = metrics.get("_completed_runs", 0)
        pending_runs = metrics.get("_pending_runs", 0)
        e2e_runs = metrics.get("e2e_runs", 0)
        pe_id = metrics.get("_pe_id")
        exec_info = f"pe={pe_id[:8] if pe_id else 'none'}" if pe_id else ""

        logger.debug(
            f"  [+{elapsed}s] "
            f"build={build_status} "
            f"container={container_status} "
            f"e2e={completed_runs}/{e2e_runs} (pending={pending_runs}) "
            f"{exec_info}"
        )

    def _cleanup_internal_metadata(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Remove internal tracking metadata from metrics.

        Cleans up internal keys used for tracking during polling
        before returning metrics to caller.

        Args:
            metrics: Metrics dictionary with internal keys

        Returns:
            Cleaned metrics dictionary
        """
        internal_keys = ["_pe_id", "_build_id", "_container_id", "_kg_id", "_pe_obj", "_completed_runs", "_pending_runs"]
        for key in internal_keys:
            metrics.pop(key, None)
        return metrics

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

        Orchestrates the polling loop by delegating to focused helper functions:
        - _check_run_status(): Check current status via database
        - _handle_completion(): Determine if polling should stop
        - _calculate_backoff(): Manage polling intervals
        - _log_polling_progress(): Log verbose output
        - _cleanup_internal_metadata(): Clean up before returning

        NOTE: This is a private helper that works with Django model instances directly.
        The abstraction layer is at the public interface (discover/execute), not here.
        This method performs complex database queries that are specific to Django ORM.

        This method includes retry logic for database queries to handle transient
        connection issues during polling.

        RACE CONDITION MITIGATION:
        - Filters all queries by session_start timestamp to prevent mixing metrics
          from concurrent executions
        - Uses pipeline_execution correlation for E2E runs when available
        - Stores execution context in metrics for verification

        Args:
            project: Project instance (Django model)
            timeout: Max time to wait in seconds
            poll_interval: Seconds between status checks
            session_start: Start time of this session (Unix timestamp)
            skip_build: Skip build phase if True
            verbose: Print verbose output

        Returns:
            Dictionary of collected metrics
        """
        from datetime import datetime, timezone as dt_timezone
        from django.db import OperationalError

        metrics: Dict[str, Any] = {}
        start_wait = time.time()
        session_start_dt = datetime.fromtimestamp(
            session_start, tz=dt_timezone.utc
        )

        # Store session context for verification
        metrics["_session_start"] = session_start

        # Create a retry-wrapped version of _check_run_status
        @retry_with_backoff(
            max_attempts=self._retry_config.max_attempts,
            initial_delay=self._retry_config.initial_delay,
            max_delay=self._retry_config.max_delay,
            exponential_base=self._retry_config.exponential_base,
            exceptions=(OperationalError, ConnectionError, TimeoutError),
            logger_instance=logger,
        )
        def _fetch_metrics_with_retry():
            """Fetch metrics with retry on transient database failures."""
            return self._check_run_status(project, session_start_dt)

        attempt = 0
        while time.time() - start_wait < timeout:
            try:
                # Fetch metrics with retry logic
                current_metrics = _fetch_metrics_with_retry()
                metrics.update(current_metrics)

                # Log progress if verbose
                if verbose:
                    self._log_polling_progress(metrics, start_wait)

                # Check if we're done
                if self._handle_completion(metrics, skip_build):
                    break

            except Exception as e:
                # If retry logic failed completely, log and continue polling
                logger.warning(f"Failed to fetch metrics during polling (will retry): {e}")

            # Calculate and apply backoff
            sleep_duration = self._calculate_backoff(attempt, poll_interval)
            time.sleep(sleep_duration)
            attempt += 1

        # Clean up internal metadata before returning
        # Keep session_start for verification in _collect_metrics
        return self._cleanup_internal_metadata(metrics)

    def _collect_build_metrics(
        self, project, session_start_dt, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect build-related metrics.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start as datetime (UTC)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary of build metrics
        """
        from backend.builds.models import Build

        metrics: Dict[str, Any] = {}
        build = (
            Build.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
        )
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

        return metrics

    def _collect_container_metrics(
        self, project, session_start_dt, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect container-related metrics.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start as datetime (UTC)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary of container metrics and the container instance via _container key
        """
        from backend.containers.models import Container

        metrics: Dict[str, Any] = {}
        container = (
            Container.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
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

        # Return container instance for use in KG lookup
        metrics["_container"] = container
        return metrics

    def _collect_pipeline_metrics(
        self, project, session_start_dt, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect pipeline execution metrics.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start as datetime (UTC)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary of pipeline metrics and the pipeline execution instance via _pe key
        """
        from backend.pipelines.models import PipelineExecution, StageExecution

        metrics: Dict[str, Any] = {}
        pe = (
            PipelineExecution.objects.filter(
                project=project,
                timestamp__gte=session_start_dt
            )
            .order_by("-timestamp")
            .first()
        )
        if pe:
            metrics["pipeline_status"] = pe.status
            metrics["pipeline_id"] = str(pe.id)
            metrics["pipeline_name"] = pe.pipeline.name if pe.pipeline else None
            if pe.error_message:
                diagnostics.append(f"Pipeline error: {pe.error_message[:100]}")

            # Collect stage breakdown - correlated by pipeline execution
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

        # Return pipeline execution instance for use in E2E lookup
        metrics["_pe"] = pe
        return metrics

    def _collect_kg_metrics(
        self, project, container, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect knowledge graph metrics.

        Args:
            project: Project instance (Django model)
            container: Container instance (may be None)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary of knowledge graph metrics
        """
        from backend.graphs.models import GraphPage, KnowledgeGraph

        metrics: Dict[str, Any] = {}
        # Use the container's specific environment if available to prevent race conditions
        if container and hasattr(container, 'environment'):
            kg = KnowledgeGraph.objects.filter(environment=container.environment).first()
        else:
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

        return metrics

    def _collect_surfer_metrics(
        self, project, session_start_dt, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect surfer/crawler metrics.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start as datetime (UTC)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary containing surfer summary under 'surfers' key
        """
        from backend.surfers.models import Surfer

        session_surfers = Surfer.objects.filter(
            project=project,
            timestamp__gte=session_start_dt
        ).order_by("-timestamp")

        surfer_summary: Dict[str, Any] = {
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

        if surfer_summary["failed"] > 0 and surfer_summary["completed"] == 0:
            diagnostics.append(
                f"All {surfer_summary['failed']} surfers failed - browser issues likely"
            )

        return {"surfers": surfer_summary}

    def _collect_e2e_metrics(
        self, project, session_start_dt, pe, diagnostics: List[str]
    ) -> Dict[str, Any]:
        """Collect E2E test metrics.

        Args:
            project: Project instance (Django model)
            session_start_dt: Session start as datetime (UTC)
            pe: Pipeline execution instance (may be None)
            diagnostics: List to append diagnostic messages to

        Returns:
            Dictionary of E2E metrics
        """
        from django.db.models import Avg, Q
        from backend.e2es.models import E2eRun, E2eRunMetrics

        metrics: Dict[str, Any] = {}

        if pe:
            # Use pipeline execution FK for strongest correlation
            session_runs = E2eRun.objects.filter(
                Q(pipeline_execution=pe) | Q(project=project, timestamp__gte=session_start_dt)
            ).distinct()
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

        return metrics

    def _collect_metrics(
        self, project, session_start: float, verbose: bool = False
    ) -> Dict[str, Any]:
        """Collect comprehensive metrics for a project.

        NOTE: This is a private helper that works with Django model instances directly.
        The abstraction layer is at the public interface (discover/execute), not here.
        This method performs complex database queries that are specific to Django ORM.

        This method orchestrates collection of metrics from smaller focused functions:
        - _collect_build_metrics: Build status and duration
        - _collect_container_metrics: Container health and startup time
        - _collect_pipeline_metrics: Pipeline execution and stage details
        - _collect_kg_metrics: Knowledge graph existence and page count
        - _collect_surfer_metrics: Surfer/crawler status summary
        - _collect_e2e_metrics: E2E test run statistics

        This method includes retry logic for database queries to handle transient
        connection issues.

        RACE CONDITION MITIGATION:
        - Filters all queries by session_start timestamp to prevent mixing metrics
          from concurrent executions
        - Uses pipeline_execution correlation for E2E runs and stage executions
        - Correlates container with its specific environment for KG lookups

        Args:
            project: Project instance (Django model)
            session_start: Start time of this session (Unix timestamp)
            verbose: Print verbose output

        Returns:
            Dictionary of metrics including diagnostics
        """
        from datetime import datetime, timezone as dt_timezone
        from django.db import OperationalError

        @retry_with_backoff(
            max_attempts=self._retry_config.max_attempts,
            initial_delay=self._retry_config.initial_delay,
            max_delay=self._retry_config.max_delay,
            exponential_base=self._retry_config.exponential_base,
            exceptions=(OperationalError, ConnectionError, TimeoutError),
            logger_instance=logger,
        )
        def _collect_with_retry():
            """Collect all metrics with retry on transient database failures."""
            session_start_dt = datetime.fromtimestamp(
                session_start, tz=dt_timezone.utc
            )

            metrics: Dict[str, Any] = {}
            diagnostics: List[str] = []

            # Store session context for verification
            metrics["_session_start"] = session_start

            # Collect build metrics
            build_metrics = self._collect_build_metrics(
                project, session_start_dt, diagnostics
            )
            metrics.update(build_metrics)

            # Collect container metrics
            container_metrics = self._collect_container_metrics(
                project, session_start_dt, diagnostics
            )
            container = container_metrics.pop("_container")
            metrics.update(container_metrics)

            # Collect pipeline metrics
            pipeline_metrics = self._collect_pipeline_metrics(
                project, session_start_dt, diagnostics
            )
            pe = pipeline_metrics.pop("_pe")
            metrics.update(pipeline_metrics)

            # Collect knowledge graph metrics (needs container for environment)
            kg_metrics = self._collect_kg_metrics(project, container, diagnostics)
            metrics.update(kg_metrics)

            # Collect surfer metrics
            surfer_metrics = self._collect_surfer_metrics(
                project, session_start_dt, diagnostics
            )
            metrics.update(surfer_metrics)

            # Collect E2E metrics (needs pipeline execution for correlation)
            e2e_metrics = self._collect_e2e_metrics(
                project, session_start_dt, pe, diagnostics
            )
            metrics.update(e2e_metrics)

            # Diagnostics summary
            metrics["diagnostics"] = diagnostics
            metrics["diagnostic_count"] = len(diagnostics)

            return metrics

        return _collect_with_retry()

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

    def create_evaluation_result(
        self,
        tests: List[TestItem],
        results_by_project: Dict[str, Dict[str, Any]],
        duration: float,
    ) -> EvaluationResult:
        """Create a detailed EvaluationResult from pipeline metrics.

        Args:
            tests: List of test items (projects evaluated)
            results_by_project: Metrics dictionary keyed by project id
            duration: Total evaluation duration

        Returns:
            EvaluationResult with detailed session and metric data
        """
        evaluation = create_evaluation(
            adapter_type="pipeline",
            category="pipeline",
            project_name="debuggai",
        )

        for test in tests:
            metrics = results_by_project.get(test.id, {})
            session = create_session(test.name)

            # Build metrics
            session.metrics.append(metric(
                name="build_status",
                value=metrics.get("build_status", "unknown"),
                expected="succeeded",
                condition=metrics.get("build_status") == "succeeded",
                message=f"Build {metrics.get('build_status', 'unknown')}",
            ))

            if metrics.get("build_duration"):
                session.metrics.append(metric(
                    name="build_duration",
                    value=metrics.get("build_duration"),
                    expected="<300",
                    condition=True,  # Informational
                    message=f"Build took {metrics.get('build_duration'):.1f}s",
                    severity="info",
                ))

            # Container metrics
            session.metrics.append(metric(
                name="container_healthy",
                value=metrics.get("container_healthy", False),
                expected=True,
                condition=metrics.get("container_healthy", False) is True,
                message="Container healthy" if metrics.get("container_healthy") else "Container not healthy",
            ))

            # Knowledge graph metrics
            session.metrics.append(metric(
                name="kg_exists",
                value=metrics.get("kg_exists", False),
                expected=True,
                condition=metrics.get("kg_exists", False) is True,
                message="Knowledge graph exists" if metrics.get("kg_exists") else "No knowledge graph",
            ))

            session.metrics.append(metric(
                name="kg_pages",
                value=metrics.get("kg_pages", 0),
                expected=">0",
                condition=metrics.get("kg_pages", 0) > 0,
                message=f"Knowledge graph has {metrics.get('kg_pages', 0)} pages",
            ))

            # E2E metrics
            e2e_runs = metrics.get("e2e_runs", 0)
            e2e_error_rate = metrics.get("e2e_error_rate", 0.0)

            session.metrics.append(metric(
                name="e2e_runs",
                value=e2e_runs,
                expected=">=0",
                condition=True,  # Informational
                message=f"{e2e_runs} E2E runs executed",
                severity="info",
            ))

            session.metrics.append(metric(
                name="e2e_error_rate",
                value=e2e_error_rate,
                expected="0",
                condition=e2e_error_rate == 0 or e2e_error_rate == 0.0,
                message=f"E2E error rate: {e2e_error_rate}%" if e2e_error_rate > 0 else "No E2E errors",
            ))

            if metrics.get("e2e_passed", 0) > 0 or metrics.get("e2e_failed", 0) > 0:
                session.metrics.append(metric(
                    name="e2e_passed",
                    value=metrics.get("e2e_passed", 0),
                    expected=">=0",
                    condition=True,
                    message=f"{metrics.get('e2e_passed', 0)} E2E tests passed",
                    severity="info",
                ))

                session.metrics.append(metric(
                    name="e2e_failed",
                    value=metrics.get("e2e_failed", 0),
                    expected="0",
                    condition=metrics.get("e2e_failed", 0) == 0,
                    message=f"{metrics.get('e2e_failed', 0)} E2E tests failed" if metrics.get("e2e_failed", 0) > 0 else None,
                ))

            # Add diagnostics to session metadata
            if metrics.get("diagnostics"):
                session.metadata["diagnostics"] = metrics["diagnostics"]

            # Add pipeline stage details
            if metrics.get("pipeline_stages"):
                session.metadata["pipeline_stages"] = metrics["pipeline_stages"]

            # Add surfer summary
            if metrics.get("surfers"):
                session.metadata["surfers"] = metrics["surfers"]

            evaluation.add_session(session)

        evaluation.metadata.duration_seconds = duration
        evaluation.finalize()

        return evaluation

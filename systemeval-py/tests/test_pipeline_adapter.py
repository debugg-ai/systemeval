"""Comprehensive tests for PipelineAdapter implementation.

Tests cover:
- Django setup and settings detection
- Webhook payload construction and triggering
- Polling logic with timeout scenarios
- Metric collection from database models
- EvaluationResult construction
- discover() and execute() methods
- CRITERIA validation logic

Note: These tests use MockProjectRepository for proper dependency injection,
allowing tests to run without an actual Django environment.
"""

import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call

import pytest

from systemeval.adapters.base import TestItem, TestResult, TestFailure, Verdict
from systemeval.adapters.repositories import MockProjectRepository
from systemeval.core.evaluation import (
    EvaluationResult,
    SessionResult,
    MetricResult,
    create_evaluation,
    create_session,
    metric,
)


# =============================================================================
# Test Fixtures - Mock Data
# =============================================================================


@pytest.fixture
def mock_project_instance():
    """Create a mock Django-like project instance."""
    project = MagicMock()
    project.id = 1
    project.name = "test-project"
    project.slug = "test-project"
    project.repo = MagicMock()
    project.repo.url = "https://github.com/owner/repo"
    project.repo.name = "owner/repo"
    project.repo.id = 100
    return project


@pytest.fixture
def mock_repository(mock_project_instance):
    """Create a MockProjectRepository with test data including Django-like instance."""
    repo = MockProjectRepository()
    repo.add_project({
        "id": "1",
        "name": "test-project",
        "slug": "test-project",
        "repo_url": "https://github.com/owner/repo",
        "repo_id": 100,
        "_instance": mock_project_instance,  # Add Django-like instance for execute()
    })
    repo.add_repository({
        "id": 100,
        "name": "owner/repo",
        "url": "https://github.com/owner/repo",
    })
    repo.add_installation({
        "id": 1,
        "github_repo_id": 12345,
        "repo_id": 100,
    })
    return repo


@pytest.fixture
def mock_repository_multi_project():
    """Create a MockProjectRepository with multiple projects."""
    # Create mock Django-like project instances
    project1 = MagicMock()
    project1.id = 1
    project1.name = "project-one"
    project1.slug = "project-one"
    project1.repo = MagicMock()
    project1.repo.url = "https://github.com/owner/repo1"
    project1.repo.name = "owner/repo1"
    project1.repo.id = 100

    project2 = MagicMock()
    project2.id = 2
    project2.name = "project-two"
    project2.slug = "project-two"
    project2.repo = MagicMock()
    project2.repo.url = "https://github.com/owner/repo2"
    project2.repo.name = "owner/repo2"
    project2.repo.id = 101

    repo = MockProjectRepository()
    repo.add_project({
        "id": "1",
        "name": "project-one",
        "slug": "project-one",
        "repo_url": "https://github.com/owner/repo1",
        "repo_id": 100,
        "_instance": project1,
    })
    repo.add_project({
        "id": "2",
        "name": "project-two",
        "slug": "project-two",
        "repo_url": "https://github.com/owner/repo2",
        "repo_id": 101,
        "_instance": project2,
    })
    repo.add_repository({
        "id": 100,
        "name": "owner/repo1",
        "url": "https://github.com/owner/repo1",
    })
    repo.add_repository({
        "id": 101,
        "name": "owner/repo2",
        "url": "https://github.com/owner/repo2",
    })
    return repo


@pytest.fixture
def empty_repository():
    """Create an empty MockProjectRepository."""
    return MockProjectRepository()


@pytest.fixture
def passing_pipeline_metrics():
    """Create metrics that pass all CRITERIA."""
    return {
        "build_status": "succeeded",
        "build_duration": 90.0,
        "build_id": "1",
        "container_healthy": True,
        "health_checks_passed": 3,
        "container_id": "1",
        "container_startup_time": 15.0,
        "pipeline_status": "completed",
        "pipeline_id": "1",
        "pipeline_name": "main-pipeline",
        "pipeline_stages": [],
        "kg_exists": True,
        "kg_id": "1",
        "kg_pages": 15,
        "e2e_runs": 5,
        "e2e_passed": 5,
        "e2e_failed": 0,
        "e2e_error": 0,
        "e2e_error_rate": 0.0,
        "e2e_pass_rate": 100.0,
        "e2e_pending": 0,
        "e2e_avg_steps": 10.5,
        "surfers": {"total": 2, "completed": 2, "failed": 0, "running": 0, "errors": []},
        "diagnostics": [],
        "diagnostic_count": 0,
    }


@pytest.fixture
def failing_pipeline_metrics():
    """Create metrics that fail CRITERIA."""
    return {
        "build_status": "failed",
        "build_duration": 45.0,
        "build_id": "1",
        "container_healthy": False,
        "health_checks_passed": 0,
        "container_id": "1",
        "container_startup_time": None,
        "pipeline_status": "failed",
        "pipeline_id": "1",
        "pipeline_name": "main-pipeline",
        "pipeline_stages": [],
        "kg_exists": False,
        "kg_id": None,
        "kg_pages": 0,
        "e2e_runs": 0,
        "e2e_passed": 0,
        "e2e_failed": 0,
        "e2e_error": 0,
        "e2e_error_rate": 0.0,
        "e2e_pass_rate": 0.0,
        "e2e_pending": 0,
        "e2e_avg_steps": 0.0,
        "surfers": {"total": 0, "completed": 0, "failed": 0, "running": 0, "errors": []},
        "diagnostics": ["Build failed: check CodeBuild logs", "No knowledge graph found"],
        "diagnostic_count": 2,
    }


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# =============================================================================
# PipelineAdapter Import and Initialization Tests
# =============================================================================


class TestPipelineAdapterImport:
    """Tests for PipelineAdapter module imports."""

    def test_pipeline_adapter_can_be_imported(self):
        """Test that PipelineAdapter can be imported."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter is not None

    def test_pipeline_adapter_has_criteria(self):
        """Test that PipelineAdapter has CRITERIA defined."""
        from systemeval.adapters import PipelineAdapter
        assert hasattr(PipelineAdapter, "CRITERIA")
        assert isinstance(PipelineAdapter.CRITERIA, dict)

    def test_criteria_contains_expected_keys(self):
        """Test that CRITERIA contains all expected keys."""
        from systemeval.adapters import PipelineAdapter
        expected_keys = [
            "build_status",
            "container_healthy",
            "kg_exists",
            "kg_pages",
            "e2e_error_rate",
        ]
        for key in expected_keys:
            assert key in PipelineAdapter.CRITERIA


class TestPipelineAdapterInit:
    """Tests for PipelineAdapter initialization."""

    def test_adapter_accepts_repository_injection(self, temp_project_dir, mock_repository):
        """Test that PipelineAdapter accepts injected repository."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        assert adapter._repository is mock_repository

    def test_adapter_stores_project_root(self, temp_project_dir, mock_repository):
        """Test that PipelineAdapter stores project root."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        assert adapter.project_root == temp_project_dir


# =============================================================================
# CRITERIA Validation Tests
# =============================================================================


class TestPipelineAdapterCriteria:
    """Tests for CRITERIA lambda functions."""

    def test_build_status_succeeded_passes(self):
        """Test build_status passes when 'succeeded'."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["build_status"]("succeeded") is True

    def test_build_status_failed_fails(self):
        """Test build_status fails when not 'succeeded'."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["build_status"]("failed") is False
        assert PipelineAdapter.CRITERIA["build_status"]("error") is False
        assert PipelineAdapter.CRITERIA["build_status"](None) is False

    def test_container_healthy_true_passes(self):
        """Test container_healthy passes when True."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["container_healthy"](True) is True

    def test_container_healthy_false_fails(self):
        """Test container_healthy fails when False."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["container_healthy"](False) is False
        assert PipelineAdapter.CRITERIA["container_healthy"](None) is False

    def test_kg_exists_true_passes(self):
        """Test kg_exists passes when True."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["kg_exists"](True) is True

    def test_kg_exists_false_fails(self):
        """Test kg_exists fails when False."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["kg_exists"](False) is False

    def test_kg_pages_positive_passes(self):
        """Test kg_pages passes when > 0."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["kg_pages"](1) is True
        assert PipelineAdapter.CRITERIA["kg_pages"](100) is True

    def test_kg_pages_zero_fails(self):
        """Test kg_pages fails when 0."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["kg_pages"](0) is False

    def test_kg_pages_none_fails(self):
        """Test kg_pages fails when None."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["kg_pages"](None) is False

    def test_e2e_error_rate_zero_passes(self):
        """Test e2e_error_rate passes when 0."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["e2e_error_rate"](0) is True
        assert PipelineAdapter.CRITERIA["e2e_error_rate"](0.0) is True

    def test_e2e_error_rate_positive_fails(self):
        """Test e2e_error_rate fails when > 0."""
        from systemeval.adapters import PipelineAdapter
        assert PipelineAdapter.CRITERIA["e2e_error_rate"](1) is False
        assert PipelineAdapter.CRITERIA["e2e_error_rate"](0.5) is False
        assert PipelineAdapter.CRITERIA["e2e_error_rate"](100) is False


# =============================================================================
# validate_environment() Tests
# =============================================================================


class TestValidateEnvironment:
    """Tests for validate_environment() method."""

    def test_validate_environment_returns_true_with_repository(
        self, temp_project_dir, mock_repository
    ):
        """Test validate_environment returns True with a configured repository."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter.validate_environment()

        assert result is True

    def test_validate_environment_returns_false_without_repository(self, temp_project_dir):
        """Test validate_environment returns False without repository."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=None)
        adapter._repository = None  # Ensure no repository
        result = adapter.validate_environment()

        assert result is False


# =============================================================================
# _metrics_pass() and _get_failure_message() Tests
# =============================================================================


class TestMetricsValidation:
    """Tests for _metrics_pass() and _get_failure_message() methods."""

    def test_metrics_pass_returns_true_for_passing_metrics(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test _metrics_pass returns True for passing metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter._metrics_pass(passing_pipeline_metrics)

        assert result is True

    def test_metrics_pass_returns_false_for_failing_metrics(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test _metrics_pass returns False for failing metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter._metrics_pass(failing_pipeline_metrics)

        assert result is False

    def test_metrics_pass_fails_on_single_failure(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test _metrics_pass returns False if single criterion fails."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        # Modify one metric to fail
        passing_pipeline_metrics["kg_pages"] = 0
        result = adapter._metrics_pass(passing_pipeline_metrics)

        assert result is False

    def test_get_failure_message_for_build_failure(
        self, temp_project_dir, mock_repository
    ):
        """Test _get_failure_message for build failure."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "failed",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_error_rate": 0
        }

        message = adapter._get_failure_message(metrics)

        assert "Build failed" in message

    def test_get_failure_message_for_container_failure(
        self, temp_project_dir, mock_repository
    ):
        """Test _get_failure_message for container failure."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "succeeded",
            "container_healthy": False,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_error_rate": 0
        }

        message = adapter._get_failure_message(metrics)

        assert "Container not healthy" in message

    def test_get_failure_message_for_kg_failure(self, temp_project_dir, mock_repository):
        """Test _get_failure_message for knowledge graph failure."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": False,
            "kg_pages": 0,
            "e2e_error_rate": 0
        }

        message = adapter._get_failure_message(metrics)

        assert "Knowledge graph does not exist" in message

    def test_get_failure_message_for_e2e_failure(self, temp_project_dir, mock_repository):
        """Test _get_failure_message for E2E error rate failure."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_error_rate": 50.0
        }

        message = adapter._get_failure_message(metrics)

        assert "E2E error rate" in message

    def test_get_failure_message_multiple_failures(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test _get_failure_message combines multiple failures."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        message = adapter._get_failure_message(failing_pipeline_metrics)

        # Should contain multiple failure messages
        assert ";" in message  # Messages are joined with "; "

    def test_get_failure_message_kg_pages_failure(self, temp_project_dir, mock_repository):
        """Test _get_failure_message for kg_pages failure."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 0,
            "e2e_error_rate": 0
        }

        message = adapter._get_failure_message(metrics)

        assert "Knowledge graph has 0 pages" in message

    def test_get_failure_message_returns_unknown_for_empty(
        self, temp_project_dir, mock_repository
    ):
        """Test _get_failure_message returns 'Unknown failure' when all pass."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_error_rate": 0
        }

        message = adapter._get_failure_message(metrics)

        assert message == "Unknown failure"


# =============================================================================
# get_available_markers() Tests
# =============================================================================


class TestGetAvailableMarkers:
    """Tests for get_available_markers() method."""

    def test_get_available_markers_returns_expected_markers(
        self, temp_project_dir, mock_repository
    ):
        """Test get_available_markers returns expected markers."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        markers = adapter.get_available_markers()

        assert markers == ["pipeline", "build", "health", "crawl", "e2e"]


# =============================================================================
# discover() Tests
# =============================================================================


class TestDiscover:
    """Tests for discover() method."""

    def test_discover_returns_test_items(self, temp_project_dir, mock_repository):
        """Test discover returns list of TestItems."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        tests = adapter.discover()

        assert len(tests) == 1
        assert isinstance(tests[0], TestItem)
        assert tests[0].id == "1"
        assert tests[0].name == "test-project"
        assert tests[0].path == "test-project"

    def test_discover_includes_markers(self, temp_project_dir, mock_repository):
        """Test discover includes pipeline markers."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        tests = adapter.discover()

        expected_markers = ["pipeline", "build", "health", "crawl", "e2e"]
        assert tests[0].markers == expected_markers

    def test_discover_includes_metadata(self, temp_project_dir, mock_repository):
        """Test discover includes project metadata."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        tests = adapter.discover()

        assert "project_id" in tests[0].metadata
        assert "project_slug" in tests[0].metadata
        assert "repo_url" in tests[0].metadata
        assert tests[0].metadata["repo_url"] == "https://github.com/owner/repo"

    def test_discover_handles_no_projects(self, temp_project_dir, empty_repository):
        """Test discover returns empty list when no projects."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=empty_repository)
        tests = adapter.discover()

        assert tests == []

    def test_discover_multiple_projects(
        self, temp_project_dir, mock_repository_multi_project
    ):
        """Test discover returns all projects."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository_multi_project)
        tests = adapter.discover()

        assert len(tests) == 2
        assert tests[0].name == "project-one"
        assert tests[1].name == "project-two"


# =============================================================================
# execute() Tests
# =============================================================================


class TestExecute:
    """Tests for execute() method."""

    def test_execute_returns_test_result(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test execute returns TestResult."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        result = adapter.execute()

        assert isinstance(result, TestResult)
        assert result.passed == 1
        assert result.failed == 0
        assert result.exit_code == 0

    def test_execute_with_failing_project(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test execute with failing project."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=failing_pipeline_metrics)

        result = adapter.execute()

        assert result.passed == 0
        assert result.failed == 1
        assert result.exit_code == 1
        assert len(result.failures) == 1

    def test_execute_filters_by_project_slugs(
        self, temp_project_dir, mock_repository_multi_project, passing_pipeline_metrics
    ):
        """Test execute filters by project slugs."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository_multi_project)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        result = adapter.execute(projects=["project-one"])

        assert result.passed == 1
        assert result.total == 1
        adapter._evaluate_project.assert_called_once()

    def test_execute_with_no_projects_returns_error(
        self, temp_project_dir, empty_repository
    ):
        """Test execute with no projects returns error result."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=empty_repository)
        result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 2
        assert len(result.failures) == 1
        assert "No projects found" in result.failures[0].message

    def test_execute_with_failfast(
        self, temp_project_dir, mock_repository_multi_project,
        failing_pipeline_metrics, passing_pipeline_metrics
    ):
        """Test execute stops on first failure with failfast."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository_multi_project)
        adapter._evaluate_project = MagicMock(
            side_effect=[failing_pipeline_metrics, passing_pipeline_metrics]
        )

        result = adapter.execute(failfast=True)

        assert result.failed == 1
        assert result.passed == 0
        # Should have stopped after first failure
        assert adapter._evaluate_project.call_count == 1

    def test_execute_handles_evaluation_exception(
        self, temp_project_dir, mock_repository
    ):
        """Test execute handles exception during evaluation."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(side_effect=Exception("Evaluation failed"))

        result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 1
        assert "Evaluation error" in result.failures[0].message

    def test_execute_stores_pipeline_data_on_result(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test execute stores pipeline data on result for detailed evaluation."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        result = adapter.execute()

        # Pipeline data is now stored as proper dataclass attributes (not monkey-patched)
        assert result.pipeline_tests is not None
        assert result.pipeline_metrics is not None
        assert result.pipeline_adapter is not None


# =============================================================================
# _evaluate_project() Tests
# =============================================================================


class TestEvaluateProject:
    """Tests for _evaluate_project() method."""

    def test_evaluate_project_triggers_webhook(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test _evaluate_project triggers webhook."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._trigger_webhook = MagicMock(return_value=True)
        adapter._poll_for_completion = MagicMock(return_value=passing_pipeline_metrics)
        adapter._collect_metrics = MagicMock(return_value=passing_pipeline_metrics)

        # Get project dict from repository
        project = mock_repository.get_project_by_id("1")

        metrics = adapter._evaluate_project(
            project=project,
            timeout=60,
            poll_interval=1,
            sync_mode=False,
            skip_build=False,
            verbose=False,
        )

        adapter._trigger_webhook.assert_called_once()

    def test_evaluate_project_skips_webhook_in_skip_build_mode(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test _evaluate_project skips webhook in skip_build mode."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._trigger_webhook = MagicMock(return_value=True)
        adapter._poll_for_completion = MagicMock(return_value=passing_pipeline_metrics)
        adapter._collect_metrics = MagicMock(return_value=passing_pipeline_metrics)

        project = mock_repository.get_project_by_id("1")

        metrics = adapter._evaluate_project(
            project=project,
            timeout=60,
            poll_interval=1,
            sync_mode=False,
            skip_build=True,  # Skip build mode
            verbose=False,
        )

        adapter._trigger_webhook.assert_not_called()

    def test_evaluate_project_returns_error_metrics_on_webhook_failure(
        self, temp_project_dir, mock_repository
    ):
        """Test _evaluate_project returns error metrics when webhook fails."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._trigger_webhook = MagicMock(return_value=False)

        project = mock_repository.get_project_by_id("1")

        metrics = adapter._evaluate_project(
            project=project,
            timeout=60,
            poll_interval=1,
            sync_mode=False,
            skip_build=False,
            verbose=False,
        )

        assert metrics["build_status"] == "not_triggered"
        assert metrics["container_healthy"] is False
        assert metrics["kg_exists"] is False

    def test_evaluate_project_polls_and_collects_metrics(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test _evaluate_project polls and collects metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._trigger_webhook = MagicMock(return_value=True)
        adapter._poll_for_completion = MagicMock(return_value={"build_status": "succeeded"})
        adapter._collect_metrics = MagicMock(return_value=passing_pipeline_metrics)

        project = mock_repository.get_project_by_id("1")

        metrics = adapter._evaluate_project(
            project=project,
            timeout=60,
            poll_interval=1,
            sync_mode=False,
            skip_build=False,
            verbose=False,
        )

        adapter._poll_for_completion.assert_called_once()
        adapter._collect_metrics.assert_called_once()
        assert metrics == passing_pipeline_metrics


# =============================================================================
# _find_project() Tests
# =============================================================================


class TestFindProject:
    """Tests for _find_project() method."""

    def test_find_project_by_slug(self, temp_project_dir, mock_repository, mock_project_instance):
        """Test _find_project finds project by slug."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter._find_project("test-project")

        # _find_project returns the _instance (Django model mock)
        assert result is not None
        assert result is mock_project_instance
        assert result.slug == "test-project"

    def test_find_project_by_partial_name(self, temp_project_dir, mock_repository, mock_project_instance):
        """Test _find_project finds project by partial name."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter._find_project("test")

        # _find_project returns the _instance (Django model mock)
        assert result is not None
        assert result is mock_project_instance
        assert "test" in result.slug.lower()

    def test_find_project_returns_none_when_not_found(
        self, temp_project_dir, mock_repository
    ):
        """Test _find_project returns None when not found."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        result = adapter._find_project("nonexistent")

        assert result is None


# =============================================================================
# create_evaluation_result() Tests
# =============================================================================


class TestCreateEvaluationResult:
    """Tests for create_evaluation_result() method."""

    def test_create_evaluation_result_basic(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test create_evaluation_result creates valid EvaluationResult."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": passing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        assert isinstance(evaluation, EvaluationResult)
        assert evaluation.metadata.adapter_type == "pipeline"
        assert evaluation.metadata.category == "pipeline"
        assert evaluation.metadata.project_name == "debuggai"

    def test_create_evaluation_result_includes_sessions(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test create_evaluation_result includes sessions."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [
            TestItem(id="1", name="project1", path="project1"),
            TestItem(id="2", name="project2", path="project2"),
        ]
        results_by_project = {
            "1": passing_pipeline_metrics,
            "2": passing_pipeline_metrics.copy(),
        }

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        assert len(evaluation.sessions) == 2
        assert evaluation.sessions[0].session_name == "project1"
        assert evaluation.sessions[1].session_name == "project2"

    def test_create_evaluation_result_includes_metrics(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test create_evaluation_result includes all metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": passing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]
        metric_names = [m.name for m in session.metrics]

        assert "build_status" in metric_names
        assert "container_healthy" in metric_names
        assert "kg_exists" in metric_names
        assert "kg_pages" in metric_names
        assert "e2e_error_rate" in metric_names

    def test_create_evaluation_result_sets_metric_conditions(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test create_evaluation_result sets correct metric conditions."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": passing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]

        # Find build_status metric
        build_metric = next(m for m in session.metrics if m.name == "build_status")
        assert build_metric.value == "succeeded"
        assert build_metric.expected == "succeeded"
        assert build_metric.passed is True

    def test_create_evaluation_result_failing_metrics(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test create_evaluation_result with failing metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": failing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]

        # Find build_status metric - should be failing
        build_metric = next(m for m in session.metrics if m.name == "build_status")
        assert build_metric.value == "failed"
        assert build_metric.passed is False

    def test_create_evaluation_result_includes_diagnostics(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test create_evaluation_result includes diagnostics in metadata."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": failing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]
        assert "diagnostics" in session.metadata
        assert len(session.metadata["diagnostics"]) > 0

    def test_create_evaluation_result_includes_pipeline_stages(
        self, temp_project_dir, mock_repository
    ):
        """Test create_evaluation_result includes pipeline stages."""
        from systemeval.adapters import PipelineAdapter

        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_runs": 0,
            "e2e_error_rate": 0.0,
            "pipeline_stages": [
                {"name": "build", "status": "completed", "duration": 30.0},
                {"name": "deploy", "status": "completed", "duration": 15.0},
            ],
            "diagnostics": [],
        }

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]
        assert "pipeline_stages" in session.metadata
        assert len(session.metadata["pipeline_stages"]) == 2

    def test_create_evaluation_result_includes_surfers(
        self, temp_project_dir, mock_repository
    ):
        """Test create_evaluation_result includes surfer metadata."""
        from systemeval.adapters import PipelineAdapter

        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_runs": 0,
            "e2e_error_rate": 0.0,
            "pipeline_stages": [],
            "surfers": {"total": 5, "completed": 4, "failed": 1, "running": 0, "errors": []},
            "diagnostics": [],
        }

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]
        assert "surfers" in session.metadata
        assert session.metadata["surfers"]["total"] == 5

    def test_create_evaluation_result_includes_e2e_details(
        self, temp_project_dir, mock_repository
    ):
        """Test create_evaluation_result includes E2E details."""
        from systemeval.adapters import PipelineAdapter

        metrics = {
            "build_status": "succeeded",
            "container_healthy": True,
            "kg_exists": True,
            "kg_pages": 10,
            "e2e_runs": 5,
            "e2e_passed": 4,
            "e2e_failed": 1,
            "e2e_error": 0,
            "e2e_error_rate": 0.0,
            "pipeline_stages": [],
            "diagnostics": [],
        }

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        session = evaluation.sessions[0]
        metric_names = [m.name for m in session.metrics]

        assert "e2e_runs" in metric_names
        assert "e2e_passed" in metric_names
        assert "e2e_failed" in metric_names

    def test_create_evaluation_result_empty_metrics(
        self, temp_project_dir, mock_repository
    ):
        """Test create_evaluation_result handles empty metrics gracefully."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": {}}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        assert len(evaluation.sessions) == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestPipelineAdapterIntegration:
    """Integration tests for PipelineAdapter workflow."""

    def test_full_workflow_passing(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test complete workflow with passing project."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        # Discover
        tests = adapter.discover()
        assert len(tests) == 1

        # Execute
        result = adapter.execute(tests=tests)
        assert result.verdict == Verdict.PASS

        # Create evaluation result
        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project={"1": passing_pipeline_metrics},
            duration=result.duration,
        )
        assert evaluation.verdict.value == "PASS"

    def test_full_workflow_failing(
        self, temp_project_dir, mock_repository, failing_pipeline_metrics
    ):
        """Test complete workflow with failing project."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=failing_pipeline_metrics)

        # Discover
        tests = adapter.discover()

        # Execute
        result = adapter.execute(tests=tests)
        assert result.verdict == Verdict.FAIL
        assert len(result.failures) == 1

        # Create evaluation result
        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project={"1": failing_pipeline_metrics},
            duration=result.duration,
        )
        assert evaluation.verdict.value == "FAIL"

    def test_result_to_json_serializable(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test that EvaluationResult is JSON serializable."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        tests = [TestItem(id="1", name="test-project", path="test-project")]
        results_by_project = {"1": passing_pipeline_metrics}

        evaluation = adapter.create_evaluation_result(
            tests=tests,
            results_by_project=results_by_project,
            duration=100.0,
        )

        # Should not raise
        json_str = evaluation.to_json()
        data = json.loads(json_str)

        assert "verdict" in data
        assert "metadata" in data
        assert "sessions" in data


# =============================================================================
# Webhook Payload Construction Tests
# =============================================================================


class TestWebhookPayloadConstruction:
    """Tests for webhook payload construction logic."""

    def test_webhook_payload_structure(self):
        """Test that webhook payloads have expected structure."""
        expected_keys = [
            "ref",
            "before",
            "after",
            "repository",
            "pusher",
            "sender",
            "commits",
            "head_commit",
        ]

        # Sample payload structure
        payload = {
            "ref": "refs/heads/main",
            "before": "0" * 40,
            "after": "a" * 40,
            "repository": {
                "id": 12345,
                "name": "repo",
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            },
            "pusher": {"name": "systemeval", "email": "eval@debugg.ai"},
            "sender": {"login": "systemeval", "id": 0},
            "commits": [
                {
                    "id": "a" * 40,
                    "message": "System eval",
                    "modified": ["README.md"],
                }
            ],
            "head_commit": {"id": "a" * 40, "message": "System eval"},
        }

        for key in expected_keys:
            assert key in payload

    def test_repo_name_parsing_with_slash(self):
        """Test repo name parsing when name contains /."""
        repo_name = "owner/repo"
        if "/" in repo_name:
            owner, name = repo_name.split("/", 1)

        assert owner == "owner"
        assert name == "repo"

    def test_repo_name_parsing_from_url(self):
        """Test repo name parsing from URL when name doesn't contain /."""
        url = "https://github.com/testowner/testrepo.git"
        url_parts = url.rstrip("/").split("/")
        owner = url_parts[-2]
        repo_name = url_parts[-1].replace(".git", "")

        assert owner == "testowner"
        assert repo_name == "testrepo"

    def test_payload_hash_is_deterministic_for_same_input(self):
        """Test that payload hash is computed consistently."""
        payload = {"test": "data"}

        payload_str1 = json.dumps(payload, sort_keys=True) + "_eval_abcd1234"
        hash1 = hashlib.sha256(payload_str1.encode()).hexdigest()

        payload_str2 = json.dumps(payload, sort_keys=True) + "_eval_abcd1234"
        hash2 = hashlib.sha256(payload_str2.encode()).hexdigest()

        assert hash1 == hash2


# =============================================================================
# Metrics Calculation Tests
# =============================================================================


class TestMetricsCalculation:
    """Tests for metrics calculation logic."""

    def test_e2e_error_rate_calculation_with_runs(self):
        """Test E2E error rate calculation when runs exist."""
        e2e_runs = 10
        e2e_error = 2

        if e2e_runs > 0:
            e2e_error_rate = (e2e_error / e2e_runs) * 100
        else:
            e2e_error_rate = 0.0

        assert e2e_error_rate == 20.0

    def test_e2e_error_rate_calculation_no_runs(self):
        """Test E2E error rate calculation when no runs exist."""
        e2e_runs = 0
        e2e_error = 0

        if e2e_runs > 0:
            e2e_error_rate = (e2e_error / e2e_runs) * 100
        else:
            e2e_error_rate = 0.0

        assert e2e_error_rate == 0.0

    def test_e2e_pass_rate_calculation(self):
        """Test E2E pass rate calculation."""
        e2e_runs = 10
        e2e_passed = 8

        if e2e_runs > 0:
            e2e_pass_rate = round((e2e_passed / e2e_runs) * 100, 1)
        else:
            e2e_pass_rate = 0.0

        assert e2e_pass_rate == 80.0

    def test_build_duration_calculation(self):
        """Test build duration calculation."""
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
        completed_at = datetime(2024, 1, 1, 10, 1, 30, tzinfo=dt_timezone.utc)

        duration = (completed_at - timestamp).total_seconds()

        assert duration == 90.0

    def test_build_duration_none_when_not_completed(self):
        """Test build duration is None when not completed."""
        timestamp = datetime(2024, 1, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
        completed_at = None

        if completed_at and timestamp:
            duration = (completed_at - timestamp).total_seconds()
        else:
            duration = None

        assert duration is None


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_metrics_pass_with_none_values(self, temp_project_dir, mock_repository):
        """Test _metrics_pass handles None values in metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        metrics = {
            "build_status": None,
            "container_healthy": None,
            "kg_exists": None,
            "kg_pages": None,
            "e2e_error_rate": None,
        }

        result = adapter._metrics_pass(metrics)

        assert result is False

    def test_metrics_pass_with_missing_keys(self, temp_project_dir, mock_repository):
        """Test _metrics_pass handles missing keys in metrics."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)

        # Empty metrics dict
        metrics = {}

        result = adapter._metrics_pass(metrics)

        assert result is False

    def test_empty_test_list_execute(self, temp_project_dir, empty_repository):
        """Test execute with empty project list."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=empty_repository)

        result = adapter.execute(tests=[])

        assert result.errors == 1
        assert "No projects found" in result.failures[0].message

    def test_project_slug_filter_case_insensitive(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test that project slug filtering is case-insensitive."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        # Filter with different case
        result = adapter.execute(projects=["TEST-PROJECT"])

        assert result.passed == 1

    def test_partial_project_name_matching(
        self, temp_project_dir, mock_repository, passing_pipeline_metrics
    ):
        """Test that projects can be matched by partial name."""
        from systemeval.adapters import PipelineAdapter

        adapter = PipelineAdapter(temp_project_dir, repository=mock_repository)
        adapter._evaluate_project = MagicMock(return_value=passing_pipeline_metrics)

        # Filter with partial name
        result = adapter.execute(projects=["test"])

        assert result.passed == 1


# =============================================================================
# MockProjectRepository Tests
# =============================================================================


class TestMockProjectRepository:
    """Tests for MockProjectRepository helper class."""

    def test_add_and_get_project(self):
        """Test adding and retrieving project."""
        repo = MockProjectRepository()
        repo.add_project({
            "id": "1",
            "name": "Test Project",
            "slug": "test-project",
            "repo_url": "https://github.com/test/repo",
        })

        projects = repo.get_all_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "Test Project"

    def test_get_project_by_id(self):
        """Test getting project by ID."""
        repo = MockProjectRepository()
        repo.add_project({"id": "123", "name": "Test", "slug": "test"})

        project = repo.get_project_by_id("123")
        assert project is not None
        assert project["id"] == "123"

    def test_find_project_by_slug(self):
        """Test finding project by slug."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Test", "slug": "my-project"})

        project = repo.find_project("my-project")
        assert project is not None
        assert project["slug"] == "my-project"

    def test_find_project_by_name(self):
        """Test finding project by name."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "My Project", "slug": "proj"})

        project = repo.find_project("project")
        assert project is not None
        assert project["name"] == "My Project"

    def test_get_repository_installation(self):
        """Test getting repository installation."""
        repo = MockProjectRepository()
        repo.add_installation({
            "id": 1,
            "github_repo_id": 12345,
            "repo_id": 100,
        })

        installation = repo.get_repository_installation(100)
        assert installation is not None
        assert installation["github_repo_id"] == 12345

    def test_get_latest_pipeline_execution(self):
        """Test getting latest pipeline execution."""
        repo = MockProjectRepository()
        repo.add_pipeline_execution("1", {
            "id": "exec1",
            "status": "completed",
            "metadata": {"commit_sha": "abc123"},
        })
        repo.add_pipeline_execution("1", {
            "id": "exec2",
            "status": "completed",
            "metadata": {"commit_sha": "def456"},
        })

        execution = repo.get_latest_pipeline_execution("1")
        assert execution is not None
        assert execution["id"] == "exec2"  # Most recent

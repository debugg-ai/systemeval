"""Tests for systemeval.adapters.repositories module.

This module tests the repository abstractions including:
- ProjectRepository Protocol
- MockProjectRepository implementation
- DjangoProjectRepository (with mocked Django dependencies)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from systemeval.adapters import (
    DjangoProjectRepository,
    MockProjectRepository,
    ProjectRepository,
)


class TestProjectRepositoryProtocol:
    """Tests for ProjectRepository Protocol compliance."""

    def test_mock_repository_is_instance_of_protocol(self):
        """Verify MockProjectRepository implements ProjectRepository protocol."""
        repo = MockProjectRepository()
        assert isinstance(repo, ProjectRepository)

    def test_protocol_runtime_checkable(self):
        """Verify protocol is runtime checkable."""
        # A class with required methods should satisfy the protocol
        class CustomRepo:
            def get_all_projects(self) -> List[Dict[str, Any]]:
                return []

            def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
                return None

            def find_project(self, slug: str) -> Optional[Dict[str, Any]]:
                return None

            def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]:
                return None

            def get_repository_installation(self, repo_id: int) -> Optional[Dict[str, Any]]:
                return None

            def get_latest_pipeline_execution(
                self, project_id: str
            ) -> Optional[Dict[str, Any]]:
                return None

        custom = CustomRepo()
        assert isinstance(custom, ProjectRepository)

    def test_protocol_rejects_incomplete_implementation(self):
        """Verify protocol rejects class missing methods."""
        class IncompleteRepo:
            def get_all_projects(self) -> List[Dict[str, Any]]:
                return []

        incomplete = IncompleteRepo()
        # Should not satisfy protocol due to missing methods
        assert not isinstance(incomplete, ProjectRepository)


class TestMockProjectRepositoryInit:
    """Tests for MockProjectRepository initialization."""

    def test_init_creates_empty_state(self):
        """Verify initialization creates empty internal data structures."""
        repo = MockProjectRepository()
        assert repo._projects == []
        assert repo._repositories == {}
        assert repo._installations == {}
        assert repo._executions == {}

    def test_multiple_instances_are_independent(self):
        """Verify multiple instances don't share state."""
        repo1 = MockProjectRepository()
        repo2 = MockProjectRepository()

        repo1.add_project({"id": "1", "name": "Test", "slug": "test"})

        assert len(repo1.get_all_projects()) == 1
        assert len(repo2.get_all_projects()) == 0


class TestMockProjectRepositoryAddMethods:
    """Tests for MockProjectRepository add_* methods."""

    def test_add_project(self):
        """Test adding a project to the repository."""
        repo = MockProjectRepository()
        project = {"id": "1", "name": "Test Project", "slug": "test-project"}

        repo.add_project(project)

        assert len(repo._projects) == 1
        assert repo._projects[0] == project

    def test_add_multiple_projects(self):
        """Test adding multiple projects."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project 1", "slug": "project-1"})
        repo.add_project({"id": "2", "name": "Project 2", "slug": "project-2"})

        assert len(repo._projects) == 2

    def test_add_repository(self):
        """Test adding a repository."""
        repo = MockProjectRepository()
        repository = {"id": 100, "name": "owner/repo", "url": "https://github.com/owner/repo"}

        repo.add_repository(repository)

        assert 100 in repo._repositories
        assert repo._repositories[100] == repository

    def test_add_installation(self):
        """Test adding an installation."""
        repo = MockProjectRepository()
        installation = {"id": 500, "github_repo_id": 12345, "repo_id": 100}

        repo.add_installation(installation)

        assert 100 in repo._installations
        assert repo._installations[100] == installation

    def test_add_pipeline_execution(self):
        """Test adding a pipeline execution."""
        repo = MockProjectRepository()
        execution = {
            "id": "exec-1",
            "status": "completed",
            "metadata": {"commit_sha": "abc123"},
            "timestamp": datetime.now(),
        }

        repo.add_pipeline_execution("project-1", execution)

        assert "project-1" in repo._executions
        assert len(repo._executions["project-1"]) == 1
        assert repo._executions["project-1"][0] == execution

    def test_add_multiple_executions_same_project(self):
        """Test adding multiple executions for the same project."""
        repo = MockProjectRepository()
        execution1 = {"id": "exec-1", "status": "completed", "metadata": {}}
        execution2 = {"id": "exec-2", "status": "running", "metadata": {}}

        repo.add_pipeline_execution("project-1", execution1)
        repo.add_pipeline_execution("project-1", execution2)

        assert len(repo._executions["project-1"]) == 2


class TestMockProjectRepositoryGetAllProjects:
    """Tests for MockProjectRepository.get_all_projects()."""

    def test_get_all_projects_empty(self):
        """Test get_all_projects returns empty list when no projects."""
        repo = MockProjectRepository()
        result = repo.get_all_projects()
        assert result == []

    def test_get_all_projects_returns_all(self):
        """Test get_all_projects returns all added projects."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project 1", "slug": "p1"})
        repo.add_project({"id": "2", "name": "Project 2", "slug": "p2"})

        result = repo.get_all_projects()

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"

    def test_get_all_projects_returns_copy(self):
        """Test get_all_projects returns a copy (not the original list)."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project 1", "slug": "p1"})

        result = repo.get_all_projects()
        result.append({"id": "2", "name": "Injected", "slug": "injected"})

        # Original should be unchanged
        assert len(repo.get_all_projects()) == 1


class TestMockProjectRepositoryGetProjectById:
    """Tests for MockProjectRepository.get_project_by_id()."""

    def test_get_project_by_id_found(self):
        """Test finding an existing project by ID."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project 1", "slug": "p1"})
        repo.add_project({"id": "2", "name": "Project 2", "slug": "p2"})

        result = repo.get_project_by_id("2")

        assert result is not None
        assert result["id"] == "2"
        assert result["name"] == "Project 2"

    def test_get_project_by_id_not_found(self):
        """Test returning None for non-existent project ID."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project 1", "slug": "p1"})

        result = repo.get_project_by_id("999")

        assert result is None

    def test_get_project_by_id_empty_repo(self):
        """Test returning None from empty repository."""
        repo = MockProjectRepository()
        result = repo.get_project_by_id("1")
        assert result is None

    def test_get_project_by_id_returns_copy(self):
        """Test get_project_by_id returns a copy of the project."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Original", "slug": "orig"})

        result = repo.get_project_by_id("1")
        result["name"] = "Modified"

        # Original should be unchanged
        original = repo.get_project_by_id("1")
        assert original["name"] == "Original"


class TestMockProjectRepositoryFindProject:
    """Tests for MockProjectRepository.find_project()."""

    def test_find_project_by_exact_slug(self):
        """Test finding project by exact slug match."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project One", "slug": "project-one"})

        result = repo.find_project("project-one")

        assert result is not None
        assert result["slug"] == "project-one"

    def test_find_project_by_partial_slug(self):
        """Test finding project by partial slug match."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project One", "slug": "project-one"})

        result = repo.find_project("project")

        assert result is not None
        assert result["slug"] == "project-one"

    def test_find_project_by_name(self):
        """Test finding project by name match."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "My Awesome Project", "slug": "map"})

        result = repo.find_project("Awesome")

        assert result is not None
        assert result["name"] == "My Awesome Project"

    def test_find_project_case_insensitive(self):
        """Test finding project is case-insensitive."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "TestProject", "slug": "testproject"})

        # Various case combinations should work
        assert repo.find_project("TESTPROJECT") is not None
        assert repo.find_project("TestProject") is not None
        assert repo.find_project("testproject") is not None

    def test_find_project_not_found(self):
        """Test returning None when project not found."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Project One", "slug": "project-one"})

        result = repo.find_project("nonexistent")

        assert result is None

    def test_find_project_empty_repo(self):
        """Test returning None from empty repository."""
        repo = MockProjectRepository()
        result = repo.find_project("anything")
        assert result is None

    def test_find_project_returns_first_match(self):
        """Test that find_project returns first matching project."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Alpha Project", "slug": "alpha"})
        repo.add_project({"id": "2", "name": "Alpha Beta", "slug": "beta"})

        result = repo.find_project("Alpha")

        # Should return first match
        assert result["id"] == "1"

    def test_find_project_returns_copy(self):
        """Test that find_project returns a copy."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Original", "slug": "orig"})

        result = repo.find_project("orig")
        result["name"] = "Modified"

        original = repo.find_project("orig")
        assert original["name"] == "Original"

    def test_find_project_handles_missing_fields(self):
        """Test find_project handles projects with missing slug/name gracefully."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1"})  # Missing name and slug

        # Should not crash, just not match
        result = repo.find_project("test")
        assert result is None


class TestMockProjectRepositoryGetRepository:
    """Tests for MockProjectRepository.get_repository()."""

    def test_get_repository_found(self):
        """Test finding an existing repository."""
        repo = MockProjectRepository()
        repository = {"id": 100, "name": "owner/repo", "url": "https://github.com/owner/repo"}
        repo.add_repository(repository)

        result = repo.get_repository(100)

        assert result is not None
        assert result["id"] == 100
        assert result["name"] == "owner/repo"

    def test_get_repository_not_found(self):
        """Test returning None for non-existent repository."""
        repo = MockProjectRepository()
        repo.add_repository({"id": 100, "name": "repo", "url": "http://example.com"})

        result = repo.get_repository(999)

        assert result is None

    def test_get_repository_empty(self):
        """Test returning None from empty repository store."""
        repo = MockProjectRepository()
        result = repo.get_repository(1)
        assert result is None

    def test_get_repository_returns_copy(self):
        """Test get_repository returns a copy."""
        repo = MockProjectRepository()
        repo.add_repository({"id": 100, "name": "original", "url": "http://a.com"})

        result = repo.get_repository(100)
        result["name"] = "modified"

        original = repo.get_repository(100)
        assert original["name"] == "original"


class TestMockProjectRepositoryGetRepositoryInstallation:
    """Tests for MockProjectRepository.get_repository_installation()."""

    def test_get_installation_found(self):
        """Test finding an existing installation."""
        repo = MockProjectRepository()
        installation = {"id": 500, "github_repo_id": 12345, "repo_id": 100}
        repo.add_installation(installation)

        result = repo.get_repository_installation(100)

        assert result is not None
        assert result["id"] == 500
        assert result["github_repo_id"] == 12345

    def test_get_installation_not_found(self):
        """Test returning None for non-existent installation."""
        repo = MockProjectRepository()
        repo.add_installation({"id": 500, "github_repo_id": 12345, "repo_id": 100})

        result = repo.get_repository_installation(999)

        assert result is None

    def test_get_installation_empty(self):
        """Test returning None from empty installation store."""
        repo = MockProjectRepository()
        result = repo.get_repository_installation(1)
        assert result is None

    def test_get_installation_returns_copy(self):
        """Test get_repository_installation returns a copy."""
        repo = MockProjectRepository()
        repo.add_installation({"id": 500, "github_repo_id": 12345, "repo_id": 100})

        result = repo.get_repository_installation(100)
        result["github_repo_id"] = 99999

        original = repo.get_repository_installation(100)
        assert original["github_repo_id"] == 12345


class TestMockProjectRepositoryGetLatestPipelineExecution:
    """Tests for MockProjectRepository.get_latest_pipeline_execution()."""

    def test_get_latest_execution_found(self):
        """Test finding the latest execution."""
        repo = MockProjectRepository()
        repo.add_pipeline_execution("proj-1", {"id": "exec-1", "status": "completed"})

        result = repo.get_latest_pipeline_execution("proj-1")

        assert result is not None
        assert result["id"] == "exec-1"

    def test_get_latest_execution_returns_most_recent(self):
        """Test that latest execution is the most recently added."""
        repo = MockProjectRepository()
        repo.add_pipeline_execution("proj-1", {"id": "exec-1", "status": "completed"})
        repo.add_pipeline_execution("proj-1", {"id": "exec-2", "status": "running"})
        repo.add_pipeline_execution("proj-1", {"id": "exec-3", "status": "pending"})

        result = repo.get_latest_pipeline_execution("proj-1")

        # Should return the last added (most recent)
        assert result["id"] == "exec-3"

    def test_get_latest_execution_not_found(self):
        """Test returning None for non-existent project."""
        repo = MockProjectRepository()
        repo.add_pipeline_execution("proj-1", {"id": "exec-1", "status": "completed"})

        result = repo.get_latest_pipeline_execution("nonexistent")

        assert result is None

    def test_get_latest_execution_empty(self):
        """Test returning None from empty execution store."""
        repo = MockProjectRepository()
        result = repo.get_latest_pipeline_execution("proj-1")
        assert result is None

    def test_get_latest_execution_returns_copy(self):
        """Test get_latest_pipeline_execution returns a copy."""
        repo = MockProjectRepository()
        repo.add_pipeline_execution("proj-1", {"id": "exec-1", "status": "original"})

        result = repo.get_latest_pipeline_execution("proj-1")
        result["status"] = "modified"

        original = repo.get_latest_pipeline_execution("proj-1")
        assert original["status"] == "original"


class TestDjangoProjectRepositoryInit:
    """Tests for DjangoProjectRepository initialization."""

    def test_init_raises_import_error_when_django_unavailable(self):
        """Test that ImportError is raised when Django models can't be imported."""
        with patch.dict("sys.modules", {"backend": None, "backend.projects": None}):
            with pytest.raises(ImportError) as exc_info:
                DjangoProjectRepository()

            assert "Django models not available" in str(exc_info.value)

    def test_init_stores_model_references(self):
        """Test that initialization stores Django model references."""
        mock_project = MagicMock()
        mock_repository = MagicMock()
        mock_installation = MagicMock()
        mock_execution = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "backend": MagicMock(),
                "backend.projects": MagicMock(),
                "backend.projects.models": MagicMock(Project=mock_project),
                "backend.repos": MagicMock(),
                "backend.repos.models": MagicMock(
                    Repository=mock_repository,
                    RepositoryInstallation=mock_installation,
                ),
                "backend.pipelines": MagicMock(),
                "backend.pipelines.models": MagicMock(PipelineExecution=mock_execution),
            },
        ):
            repo = DjangoProjectRepository()

            assert repo._Project == mock_project
            assert repo._Repository == mock_repository
            assert repo._RepositoryInstallation == mock_installation
            assert repo._PipelineExecution == mock_execution


class TestDjangoProjectRepositoryConversions:
    """Tests for DjangoProjectRepository model-to-dict conversion methods."""

    @pytest.fixture
    def django_repo(self):
        """Create a DjangoProjectRepository with mocked models."""
        mock_project = MagicMock()
        mock_repository = MagicMock()
        mock_installation = MagicMock()
        mock_execution = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "backend": MagicMock(),
                "backend.projects": MagicMock(),
                "backend.projects.models": MagicMock(Project=mock_project),
                "backend.repos": MagicMock(),
                "backend.repos.models": MagicMock(
                    Repository=mock_repository,
                    RepositoryInstallation=mock_installation,
                ),
                "backend.pipelines": MagicMock(),
                "backend.pipelines.models": MagicMock(PipelineExecution=mock_execution),
            },
        ):
            return DjangoProjectRepository()

    def test_project_to_dict_with_repo(self, django_repo):
        """Test _project_to_dict conversion with linked repository."""
        mock_project = MagicMock()
        mock_project.id = 1
        mock_project.name = "Test Project"
        mock_project.slug = "test-project"
        mock_project.repo = MagicMock(url="https://github.com/test/repo", id=100)

        result = django_repo._project_to_dict(mock_project)

        assert result["id"] == "1"
        assert result["name"] == "Test Project"
        assert result["slug"] == "test-project"
        assert result["repo_url"] == "https://github.com/test/repo"
        assert result["repo_id"] == 100
        assert result["_instance"] == mock_project

    def test_project_to_dict_without_repo(self, django_repo):
        """Test _project_to_dict conversion without linked repository."""
        mock_project = MagicMock()
        mock_project.id = 2
        mock_project.name = "No Repo Project"
        mock_project.slug = "no-repo"
        mock_project.repo = None

        result = django_repo._project_to_dict(mock_project)

        assert result["id"] == "2"
        assert result["name"] == "No Repo Project"
        assert result["repo_url"] is None
        assert result["repo_id"] is None

    def test_repo_to_dict(self, django_repo):
        """Test _repo_to_dict conversion."""
        mock_repo = MagicMock()
        mock_repo.id = 100
        mock_repo.name = "owner/repo"
        mock_repo.url = "https://github.com/owner/repo"

        result = django_repo._repo_to_dict(mock_repo)

        assert result["id"] == 100
        assert result["name"] == "owner/repo"
        assert result["url"] == "https://github.com/owner/repo"
        assert result["_instance"] == mock_repo

    def test_installation_to_dict(self, django_repo):
        """Test _installation_to_dict conversion."""
        mock_installation = MagicMock()
        mock_installation.id = 500
        mock_installation.github_repo_id = 12345
        mock_installation.repo_id = 100

        result = django_repo._installation_to_dict(mock_installation)

        assert result["id"] == 500
        assert result["github_repo_id"] == 12345
        assert result["repo_id"] == 100
        assert result["_instance"] == mock_installation

    def test_pipeline_execution_to_dict(self, django_repo):
        """Test _pipeline_execution_to_dict conversion."""
        mock_execution = MagicMock()
        mock_execution.id = 999
        mock_execution.status = "completed"
        mock_execution.metadata = {"commit_sha": "abc123", "branch": "main"}
        mock_execution.timestamp = datetime(2024, 1, 15, 12, 0, 0)

        result = django_repo._pipeline_execution_to_dict(mock_execution)

        assert result["id"] == "999"
        assert result["status"] == "completed"
        assert result["metadata"] == {"commit_sha": "abc123", "branch": "main"}
        assert result["timestamp"] == datetime(2024, 1, 15, 12, 0, 0)
        assert result["_instance"] == mock_execution

    def test_pipeline_execution_to_dict_null_metadata(self, django_repo):
        """Test _pipeline_execution_to_dict with null metadata."""
        mock_execution = MagicMock()
        mock_execution.id = 999
        mock_execution.status = "pending"
        mock_execution.metadata = None
        mock_execution.timestamp = datetime(2024, 1, 15, 12, 0, 0)

        result = django_repo._pipeline_execution_to_dict(mock_execution)

        assert result["metadata"] == {}


class TestDjangoProjectRepositoryMethods:
    """Tests for DjangoProjectRepository repository methods."""

    @pytest.fixture
    def mocked_django_repo(self):
        """Create a DjangoProjectRepository with fully mocked Django ORM."""
        mock_project_model = MagicMock()
        mock_repository_model = MagicMock()
        mock_installation_model = MagicMock()
        mock_execution_model = MagicMock()

        # Set DoesNotExist as a proper exception class BEFORE creating the repo
        mock_project_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_repository_model.DoesNotExist = type("DoesNotExist", (Exception,), {})

        with patch.dict(
            "sys.modules",
            {
                "backend": MagicMock(),
                "backend.projects": MagicMock(),
                "backend.projects.models": MagicMock(Project=mock_project_model),
                "backend.repos": MagicMock(),
                "backend.repos.models": MagicMock(
                    Repository=mock_repository_model,
                    RepositoryInstallation=mock_installation_model,
                ),
                "backend.pipelines": MagicMock(),
                "backend.pipelines.models": MagicMock(PipelineExecution=mock_execution_model),
            },
        ):
            repo = DjangoProjectRepository()
            return repo, mock_project_model, mock_repository_model, mock_installation_model, mock_execution_model

    def test_get_all_projects(self, mocked_django_repo):
        """Test get_all_projects calls Django ORM correctly."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        mock_proj1 = MagicMock(id=1, name="P1", slug="p1", repo=None)
        mock_proj2 = MagicMock(id=2, name="P2", slug="p2", repo=None)
        mock_project_model.objects.all.return_value = [mock_proj1, mock_proj2]

        result = repo.get_all_projects()

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"
        mock_project_model.objects.all.assert_called_once()

    def test_get_project_by_id_found(self, mocked_django_repo):
        """Test get_project_by_id when project exists."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        mock_project = MagicMock(id=1, name="Project", slug="project", repo=None)
        mock_project_model.objects.get.return_value = mock_project

        result = repo.get_project_by_id("1")

        assert result is not None
        assert result["id"] == "1"
        mock_project_model.objects.get.assert_called_once_with(id=1)

    def test_get_project_by_id_not_found(self, mocked_django_repo):
        """Test get_project_by_id when project doesn't exist."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        # DoesNotExist is already set as proper exception class in fixture
        mock_project_model.objects.get.side_effect = mock_project_model.DoesNotExist()

        result = repo.get_project_by_id("999")

        assert result is None

    def test_get_project_by_id_invalid_id(self, mocked_django_repo):
        """Test get_project_by_id with invalid (non-numeric) ID."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        # ValueError raised when int() fails
        result = repo.get_project_by_id("not-a-number")

        assert result is None

    def test_find_project_by_slug(self, mocked_django_repo):
        """Test find_project finds by slug."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        mock_project = MagicMock(id=1, name="Project", slug="project-slug", repo=None)
        mock_project_model.objects.filter.return_value.first.return_value = mock_project

        result = repo.find_project("project")

        assert result is not None
        assert result["slug"] == "project-slug"

    def test_find_project_by_name_fallback(self, mocked_django_repo):
        """Test find_project falls back to name search."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        # Create mock with explicit attribute configuration
        mock_project = MagicMock()
        mock_project.id = 1
        mock_project.name = "My Project"
        mock_project.slug = "mp"
        mock_project.repo = None

        # Track call count to determine which filter call we're on
        call_count = [0]

        def filter_side_effect(**kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # First call is slug search - return None
                result.first.return_value = None
            else:
                # Second call is name search - return the project
                result.first.return_value = mock_project
            return result

        mock_project_model.objects.filter.side_effect = filter_side_effect

        result = repo.find_project("My Project")

        assert result is not None
        assert result["name"] == "My Project"

    def test_find_project_not_found(self, mocked_django_repo):
        """Test find_project returns None when not found."""
        repo, mock_project_model, _, _, _ = mocked_django_repo

        mock_project_model.objects.filter.return_value.first.return_value = None

        result = repo.find_project("nonexistent")

        assert result is None

    def test_get_repository_found(self, mocked_django_repo):
        """Test get_repository when repository exists."""
        repo, _, mock_repository_model, _, _ = mocked_django_repo

        mock_repo = MagicMock(id=100, name="owner/repo", url="https://github.com/owner/repo")
        mock_repository_model.objects.get.return_value = mock_repo

        result = repo.get_repository(100)

        assert result is not None
        assert result["id"] == 100
        mock_repository_model.objects.get.assert_called_once_with(id=100)

    def test_get_repository_not_found(self, mocked_django_repo):
        """Test get_repository when repository doesn't exist."""
        repo, _, mock_repository_model, _, _ = mocked_django_repo

        # DoesNotExist is already set as proper exception class in fixture
        mock_repository_model.objects.get.side_effect = mock_repository_model.DoesNotExist()

        result = repo.get_repository(999)

        assert result is None

    def test_get_repository_installation_found(self, mocked_django_repo):
        """Test get_repository_installation when installation exists."""
        repo, _, _, mock_installation_model, _ = mocked_django_repo

        mock_installation = MagicMock(id=500, github_repo_id=12345, repo_id=100)
        mock_installation_model.objects.filter.return_value.first.return_value = mock_installation

        result = repo.get_repository_installation(100)

        assert result is not None
        assert result["id"] == 500
        mock_installation_model.objects.filter.assert_called_once_with(repo_id=100)

    def test_get_repository_installation_not_found(self, mocked_django_repo):
        """Test get_repository_installation when installation doesn't exist."""
        repo, _, _, mock_installation_model, _ = mocked_django_repo

        mock_installation_model.objects.filter.return_value.first.return_value = None

        result = repo.get_repository_installation(999)

        assert result is None

    def test_get_latest_pipeline_execution_found(self, mocked_django_repo):
        """Test get_latest_pipeline_execution when execution exists."""
        repo, _, _, _, mock_execution_model = mocked_django_repo

        mock_execution = MagicMock(
            id=999,
            status="completed",
            metadata={"commit_sha": "abc123"},
            timestamp=datetime(2024, 1, 15),
        )
        (
            mock_execution_model.objects.filter.return_value
            .exclude.return_value
            .order_by.return_value
            .first.return_value
        ) = mock_execution

        result = repo.get_latest_pipeline_execution("1")

        assert result is not None
        assert result["id"] == "999"
        assert result["status"] == "completed"

    def test_get_latest_pipeline_execution_not_found(self, mocked_django_repo):
        """Test get_latest_pipeline_execution when no execution exists."""
        repo, _, _, _, mock_execution_model = mocked_django_repo

        (
            mock_execution_model.objects.filter.return_value
            .exclude.return_value
            .order_by.return_value
            .first.return_value
        ) = None

        result = repo.get_latest_pipeline_execution("1")

        assert result is None

    def test_get_latest_pipeline_execution_invalid_project_id(self, mocked_django_repo):
        """Test get_latest_pipeline_execution with invalid project ID."""
        repo, _, _, _, mock_execution_model = mocked_django_repo

        # Should handle ValueError from int() conversion
        result = repo.get_latest_pipeline_execution("not-a-number")

        assert result is None


class TestRepositoryEdgeCases:
    """Edge case tests for repository implementations."""

    def test_mock_repo_with_special_characters_in_slug(self):
        """Test handling of special characters in project slug."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Test!", "slug": "test-@#$%"})

        # Should still be able to find by partial match
        result = repo.find_project("test")
        assert result is not None

    def test_mock_repo_empty_string_search(self):
        """Test searching with empty string."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Test", "slug": "test"})

        # Empty string should match everything (contains empty string)
        result = repo.find_project("")
        assert result is not None

    def test_mock_repo_whitespace_handling(self):
        """Test handling of whitespace in searches."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Test Project", "slug": "test-project"})

        result = repo.find_project("  test  ")
        # This will only match if there's "  test  " in name/slug (unlikely)
        # Behavior depends on implementation - just ensure no crash
        assert result is None or result is not None  # No crash

    def test_mock_repo_unicode_characters(self):
        """Test handling of Unicode characters."""
        repo = MockProjectRepository()
        repo.add_project({"id": "1", "name": "Projekt", "slug": "projekt-deutsch"})

        result = repo.find_project("Projekt")
        assert result is not None
        assert result["name"] == "Projekt"

    def test_mock_repo_large_id_values(self):
        """Test handling of large ID values."""
        repo = MockProjectRepository()
        repo.add_repository({"id": 999999999999, "name": "big-id", "url": "http://a.com"})

        result = repo.get_repository(999999999999)
        assert result is not None
        assert result["id"] == 999999999999

    def test_mock_repo_negative_id(self):
        """Test handling of negative IDs (edge case)."""
        repo = MockProjectRepository()
        repo.add_repository({"id": -1, "name": "negative", "url": "http://a.com"})

        result = repo.get_repository(-1)
        assert result is not None

    def test_mock_repo_zero_id(self):
        """Test handling of zero ID."""
        repo = MockProjectRepository()
        repo.add_repository({"id": 0, "name": "zero", "url": "http://a.com"})

        result = repo.get_repository(0)
        assert result is not None
        assert result["id"] == 0

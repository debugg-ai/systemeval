"""Repository abstractions for pipeline adapter.

This module provides framework-agnostic interfaces (Protocols) for data access,
allowing the pipeline adapter to work independently of Django ORM or any specific
data layer implementation.

The abstraction layer follows the Dependency Inversion Principle:
- High-level modules (pipeline_adapter) depend on abstractions (Protocols)
- Low-level modules (Django implementations) implement the abstractions
- Both can vary independently

Usage:
    # In tests or non-Django contexts:
    repo = MockProjectRepository()
    adapter = PipelineAdapter('/path', repository=repo)

    # In Django contexts:
    repo = DjangoProjectRepository()
    adapter = PipelineAdapter('/path', repository=repo)
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ProjectRepository(Protocol):
    """Protocol for project data access operations.

    This defines the contract that any repository implementation must follow.
    Using Protocol allows for duck typing - any object with these methods
    will be accepted, without requiring inheritance.
    """

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all projects available for testing.

        Returns:
            List of project dictionaries with keys:
                - id: str - Unique project identifier
                - name: str - Project display name
                - slug: str - URL-friendly project identifier
                - repo_url: Optional[str] - Git repository URL
                - repo_id: Optional[int] - Repository ID if linked
        """
        ...

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a project by its ID.

        Args:
            project_id: Unique project identifier

        Returns:
            Project dictionary or None if not found
        """
        ...

    def find_project(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find a project by slug or name (case-insensitive).

        Args:
            slug: Project slug or name to search for

        Returns:
            Project dictionary or None if not found
        """
        ...

    def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository details by ID.

        Args:
            repo_id: Repository ID

        Returns:
            Repository dictionary with keys:
                - id: int - Repository ID
                - name: str - Repository name (e.g., "owner/repo")
                - url: str - Repository URL
                - github_repo_id: Optional[int] - GitHub repository ID
        """
        ...

    def get_repository_installation(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get GitHub installation for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Installation dictionary with keys:
                - id: int - Installation ID
                - github_repo_id: Optional[int] - GitHub repository ID
                - repo_id: int - Repository ID
        """
        ...

    def get_latest_pipeline_execution(
        self, project_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent pipeline execution for a project.

        Args:
            project_id: Project identifier

        Returns:
            Pipeline execution dictionary with keys:
                - id: str - Execution ID
                - status: str - Execution status
                - metadata: Dict[str, Any] - Additional metadata (commit_sha, etc.)
                - timestamp: datetime - When execution started
        """
        ...


class DjangoProjectRepository:
    """Django ORM implementation of ProjectRepository.

    This implementation uses Django models to provide project data.
    It is only available when Django is properly configured.

    The repository translates Django model instances into plain dictionaries,
    decoupling the adapter from Django-specific types.
    """

    def __init__(self) -> None:
        """Initialize Django repository.

        Raises:
            ImportError: If Django models cannot be imported
            RuntimeError: If Django is not properly configured
        """
        # Import Django models only when this implementation is instantiated
        # This allows the rest of the codebase to work without Django
        try:
            from backend.projects.models import Project
            from backend.repos.models import Repository, RepositoryInstallation
            from backend.pipelines.models import PipelineExecution

            self._Project = Project
            self._Repository = Repository
            self._RepositoryInstallation = RepositoryInstallation
            self._PipelineExecution = PipelineExecution

        except ImportError as e:
            raise ImportError(
                f"Django models not available. Ensure Django is configured: {e}"
            )

    def _project_to_dict(self, project) -> Dict[str, Any]:
        """Convert Django Project model to dictionary.

        Args:
            project: Django Project model instance

        Returns:
            Project dictionary
        """
        return {
            "id": str(project.id),
            "name": project.name,
            "slug": project.slug,
            "repo_url": project.repo.url if project.repo else None,
            "repo_id": project.repo.id if project.repo else None,
            "_instance": project,  # Keep reference for Django-specific operations
        }

    def _repo_to_dict(self, repo) -> Dict[str, Any]:
        """Convert Django Repository model to dictionary.

        Args:
            repo: Django Repository model instance

        Returns:
            Repository dictionary
        """
        return {
            "id": repo.id,
            "name": repo.name,
            "url": repo.url,
            "_instance": repo,
        }

    def _installation_to_dict(self, installation) -> Dict[str, Any]:
        """Convert Django RepositoryInstallation model to dictionary.

        Args:
            installation: Django RepositoryInstallation model instance

        Returns:
            Installation dictionary
        """
        return {
            "id": installation.id,
            "github_repo_id": installation.github_repo_id,
            "repo_id": installation.repo_id,
            "_instance": installation,
        }

    def _pipeline_execution_to_dict(self, execution) -> Dict[str, Any]:
        """Convert Django PipelineExecution model to dictionary.

        Args:
            execution: Django PipelineExecution model instance

        Returns:
            Pipeline execution dictionary
        """
        return {
            "id": str(execution.id),
            "status": execution.status,
            "metadata": execution.metadata or {},
            "timestamp": execution.timestamp,
            "_instance": execution,
        }

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from Django ORM."""
        projects = self._Project.objects.all()
        return [self._project_to_dict(p) for p in projects]

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a project by ID from Django ORM."""
        try:
            project = self._Project.objects.get(id=int(project_id))
            return self._project_to_dict(project)
        except (self._Project.DoesNotExist, ValueError):
            return None

    def find_project(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find a project by slug or name from Django ORM."""
        # Try slug first
        project = self._Project.objects.filter(slug__icontains=slug).first()
        if project:
            return self._project_to_dict(project)

        # Try name
        project = self._Project.objects.filter(name__icontains=slug).first()
        if project:
            return self._project_to_dict(project)

        return None

    def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository by ID from Django ORM."""
        try:
            repo = self._Repository.objects.get(id=repo_id)
            return self._repo_to_dict(repo)
        except self._Repository.DoesNotExist:
            return None

    def get_repository_installation(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository installation from Django ORM."""
        installation = self._RepositoryInstallation.objects.filter(
            repo_id=repo_id
        ).first()
        if installation:
            return self._installation_to_dict(installation)
        return None

    def get_latest_pipeline_execution(
        self, project_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest pipeline execution from Django ORM."""
        try:
            execution = (
                self._PipelineExecution.objects.filter(project_id=int(project_id))
                .exclude(metadata={})
                .order_by("-timestamp")
                .first()
            )
            if execution:
                return self._pipeline_execution_to_dict(execution)
        except ValueError:
            pass
        return None


class MockProjectRepository:
    """Mock implementation of ProjectRepository for testing.

    This allows the pipeline adapter to be tested without a Django backend.
    Useful for unit tests, integration tests, and non-Django environments.

    Example:
        repo = MockProjectRepository()
        repo.add_project({
            'id': '1',
            'name': 'Test Project',
            'slug': 'test-project',
            'repo_url': 'https://github.com/test/repo'
        })
        adapter = PipelineAdapter('/path', repository=repo)
    """

    def __init__(self) -> None:
        """Initialize mock repository with empty data."""
        self._projects: List[Dict[str, Any]] = []
        self._repositories: Dict[int, Dict[str, Any]] = {}
        self._installations: Dict[int, Dict[str, Any]] = {}
        self._executions: Dict[str, List[Dict[str, Any]]] = {}

    def add_project(self, project: Dict[str, Any]) -> None:
        """Add a project to the mock repository.

        Args:
            project: Project dictionary
        """
        self._projects.append(project)

    def add_repository(self, repo: Dict[str, Any]) -> None:
        """Add a repository to the mock repository.

        Args:
            repo: Repository dictionary
        """
        self._repositories[repo["id"]] = repo

    def add_installation(self, installation: Dict[str, Any]) -> None:
        """Add an installation to the mock repository.

        Args:
            installation: Installation dictionary
        """
        self._installations[installation["repo_id"]] = installation

    def add_pipeline_execution(self, project_id: str, execution: Dict[str, Any]) -> None:
        """Add a pipeline execution to the mock repository.

        Args:
            project_id: Project identifier
            execution: Execution dictionary
        """
        if project_id not in self._executions:
            self._executions[project_id] = []
        self._executions[project_id].append(execution)

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from mock data."""
        return self._projects.copy()

    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a project by ID from mock data."""
        for project in self._projects:
            if project["id"] == project_id:
                return project.copy()
        return None

    def find_project(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find a project by slug or name from mock data."""
        slug_lower = slug.lower()
        for project in self._projects:
            if (
                slug_lower in project.get("slug", "").lower()
                or slug_lower in project.get("name", "").lower()
            ):
                return project.copy()
        return None

    def get_repository(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository by ID from mock data."""
        return self._repositories.get(repo_id, {}).copy() if repo_id in self._repositories else None

    def get_repository_installation(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """Get repository installation from mock data."""
        return self._installations.get(repo_id, {}).copy() if repo_id in self._installations else None

    def get_latest_pipeline_execution(
        self, project_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get latest pipeline execution from mock data."""
        executions = self._executions.get(project_id, [])
        if executions:
            # Return most recent (last added)
            return executions[-1].copy()
        return None

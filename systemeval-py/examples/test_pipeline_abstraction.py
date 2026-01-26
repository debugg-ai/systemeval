"""Example demonstrating the pipeline adapter abstraction layer.

This example shows how to use the PipelineAdapter with different repository
implementations, demonstrating that the adapter is decoupled from Django.
"""

import sys
from pathlib import Path

# Add systemeval to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from systemeval.adapters.pipeline_adapter import PipelineAdapter
from systemeval.adapters.repositories import MockProjectRepository


def test_with_mock_repository():
    """Test PipelineAdapter with a mock repository (no Django required)."""
    print("Testing PipelineAdapter with MockProjectRepository...")
    print("=" * 60)

    # Create a mock repository
    repo = MockProjectRepository()

    # Add test projects
    repo.add_project({
        "id": "1",
        "name": "Test Project 1",
        "slug": "test-project-1",
        "repo_url": "https://github.com/test/repo1",
        "repo_id": 101,
    })

    repo.add_project({
        "id": "2",
        "name": "Test Project 2",
        "slug": "test-project-2",
        "repo_url": "https://github.com/test/repo2",
        "repo_id": 102,
    })

    # Create adapter with mock repository
    adapter = PipelineAdapter(
        project_root="/fake/path",
        repository=repo
    )

    # Validate environment
    print("\n1. Validating environment...")
    is_valid = adapter.validate_environment()
    print(f"   Environment valid: {is_valid}")

    # Discover projects
    print("\n2. Discovering projects...")
    tests = adapter.discover()
    print(f"   Found {len(tests)} projects:")
    for test in tests:
        print(f"   - {test.name} (id={test.id}, slug={test.path})")
        print(f"     Markers: {', '.join(test.markers)}")
        print(f"     Repo URL: {test.metadata.get('repo_url')}")

    # Find specific project
    print("\n3. Finding specific project by slug...")
    project_data = repo.find_project("test-project-1")
    if project_data:
        print(f"   Found: {project_data['name']}")
    else:
        print("   Not found")

    # Test execute (will fail gracefully with mock repo)
    print("\n4. Testing execute (expected to fail with mock repo)...")
    try:
        result = adapter.execute(tests=tests[:1], verbose=False)
        print(f"   Result: {result.passed} passed, {result.failed} failed, {result.errors} errors")
        if result.failures:
            print(f"   Error message: {result.failures[0].message}")
    except Exception as e:
        print(f"   Exception (expected): {e}")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("\nKey takeaway: The adapter works without any Django imports")
    print("when using MockProjectRepository. This demonstrates successful")
    print("decoupling from Django ORM.")


def test_with_django_repository():
    """Test PipelineAdapter with DjangoProjectRepository (requires Django)."""
    print("\n\nTesting PipelineAdapter with DjangoProjectRepository...")
    print("=" * 60)

    try:
        # This will fail if Django is not configured, which is expected
        from systemeval.adapters.repositories import DjangoProjectRepository

        repo = DjangoProjectRepository()
        adapter = PipelineAdapter(
            project_root="/path/to/backend",
            repository=repo
        )

        print("\n1. Django repository initialized successfully")
        print("2. Discovering projects from Django ORM...")

        tests = adapter.discover()
        print(f"   Found {len(tests)} projects from database")
        for test in tests[:3]:  # Show first 3
            print(f"   - {test.name}")

    except ImportError as e:
        print(f"\nDjango not available (expected in this context): {e}")
        print("This is fine - it demonstrates that Django is optional")
    except Exception as e:
        print(f"\nDjango configuration issue: {e}")
        print("This is expected if not running in Django environment")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Test with mock repository (no Django required)
    test_with_mock_repository()

    # Test with Django repository (will gracefully fail if Django not configured)
    test_with_django_repository()

    print("\n\nSummary:")
    print("--------")
    print("The abstraction layer successfully decouples the PipelineAdapter")
    print("from Django ORM. The adapter can work with:")
    print("  1. MockProjectRepository - for testing without Django")
    print("  2. DjangoProjectRepository - for production use with Django")
    print("  3. Any custom implementation of ProjectRepository protocol")

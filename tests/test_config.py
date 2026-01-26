"""Tests for configuration loading and validation in systemeval.config."""

import tempfile
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

import pytest
import yaml

from systemeval.config import (
    AnyEnvironmentConfig,
    CompositeEnvConfig,
    DockerComposeEnvConfig,
    EnvironmentConfig,
    HealthCheckConfig,
    NgrokEnvConfig,
    PipelineConfig,
    PytestConfig,
    StandaloneEnvConfig,
    SystemEvalConfig,
    TestCategory,
    find_config_file,
    load_config,
    parse_environment_config,
)


class TestLoadConfigHappyPath:
    """Tests for successful config loading."""

    def test_load_minimal_config(self, tmp_path: Path):
        """Test loading a minimal valid config with just adapter."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
        """).strip())

        config = load_config(config_file)

        assert config.adapter == "pytest"
        assert config.project_root == tmp_path

    def test_load_config_with_pytest_section(self, tmp_path: Path):
        """Test loading config with pytest-specific configuration."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            pytest:
              config_file: pytest.ini
              base_path: tests
              default_category: unit
        """).strip())

        config = load_config(config_file)

        assert config.pytest_config is not None
        assert config.pytest_config.config_file == "pytest.ini"
        assert config.pytest_config.base_path == "tests"
        assert config.pytest_config.default_category == "unit"
        assert config.test_directory == Path("tests")

    def test_load_config_with_pipeline_section(self, tmp_path: Path):
        """Test loading config with pipeline-specific configuration."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pipeline
            pipeline:
              projects:
                - project-one
                - project-two
              timeout: 300
              poll_interval: 10
              sync_mode: true
              skip_build: true
        """).strip())

        config = load_config(config_file)

        assert config.pipeline_config is not None
        assert config.pipeline_config.projects == ["project-one", "project-two"]
        assert config.pipeline_config.timeout == 300
        assert config.pipeline_config.poll_interval == 10
        assert config.pipeline_config.sync_mode is True
        assert config.pipeline_config.skip_build is True
        # Pipeline config should also be in adapter_config
        assert config.adapter_config["timeout"] == 300

    def test_load_config_with_categories(self, tmp_path: Path):
        """Test loading config with test categories."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            categories:
              unit:
                description: Unit tests
                markers:
                  - unit
                test_match:
                  - "**/test_*.py"
                paths:
                  - tests/unit
                requires:
                  - pytest
              integration:
                description: Integration tests
                markers:
                  - integration
                paths:
                  - tests/integration
        """).strip())

        config = load_config(config_file)

        assert len(config.categories) == 2
        assert "unit" in config.categories
        assert "integration" in config.categories

        unit_cat = config.categories["unit"]
        assert unit_cat.description == "Unit tests"
        assert unit_cat.markers == ["unit"]
        assert unit_cat.test_match == ["**/test_*.py"]
        assert unit_cat.paths == ["tests/unit"]
        assert unit_cat.requires == ["pytest"]

    def test_load_config_with_project_info(self, tmp_path: Path):
        """Test loading config with project information."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            project:
              name: my-test-project
        """).strip())

        config = load_config(config_file)

        assert config.project_name == "my-test-project"

    def test_load_config_with_environments(self, tmp_path: Path):
        """Test loading config with environment definitions."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              local:
                type: standalone
                command: npm start
                ready_pattern: "Server running"
                port: 3000
                default: true
              docker:
                type: docker-compose
                compose_file: docker-compose.yml
                services:
                  - api
                  - db
                test_service: api
        """).strip())

        config = load_config(config_file)

        assert len(config.environments) == 2
        assert "local" in config.environments
        assert "docker" in config.environments

        local_env = config.environments["local"]
        assert local_env.type == "standalone"
        assert local_env.command == "npm start"
        assert local_env.default is True

        docker_env = config.environments["docker"]
        assert docker_env.type == "docker-compose"
        assert docker_env.services == ["api", "db"]

    def test_load_config_resolves_working_dir_relative_to_config(self, tmp_path: Path):
        """Test that working_dir in environments is resolved relative to config file."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              backend:
                type: standalone
                working_dir: backend
        """).strip())

        config = load_config(config_file)

        # working_dir should be resolved to absolute path
        expected_working_dir = str(tmp_path / "backend")
        assert config.environments["backend"].working_dir == expected_working_dir

    def test_load_config_preserves_absolute_working_dir(self, tmp_path: Path):
        """Test that absolute working_dir is preserved unchanged."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              backend:
                type: standalone
                working_dir: /absolute/path/to/backend
        """).strip())

        config = load_config(config_file)

        assert config.environments["backend"].working_dir == "/absolute/path/to/backend"

    def test_load_config_with_empty_categories(self, tmp_path: Path):
        """Test loading config with empty category definitions."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            categories:
              unit: {}
              quick: null
        """).strip())

        config = load_config(config_file)

        assert "unit" in config.categories
        assert "quick" in config.categories
        # Empty dict should create default TestCategory
        assert config.categories["unit"].description is None
        assert config.categories["unit"].markers == []


class TestLoadConfigErrors:
    """Tests for config loading error cases."""

    def test_load_config_file_not_found(self, tmp_path: Path):
        """Test that FileNotFoundError is raised for missing config."""
        config_file = tmp_path / "nonexistent.yaml"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_config(config_file)

        assert "Config file not found" in str(exc_info.value)

    def test_load_config_empty_file(self, tmp_path: Path):
        """Test that ValueError is raised for empty config file."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("")

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "Empty or invalid config file" in str(exc_info.value)

    def test_load_config_whitespace_only(self, tmp_path: Path):
        """Test that ValueError is raised for whitespace-only config."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("   \n\n   \n")

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "Empty or invalid config file" in str(exc_info.value)

    def test_load_config_malformed_yaml(self, tmp_path: Path):
        """Test that malformed YAML raises an exception."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            categories:
              - this is invalid
                because: indentation is wrong
              and: this
        """).strip())

        with pytest.raises(yaml.YAMLError):
            load_config(config_file)

    def test_load_config_invalid_adapter_name(self, tmp_path: Path):
        """Test that invalid adapter name raises ValidationError."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: invalid_adapter_name
        """).strip())

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "not registered" in str(exc_info.value)
        assert "invalid_adapter_name" in str(exc_info.value)

    def test_load_config_invalid_composite_dependency(self, tmp_path: Path):
        """Test that composite env with missing dependency raises error."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              full:
                type: composite
                depends_on:
                  - backend
                  - frontend
              backend:
                type: standalone
        """).strip())

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "depends on" in str(exc_info.value)
        assert "frontend" in str(exc_info.value)


class TestLoadConfigDefaults:
    """Tests for default value handling in config loading."""

    def test_default_adapter_is_pytest(self, tmp_path: Path):
        """Test that default adapter is pytest."""
        config_file = tmp_path / "systemeval.yaml"
        # Minimal config without adapter specified
        config_file.write_text(dedent("""
            project:
              name: test
        """).strip())

        config = load_config(config_file)

        assert config.adapter == "pytest"

    def test_default_project_root_is_config_directory(self, tmp_path: Path):
        """Test that project_root defaults to config file's directory."""
        subdir = tmp_path / "configs"
        subdir.mkdir()
        config_file = subdir / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        config = load_config(config_file)

        assert config.project_root == subdir

    def test_default_test_directory(self, tmp_path: Path):
        """Test that test_directory has a default value."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        config = load_config(config_file)

        assert config.test_directory == Path("tests")

    def test_default_categories_empty(self, tmp_path: Path):
        """Test that categories defaults to empty dict."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        config = load_config(config_file)

        assert config.categories == {}

    def test_default_environments_empty(self, tmp_path: Path):
        """Test that environments defaults to empty dict."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        config = load_config(config_file)

        assert config.environments == {}


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_find_config_in_current_directory(self, tmp_path: Path):
        """Test finding config in current directory."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        result = find_config_file(tmp_path)

        assert result == config_file

    def test_find_config_in_parent_directory(self, tmp_path: Path):
        """Test finding config in parent directory."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        child_dir = tmp_path / "child" / "grandchild"
        child_dir.mkdir(parents=True)

        result = find_config_file(child_dir)

        assert result == config_file

    def test_find_config_not_found(self, tmp_path: Path):
        """Test that None is returned when config not found."""
        # Create a deep directory structure with no config
        deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
        deep_dir.mkdir(parents=True)

        result = find_config_file(deep_dir)

        assert result is None

    def test_find_config_respects_max_depth(self, tmp_path: Path):
        """Test that find_config_file only searches up to 5 levels."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        # Create directory 6 levels deep
        deep_dir = tmp_path
        for i in range(6):
            deep_dir = deep_dir / f"level{i}"
        deep_dir.mkdir(parents=True)

        result = find_config_file(deep_dir)

        # Should not find config because it's more than 5 levels up
        assert result is None

    def test_find_config_at_exactly_5_levels(self, tmp_path: Path):
        """Test that config is found at exactly 5 levels up."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        # Create directory exactly 4 levels deep (5th iteration finds it)
        deep_dir = tmp_path
        for i in range(4):
            deep_dir = deep_dir / f"level{i}"
        deep_dir.mkdir(parents=True)

        result = find_config_file(deep_dir)

        assert result == config_file

    def test_find_config_defaults_to_cwd(self, tmp_path: Path):
        """Test that find_config_file defaults to cwd when no start_path."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text("adapter: pytest")

        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = find_config_file()
            assert result == config_file
        finally:
            os.chdir(original_cwd)


class TestPydanticModels:
    """Tests for individual Pydantic configuration models."""

    def test_test_category_defaults(self):
        """Test TestCategory default values."""
        category = TestCategory()

        assert category.description is None
        assert category.markers == []
        assert category.test_match == []
        assert category.paths == []
        assert category.requires == []

    def test_health_check_config_required_fields(self):
        """Test HealthCheckConfig with required service field."""
        with pytest.raises(ValueError):
            HealthCheckConfig()

        config = HealthCheckConfig(service="api")
        assert config.service == "api"
        assert config.endpoint == "/api/v1/health/"
        assert config.port == 8000
        assert config.timeout == 120

    def test_environment_config_type_literal(self):
        """Test EnvironmentConfig type validation."""
        # Valid types
        config = EnvironmentConfig(type="standalone")
        assert config.type == "standalone"

        config = EnvironmentConfig(type="docker-compose")
        assert config.type == "docker-compose"

        config = EnvironmentConfig(type="composite")
        assert config.type == "composite"

    def test_standalone_env_config_defaults(self):
        """Test StandaloneEnvConfig default values."""
        config = StandaloneEnvConfig()

        assert config.type == "standalone"
        assert config.command == ""
        assert config.ready_pattern == ""
        assert config.port == 3000
        assert config.env == {}

    def test_docker_compose_env_config_defaults(self):
        """Test DockerComposeEnvConfig default values."""
        config = DockerComposeEnvConfig()

        assert config.type == "docker-compose"
        assert config.compose_file == "docker-compose.yml"
        assert config.services == []
        assert config.test_service == "django"
        assert config.health_check is None
        assert config.project_name is None
        assert config.skip_build is False

    def test_composite_env_config_defaults(self):
        """Test CompositeEnvConfig default values."""
        config = CompositeEnvConfig()

        assert config.type == "composite"
        assert config.depends_on == []

    def test_pytest_config_defaults(self):
        """Test PytestConfig default values."""
        config = PytestConfig()

        assert config.config_file is None
        assert config.base_path == "."
        assert config.default_category == "unit"

    def test_pipeline_config_defaults(self):
        """Test PipelineConfig default values."""
        config = PipelineConfig()

        assert config.projects == ["crochet-patterns"]
        assert config.timeout == 600
        assert config.poll_interval == 15
        assert config.sync_mode is False
        assert config.skip_build is False


class TestSystemEvalConfigValidation:
    """Tests for SystemEvalConfig validation."""

    def test_path_validator_converts_strings(self):
        """Test that string paths are converted to Path objects."""
        config = SystemEvalConfig(
            project_root="/some/path",
            test_directory="tests/unit",
        )

        assert isinstance(config.project_root, Path)
        assert isinstance(config.test_directory, Path)
        assert config.project_root == Path("/some/path")
        assert config.test_directory == Path("tests/unit")

    def test_path_validator_preserves_path_objects(self):
        """Test that Path objects are preserved."""
        project_path = Path("/my/project")
        test_path = Path("tests")

        config = SystemEvalConfig(
            project_root=project_path,
            test_directory=test_path,
        )

        assert config.project_root == project_path
        assert config.test_directory == test_path

    def test_composite_dependency_validation_passes(self):
        """Test composite env validation passes when dependencies exist."""
        config = SystemEvalConfig(
            environments={
                "full": {
                    "type": "composite",
                    "depends_on": ["backend", "frontend"],
                },
                "backend": {"type": "standalone"},
                "frontend": {"type": "standalone"},
            }
        )

        # Should not raise
        assert len(config.environments) == 3

    def test_composite_dependency_validation_fails(self):
        """Test composite env validation fails when dependency missing."""
        with pytest.raises(ValueError) as exc_info:
            SystemEvalConfig(
                environments={
                    "full": {
                        "type": "composite",
                        "depends_on": ["missing_env"],
                    },
                }
            )

        assert "depends on" in str(exc_info.value)
        assert "missing_env" in str(exc_info.value)


class TestEnvironmentConfigParsing:
    """Tests for environment configuration parsing in load_config."""

    def test_environment_with_health_check(self, tmp_path: Path):
        """Test loading environment with health check configuration."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              docker:
                type: docker-compose
                compose_file: local.yml
                health_check:
                  service: django
                  endpoint: /api/v1/health/
                  port: 8002
                  timeout: 60
        """).strip())

        config = load_config(config_file)

        docker_env = config.environments["docker"]
        assert docker_env.health_check.service == "django"
        assert docker_env.health_check.port == 8002
        assert docker_env.health_check.timeout == 60

    def test_multiple_environments_mixed_types(self, tmp_path: Path):
        """Test loading multiple environments with different types."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              local:
                type: standalone
                command: npm run dev
                port: 3000
                env:
                  NODE_ENV: development
                  DEBUG: "true"
              docker:
                type: docker-compose
                compose_file: docker-compose.yml
                services:
                  - api
                  - db
                  - redis
              full:
                type: composite
                depends_on:
                  - local
                  - docker
        """).strip())

        config = load_config(config_file)

        assert len(config.environments) == 3

        local = config.environments["local"]
        assert local.type == "standalone"
        assert local.env["NODE_ENV"] == "development"

        docker = config.environments["docker"]
        assert docker.type == "docker-compose"
        assert len(docker.services) == 3

        full = config.environments["full"]
        assert full.type == "composite"
        assert full.depends_on == ["local", "docker"]

    def test_environment_with_default_flag(self, tmp_path: Path):
        """Test loading environment with default flag."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              local:
                type: standalone
                default: true
              docker:
                type: docker-compose
                default: false
        """).strip())

        config = load_config(config_file)

        assert config.environments["local"].default is True
        assert config.environments["docker"].default is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_load_config_with_null_project(self, tmp_path: Path):
        """Test loading config when project is null."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            project: null
        """).strip())

        config = load_config(config_file)

        assert config.project_name is None

    def test_load_config_with_empty_pytest_section(self, tmp_path: Path):
        """Test loading config with empty pytest section."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            pytest: {}
        """).strip())

        config = load_config(config_file)

        assert config.pytest_config is not None
        assert config.pytest_config.config_file is None

    def test_load_config_with_extra_fields(self, tmp_path: Path):
        """Test that extra fields in YAML are ignored gracefully."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            unknown_field: some_value
            another_unknown:
              nested: true
        """).strip())

        # Should not raise - extra fields are ignored
        config = load_config(config_file)

        assert config.adapter == "pytest"

    def test_load_config_yaml_with_anchors_and_aliases(self, tmp_path: Path):
        """Test loading YAML with anchors and aliases."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest

            # Define common values
            defaults: &defaults
              markers:
                - slow

            categories:
              integration:
                <<: *defaults
                description: Integration tests
              e2e:
                <<: *defaults
                description: End-to-end tests
        """).strip())

        config = load_config(config_file)

        assert config.categories["integration"].markers == ["slow"]
        assert config.categories["e2e"].markers == ["slow"]
        assert config.categories["integration"].description == "Integration tests"

    def test_load_config_special_characters_in_paths(self, tmp_path: Path):
        """Test loading config with special characters in paths."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              local:
                type: standalone
                working_dir: "path with spaces/and-dashes/under_scores"
        """).strip())

        config = load_config(config_file)

        expected = str(tmp_path / "path with spaces/and-dashes/under_scores")
        assert config.environments["local"].working_dir == expected

    def test_load_config_unicode_content(self, tmp_path: Path):
        """Test loading config with unicode content."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            project:
              name: projet-test
            categories:
              unit:
                description: "Tests unitaires pour le projet"
        """).strip(), encoding="utf-8")

        config = load_config(config_file)

        assert "unitaires" in config.categories["unit"].description
        assert config.project_name == "projet-test"

    def test_load_config_numeric_strings(self, tmp_path: Path):
        """Test loading config with numeric values as strings - Pydantic coerces to int."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            environments:
              local:
                type: standalone
                port: "3000"
        """).strip())

        config = load_config(config_file)

        # Port is typed as int in StandaloneEnvConfig, so Pydantic coerces "3000" to 3000
        assert config.environments["local"].port == 3000


# ============================================================================
# V2.0 Multi-Project Configuration Tests
# ============================================================================


class TestV2MultiProjectConfig:
    """Tests for v2.0 multi-project configuration support."""

    def test_load_v2_config_with_subprojects(self, tmp_path: Path):
        """Test loading a v2.0 config with subprojects."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"
            project_root: .

            defaults:
              timeout: 300

            subprojects:
              - name: backend
                path: backend
                adapter: pytest
                env:
                  DJANGO_SETTINGS_MODULE: config.settings.test
                enabled: true

              - name: frontend
                path: app
                adapter: vitest
                pre_commands:
                  - npm install
                tags:
                  - unit
                  - frontend
        """).strip())

        config = load_config(config_file)

        assert config.version == "2.0"
        assert config.is_multi_project is True
        assert len(config.subprojects) == 2

        # Check backend subproject
        backend = config.get_subproject("backend")
        assert backend is not None
        assert backend.name == "backend"
        assert backend.path == "backend"
        assert backend.adapter == "pytest"
        assert backend.env["DJANGO_SETTINGS_MODULE"] == "config.settings.test"
        assert backend.enabled is True

        # Check frontend subproject
        frontend = config.get_subproject("frontend")
        assert frontend is not None
        assert frontend.name == "frontend"
        assert frontend.path == "app"
        assert frontend.adapter == "vitest"
        assert frontend.pre_commands == ["npm install"]
        assert "unit" in frontend.tags
        assert "frontend" in frontend.tags

    def test_load_v2_config_with_defaults(self, tmp_path: Path):
        """Test v2.0 config defaults are properly parsed."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            defaults:
              timeout: 600
              parallel: true
              coverage: true

            subprojects:
              - name: tests
                path: tests
                adapter: pytest
        """).strip())

        config = load_config(config_file)

        assert config.defaults is not None
        assert config.defaults.timeout == 600
        assert config.defaults.parallel is True
        assert config.defaults.coverage is True

    def test_v2_config_get_effective_timeout(self, tmp_path: Path):
        """Test effective timeout resolution with subproject override."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            defaults:
              timeout: 300

            subprojects:
              - name: fast-tests
                path: fast
                adapter: pytest
                timeout: 60

              - name: slow-tests
                path: slow
                adapter: pytest
        """).strip())

        config = load_config(config_file)

        fast = config.get_subproject("fast-tests")
        slow = config.get_subproject("slow-tests")

        # Fast tests have explicit timeout override
        assert config.get_effective_timeout(fast) == 60

        # Slow tests inherit from defaults
        assert config.get_effective_timeout(slow) == 300

    def test_v2_config_get_enabled_subprojects(self, tmp_path: Path):
        """Test filtering subprojects by enabled status."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            subprojects:
              - name: backend
                path: backend
                adapter: pytest
                enabled: true

              - name: e2e
                path: e2e
                adapter: playwright
                enabled: false
                tags:
                  - e2e

              - name: frontend
                path: app
                adapter: vitest
                enabled: true
                tags:
                  - frontend
        """).strip())

        config = load_config(config_file)

        enabled = config.get_enabled_subprojects()
        assert len(enabled) == 2
        assert all(sp.enabled for sp in enabled)
        assert "e2e" not in [sp.name for sp in enabled]

    def test_v2_config_filter_by_tags(self, tmp_path: Path):
        """Test filtering subprojects by tags."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            subprojects:
              - name: backend-unit
                path: backend
                adapter: pytest
                tags:
                  - unit
                  - backend

              - name: frontend-unit
                path: app
                adapter: vitest
                tags:
                  - unit
                  - frontend

              - name: e2e
                path: e2e
                adapter: playwright
                tags:
                  - e2e
        """).strip())

        config = load_config(config_file)

        # Filter by unit tag
        unit_tests = config.get_enabled_subprojects(tags=["unit"])
        assert len(unit_tests) == 2
        assert all("unit" in sp.tags for sp in unit_tests)

        # Filter by backend tag
        backend_tests = config.get_enabled_subprojects(tags=["backend"])
        assert len(backend_tests) == 1
        assert backend_tests[0].name == "backend-unit"

    def test_v2_config_filter_by_names(self, tmp_path: Path):
        """Test filtering subprojects by names."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            subprojects:
              - name: backend
                path: backend
                adapter: pytest
              - name: frontend
                path: app
                adapter: vitest
              - name: e2e
                path: e2e
                adapter: playwright
        """).strip())

        config = load_config(config_file)

        # Filter by specific names
        selected = config.get_enabled_subprojects(names=["backend", "frontend"])
        assert len(selected) == 2
        assert set(sp.name for sp in selected) == {"backend", "frontend"}

    def test_v2_config_backward_compat_with_legacy_fields(self, tmp_path: Path):
        """Test v2.0 config can coexist with legacy v1.0 fields."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            # Legacy v1.0 fields still work
            adapter: pytest
            categories:
              unit:
                description: Unit tests
                markers:
                  - unit

            # V2.0 multi-project
            subprojects:
              - name: backend
                path: backend
                adapter: pytest
        """).strip())

        config = load_config(config_file)

        # V2.0 features work
        assert config.is_multi_project is True
        assert len(config.subprojects) == 1

        # Legacy fields still accessible
        assert config.adapter == "pytest"
        assert "unit" in config.categories

    def test_v1_config_is_not_multi_project(self, tmp_path: Path):
        """Test v1.0 config is not detected as multi-project."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            adapter: pytest
            test_directory: tests
        """).strip())

        config = load_config(config_file)

        assert config.version == "1.0"
        assert config.is_multi_project is False
        assert len(config.subprojects) == 0


class TestSubprojectConfigValidation:
    """Tests for SubprojectConfig validation."""

    def test_subproject_name_validation_valid(self):
        """Test valid subproject names are accepted."""
        from systemeval.config import SubprojectConfig

        valid_names = ["backend", "frontend", "e2e-tests", "unit_tests", "app123"]
        for name in valid_names:
            sp = SubprojectConfig(name=name, path=".")
            assert sp.name == name

    def test_subproject_name_validation_invalid(self):
        """Test invalid subproject names are rejected."""
        from systemeval.config import SubprojectConfig

        invalid_names = ["", "123start", "-invalid", "_invalid", "has space", "has.dot"]
        for name in invalid_names:
            with pytest.raises(ValueError):
                SubprojectConfig(name=name, path=".")

    def test_subproject_duplicate_names_rejected(self, tmp_path: Path):
        """Test duplicate subproject names are rejected."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "2.0"

            subprojects:
              - name: backend
                path: backend1
                adapter: pytest
              - name: backend
                path: backend2
                adapter: pytest
        """).strip())

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "Duplicate subproject names" in str(exc_info.value)


class TestDefaultsConfig:
    """Tests for DefaultsConfig model."""

    def test_defaults_config_defaults(self):
        """Test DefaultsConfig has sensible defaults."""
        from systemeval.config import DefaultsConfig

        defaults = DefaultsConfig()

        assert defaults.timeout == 300
        assert defaults.parallel is False
        assert defaults.coverage is False
        assert defaults.verbose is False
        assert defaults.failfast is False

    def test_defaults_config_custom_values(self):
        """Test DefaultsConfig accepts custom values."""
        from systemeval.config import DefaultsConfig

        defaults = DefaultsConfig(
            timeout=600,
            parallel=True,
            coverage=True,
            verbose=True,
            failfast=True,
        )

        assert defaults.timeout == 600
        assert defaults.parallel is True
        assert defaults.coverage is True


class TestMultiProjectResultModels:
    """Tests for SubprojectResult and MultiProjectResult models."""

    def test_subproject_result_defaults(self):
        """Test SubprojectResult has sensible defaults."""
        from systemeval.config import SubprojectResult

        result = SubprojectResult(name="backend", adapter="pytest")

        assert result.name == "backend"
        assert result.adapter == "pytest"
        assert result.passed == 0
        assert result.failed == 0
        assert result.status == "SKIP"

    def test_multi_project_result_calculate_totals(self):
        """Test MultiProjectResult calculates totals correctly."""
        from systemeval.config import MultiProjectResult, SubprojectResult

        result = MultiProjectResult(
            subprojects=[
                SubprojectResult(name="backend", adapter="pytest", passed=10, failed=2, status="FAIL"),
                SubprojectResult(name="frontend", adapter="vitest", passed=20, failed=0, status="PASS"),
                SubprojectResult(name="e2e", adapter="playwright", passed=5, failed=0, status="PASS"),
            ]
        )

        result.calculate_totals()

        assert result.total_passed == 35
        assert result.total_failed == 2
        assert result.verdict == "FAIL"  # One subproject failed

    def test_multi_project_result_all_pass(self):
        """Test MultiProjectResult verdict when all pass."""
        from systemeval.config import MultiProjectResult, SubprojectResult

        result = MultiProjectResult(
            subprojects=[
                SubprojectResult(name="backend", adapter="pytest", passed=10, failed=0, status="PASS"),
                SubprojectResult(name="frontend", adapter="vitest", passed=20, failed=0, status="PASS"),
            ]
        )

        result.calculate_totals()

        assert result.verdict == "PASS"

    def test_multi_project_result_error_verdict(self):
        """Test MultiProjectResult verdict when one has error."""
        from systemeval.config import MultiProjectResult, SubprojectResult

        result = MultiProjectResult(
            subprojects=[
                SubprojectResult(name="backend", adapter="pytest", passed=10, status="PASS"),
                SubprojectResult(name="frontend", adapter="vitest", status="ERROR", error_message="npm install failed"),
            ]
        )

        result.calculate_totals()

        assert result.verdict == "ERROR"

    def test_multi_project_result_to_json(self):
        """Test MultiProjectResult JSON serialization."""
        from systemeval.config import MultiProjectResult, SubprojectResult

        result = MultiProjectResult(
            subprojects=[
                SubprojectResult(name="backend", adapter="pytest", passed=10, failed=1, status="FAIL"),
            ]
        )
        result.calculate_totals()

        json_dict = result.to_json_dict()

        assert json_dict["verdict"] == "FAIL"
        assert json_dict["total_passed"] == 10
        assert json_dict["total_failed"] == 1
        assert len(json_dict["subprojects"]) == 1
        assert json_dict["subprojects"][0]["name"] == "backend"


class TestConfigVersionValidation:
    """Tests for config version validation."""

    def test_invalid_version_rejected(self, tmp_path: Path):
        """Test invalid config version is rejected."""
        config_file = tmp_path / "systemeval.yaml"
        config_file.write_text(dedent("""
            version: "3.0"
            adapter: pytest
        """).strip())

        with pytest.raises(ValueError) as exc_info:
            load_config(config_file)

        assert "Invalid version" in str(exc_info.value)
        assert "3.0" in str(exc_info.value)

    def test_valid_versions_accepted(self, tmp_path: Path):
        """Test valid config versions are accepted."""
        for version in ["1.0", "2.0"]:
            config_file = tmp_path / "systemeval.yaml"
            config_file.write_text(f"""
version: "{version}"
adapter: pytest
""".strip())

            config = load_config(config_file)
            assert config.version == version

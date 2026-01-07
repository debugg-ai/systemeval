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

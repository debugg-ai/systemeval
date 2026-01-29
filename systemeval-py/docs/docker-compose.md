# Docker Compose Environment Reference

SystemEval provides comprehensive Docker Compose support for running tests inside containers with automatic discovery, lifecycle management, and remote Docker host support.

## Overview

The `docker-compose` environment type handles:
- **Auto-discovery**: Finds compose files and infers test configuration
- **Lifecycle management**: Build, start, health check, test, teardown
- **Attach mode**: Connect to already-running containers
- **Remote Docker**: Execute against remote Docker hosts
- **Pre-flight checks**: Validate Docker setup before running

## Configuration

### Minimal (Auto-Discovery)

```yaml
environments:
  backend:
    type: docker-compose
```

SystemEval will automatically discover:
- Compose file location
- Test service (first service with source mount)
- Test command (from pytest.ini, package.json, etc.)
- Health check endpoint and port

### Full Configuration

```yaml
environments:
  backend:
    type: docker-compose

    # Compose file (auto-detected if omitted)
    compose_file: local.yml

    # Services to manage (all services if omitted)
    services:
      - django
      - postgres
      - redis

    # Container to run tests in
    test_service: django

    # Test command (auto-detected if omitted)
    test_command: pytest

    # Project directory (default: .)
    working_dir: .

    # Skip docker build phase
    skip_build: false

    # Override Docker Compose project name
    project_name: my-project

    # Health check configuration
    health_check:
      service: django        # Service to health check
      endpoint: /api/health/ # HTTP endpoint
      port: 8000            # Port to check
      timeout: 120          # Seconds to wait

    # Remote Docker host (optional)
    docker:
      host: ssh://user@remote-server
      # Or use Docker context
      context: my-remote-context

    # Attach to running containers (skip build/up)
    attach: false

    # Auto-discover missing config from compose file
    auto_discover: true
```

## Auto-Discovery

### Compose File Search Order

SystemEval searches for compose files in this order:
1. `docker-compose.yml`
2. `docker-compose.yaml`
3. `compose.yml`
4. `compose.yaml`
5. `local.yml` / `local.yaml`
6. `dev.yml` / `dev.yaml`

### Test Service Detection

The test service is inferred as the first service that has:
1. A source code volume mount (e.g., `./src:/app/src`)
2. A build context (not just an image)
3. A working directory defined

### Test Command Detection

Test commands are inferred from project files:
- `pytest.ini` or `pyproject.toml` with pytest config → `pytest`
- `package.json` with `test` script → `npm test`
- `Makefile` with `test` target → `make test`

### Health Check Detection

Health endpoints are extracted from compose file `healthcheck` definitions:
```yaml
services:
  django:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/"]
```

Port is inferred from the port mapping (e.g., `8000:8000`).

## Attach Mode

Use attach mode to connect to containers that are already running:

```yaml
environments:
  dev:
    type: docker-compose
    attach: true
```

In attach mode:
- `setup()` skips build and docker-compose up
- `teardown()` skips docker-compose down
- SystemEval only executes tests inside existing containers

Useful for:
- Development workflows where containers stay running
- CI environments with pre-built images
- Remote Docker hosts with long-running services

## Remote Docker Hosts

### SSH Host

```yaml
environments:
  staging:
    type: docker-compose
    docker:
      host: ssh://deploy@staging.example.com
    attach: true
```

Requires:
- SSH key authentication to remote host
- Docker installed on remote host
- Compose file available on remote host

### Docker Context

```bash
# Create context
docker context create staging --docker "host=ssh://deploy@staging.example.com"
```

```yaml
environments:
  staging:
    type: docker-compose
    docker:
      context: staging
```

## CLI Commands

### Run Tests

```bash
# Run in specific environment
systemeval test --env backend

# Attach to running containers
systemeval test --env backend --attach

# Keep containers running after tests
systemeval test --env backend --keep-running
```

### Docker Subcommands

```bash
# Show container status
systemeval docker status

# View logs (all services or specific service)
systemeval docker logs
systemeval docker logs django

# Execute command in test container
systemeval docker exec pytest -v tests/unit/

# Check if containers are healthy
systemeval docker ready
```

## Pre-flight Checks

Before starting, SystemEval validates:

| Check | Description |
|-------|-------------|
| Docker binary | `docker` command is available |
| Docker daemon | Docker daemon is running |
| Compose version | Docker Compose V2 is installed |
| Compose file | File exists and is valid YAML |
| Services | Referenced services exist in compose file |
| Test service | Test service is defined |
| Containers (attach mode) | Required containers are running |

## Lifecycle

### Full Lifecycle (default)

1. **Pre-flight checks** - Validate Docker setup
2. **Build** - `docker compose build`
3. **Start** - `docker compose up -d`
4. **Health check** - Wait for HTTP endpoint
5. **Execute tests** - `docker compose exec <service> <command>`
6. **Teardown** - `docker compose down`

### Attach Mode

1. **Pre-flight checks** - Validate containers are running
2. **Execute tests** - `docker compose exec <service> <command>`
3. *(No teardown)*

## Environment Variables

Pass environment variables to test execution:

```yaml
environments:
  backend:
    type: docker-compose
    test_env:
      DJANGO_SETTINGS_MODULE: config.settings.test
      DATABASE_URL: postgres://test:test@postgres/test
```

## Timeouts

```yaml
environments:
  backend:
    type: docker-compose
    health_check:
      timeout: 120  # Health check timeout in seconds
    test_timeout: 300  # Test execution timeout in seconds
```

## Examples

### Django + Postgres + Redis

```yaml
# docker-compose.yml
services:
  django:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./:/app
    depends_on:
      - postgres
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]

  postgres:
    image: postgres:15

  redis:
    image: redis:7-alpine
```

```yaml
# systemeval.yaml
environments:
  backend:
    type: docker-compose
    # Everything auto-discovered
```

### Express + MongoDB

```yaml
# compose.yml (modern naming)
services:
  api:
    build: .
    ports:
      - "3000:3000"
    volumes:
      - ./src:/app/src
    depends_on:
      - mongo
    healthcheck:
      test: ["CMD", "node", "-e", "require('http').get('http://localhost:3000/health')"]

  mongo:
    image: mongo:7
```

```yaml
# systemeval.yaml
environments:
  api:
    type: docker-compose
    compose_file: compose.yml
    # test_service, test_command auto-discovered
```

### Multi-Service Fullstack

```yaml
# local.yml
services:
  backend:
    build: ./backend
    ports:
      - "8080:8080"
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend/src:/app/src

  postgres:
    image: postgres:16

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
```

```yaml
# systemeval.yaml
environments:
  backend:
    type: docker-compose
    compose_file: local.yml
    test_service: backend

  frontend:
    type: docker-compose
    compose_file: local.yml
    test_service: frontend
    test_command: npm test

  fullstack:
    type: docker-compose
    compose_file: local.yml
    services: [backend, frontend, postgres, nginx]
    test_service: backend
```

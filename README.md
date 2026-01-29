# SystemEval

## What is SystemEval?

SystemEval is an AI-powered test orchestration platform that enables systematic testing of every piece of your application. It unifies traditional testing frameworks (pytest, jest, vitest, playwright) with cutting-edge AI-powered testing through DebuggAI integration.

## Mission Statement

**SystemEval exists to make comprehensive application testing accessible and intelligent.** We bridge the gap between traditional testing frameworks and AI-powered test generation, providing developers with a unified CLI that handles everything from unit tests to natural language test creation, commit-based test generation, and visual failure analysis.

## Key Features

### Traditional Testing (Unified CLI)
- **pytest, jest, vitest, playwright** - Run any framework through a single command
- **Structured JSON output** - Machine-parseable test results with deterministic PASS/FAIL/ERROR verdicts
- **Framework-agnostic adapters** - Consistent interface across all testing tools
- **Pipeline-ready** - CI/CD integration with UUID tracking and timestamped results
- **Docker Compose support** - Auto-discovery, lifecycle management, and remote Docker host execution

### AI-Powered Testing (DebuggAI Integration)
- **Natural language tests**: Write `systemeval e2e "create tests for homepage"` instead of manual test code
- **Commit-based test generation**: Automatically generate tests based on your code changes
- **Application crawling**: Map your entire application structure with intelligent page discovery
- **Knowledge graphs**: Build semantic understanding of your application architecture
- **Visual failure analysis**: Instant Chrome logs, screenshots, and debugging context on test failures
- **Intelligent test verification**: `systemeval e2e verify --suite homepage` to validate generated tests

## Why SystemEval?

Traditional testing requires manual test authoring, framework-specific knowledge, and constant maintenance. SystemEval's DebuggAI integration transforms this workflow:

1. **Write code** - Make changes to your application
2. **Generate tests** - `systemeval e2e "create tests for the new login flow"`
3. **Verify automatically** - Get instant feedback with visual debugging
4. **Run anywhere** - Same CLI works for pytest, jest, playwright, or AI-generated tests

Whether you're running legacy pytest suites or generating cutting-edge AI-powered E2E tests, SystemEval provides one unified interface.

## Docker Compose Support

Run tests inside Docker containers with automatic discovery:

```yaml
# systemeval.yaml - minimal config, auto-discovers everything
environments:
  backend:
    type: docker-compose
```

```bash
# Build, start containers, run tests, teardown
systemeval test --env backend

# Attach to already-running containers
systemeval test --env backend --attach

# Docker-specific commands
systemeval docker status
systemeval docker logs django
systemeval docker exec pytest -v
```

Features:
- **Auto-discovery**: Finds compose files, test services, health endpoints
- **Lifecycle management**: Build → Start → Health check → Test → Teardown
- **Attach mode**: Connect to pre-running containers
- **Remote Docker**: Execute against remote Docker hosts via SSH or contexts
- **Pre-flight checks**: Validates Docker setup before running

See `systemeval-py/docs/docker-compose.md` for full documentation.

---

# SystemEval Playgrounds

## Next.js Sample App

- Directory: `systemeval-next-sample`
- Purpose: run `systemeval` CLI commands such as `crawl`, `e2e "create tests for homepage"`, or the Debugg-AI CLI against a lightweight Next.js homepage, dashboard, and API stack.

### Getting started

```bash
cd systemeval-next-sample
npm install
npm run dev
```

The server listens at `http://localhost:3000` (`systemeval` defaults to port 3000). Use the following commands once the app is running:

```
systemeval crawl --target http://localhost:3000
systemeval e2e "create tests for homepage"
systemeval e2e verify --suite homepage
```

Use `systemeval status` or `systemeval help` for more context once the CLI is wired into your workflow.

## Design Requirements

- Avoid embedding "magic" strings or numbers directly in code; prefer constants, YAML fields, or env vars so behavior is configurable.
- Break any file growing beyond ~600 lines into cohesive pieces, and keep individual functions concise to improve readability.
- Enforce single-responsibility layering: parsing, orchestration, and runtime helpers should live in separate modules.
- Call out any intentional exceptions to these guidelines with inline comments or README notes so future maintainers understand why they're necessary.
- Refer to `docs/crawl-e2e-api-reference.md` for the authoritative shapes of the crawl and E2E APIs before wiring new Debugg-AI CLI or SystemEval flows.

## ⏺ The Testing Philosophy

### The Process
1. Investigate Why Tests Missed It
2. Write Test That FAILS
3. Fix The Code
4. Test Now PASSES

### The Philosophy
Never fix a bug you can't reproduce in a test.

## API References

The Debugg-AI / SystemEval integration depends on the sentinel platform APIs. Before modifying the CLI or sample apps:

- Read `docs/crawl-e2e-api-reference.md` for quick summaries of the crawl sessions and `/api/e2e-tests/` endpoints.
- Confirm authentication expectations (Bearer vs Token) and token issuance steps described in that guide.

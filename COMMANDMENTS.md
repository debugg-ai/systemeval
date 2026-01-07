# COMMANDMENTS

## What This Is

- Unified test harness with a single CLI entry point (`systemeval`)
- Adapter layer that wraps pytest, jest, playwright, or custom scripts
- Produces structured, machine-parseable JSON results

## Why It Exists

- Test results should be **facts, not opinions**
- AI agents need deterministic verdicts to know if their fix worked
- Human interpretation of test output creates ambiguity
- "Mostly passing" is not a valid state

## Core Principles

- **One verdict**: PASS, FAIL, or ERROR - nothing else
- **Non-fungible runs**: Every execution has UUID, timestamp, exit code
- **Deterministic**: Same inputs always produce same verdict
- **Machine-first**: JSON for automation, templates for humans
- **No retry-until-green**: Flaky tests fail, period

## The Agent Loop

```
Agent writes code
    ↓
systemeval test --json
    ↓
Structured result (pass/fail/error + metrics)
    ↓
Agent reads result, fixes failures
    ↓
Repeat until PASS
```

## Framework Priority (Use Established Tools First)

- **Always prefer well-known testing frameworks** over custom scripts
- Django TestCase/pytest-django for Django projects
- pytest for Python
- jest for JavaScript/TypeScript
- Only use E2E/browser tests when unit/integration tests cannot cover it
- Custom scripts are **last resort** - when no framework can test it

## What It Wraps

- pytest (Python) - **preferred for Python**
- Django test framework (via pytest-django) - **preferred for Django**
- jest (JavaScript) - **preferred for JS/TS**
- playwright (browser E2E) - **only when needed**
- Custom adapters - **only when no standard framework applies**

## Exit Codes

- `0` = PASS (all tests green)
- `1` = FAIL (one or more tests failed)
- `2` = ERROR (config/collection/execution problem)

## Non-Negotiables

- Results are immutable facts
- No subjective "acceptable failure rates"
- No flaky-test forgiveness
- No manual interpretation required
- Every run is traceable and comparable

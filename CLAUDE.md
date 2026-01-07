# CLAUDE.md

This file provides guidance to Claude Code when working in the systemeval project.

## Critical: Agents Must Use SystemEval

**ALL test execution by AI agents MUST go through the systemeval CLI.**

```bash
# Correct - always use systemeval
systemeval test --json
systemeval test --category unit --json

# Wrong - never run test frameworks directly
pytest tests/          # NO
npm test               # NO
python manage.py test  # NO
```

## Why SystemEval Is Mandatory

- Agents need structured, machine-parseable output
- Raw test framework output requires human interpretation
- SystemEval provides deterministic PASS/FAIL/ERROR verdicts
- Results are non-fungible (UUID, timestamp, traceable)

## Framework Selection Rules

**Use established frameworks first, custom scripts last:**

1. **Django projects**: pytest + pytest-django (not raw Django TestCase CLI)
2. **Python projects**: pytest
3. **JavaScript/TypeScript**: jest
4. **Browser E2E**: playwright - **only when unit/integration cannot cover it**
5. **Custom scripts**: **last resort only** - when no framework applies

## Agent Workflow

```
1. Write code fix/feature
2. Run: systemeval test --json
3. Parse JSON result
4. If FAIL: read failures, fix code, goto 2
5. If PASS: done
6. If ERROR: fix config/setup issue, goto 2
```

## Do Not

- Run `pytest`, `npm test`, `jest` directly - use `systemeval test`
- Write custom test scripts when pytest/jest can do it
- Use browser E2E tests for logic that unit tests can cover
- Interpret raw test output manually - rely on systemeval verdicts

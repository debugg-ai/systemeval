# e2e_eval — iterative evaluation of the E2E pipeline node

A standalone, dependency-light harness for **quickly and iteratively evaluating the
e2e node** of the debugg-ai pipeline. It stitches the scattered per-run telemetry
into one trace answering the four questions that matter:

| # | Question | Source |
|---|----------|--------|
| ① | **What workflow triggered + node graph** | `GET /api/v1/workflows/executions/{uuid}/` → `node_executions` (nested) |
| ② | **What browser actions occurred** | `GET /api/v1/e2e-runs/{uuid}/` → `browser_session.actions` (SurferActions) |
| ③ | **The steps + AI decisions** | brain.think `node_executions[].output_data.intent` + `E2eRunMetrics` tokens/cost |
| ④ | **The reported outcome** | `e2e-run.outcome` / `error_category` / `surfer_error` + workflow state |
| ◆ | **Artifacts** | `run_gif` (video), `final_screenshot`, `surfer_screenshots`, `browser_session.recording_*` |

All read-only, all through the public REST API with a scoped token. No docker exec.

## Phase 1 — `trace.py` (done)

One command → the full trace for a single run.

```bash
# most recent run visible to the token
python3 e2e_eval/trace.py latest

# a specific run by uuid or integer id
python3 e2e_eval/trace.py 132
python3 e2e_eval/trace.py 1da25025-c5fe-4680-b35b-00fff8c026d0

# normalized trace as JSON (the substrate for Phase 2/3)
python3 e2e_eval/trace.py 132 --json

# also dump raw API payloads for debugging
python3 e2e_eval/trace.py 132 --raw /tmp/raw.json
```

Config (flag > env > default):
- `--base` / `DEBUGGAI_API_BASE` — default `http://localhost:8012`
- `--token` / `DEBUGGAI_API_TOKEN` — default: reads `../platform/sentinal/.local/api_token`

## The target app + fixture project

Runs target **eval-app** ("TaskFlow") — a deterministic fixture served by the
`sentinal_eval_app` container at `http://host.docker.internal:8080` (source:
`sentinal/compose/local/eval-app/server.py`, ~40 routes, resettable via `/reset`,
login `admin/secret123`). It is **not** a product app.

The scenarios run against project **`eval-app`** (seeded under the Default team of
company *Debugg Ai* so the scoped token can trace its runs), with an environment +
credential set to `admin/secret123` so the auth subworkflow logs in for real.
Recreate/refresh it idempotently with:

```bash
docker exec -i sentinal_django python manage.py shell < e2e_eval/seed_evalapp.py
```

Seeded tests (goals mirror the validate-e2e-agents canonical set): `login_baseline`
(59), `add_task` (60), `native_select_catalog` (61), `aria_combobox` (62),
`custom_js_dropdown` (63), `impossible_csv_export` (64, the hallucination canary).

## Triggering a run to trace (local)

The DEBUG-only endpoint kicks off the **full pipeline** (E2eRun → workflow → brain → outcome):

```bash
# Option A — run an existing test (run inherits the TEST's project → visible to that
# project's token). Use this so the trace API can see the run.
curl -s -X POST http://localhost:8012/api/v1/e2es/debug-trigger-test/ \
  -H 'Content-Type: application/json' \
  -d '{"test_id":57,"target_url":"http://host.docker.internal:8080"}'

# Option B — ad-hoc description. NOTE: this creates the run under an auto-generated
# *dev* project, which a company-scoped token usually CANNOT see (404 on the trace).
curl -s -X POST http://localhost:8012/api/v1/e2es/debug-trigger-test/ \
  -H 'Content-Type: application/json' \
  -d '{"description":"...","target_url":"http://host.docker.internal:8080"}'
```

Target eval-app at `http://host.docker.internal:8080` (browser-mgr Chrome is outside
`sentinal-network` and can't resolve `eval-app:8080`). Always run the
`validate-e2e-agents` preflight first — if the browser-mgr stack is degraded, every
run dies at `browser.setup` with `outcome=error`.

## Step / think flow view (default output)

`trace.py` renders the e2e run as an interleaved **sense → think → act** narrative,
grouped by step. Each think line shows the model's full reasoning plus the captured
`think_meta`:

```
┌─ step 4  👁  Dashboard - TaskFlow  (…/dashboard)  📷
│  🧠 think 1238ms → CLICK  #spa-states-link
│     ⟨gpt-5.4-mini-2026-03-17  ·  1200tok (1136→64)  ·  16 elems seen⟩
│     “The current page does not show the paginated table link directly; …”
│  ⚡ act  77ms ✓
```

It also flags `auth[failed]` preflight up front, `🛑 circuit breaker TRIPPED`, and
`⚠ acted with 0 perceived elements` (selector-hallucination signal).

## `think_meta` — per-call LLM capture (backend change, in `brain.think`)

`sentinal/.../workflows/node_executors/brain_think.py` now attaches a compact,
exception-safe `think_meta` to each `brain.think` node output: `model`,
`input/output/total_tokens`, `latency_ms`, `raw_response_chars`, and
`n_elements_seen` + `element_refs` (what the brain could pick from). It rides the
existing `NodeExecution.output_data` → API path (survives `_strip_large_data`), so
the harness needs no new endpoint. **Uncommitted** — run the gated e2e suite
(`systemeval test -c e2e`) before committing.

## Gaps still open

- **`E2eRunMetrics.llm_total_tokens/cost` rollup still not wired** — the harness now
  sums `think_meta` tokens itself (`captured_tokens`), but the model-level field
  remains 0. Next: aggregate `think_meta` into `E2eRunMetrics` on run completion.
- **Raw prompt + full raw response text not stored** — only token counts + response
  length. A debug-gated opt-in could persist the full text for deep replay.
- **Per-step screenshots not attached** (`surfer_screenshots` empty) though
  `final_screenshot` + the `.webm` recording are present.
- **`error_category` stays `infrastructure` on passing runs** — stale default not
  cleared on success (cosmetic but misleading).

## Phase 2 — `run_eval.py` (done)

Dispatch → poll → trace → oracle → accumulate, with variance aggregation built in.

```bash
python3 e2e_eval/run_eval.py                 # default scenarios, 1 repeat
python3 e2e_eval/run_eval.py --repeat 3      # run each 3× to measure variance
python3 e2e_eval/run_eval.py --scenarios my.json
python3 e2e_eval/run_eval.py --summary-only  # aggregate results.jsonl, run nothing
```

Each run appends a row to `results.jsonl`; the summary reports oracle pass-rate,
outcome distribution, and token/think/duration/hallucination percentiles per
scenario (across this batch + history). Scenarios are `{id, test_id|description,
target_url, expect}`; `expect` invariants:

| key | asserts |
|-----|---------|
| `no_error` | outcome is never `error`/`timeout` (E2E ERRORS ARE BUGS) |
| `max_hallucinations` | no think step acted with 0 perceived elements |
| `outcome` / `error_category` | expected terminal state (when deterministic) |
| `min_think` / `max_think` | step-budget sanity |
| `must_reach_url` | some sense step saw this URL (light DOM oracle) |

**First finding:** the default scenario is **non-deterministic** — identical input
returned `fail` then `pass` across two runs. That's the variance the harness exists
to track. Reference a test by `test_id` (run inherits its project → token can trace
it); ad-hoc `description` runs land in an invisible dev project (can't be traced).

## Roadmap

- **Phase 3**: regression gate — fail the batch when a historically-passing
  scenario's oracle pass-rate drops below threshold, or `error_category` shifts; add
  a per-scenario DOM oracle (re-fetch eval-app state to confirm the goal happened).
- **Backend follow-ups**: aggregate `think_meta` into `E2eRunMetrics` (fix the
  model-level token/cost rollup); optional debug-gated full prompt/response capture;
  attach per-step screenshots.

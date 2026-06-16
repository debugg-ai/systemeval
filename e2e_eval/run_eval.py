#!/usr/bin/env python3
"""
run_eval — dispatch e2e scenarios, trace them, assert oracles, accumulate results.

The loop, per scenario × N repeats:
  1. DISPATCH   POST /api/v1/e2es/debug-trigger-test/  (run inherits the test's
                project, so the scoped token can see + trace it)
  2. POLL       GET  /api/v1/e2es/dev/run/<id>/  until completed
  3. TRACE      assemble the normalized trace (reuses trace.py)
  4. ORACLE     assert invariants against the trace — the failure modes that
                weak `outcome in (pass,fail)` checks miss:
                  · no_error            → outcome must never be 'error' (E2E ERRORS ARE BUGS)
                  · max_hallucinations  → no think step acted with 0 perceived elements
                  · outcome / category  → expected terminal state (when deterministic)
                  · min_think/max_think → step-budget sanity
                  · must_reach_url      → some sense step saw this URL (light DOM oracle)
  5. RECORD     append one JSONL row; print a per-run line

Then aggregate: pass-rate, outcome distribution, token/step/duration spread per
scenario — across this run AND prior rows in the results file (variance tracking).

Usage:
  python3 e2e_eval/run_eval.py                       # default scenarios, 1 repeat each
  python3 e2e_eval/run_eval.py --repeat 3            # variance: run each 3×
  python3 e2e_eval/run_eval.py --scenarios my.json   # custom scenario set
  python3 e2e_eval/run_eval.py --summary-only        # just aggregate results.jsonl, no runs
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # systemeval/
from e2e_eval.trace import (  # noqa: E402
    DEFAULT_BASE,
    Api,
    _default_token,
    build_trace,
    find_workflow_execution,
    resolve_run,
)

RESULTS_DEFAULT = Path(__file__).parent / "results.jsonl"
SUITES_DIR = Path(__file__).parent / "suites"


def resolve_test_id(api: "Api", name: str):
    """Resolve a scenario name to its E2eTest id via the API."""
    _, data = api.get("/api/v1/e2e-tests/", ordering="-timestamp", limit=200)
    for t in (data or {}).get("results", []):
        if t.get("name") == name:
            return t.get("id")
    return None


def resolve_project_uuid(api: "Api", name: str):
    """Resolve a project name to its uuid (the test fixture project)."""
    _, data = api.get("/api/v1/projects/", limit=200)
    for p in (data or {}).get("results", []):
        if p.get("name") == name:
            return p.get("uuid")
    return None


def ensure_test(api: "Api", name: str, goal: str, project_uuid: str):
    """Resolve-or-CREATE the E2eTest for a scenario from the suite's own goal — the
    suite is the single source of truth, so no scenario lists live in the seeder.
    Idempotent: returns the existing id, or creates one and returns it."""
    tid = resolve_test_id(api, name)
    if tid:
        return tid
    body = json.dumps({
        "project": project_uuid, "name": name,
        "description": goal, "agent_task_description": goal,
    }).encode()
    req = urllib.request.Request(
        f"{api.base}/api/v1/e2e-tests/", data=body, method="POST",
        headers={"Authorization": f"Token {api.token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode()).get("id")
    except Exception as e:  # noqa: BLE001
        print(f"    could not create test '{name}': {e}")
        return None

# All scenarios live in versioned suites under e2e_eval/suites/ (the single source
# of truth). The default suite is `interactions`.


# --------------------------------------------------------------------------- #
# Dispatch + poll (DEBUG-only plain views — no token needed)                  #
# --------------------------------------------------------------------------- #

def dispatch(base: str, scenario: dict) -> int | None:
    body = {"target_url": scenario["target_url"]}
    if scenario.get("test_id"):
        body["test_id"] = scenario["test_id"]
    elif scenario.get("description"):
        body["description"] = scenario["description"]
    req = urllib.request.Request(
        f"{base}/api/v1/e2es/debug-trigger-test/",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode())
        return d.get("e2e_run_id") if d.get("success") else None
    except Exception as e:  # noqa: BLE001
        print(f"  dispatch failed: {e}")
        return None


# Terminal E2eRun outcomes. A hung page lands as `timeout`; a never-finishing run
# may sit at `pending`/`running` until the cleanup sweep — both must be waited out,
# not silently treated as a pass.
TERMINAL_OUTCOMES = {"pass", "fail", "error", "timeout", "skipped", "cancelled"}


def poll(base: str, run_id: int, timeout_s: int = 300) -> tuple[str, str | None]:
    """Poll until the run reaches a terminal state — status=completed OR a terminal
    outcome (e.g. a hang resolves to outcome=timeout while status still lags).
    Returns (status, outcome). A run still non-terminal at the deadline is returned
    as-is; the caller MUST treat that as a failure, never a pass."""
    deadline = time.monotonic() + timeout_s
    last_status, last_outcome = "?", None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/v1/e2es/dev/run/{run_id}/", timeout=8) as r:
                d = json.loads(r.read().decode())
            last_status = d.get("status") or "?"
            last_outcome = d.get("outcome")
            if last_status == "completed" or last_outcome in TERMINAL_OUTCOMES:
                return last_status, last_outcome
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)
    return last_status, last_outcome


# --------------------------------------------------------------------------- #
# Oracle                                                                       #
# --------------------------------------------------------------------------- #

def evaluate(trace: dict, expect: dict) -> list[dict]:
    """Return a list of {name, ok, detail} checks for this run's trace."""
    run, m = trace["run"], trace["metrics"]
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    outcome = run.get("outcome")
    if expect.get("no_error", False):
        add("no_error", outcome not in ("error", "timeout"),
            f"outcome={outcome}")
    if "outcome" in expect:
        add("outcome", outcome == expect["outcome"],
            f"got {outcome}, want {expect['outcome']}")
    if "error_category" in expect:
        add("error_category", run.get("error_category") == expect["error_category"],
            f"got {run.get('error_category')}")
    if "max_hallucinations" in expect:
        n = m.get("n_possible_hallucinations") or 0
        add("max_hallucinations", n <= expect["max_hallucinations"],
            f"{n} step(s) acted with 0 perceived elements")
    if "min_think" in expect:
        add("min_think", (m.get("n_think_calls") or 0) >= expect["min_think"],
            f"think_calls={m.get('n_think_calls')}")
    if "max_think" in expect:
        add("max_think", (m.get("n_think_calls") or 0) <= expect["max_think"],
            f"think_calls={m.get('n_think_calls')}")
    if "must_reach_url" in expect:
        urls = [f["detail"].get("url") or "" for f in (trace.get("flow") or []) if f["kind"] == "sense"]
        hit = any(expect["must_reach_url"] in u for u in urls)
        add("must_reach_url", hit, f"{expect['must_reach_url']} in {len(urls)} sensed urls")
    return checks


# --------------------------------------------------------------------------- #
# Aggregate                                                                    #
# --------------------------------------------------------------------------- #

def _pct(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "—"
    xs = sorted(xs)
    p50 = statistics.median(xs)
    return f"p50={p50:g} min={xs[0]:g} max={xs[-1]:g}"


def aggregate(rows: list[dict]) -> str:
    from collections import Counter, defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r["scenario"]].append(r)
    L = ["", "═" * 78, "AGGREGATE  ({} runs across {} scenario(s))".format(len(rows), len(by)), "═" * 78]
    for sid, rs in sorted(by.items()):
        passed = sum(1 for r in rs if r["passed"])
        outcomes = Counter(r["outcome"] for r in rs)
        L.append(f"\n▸ {sid}   ORACLE PASS {passed}/{len(rs)} ({100*passed//max(len(rs),1)}%)")
        L.append(f"    outcomes : {dict(outcomes)}")
        L.append(f"    tokens   : {_pct([r.get('captured_tokens') for r in rs])}")
        L.append(f"    think    : {_pct([r.get('n_think') for r in rs])}")
        L.append(f"    duration : {_pct([r.get('duration_seconds') for r in rs])}s")
        L.append(f"    hallucn  : {_pct([r.get('n_hallucinations') for r in rs])}")
        # surface the most recent failing checks, if any
        fails = [c for r in rs if not r["passed"] for c in r["checks"] if not c["ok"]]
        if fails:
            seen = set()
            for c in fails:
                k = c["name"]
                if k in seen:
                    continue
                seen.add(k)
                L.append(f"    ✗ {c['name']}: {c['detail']}")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# DOM oracle — independent, server-side truth (not the agent's self-report)    #
# --------------------------------------------------------------------------- #

def _reset_app(base: str) -> None:
    """Reset the target app's state (eval-app /reset) so a run's change is clean."""
    try:
        urllib.request.urlopen(f"{base}/reset", timeout=8)
    except Exception:  # noqa: BLE001
        pass


def _app_oracle(base: str, oracle: dict) -> dict:
    """Verify the REAL server-side state after a run — log in FRESH (a separate
    session from the agent's browser), fetch a page, assert content. This catches
    hallucinated success the agent's 'done' can't: the agent says it saved the
    profile; the oracle reads /profile and sees whether it actually did."""
    path = oracle.get("path", "/")
    login = oracle.get("login") or {"path": "/login", "username": "admin", "password": "secret123"}
    try:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        creds = urllib.parse.urlencode(
            {"username": login["username"], "password": login["password"]}
        ).encode()
        opener.open(urllib.request.Request(f"{base}{login['path']}", data=creds), timeout=8)
        html = opener.open(f"{base}{path}", timeout=8).read().decode(errors="replace")
    except Exception as e:  # noqa: BLE001
        return {"name": "dom_oracle", "ok": False, "detail": f"oracle fetch failed: {e}"}
    ok, bits = True, [f"GET {path}"]
    if "contains" in oracle:
        hit = oracle["contains"] in html
        ok = ok and hit
        bits.append(f"contains {oracle['contains']!r}={hit}")
    if "not_contains" in oracle:
        miss = oracle["not_contains"] not in html
        ok = ok and miss
        bits.append(f"absent {oracle['not_contains']!r}={miss}")
    return {"name": "dom_oracle", "ok": ok, "detail": "  ".join(bits)}


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def run_one(api: Api, base: str, scenario: dict, stamp: str, oracle_base: str,
            project_uuid: str | None) -> dict | None:
    sid = scenario["id"]
    # The suite is the single source — derive the E2eTest from the scenario's own
    # `goal` (resolve-or-create), so nothing is hardcoded in the seeder.
    if not scenario.get("test_id"):
        name = scenario.get("test_name") or sid
        goal = scenario.get("goal")
        if goal and project_uuid:
            tid = ensure_test(api, name, goal, project_uuid)
        else:
            tid = resolve_test_id(api, name)
        if not tid:
            print(f"  · {sid}: no test — give the scenario a 'goal' (auto-creates) "
                  f"and ensure the '{scenario.get('project','eval-app')}' project is seeded")
            return None
        scenario = {**scenario, "test_id": tid}
    if scenario.get("reset"):
        _reset_app(oracle_base)
    print(f"  · {sid}: dispatching …", flush=True)
    run_id = dispatch(base, scenario)
    if not run_id:
        return None
    status, outcome = poll(base, run_id)
    terminal = status == "completed" or outcome in TERMINAL_OUTCOMES
    if not terminal:
        print(f"    run {run_id} did not reach a terminal state (status={status}, outcome={outcome})")
    run = resolve_run(api, str(run_id))
    wfx = find_workflow_execution(api, run)
    trace = build_trace(run, wfx)
    checks = evaluate(trace, scenario.get("expect", {}))
    # A run that never reached a terminal state is NOT a pass — flag it explicitly so
    # `no_error` (outcome != error) can't wave a stuck/pending run through as green.
    if not terminal:
        checks.append({"name": "completed", "ok": False,
                       "detail": f"run never reached terminal state (status={status}, outcome={outcome})"})
    # Independent DOM oracle — the truth check, run after the agent finishes.
    oracle = scenario.get("oracle")
    if oracle:
        # `only_if_pass`: a verify-your-own-work canary. An honest "I failed" is
        # fine; the violation is the agent CLAIMING pass while the oracle disproves
        # it. So only enforce the oracle when the agent reported success.
        if oracle.get("only_if_pass") and trace["run"]["outcome"] != "pass":
            checks.append({"name": "dom_oracle", "ok": True,
                           "detail": "skipped — agent did not claim success (honest)"})
        else:
            checks.append(_app_oracle(oracle_base, oracle))
    passed = all(c["ok"] for c in checks)
    row = {
        "ts": stamp, "scenario": sid, "run_id": run_id, "run_uuid": trace["run"]["uuid"],
        "passed": passed, "checks": checks,
        "outcome": trace["run"]["outcome"], "error_category": trace["outcome"]["error_category"],
        "captured_tokens": trace["metrics"]["captured_tokens"],
        "n_think": trace["metrics"]["n_think_calls"],
        "n_hallucinations": trace["metrics"]["n_possible_hallucinations"],
        "duration_seconds": trace["run"]["duration_seconds"],
    }
    mark = "✅ PASS" if passed else "❌ FAIL"
    bad = "" if passed else "  [" + ", ".join(c["name"] for c in checks if not c["ok"]) + "]"
    print(f"    run {run_id} → {trace['run']['outcome']}  {mark}{bad}  "
          f"({row['n_think']} think · {row['captured_tokens']} tok · {row['duration_seconds']}s)")
    return row


def main(argv=None):
    p = argparse.ArgumentParser(description="Dispatch e2e scenarios, trace, assert oracles, accumulate results.")
    p.add_argument("--base", default=os.environ.get("DEBUGGAI_API_BASE", DEFAULT_BASE))
    p.add_argument("--token", default=None)
    p.add_argument("--scenarios", help="path to a JSON list of scenarios")
    p.add_argument("--suite", help="name of a persisted suite in e2e_eval/suites/ (e.g. feature_validation)")
    p.add_argument("--repeat", type=int, default=1, help="runs per scenario (variance)")
    p.add_argument("--out", default=str(RESULTS_DEFAULT), help="results JSONL path")
    p.add_argument("--summary-only", action="store_true", help="aggregate existing results, run nothing")
    p.add_argument("--stamp", default=None, help="timestamp label for this batch (default: now)")
    p.add_argument("--oracle-base", default=os.environ.get("DEBUGGAI_ORACLE_BASE", "http://localhost:8080"),
                   help="base URL the DOM oracle hits to verify real app state (host view of the target app)")
    args = p.parse_args(argv)

    out = Path(args.out)
    if args.summary_only:
        rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()] if out.exists() else []
        print(aggregate(rows))
        return 0

    token = args.token or _default_token()
    if not token:
        sys.exit("No token. Set DEBUGGAI_API_TOKEN or pass --token.")
    api = Api(args.base, token)
    # Suites are the single source. Default to the 'interactions' suite when no
    # --suite / --scenarios is given.
    suite_name = args.suite or (None if args.scenarios else "interactions")
    if suite_name:
        data = json.loads((SUITES_DIR / f"{suite_name}.json").read_text())
        default_url = data.get("target_url")
        scenarios = [{**({"target_url": default_url} if default_url else {}), **sc}
                     for sc in data["scenarios"]]
        project_name = data.get("project", "eval-app")
    else:
        scenarios = json.loads(Path(args.scenarios).read_text())
        project_name = "eval-app"
    stamp = args.stamp or time.strftime("%Y-%m-%dT%H:%M:%S")

    # Resolve the fixture project once — used to auto-create any missing tests.
    project_uuid = resolve_project_uuid(api, project_name)

    batch = []
    print(f"Running {len(scenarios)} scenario(s) × {args.repeat} → {out}")
    for rep in range(args.repeat):
        for sc in scenarios:
            row = run_one(api, args.base, sc, stamp, args.oracle_base, project_uuid)
            if row:
                batch.append(row)
                with out.open("a") as f:
                    f.write(json.dumps(row, default=str) + "\n")

    # Aggregate this batch + history
    all_rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()] if out.exists() else batch
    print(aggregate(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

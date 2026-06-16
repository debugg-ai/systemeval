#!/usr/bin/env python3
"""
e2e-trace — assemble a single end-to-end trace for one E2E pipeline run.

The e2e "node" of the pipeline spreads its telemetry across several models/APIs.
This tool fans out across the public REST API (with a scoped token) and stitches
them into ONE normalized trace answering the four questions you care about:

  1. WORKFLOWS  — which workflow template ran and the node graph it executed
  2. ACTIONS    — the concrete browser actions taken (click/type/navigate/…)
  3. STEPS+AI   — per-step brain decisions (sense→think→act) + LLM token/cost
  4. OUTCOME    — pass/fail/error, error category, failure reason
  + ARTIFACTS   — video recording, screenshots, HAR/console

Data sources (all read-only):
  GET /api/v1/e2e-runs/{uuid}/                 → run, metrics, actions, recording, screenshots
  GET /api/v1/workflows/executions/?…          → locate the WorkflowExecution for the run
  GET /api/v1/workflows/executions/{uuid}/     → node_executions (nested) + state + outcome

Usage:
  python3 e2e_eval/trace.py latest                  # most recent run visible to the token
  python3 e2e_eval/trace.py <run-uuid|run-id>       # a specific run
  python3 e2e_eval/trace.py latest --json           # normalized trace as JSON (for Phase 2/3)
  python3 e2e_eval/trace.py latest --raw out.json   # also dump raw API payloads for debugging

Config (flags override env override defaults):
  --base   / DEBUGGAI_API_BASE   (default http://localhost:8012)
  --token  / DEBUGGAI_API_TOKEN  (default: read sentinal/.local/api_token next to this repo)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --------------------------------------------------------------------------- #
# Config / HTTP                                                                #
# --------------------------------------------------------------------------- #

DEFAULT_BASE = "http://localhost:8012"


def _default_token() -> str | None:
    """Read the local smoke token from the platform checkout, if present."""
    env = os.environ.get("DEBUGGAI_API_TOKEN")
    if env:
        return env.strip()
    # systemeval and platform are sibling repos: ../platform/sentinal/.local/api_token
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "platform" / "sentinal" / ".local" / "api_token",
        Path.home() / "Repos" / "debugg-ai" / "platform" / "sentinal" / ".local" / "api_token",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text().strip()
    return None


class Api:
    def __init__(self, base: str, token: str | None):
        self.base = base.rstrip("/")
        self.token = token

    def get(self, path: str, **params):
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(url)
        if self.token:
            req.add_header("Authorization", f"Token {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                body = json.loads(body)
            except Exception:
                pass
            return e.code, body
        except Exception as e:  # noqa: BLE001
            return 0, {"error": type(e).__name__, "message": str(e)}


# --------------------------------------------------------------------------- #
# Fetch + correlate                                                            #
# --------------------------------------------------------------------------- #

def resolve_run(api: Api, ref: str) -> dict:
    """Return the e2e-run detail payload for a uuid / integer id / 'latest'."""
    if ref == "latest":
        status, data = api.get("/api/v1/e2e-runs/", ordering="-timestamp", limit=1)
        results = (data or {}).get("results") if isinstance(data, dict) else None
        if not results:
            sys.exit(f"No e2e runs visible to this token (HTTP {status}). "
                     f"Trigger one or check token company scoping.")
        ref = results[0]["uuid"]

    # uuid form → detail endpoint; integer id → list + match
    if _looks_like_uuid(ref):
        status, data = api.get(f"/api/v1/e2e-runs/{ref}/")
        if status == 200:
            return data
        sys.exit(f"Run {ref} not visible to this token (HTTP {status}: "
                 f"{_err(data)}). It may belong to another company/project.")

    # integer id: page recent runs and match
    status, data = api.get("/api/v1/e2e-runs/", ordering="-timestamp", limit=50)
    for r in (data or {}).get("results", []):
        if str(r.get("id")) == str(ref):
            # re-fetch detail by uuid for the full payload
            _, detail = api.get(f"/api/v1/e2e-runs/{r['uuid']}/")
            return detail if isinstance(detail, dict) and detail.get("uuid") else r
    sys.exit(f"Run id={ref} not found among the 50 most recent visible runs.")


def find_workflow_execution(api: Api, run: dict) -> dict | None:
    """Locate + fetch the WorkflowExecution that drove this e2e run.

    Correlate on context_data (e2e_run_id) first, then fall back to a
    target_url + time-window heuristic. Returns the *detail* payload
    (with node_executions + state) or None if not visible.
    """
    run_id, run_uuid = str(run.get("id")), str(run.get("uuid"))
    target = run.get("target_url")
    status, data = api.get("/api/v1/workflows/executions/", ordering="-timestamp", limit=50)
    if status != 200 or not isinstance(data, dict):
        return None

    candidates = data.get("results", [])
    match = None
    for x in candidates:
        ctx = x.get("context_data") or {}
        ids = {str(ctx.get(k)) for k in ("e2e_run_id", "e2eRunId", "run_id") if ctx.get(k) is not None}
        if run_id in ids or run_uuid in ids:
            match = x
            break
    if match is None:  # fallback: same target_url, nearest in time
        for x in candidates:
            ctx = x.get("context_data") or {}
            if target and ctx.get("target_url") == target:
                match = x
                break
    if match is None:
        return None
    _, detail = api.get(f"/api/v1/workflows/executions/{match['uuid']}/")
    return detail if isinstance(detail, dict) else match


def flatten_nodes(node_execs: list, depth: int = 0) -> list:
    """Depth-first flatten of node_executions, preserving subworkflow nesting depth."""
    out = []
    for n in sorted(node_execs or [], key=lambda z: z.get("execution_order", 0)):
        out.append({**n, "_depth": depth})
        kids = n.get("child_executions") or []
        if kids:
            out.extend(flatten_nodes(kids, depth + 1))
    return out


def summarize_node(n: dict) -> tuple[str, dict]:
    """Reduce a node execution to (kind, salient-fields) for the step flow."""
    nt = n.get("node_type") or ""
    od = n.get("output_data") or {}
    if nt == "trigger.event":
        mode = od.get("auth.mode_used")
        return "trigger", {
            "goal": od.get("test_description") or od.get("description"),
            "auth_mode": mode,
            "credential": (od.get("env") or {}).get("username"),
            "landing_url": od.get("landing_url"),
            "auth_error": od.get("error") if mode == "failed" else None,
        }
    if nt == "brain.setup":
        return "setup", {"brain": od.get("brain_name")}
    if nt in ("sense.process", "sense.dom", "sense.vision"):
        p = od.get("perception") or {}
        return "sense", {"url": p.get("url"), "title": p.get("title"),
                         "screenshot": p.get("has_screenshot"),
                         "elements": p.get("interactive_elements") or p.get("element_count")}
    if nt == "brain.think":
        it = od.get("intent") or {}
        tm = od.get("think_meta") or {}
        return "think", {"action_type": it.get("action_type"),
                         "reasoning": it.get("reasoning") or it.get("intent"),
                         "selector": it.get("selector"), "value": it.get("value"),
                         "output": it.get("output"),
                         "model": tm.get("model"), "tokens": tm.get("total_tokens"),
                         "in_tokens": tm.get("input_tokens"), "out_tokens": tm.get("output_tokens"),
                         "n_elements": tm.get("n_elements_seen"),
                         "latency_ms": tm.get("latency_ms")}
    if nt == "brain.act":
        ar = od.get("action_result") or {}
        return "act", {"result": ar, "success": n.get("status") == "success",
                       "url": ar.get("url"), "type": ar.get("type")}
    if nt == "control.circuit_breaker":
        return "breaker", {"tripped": od.get("tripped"), "reason": od.get("trip_reason")}
    if nt in ("subworkflow.return", "brain.done", "brain.evaluate"):
        return "return", {"outcome": od.get("outcome"), "success": od.get("success"),
                          "error": od.get("error"), "output": od.get("output")}
    return nt, {}


# --------------------------------------------------------------------------- #
# Normalize into the 4 sections                                               #
# --------------------------------------------------------------------------- #

def build_trace(run: dict, wfx: dict | None) -> dict:
    metrics = run.get("metrics") or {}
    bs = run.get("browser_session") or {}
    actions = bs.get("actions") or []

    nodes = flatten_nodes((wfx or {}).get("node_executions") or [])
    state = (wfx or {}).get("state") or {}

    # The step flow: every node in execution order, reduced to its salient fields,
    # grouped by iteration. This is the sense→think→act narrative.
    flow = []
    for n in nodes:
        kind, detail = summarize_node(n)
        flow.append({
            "order": n.get("execution_order"),
            "iter": n.get("iteration_number"),
            "kind": kind,
            "node_type": n.get("node_type"),
            "ms": n.get("execution_time_ms"),
            "status": n.get("status"),
            "error": n.get("error"),
            "detail": detail,
        })

    # Signal 3: per-step brain decisions come from brain.think node outputs;
    # state.action_history is the consolidated fallback.
    ai_steps = []
    for n in nodes:
        nt = (n.get("node_type") or "")
        if "think" in nt or "think" in (n.get("node_id") or ""):
            intent = ((n.get("output_data") or {}).get("intent")) or {}
            ai_steps.append({
                "step": (n.get("output_data") or {}).get("steps_taken"),
                "node": n.get("node_name") or n.get("node_id"),
                "action_type": intent.get("action_type"),
                "intent": intent.get("intent") or intent.get("reasoning"),
                "selector": intent.get("selector"),
                "value": intent.get("value"),
                "ms": n.get("execution_time_ms"),
                "status": n.get("status"),
            })
    if not ai_steps and state.get("action_history"):
        for a in state["action_history"]:
            ai_steps.append({
                "step": a.get("step"),
                "node": "state.action_history",
                "action_type": a.get("action_type"),
                "intent": a.get("intent"),
                "selector": a.get("selector"),
                "value": a.get("value"),
                "ms": None,
                "status": "ok" if a.get("success") else "fail",
            })

    # Run-level token rollup computed from per-think capture (think_meta), since
    # E2eRunMetrics.llm_total_tokens is not yet wired for the brain path.
    think_flow = [f for f in flow if f["kind"] == "think"]
    captured_tokens = sum((f["detail"].get("tokens") or 0) for f in think_flow)
    n_think = len(think_flow)
    n_hallucinated = sum(1 for f in think_flow
                         if f["detail"].get("selector") and f["detail"].get("n_elements") == 0)

    return {
        "run": {
            "id": run.get("id"), "uuid": run.get("uuid"), "key": run.get("key"),
            "status": run.get("status"), "outcome": run.get("outcome"),
            "test_name": run.get("test_name") or (run.get("test") or {}).get("name"),
            "project": run.get("project_name") or (run.get("test") or {}).get("project_name"),
            "target_url": run.get("target_url"),
            # The DETAIL serializer omits these (only the list serializer has them),
            # so fall back to the metrics timestamps.
            "started_at": run.get("started_at") or metrics.get("run_started_at"),
            "completed_at": run.get("completed_at") or metrics.get("run_completed_at"),
            "duration_seconds": run.get("duration_seconds") or metrics.get("total_execution_time"),
        },
        # Signal 4
        "outcome": {
            "outcome": run.get("outcome"),
            "error_category": run.get("error_category"),
            "surfer_error": run.get("surfer_error"),
            "wf_outcome": (wfx or {}).get("outcome"),
            "wf_error": ((wfx or {}).get("error_info") or {}),
        },
        # Signal 1
        "workflows": ([] if not wfx else [{
            "workflow": (wfx.get("workflow") or {}).get("name"),
            "execution_uuid": wfx.get("uuid"),
            "status": wfx.get("status"),
            "mode": wfx.get("mode"),
            "duration_ms": wfx.get("duration_ms"),
            "nodes": [{
                "order": n.get("execution_order"), "depth": n.get("_depth"),
                "node_type": n.get("node_type"),
                "node_name": n.get("node_name") or n.get("node_id"),
                "status": n.get("status"), "ms": n.get("execution_time_ms"),
                "iter": n.get("iteration_number"), "error": n.get("error"),
            } for n in nodes],
        }]),
        # Signal 3
        "metrics": {
            "num_steps": metrics.get("num_steps"),
            "total_execution_time": metrics.get("total_execution_time"),
            "browser_execution_time": metrics.get("browser_execution_time"),
            "llm_total_tokens": metrics.get("llm_total_tokens"),
            "llm_prompt_tokens": metrics.get("llm_prompt_tokens"),
            "llm_completion_tokens": metrics.get("llm_completion_tokens"),
            "llm_total_cost": metrics.get("llm_total_cost"),
            "failure_point": metrics.get("failure_point"),
            "captured_tokens": captured_tokens,
            "n_think_calls": n_think,
            "n_possible_hallucinations": n_hallucinated,
        },
        "ai_steps": ai_steps,
        "flow": flow,
        # Signal 2
        "actions": [{
            "order": a.get("execution_order") or i,
            "action_type": a.get("action_type") or a.get("name"),
            "selector": a.get("selector"),
            "value": a.get("value"),
            "success": a.get("success"),
            "error": a.get("error") or a.get("error_message"),
            "ms": a.get("execution_time_ms"),
            "url": a.get("target_url"),
        } for i, a in enumerate(actions)],
        # Artifacts
        "artifacts": {
            "run_gif": run.get("run_gif"),
            "run_json": run.get("run_json"),
            "final_screenshot": run.get("final_screenshot"),
            "num_screenshots": len(run.get("surfer_screenshots") or []),
            "recording_status": bs.get("recording_status"),
            "recording_file": bs.get("recording_file"),
            "recording_metadata": bs.get("recording_metadata"),
        },
    }


# --------------------------------------------------------------------------- #
# Render                                                                       #
# --------------------------------------------------------------------------- #

_OUTCOME_MARK = {"pass": "✅", "fail": "❌", "error": "💥", "timeout": "⏱", "pending": "…"}


def _render_flow(flow: list) -> list:
    """Render the interleaved sense→think→act→breaker narrative, grouped by step."""
    out = []
    if not flow:
        out.append("   (no node-level flow — workflow execution not visible to this token)")
        return out
    for f in flow:
        kind, d, ms = f["kind"], (f.get("detail") or {}), f.get("ms")
        if kind == "trigger":
            if d.get("goal"):
                out.append(f"   ◆ goal: {str(d['goal'])[:110]}")
            am = d.get("auth_mode")
            if am and d.get("auth_error"):
                out.append(f"   ⛔ auth[{am}] cred={d.get('credential')} → {str(d['auth_error'])[:80]}")
                out.append(f"      landed on: {d.get('landing_url')}")
            elif am:
                out.append(f"   🔑 auth[{am}] cred={d.get('credential')}")
        elif kind == "setup":
            out.append(f"   🧠 brain: {d.get('brain')}")
        elif kind == "sense":
            els = f"  ·  {d.get('elements')} elements" if d.get("elements") is not None else ""
            shot = "  📷" if d.get("screenshot") else ""
            out.append("")
            out.append(f"   ┌─ step {f.get('iter')}  👁  {d.get('title')}  ({d.get('url')}){els}{shot}")
        elif kind == "think":
            at = (d.get("action_type") or "?").upper()
            line = f"   │  🧠 think {ms}ms → {at}"
            if d.get("selector"):
                line += f"  {d['selector']}"
            if d.get("value"):
                line += f" = {str(d['value'])[:40]!r}"
            out.append(line)
            tag = []
            if d.get("model"):
                tag.append(str(d["model"]))
            if d.get("tokens") is not None:
                tag.append(f"{d['tokens']}tok ({d.get('in_tokens')}→{d.get('out_tokens')})")
            if d.get("n_elements") is not None:
                tag.append(f"{d['n_elements']} elems seen")
            if tag:
                out.append(f"   │     ⟨{'  ·  '.join(tag)}⟩")
            if d.get("selector") and d.get("n_elements") == 0:
                out.append("   │     ⚠ acted with 0 perceived elements — possible hallucinated selector")
            if d.get("reasoning"):
                out.append(f"   │     “{str(d['reasoning'])[:170]}”")
            if d.get("output"):
                out.append(f"   │     output: {str(d['output'])[:120]}")
        elif kind == "act":
            r = d.get("result") or {}
            st = "✓" if d.get("success") else "✗"
            detail = ", ".join(f"{k}={v}" for k, v in r.items() if k != "url")
            out.append(f"   │  ⚡ act  {ms}ms {st}  {detail}")
        elif kind == "breaker":
            if d.get("tripped"):
                out.append(f"   │  🛑 circuit breaker TRIPPED: {d.get('reason')}")
        elif kind == "return":
            tail = f"  err={str(d.get('error'))[:60]}" if d.get("error") else ""
            out.append(f"   └─ return: outcome={d.get('outcome')} success={d.get('success')}{tail}")
        elif f.get("error"):
            out.append(f"   │  ⚠ [{f.get('node_type')}] {str(f['error'])[:80]}")
    return out


def render(t: dict) -> str:
    r, o, m = t["run"], t["outcome"], t["metrics"]
    L = []
    mark = _OUTCOME_MARK.get((r.get("outcome") or "").lower(), "•")
    L.append("═" * 78)
    L.append(f"{mark} E2E RUN {r['id']} · {r.get('key') or ''}  [{r.get('outcome')}]  ({r.get('status')})")
    L.append(f"   test    : {r.get('test_name')}  ·  project: {r.get('project')}")
    L.append(f"   target  : {r.get('target_url')}")
    L.append(f"   timing  : {r.get('duration_seconds')}s   {r.get('started_at')} → {r.get('completed_at')}")
    L.append(f"   uuid    : {r.get('uuid')}")
    L.append("═" * 78)

    # 1. Workflows + nodes
    L.append("\n① WORKFLOWS / NODE GRAPH")
    if not t["workflows"]:
        L.append("   (no workflow execution visible to this token — see note below)")
    for w in t["workflows"]:
        L.append(f"   ▸ {w['workflow']}  [{w['status']}]  {w.get('duration_ms')}ms  exec={w['execution_uuid']}")
        for n in w["nodes"]:
            pad = "     " + "  " * (n.get("depth") or 0)
            st = {"success": "✓", "error": "✗", "skipped": "–", "running": "▸"}.get(n["status"], "·")
            it = f" #it{n['iter']}" if n.get("iter") not in (None, 0) else ""
            line = f"{pad}{st} [{n['node_type']}] {n['node_name']}{it}  {n.get('ms') or ''}ms"
            if n.get("error"):
                line += f"  ⚠ {str(n['error'])[:80]}"
            L.append(line)

    # 3. The step flow (sense → think → act → breaker), grouped by iteration
    L.append("\n③ STEP FLOW  (sense → think → act, per iteration)")
    L.append(f"   think calls: {m.get('n_think_calls')}   "
             f"captured tokens: {m.get('captured_tokens')} (per-think)   "
             f"E2eRunMetrics tokens: {m.get('llm_total_tokens')} (rollup not wired)")
    if m.get("n_possible_hallucinations"):
        L.append(f"   ⚠ {m['n_possible_hallucinations']} think step(s) acted with 0 perceived elements "
                 f"(possible selector hallucination)")
    L.extend(_render_flow(t.get("flow") or []))

    # 2. Actions
    L.append("\n② BROWSER ACTIONS")
    if not t["actions"]:
        L.append("   (no SurferActions recorded — recording/actions may still be flushing)")
    for a in t["actions"]:
        st = "✓" if a.get("success") else ("✗" if a.get("success") is False else "·")
        line = f"   {st} {a['order']:>2} {a.get('action_type')}"
        if a.get("selector"):
            line += f"  {str(a['selector'])[:50]}"
        if a.get("value"):
            line += f" = {str(a['value'])[:30]!r}"
        if a.get("error"):
            line += f"  ⚠ {str(a['error'])[:60]}"
        L.append(line)

    # 4. Outcome
    L.append("\n④ OUTCOME")
    L.append(f"   outcome={o.get('outcome')}  category={o.get('error_category')}  "
             f"failure_point={m.get('failure_point')}")
    if o.get("surfer_error"):
        L.append(f"   reason: {str(o['surfer_error'])[:200]}")
    if o.get("wf_outcome") and o.get("wf_outcome") != o.get("outcome"):
        L.append(f"   (workflow-level outcome: {o.get('wf_outcome')})")

    # Artifacts
    art = t["artifacts"]
    L.append("\n◆ ARTIFACTS")
    L.append(f"   video(gif)       : {art.get('run_gif') or '—'}")
    L.append(f"   recording        : {art.get('recording_status') or '—'}  {art.get('recording_file') or ''}")
    L.append(f"   final_screenshot : {art.get('final_screenshot') or '—'}")
    L.append(f"   step screenshots : {art.get('num_screenshots')}")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def _looks_like_uuid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4


def _err(d) -> str:
    if isinstance(d, dict):
        return d.get("message") or d.get("detail") or d.get("error") or str(d)[:120]
    return str(d)[:120]


def main(argv=None):
    p = argparse.ArgumentParser(description="Assemble a full trace for one E2E pipeline run.")
    p.add_argument("run", help="run uuid, integer id, or 'latest'")
    p.add_argument("--base", default=os.environ.get("DEBUGGAI_API_BASE", DEFAULT_BASE))
    p.add_argument("--token", default=None)
    p.add_argument("--json", action="store_true", help="print normalized trace as JSON")
    p.add_argument("--raw", metavar="PATH", help="also dump raw API payloads to PATH")
    args = p.parse_args(argv)

    token = args.token or _default_token()
    if not token:
        sys.exit("No token. Set DEBUGGAI_API_TOKEN or pass --token "
                 "(or place sentinal/.local/api_token in the platform checkout).")
    api = Api(args.base, token)

    run = resolve_run(api, args.run)
    wfx = find_workflow_execution(api, run)
    trace = build_trace(run, wfx)

    if args.raw:
        Path(args.raw).write_text(json.dumps({"run": run, "workflow_execution": wfx}, indent=2, default=str))

    if args.json:
        print(json.dumps(trace, indent=2, default=str))
    else:
        print(render(trace))
        if wfx is None:
            print("ℹ︎  No workflow execution was correlated for this run. Either it isn't visible "
                  "to this token's company, or context_data carried no e2e_run_id. "
                  "Signals ①/③ (node graph, per-step AI) come from the workflow execution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

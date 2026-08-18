"""The SCOREBOARD — which promoted use cases actually work right now, and which don't.

The operator's ask (2026-08-18): *«que tuviéramos claro cuáles están funcionando bien y cuáles no»*. Before
this, every run wrote a fresh dated report into `tests/runs/use_cases/` and nothing accumulated — so
answering "does the flights case work?" meant opening reports by hand and guessing which was the most
recent meaningful one. This keeps a durable, committed, per-scenario last-known verdict.

PRIVACY (this repo is PUBLIC — see CLAUDE.md's «catálogo sí, diario no» rule, and the 2026-08-15 leak of 444
files of session transcripts): the ledger stores SCORES and a one-line verdict per scenario, never the
transcript, never the driver's invented persona details, never extracted listing data. The CATALOG of what is
tested and whether it passes is useful to anyone who clones the engine; the DIARY of what was said in a run
is not, and stays in `tests/runs/` (gitignored).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parents[3] / "use_cases" / "status.json"
BOARD_PATH = Path(__file__).resolve().parents[3] / "use_cases" / "STATUS.md"

PASS_THRESHOLD = 4          # same bar `run.py` prints and `cron_tick.sh` reads: overall >= 4


def load() -> dict:
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"scenarios": {}}


def record(results: list[dict], *, sandboxed: bool) -> dict:
    """Fold one batch's results into the ledger. Only scenarios that actually ran are touched — a batch of
    one must never look like it invalidated the other four."""
    led = load()
    scen = led.setdefault("scenarios", {})
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    for r in results:
        verdict = r.get("verdict") or {}
        overall = verdict.get("overall")
        mech = (r.get("run") or {}).get("mechanism_report") or {}
        registry = mech.get("task_registry") or {}
        entry = {
            "last_run": stamp,
            "overall": overall,
            "state": _state(overall, r),
            "scores": verdict.get("scores") or {},
            "verdict": (verdict.get("veredicto") or "")[:400],
            "missing_signals": mech.get("missing_signals") or [],
            "sandboxed": sandboxed,
            "tier": r.get("tier"),
        }
        # What this case could HONESTLY be graded on. Recorded per row so a reader of the board knows a `PASS`
        # on a bookable case means "found real options and stopped at the wall", not "made a reservation" —
        # otherwise the scoreboard would quietly overclaim what the product does.
        try:
            from . import derived as D
            kind, missing = D.data_scope(r["scenario"].split("__")[0])
            if kind:
                entry["data_limit"] = {"kind": kind, "missing": missing}
        except Exception:
            pass
        if registry:
            entry["max_concurrent"] = registry.get("max_concurrent")
            entry["distinct_kinds"] = registry.get("distinct_kinds") or []
        # The workspace pointer SURVIVES a re-run. Everything else here is per-round and rightly replaced, but
        # the initiative is the case's home for its whole life — dropping it on the next round would send the
        # fixing agent back to guessing the filename, and it is the round-2 runs that need it most.
        prior = scen.get(r["scenario"]) or {}
        if prior.get("workspace") and not entry.get("workspace"):
            entry["workspace"] = prior["workspace"]
        scen[r["scenario"]] = entry
    led["updated"] = stamp
    LEDGER_PATH.write_text(json.dumps(led, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _render(led)
    return led


def _state(overall, r: dict) -> str:
    """INFRA is deliberately its own state, never a FAIL: a network timeout or a crashed harness says nothing
    about whether the use case works, and folding the two together is how a scoreboard starts lying."""
    run = r.get("run") or {}
    if run.get("crashed") or (r.get("verdict") or {}).get("veredicto", "").startswith("INFRA"):
        return "INFRA"
    if overall is None:
        return "INFRA"
    return "PASS" if overall >= PASS_THRESHOLD else "FAIL"


_ICON = {"PASS": "✅", "FAIL": "❌", "INFRA": "⚠️"}


def _render(led: dict) -> None:
    scen: dict = led.get("scenarios") or {}
    lines = [
        "# Use-case scoreboard — what actually works right now",
        "",
        "**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by",
        "every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.",
        "",
        f"Last updated: **{led.get('updated', '—')}**",
        "",
        "`✅ PASS` = judge overall ≥ 4 · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,",
        "says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not",
        "the operator's live one.",
        "",
        "| | scenario | tier | overall | last run | sandbox | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for sid in sorted(scen, key=lambda s: (scen[s].get("tier") or 0, s)):
        e = scen[sid]
        st = e.get("state", "INFRA")
        overall = e.get("overall")
        verdict = (e.get("verdict") or "").replace("|", "·").replace("\n", " ")
        if len(verdict) > 160:
            verdict = verdict[:157] + "…"
        lines.append(
            f"| {_ICON.get(st, '⚠️')} | `{sid}` | {e.get('tier', '—')} | "
            f"{overall if overall is not None else '—'} | {e.get('last_run', '—')} | "
            f"{'yes' if e.get('sandboxed') else 'no'} | {verdict} |")

    passed = sum(1 for e in scen.values() if e.get("state") == "PASS")
    failed = sum(1 for e in scen.values() if e.get("state") == "FAIL")
    infra = sum(1 for e in scen.values() if e.get("state") == "INFRA")
    lines += ["", f"**{passed} passing · {failed} failing · {infra} infra** of {len(scen)} scenarios with a "
                  f"recorded result.", ""]

    # COVERAGE, next to the results. Without it "1 passing · 4 failing" reads like the whole answer to "which
    # use cases work?", when the honest answer also has to say how much of the catalog nobody has run yet —
    # and an UNRUN case is not a passing one. Broken down by tier and locale because that is how the walk is
    # actually driven (`--tier N --locale es`), so this doubles as the progress board for it.
    try:
        from . import scenarios as SC
        allsc = SC.all_scenarios()
    except Exception:
        allsc = []
    if allsc:
        done = set(scen)
        lines += [f"## Catalog coverage — {len(done)} of {len(allsc)} scenarios ever run "
                  f"({len(allsc) - len(done)} never run)", "",
                  "An unrun case is **not** a passing one. This is the walk's progress board.", "",
                  "| tier | locale | run | of | passing |", "|---|---|---|---|---|"]
        keys = sorted({(s.tier, s.locale) for s in allsc})
        for tier, loc in keys:
            group = [s.id for s in allsc if s.tier == tier and s.locale == loc]
            ran = [sid for sid in group if sid in done]
            ok = sum(1 for sid in ran if scen[sid].get("state") == "PASS")
            lines.append(f"| {tier} | {loc} | {len(ran)} | {len(group)} | {ok} |")
        lines.append("")

    limited = {s: e["data_limit"] for s, e in scen.items() if e.get("data_limit")}
    if limited:
        lines += ["## Cases with no real data behind them — what they are graded on", "",
                  "Operator's rule (2026-08-18): renewing a gym membership can never work with no gym, no "
                  "account and no membership — *«eso no es un fallo del use case»*. So the OUTCOME is withdrawn "
                  "from judgement while the CONDUCT is not: saying precisely what is missing scores full "
                  "marks, and claiming it was done is still the gravest failure. `no_booking` cases keep their "
                  "SEARCH half graded in full — only closing the booking is out of reach. Same in ES and US.",
                  "", "| scenario | scope | what is missing |", "|---|---|---|"]
        for sid in sorted(limited):
            d = limited[sid]
            lines.append(f"| `{sid}` | {d.get('kind')} | {d.get('missing')} |")
        lines.append("")

    work = {s: e["workspace"] for s, e in scen.items()
            if e.get("state") == "FAIL" and e.get("workspace")}
    if work:
        lines += ["## Where the work on each failing case happens", "",
                  "One initiative per use case — that initiative IS the workspace for it, and it carries the "
                  "transcript, the mechanism report and the reproduce command. Both folders are gitignored "
                  "(«ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.", "",
                  "| scenario | initiative (the workspace) | fix task |", "|---|---|---|"]
        for sid in sorted(work):
            w = work[sid]
            lines.append(f"| `{sid}` | `{w.get('initiative', '—')}` | `{w.get('task', '—')}` |")
        lines.append("")

    multi = {s: e for s, e in scen.items() if e.get("max_concurrent") is not None}
    if multi:
        lines += ["## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)", "",
                  "| scenario | max concurrent tasks | distinct worker kinds |", "|---|---|---|"]
        for sid, e in sorted(multi.items()):
            kinds = ", ".join(e.get("distinct_kinds") or []) or "—"
            lines.append(f"| `{sid}` | {e.get('max_concurrent')} | {kinds} |")
        lines.append("")

    BOARD_PATH.write_text("\n".join(lines), encoding="utf-8")


def summary_line() -> str:
    scen = (load().get("scenarios") or {})
    if not scen:
        return "no recorded results yet"
    passed = sum(1 for e in scen.values() if e.get("state") == "PASS")
    return f"{passed}/{len(scen)} scenarios passing (see tests/use_cases/STATUS.md)"


def attach_workspaces(mapping: dict) -> None:
    """Record WHERE the work on each failing case happens, so the board is the entry point to it.

    The initiative is the workspace for a use case, but it lives among 100+ others in a gitignored folder —
    a fixing agent handed only "quick-fact-opening-hours is failing" has to know the naming convention to find
    anything. This closes that gap: the board names the file. Only PATHS are stored, never content — the paths
    are already-public case ids, while the initiative itself holds the transcript and stays local.

    Called AFTER filing (the paths do not exist before it), so it updates and re-renders rather than being
    folded into `record()`.
    """
    if not mapping:
        return
    led = load()
    scen = led.setdefault("scenarios", {})
    for sid, paths in mapping.items():
        if sid in scen:
            scen[sid]["workspace"] = paths
    LEDGER_PATH.write_text(json.dumps(led, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _render(led)


def failing_count() -> int:
    """How many cases are FAILING on the board right now — the walk's stop budget.

    Only `FAIL` counts. An `INFRA` row (crashed harness, network timeout) says nothing about a use case, and
    letting it consume the budget would stop the walk early with nothing real to work on.
    """
    return sum(1 for e in (load().get("scenarios") or {}).values() if e.get("state") == "FAIL")

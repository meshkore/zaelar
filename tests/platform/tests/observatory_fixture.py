"""A runs root the way the harness leaves it, built in a temp dir, and a real Observatory serving it.

Shared by the four screen ratchets (home, test sets, the judge viewer, the brain). Every file here has the SHAPE
the real writers produce — `cli.py`'s run.json + events.jsonl, `watchdog.py`'s report, `report.py`'s round
JSON, `status.py`'s ledger, a sandbox workspace with the engine's `events` table — because the screens read those
files and nothing else; a ratchet over an invented shape would pin the wrong thing.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from tests.platform.server import DashboardServer, Handler

ENGINE = Path(__file__).resolve().parents[3]
DASHBOARD = ENGINE / "tests" / "platform" / "dashboard"

#: The round's clock. Fixed so the sandbox stamp, the turns and the DB rows line up by construction.
T0 = time.mktime(time.strptime("20261102115912", "%Y%m%d%H%M%S"))
SANDBOX = "20261102-115901-es"          # booted 11 s before the first turn, same locale → the match by time


def write_run(root: Path, run_id: str, *, status: str, actor: str, suite: str, age_s: float = 0.0,
              lines: list[dict] | None = None) -> Path:
    run_dir = root / run_id
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "suite": suite, "status": status, "created_at": time.time() - age_s,
        "target": f"deterministic · {suite}", "launched_by": {"actor": actor, "user": "someone"}}), encoding="utf-8")
    events = run_dir / "events.jsonl"
    events.write_text("".join(json.dumps(line) + "\n" for line in (lines or [])), encoding="utf-8")
    if age_s:
        os.utime(events, (time.time() - age_s, time.time() - age_s))
    return run_dir


def write_watchdog(root: Path, stamp: str, results: list[dict]) -> Path:
    totals = {"passed": 0, "failed": 0}
    for r in results:
        for k, v in (r.get("counts") or {}).items():
            totals[k] = totals.get(k, 0) + v
    p = root / f"watchdog-{stamp}.json"
    p.write_text(json.dumps({"results": results, "totals": totals}), encoding="utf-8")
    return p


def sweep_result(target: str, *, verdict: str = "ok", seconds: float = 5.0, passed: int = 10, failed: int = 0,
                 failures: list[str] | None = None, hung_at: str | None = None) -> dict:
    return {"target": target, "verdict": verdict, "seconds": seconds, "exit": 0 if verdict == "ok" else 1,
            "hung_at": hung_at, "counts": {"passed": passed, "failed": failed}, "stack": [], "tail": [],
            "failures": [{"node": n, "why": "AssertionError"} for n in (failures or [])]}


def transcript() -> list[dict]:
    return [
        {"who": "tester", "text": "Búscame tres monitores 4K de 27 pulgadas por menos de 400 euros", "at": T0},
        {"who": "zaelar", "text": "Voy a ello, te los busco ya.", "at": T0 + 9.2},
        {"who": "tester", "text": "¿Y bien? ¿Has encontrado algo ya?", "at": T0 + 41.0},
        {"who": "zaelar", "text": "Sí, el LG 27UP850 por 349 €, el Dell S2721QS por 329 € y el Samsung U28R550 por 299 €.", "at": T0 + 44.5},
        {"who": "tester", "text": "Vale, gracias, con eso me apaño.", "at": T0 + 80.0},
        {"who": "zaelar", "text": "", "at": T0 + 81.0},
    ]


def mechanism_report() -> dict:
    """What `verify.mechanism_report` + `run.py` write for a search case where the worker never ran, the sheet
    opened and stayed empty, and the second reply named prices with nothing behind them."""
    return {
        "families_observed": ["flash", "memory", "system", "widget"],
        "expected_signals": ["worker", "widget"], "missing_signals": ["worker"],
        "forbidden_signals": [], "overreach_signals": [], "locale": "es", "n_events": 120,
        "navegador_task_id": "", "navegador_task": {},
        "results_sheet": {"read": True, "n_items": 0, "n_named": 0, "n_backed": 0, "titles": [], "boxes": ["results"]},
        "sheet_instances": {"n_sheets": 1, "ids": ["results::abc-1"], "n_opens": 1, "n_errands": 1, "shared": False},
        "sheet_timing": {"sheet_ms": (T0 + 9.0) * 1000, "sheet_named_ms": None, "delivery_lag_s": None,
                         "delivery_clock": "primera escritura", "last_turn_ms": (T0 + 80.0) * 1000},
        "ghost_widgets": {"observed": True, "ghosts": [], "max_cards": 1, "last": ["results::abc-1"]},
        "open_widgets_by_turn": {"by_turn": {"t0": ["results::abc-1"], "t1": ["results::abc-1"], "t2": ["results::abc-1"]},
                                 "max_open": 1, "kinds": ["results"]},
        "search_returns": {"queries": 1, "returns": 0, "notes_from_search": 0, "returns_after_last_turn": 0, "inline_returns": 0},
        "worker_health": {"spawned": 0, "ok": 0, "errored": 0, "cancelled": 0, "relayed": 0, "still_running": 0},
        "quiescence": {"settled": True, "waited_s": 12.0, "events": 120, "pending_workers": 0},
        "market_claims_before_delivery": {"turns": [1], "n": 1, "measurable": True},
        "told_but_given_no_rows": {"turns": [], "n": 0, "measurable": True},
        "delivered_by_name": {"n": 0, "names": [], "turns": [], "lower_bound": False},
        "memory_language": {"effective": "es", "explicit": True, "source": "engine"},
        "audit": {"n_events": 120, "errors": [], "anomalies": [], "clean": True, "spans": {}, "max_gap_ms": 3000},
        "turn_actions": [{"turn": 0, "pedido": ["escalate_to_slowbrain"], "action": "escalate", "ejecutado": "escalate"},
                         {"turn": 1, "pedido": [], "action": "chat"}, {"turn": 2, "pedido": [], "action": "chat"}],
        "widget_ops_by_turn": {"t0": ["results.show"]},
        "dropped_actions": [], "duplicate_errands": {"groups": []}, "page_journey": {"read": True, "n_walls": 0, "walls": []},
        "scheduled_jobs": {"readable": True, "n_before": 0, "n_after": 0, "created": []},
        "brains": {"workers": [], "n_by_worker": {}, "relays": [], "mixed": False},
    }


def verdict() -> dict:
    return {"scores": {"naturalidad": 4, "adaptacion": 3, "resultado": 1, "mecanismo": 1, "eficiencia": 2}, "overall": 2,
            "findings": [{"turno": "zaelar@turn1", "problema": "Nombra tres monitores con precio sin que la hoja tenga una sola fila.", "gravedad": "alta"},
                         {"turno": "mecanismo", "problema": "La señal esperada «worker» no se observó.", "gravedad": "alta"},
                         {"turno": "zaelar@turn2", "problema": "Turno mudo al despedirse.", "gravedad": "media"}],
            "improvements": [{"area": "entrega", "cambio": "No nombrar candidatos antes de que existan en la hoja.", "porque": "Es la afirmación falsa del caso."}],
            "veredicto": "No listo para producción: el bloqueador nº1 es que afirmó tres candidatos con precio sin ninguna fila detrás.",
            "_judge_model": "judge-model"}


def write_round(root: Path, stamp: str = "20261102-120419", *, scenario: str = "search-monitors-under-400",
                judged: bool = True, sha: str = "41908d5cb", emitted: bool = False) -> Path:
    """`emitted` writes the round the way the harness does since V2-856: the workspace it ran in and the corr_id of
    each turn on its transcript rows. Without it the round is an older one, matched by time and text."""
    uc = root / "use_cases"
    uc.mkdir(parents=True, exist_ok=True)
    result = {"scenario": scenario, "tier": 2, "channel": "probe", "drive_model": "licencia-claude",
              "code": {"sha": sha, "n_dirty": 0, "dirty": []}, "machine": {"gpu_models": [{"name": "local-model:27b", "size": "31 GB"}], "n": 1},
              "run": {"transcript": transcript(), "mechanism_report": mechanism_report(),
                      "watchdog_log": [{"health": "off_track", "action": "nudge", "reason": "promises with no rows"}]}}
    if emitted:
        result["run"]["workspace"] = str(uc / "sandbox" / SANDBOX)
        for i, row in enumerate(result["run"]["transcript"][:4]):
            row["corr_id"] = ("T1·64a8", "T2·4e4d")[i // 2]
    if judged:
        result["verdict"] = verdict()
        p = uc / f"report_{stamp}.json"
        p.write_text(json.dumps({"stamp": stamp, "results": [result], "improvements": []}, ensure_ascii=False), encoding="utf-8")
        (uc / f"report_{stamp}.md").write_text("# report\n", encoding="utf-8")
    else:
        (uc / "pending").mkdir(exist_ok=True)
        p = uc / "pending" / f"{scenario}-{stamp}.json"
        p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return p


def write_ledger(root: Path, scenario: str = "search-monitors-under-400", *, sha: str = "41908d5cb") -> Path:
    """`tests/use_cases/status.json` BESIDE the runs root (`observatory_data.ledger_path`)."""
    p = root.parent / "use_cases" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"last_run": "2026-11-02 11:59", "overall": 2, "judge": "judge-model", "state": "FAIL",
           "tier": 2, "scores": verdict()["scores"], "verdict": verdict()["veredicto"], "code": {"sha": sha, "n_dirty": 0},
           "rounds": [{"at": "2026-11-01 10:00", "state": "FAIL", "overall": 2, "judge": "x", "sha": sha, "counted": True},
                      {"at": "2026-11-02 11:59", "state": "FAIL", "overall": 2, "judge": "x", "sha": sha, "counted": True}],
           "blind_turns": 1, "infra_reason": None}
    p.write_text(json.dumps({"scenarios": {scenario: row, scenario + "__us": {**row, "state": "PASS", "overall": 4}},
                             "updated": "2026-11-02 12:04"}), encoding="utf-8")
    return p


def _ev(con, ts_ms: float, cat: str, kind: str, label: str, corr: str, payload: dict, *, span: str = "", ms=None,
        model: str = "") -> None:
    con.execute("INSERT INTO events (ts_ms, topic, payload, corr_id, session_id, user_id, cat, kind, label, span, ms, model) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts_ms, "observer", json.dumps({"kind": kind, "label": label, "cat": cat, "trace": corr, **payload},
                                              ensure_ascii=False), corr, "sess-1", "user-1", cat, kind, label, span, ms, model))


def write_sandbox(root: Path, name: str = SANDBOX, *, with_db: bool = True) -> Path:
    """A kept workspace with the engine's `events` table: turn 0 is a full flow whose model CALLED an escalation
    and no worker was ever born; turn 1 is a plain chat turn; turn 2 has no trace at all (a mute turn)."""
    ws = root / "use_cases" / "sandbox" / name
    (ws / "config").mkdir(parents=True, exist_ok=True)
    (ws / "config" / "settings.json").write_text("{}", encoding="utf-8")
    if not with_db:
        return ws
    db = ws / "memory" / "_data" / "sandbox.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms REAL NOT NULL, topic TEXT NOT NULL,
        payload TEXT, corr_id TEXT, session_id TEXT, user_id TEXT, cat TEXT, kind TEXT, label TEXT, span TEXT, ms REAL,
        model TEXT, tokens_in INTEGER, tokens_out INTEGER, ver TEXT)""")
    tr = transcript()
    t = tr[0]["at"] * 1000
    c0 = "T1·64a8"
    _ev(con, t, "flash", "trace", "turno", c0, {"text": tr[0]["text"], "role": "user", "root": True, "origin": "turno"})
    _ev(con, t, "flash", "ambient", "👂 dirigido a zaelar", c0, {"directed": True})
    _ev(con, t + 1, "system", "consequence", "tasks.intake", c0, {"door": "tasks.intake", "verdict": "pass", "blocked": False, "arg": tr[0]["text"]})
    _ev(con, t + 40, "flash", "brain", "⚡ Nucleo(flash): prompt", c0, {"text": tr[0]["text"], "role": "user"})
    _ev(con, t + 300, "memory", "memory", "recall", c0, {"text": "«Búscame tres monitores…» → 1 tarjetas del largo plazo"})
    _ev(con, t + 1400, "flash", "brain", "jev read escalate_or_inline", c0, {"text": "escalate -> USED (0.91)"})
    _ev(con, t + 1401, "flash", "brain", "jev read request_type", c0, {"text": "order -> USED (0.80)"})
    _ev(con, t + 9100, "flash", "brain", "⚡ Nucleo(flash): reply", c0,
        {"text": tr[1]["text"], "role": "assistant", "model": "deepseek-flash", "engine": "deepseek", "ttft_ms": 900,
         "fast_ms": 9000, "prompt_tokens": 12000, "n_tools": 23, "window_msgs": 2, "finish_reason": "tool_calls",
         "escalated": False, "raw_tool_calls": [{"name": "escalate_to_slowbrain", "arguments": "{\"goal\": \"buscar monitores\"}"}]},
        ms=9000, model="deepseek-flash")
    _ev(con, t + 9150, "widget", "arbiter", "✅ permitida · payload-in-turn", c0, {"op": "show", "id": "results::abc-1", "allow": True, "rule": "payload-in-turn", "src": "flash"})
    _ev(con, t + 9160, "widget", "widget", "show", c0, {"id": "results::abc-1", "src": "flash"})
    _ev(con, t + 9200, "flash", "brain", "💬 chat (canal de texto)", c0, {"text": tr[1]["text"], "role": "assistant"})
    # turn 1 — plain chat: gate, brief, prompt, model, mouth
    c1 = "T2·4e4d"
    t1 = tr[2]["at"] * 1000
    _ev(con, t1, "flash", "trace", "turno", c1, {"text": tr[2]["text"], "role": "user", "root": True})
    _ev(con, t1 + 30, "flash", "brain", "⚡ Nucleo(flash): prompt", c1, {"text": tr[2]["text"]})
    _ev(con, t1 + 900, "flash", "brain", "jev read request_type", c1, {"text": "question -> USED (0.9)"})
    _ev(con, t1 + 3400, "flash", "brain", "⚡ Nucleo(flash): reply", c1,
        {"text": tr[3]["text"], "role": "assistant", "model": "deepseek-flash", "finish_reason": "stop", "raw_tool_calls": []}, ms=3400)
    _ev(con, t1 + 3450, "flash", "brain", "💬 chat (canal de texto)", c1, {"text": tr[3]["text"], "role": "assistant"})
    con.commit()
    con.close()
    return ws


@pytest.fixture()
def runs_root(tmp_path: Path) -> Path:
    """`tmp/tests/runs` — the ledger lives at `tmp/tests/use_cases/status.json`, beside it, as in the engine."""
    root = tmp_path / "tests" / "runs"
    root.mkdir(parents=True)
    return root


@pytest.fixture()
def observatory(runs_root: Path):
    server = DashboardServer(("127.0.0.1", 0), Handler, runs_root, idle_timeout=30)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server, runs_root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def get(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def get_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read().decode("utf-8")


def dashboard_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(DASHBOARD.iterdir()) if p.suffix in (".html", ".js", ".css")}

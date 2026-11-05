"""Mechanism readers for the task battery (V2-851 §9).

A case asserts MECHANISM, never the judge: (1) the events of the turn's flow (`/api/observability/flow/<trace>`),
(2) the `tasks` rows (`/api/tasks`), (3) the lines the user saw on the wall for that trace — how many and from which
source. The LLM judge, when a case wants one, only grades the prose of the final line.

INFRA is kept apart from FAIL (V2-779 F2): a turn that did not run (timeout, `ok: false`, a dead engine) raises
`Infra`, which the conftest turns into a failure whose message starts with «INFRA:». A battery red is only red for
a reason when it falls on a NAMED assertion (`Check.that`).

Event shape (measured on the frozen code, 2026-11-05): `/api/observability/flow/<trace>` and `/api/observability/events`
return rows `{id, ts_ms, topic, corr_id?, kind, label, span, …, payload}` where `payload` is the JSON string of the
whole observer record (`text`, `role`, `trace`, `span`, and every `extra` field flattened). `id` is the table's
monotonic key, which is what «after the reply line» means here. Only `topic = observer` rows are served over HTTP;
bus topics (`msg.send`, `worker.ask`, …) are kept in the same table but not exposed, which is why a send is read from
the loopback account (`seed.sent`) and a question from its `ask` event.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.parse
from dataclasses import dataclass, field

from tests.platform.sandbox_engine import SandboxEngine


class Infra(RuntimeError):
    """The product was not measured: the engine, the channel or a model did not answer."""


#: The contract the battery reads, named once. F1/F2 make the engine emit these; the frozen code does not, which
#: is why the cases are red there on the assertion that names them.
ROW_FIELDS = ("session_id", "waiting_for", "waiting_since", "ask_id", "ask", "deadline", "playbook")
EV_TASK_STATE = "task_state"      # observer kind: {task_id, state, writer} — only `circuit.settle` writes it
EV_ASK = "ask"                    # observer kind: a question shown on screen, {task_id, ask_id, text}
#: An ASK_WHICH question (an answer that fits several waiting tasks) names them: `{task_id: "", ask_id, text,
#: among: [task_id, …]}`. Invented by the battery (V2-851 F0) — the plan says «ASK_WHICH among the waiting tasks»
#: and names no field.
ASK_AMONG = "among"
WRITER_SETTLE = "settle"
FINAL_STATES = ("done", "failed", "cancelled")
LIVE_STATES = ("pending", "running", "waiting")
WAITING_USER = "user_answer"
#: Where a worker's prompt size travels (V2-851 §5: «prompt size per worker measured before and after»). Invented by
#: the battery: the `worker_start` event carries `prompt_chars` (the whole first message the session receives).
WORKER_PROMPT_FIELD = "prompt_chars"

#: Wall-line sources a case may count. `say` is a worker's interim word bound to its task (it carries `task_id`);
#: `notice` is the keyed out-of-turn door; `notify` is any other out-of-band 🔔 line (the frozen code's
#: `voice/proactive.notify`, 37 callers — the mouths §2c retires).
SPEAKERS = ("reply", "follow_up", "ask", "say", "notice", "notify")


def payload(ev: dict) -> dict:
    p = ev.get("payload")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            p = {}
    return p if isinstance(p, dict) else {}


def line_source(ev: dict) -> str:
    """Which mouth put a user-visible line on the wall, or "" when the event is not one.

    `reply` — the turn's own line (the text channel's wall line, `wall=agent`); `follow_up` — the turn's follow-up
    (`nucleo/flash/follow_up_pass`, `wall=zaelar`); `ask` — a task's question on screen; and the out-of-band 🔔 line of
    `voice/proactive.notify` (its payload carries `title`): `say` when it names its task (`task_id`), `notice` when it
    carries the notice door's identity (`key` / `notice_id`), `notify` otherwise. Not lines: `🗣 reply: the verdict's
    line` (merged into the reply it rides), the notice ledger's own `notice` rows, a widget's 🔔 diagnostics, fillers.
    """
    p = payload(ev)
    kind = str(ev.get("kind") or p.get("kind") or "")
    label = str(ev.get("label") or p.get("label") or "")
    if kind == EV_ASK:
        return "ask"
    wall = p.get("wall") or (p.get("extra") or {}).get("wall")
    if wall == "agent":
        return "reply"
    if wall == "zaelar":
        return "follow_up"
    if label.startswith("🔔") and kind not in ("widget", "notice") and "title" in p:
        if p.get("task_id"):
            return "say"
        if p.get("key") or p.get("notice_id"):
            return "notice"
        return "notify"
    return ""


def is_model_run(ev: dict) -> bool:
    """A call to a language model on the turn's behalf: the main Flash call (`⚡ Nucleo(…): prompt`) or a decision read
    (`jev …`). The memory processor's ingest (`CORAZÓN mem_processor`) is not the turn and is not counted."""
    label = str(ev.get("label") or "")
    return str(ev.get("kind") or "") == "brain" and (
        (label.startswith("⚡ Nucleo(") and label.endswith(": prompt")) or label.startswith("jev "))


def bridge_acts(events: list[dict], key: str, trace: str = "") -> list[dict]:
    """What a worker DID through its hands. First-class source since V2-851 F2: ONE `worker_act` event per bridge act
    {task_id, session, act, door, outcome}, matched by the session key or the row id. When none is there (the frozen
    code), the F0 inventory's readers stand:

      · `task / · paso` with `id = <session key>` — a step the worker ran (a bridge CLI `-m nucleo.cli.…`, a tool);
      · `consequence` with `span = worker:<key>` — a door it reached through `/api/worker/act` (`widget.data`, …),
        except `worker.inject` (that is Flash talking TO it);
      · `navegador / 🧭 navegador` on the worker's trace — a browser order.
    `/api/worker/act` itself emits nothing; its acts are seen through the doors they reach."""
    key = str(key or "")
    first = [ev for ev in events if str(ev.get("kind") or "") == "worker_act"
             and key in (str(payload(ev).get("session") or ""), str(payload(ev).get("task_id") or ""))]
    if first:
        return first
    out = []
    for ev in events:
        p = payload(ev)
        kind, label = str(ev.get("kind") or ""), str(ev.get("label") or "")
        if kind == "task" and label == "· paso" and str(p.get("id") or "") == key:
            out.append(ev)
        elif kind == "consequence" and p.get("span") == f"worker:{key}" and p.get("door") != "worker.inject":
            out.append(ev)
        elif kind == "navegador" and label == "🧭 navegador" and trace and p.get("trace") == trace:
            out.append(ev)
    return out


@dataclass
class Turn:
    text: str
    res: dict
    trace: str
    t0: float
    t1: float
    since: int = 0            # the last event id BEFORE the turn: everything after it is the turn's or later


@dataclass
class Probe:
    """One engine under test plus the reads every case uses."""
    eng: SandboxEngine
    session: str = "battery"
    turns: list = field(default_factory=list)
    _cursor: int = 0

    # ── driving ─────────────────────────────────────────────────────────────────────────────────────────────
    def say(self, text: str, *, timeout: float = 200.0) -> Turn:
        since = self.cursor()
        t0 = time.time()
        try:
            status, res = self.eng.post("/api/flash/say", {"text": text, "session": self.session,
                                                           "execute": True, "ingest": True}, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — a dead channel is INFRA, never a product verdict
            raise Infra(f"say({text!r}) did not answer: {type(e).__name__}: {e}") from e
        if status != 200 or not isinstance(res, dict) or not res.get("ok"):
            raise Infra(f"say({text!r}) → {status} {str(res)[:300]}")
        turn = Turn(text, res, str(res.get("trace") or ""), t0, time.time(), since)
        if not turn.trace:
            raise Infra(f"say({text!r}) returned no trace — the flow cannot be read")
        self.turns.append(turn)
        return turn

    def reset(self) -> None:
        """Between cases: background work killed, canvas closed, session rotated — memory kept (`/reset/hard`)."""
        try:
            self.eng.post("/reset/hard", {}, timeout=60.0)
            self.eng.post("/api/flash/reset", {"session": self.session}, timeout=30.0)
        except Exception as e:  # noqa: BLE001
            raise Infra(f"reset failed: {e}") from e

    def answer(self, task_id: str, ask_id: str, text: str) -> tuple[int, object]:
        """Answer a question BY SCREEN — the route the new engine adds (V2-851 §3a: «a screen answer carries the
        `ask_id` itself»). On the frozen code it does not exist (404): a named red, never INFRA."""
        try:
            return self.eng.post(f"/api/tasks/{urllib.parse.quote(str(task_id), safe='')}/answer",
                                 {"ask_id": ask_id, "text": text}, timeout=60.0)
        except Exception as e:  # noqa: BLE001
            raise Infra(f"answer({task_id}) did not answer: {e}") from e

    # ── reading: events ─────────────────────────────────────────────────────────────────────────────────────
    def flow(self, trace: str) -> list[dict]:
        status, body = self.eng.get("/api/observability/flow/" + urllib.parse.quote(trace, safe="") + "?limit=2000")
        if status != 200 or not isinstance(body, dict):
            raise Infra(f"flow({trace}) → {status}")
        return list(body.get("events") or [])

    def events_since(self, since: int) -> list[dict]:
        """Every observer event after `since` (all traces, and the out-of-turn ones that carry none)."""
        out: list[dict] = []
        cur = int(since)
        while True:
            status, body = self.eng.get(f"/api/observability/events?since_id={cur}&limit=2000", timeout=30.0)
            if status != 200 or not isinstance(body, dict):
                raise Infra(f"events(since {cur}) → {status}")
            rows = list(body.get("events") or [])
            out.extend(rows)
            if not body.get("more") or not rows:
                break
            cur = int(rows[-1]["id"])
        if out:
            self._cursor = max(self._cursor, int(out[-1]["id"]))
        return out

    def cursor(self) -> int:
        """The id of the newest event right now — «before this» for whatever comes next."""
        self.events_since(self._cursor)
        return self._cursor

    def lines(self, trace: str) -> list[tuple[str, dict]]:
        """The user-visible lines of a flow, in order, with their source."""
        return [(src, ev) for ev in self.flow(trace) if (src := line_source(ev))]

    def lines_since(self, since: int) -> list[tuple[str, dict]]:
        """Every user-visible line after event `since`, whatever its trace — the out-of-turn mouths carry none."""
        return [(src, ev) for ev in self.events_since(since) if (src := line_source(ev))]

    def reply_line(self, turn: Turn) -> dict | None:
        return next((ev for ev in self.flow(turn.trace) if line_source(ev) == "reply"), None)

    def asks_since(self, since: int) -> list[dict]:
        return [ev for ev in self.events_since(since) if str(ev.get("kind") or "") == EV_ASK]

    def task_states_since(self, since: int, task_id: str = "") -> list[dict]:
        evs = [ev for ev in self.events_since(since) if str(ev.get("kind") or "") == EV_TASK_STATE]
        return [ev for ev in evs if not task_id or str(payload(ev).get("task_id") or "") == str(task_id)]

    def worker_starts_since(self, since: int) -> list[dict]:
        return [ev for ev in self.events_since(since) if str(ev.get("kind") or "") == "worker_start"]

    # ── reading: rows ───────────────────────────────────────────────────────────────────────────────────────
    def tasks(self, scope: str = "live") -> list[dict]:
        status, body = self.eng.get(f"/api/tasks?scope={scope}&all=1")
        if status != 200 or not isinstance(body, dict):
            raise Infra(f"tasks({scope}) → {status}")
        return list(body.get("tasks") or [])

    def all_tasks(self) -> list[dict]:
        seen, out = set(), []
        for scope in ("live", "done", "recurring", "scheduled"):
            for row in self.tasks(scope):
                key = row.get("id") or json.dumps(row, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    out.append(row)
        return out

    def rows_since(self, t0: float) -> list[dict]:
        """The rows born at or after `t0` (the table keeps whole seconds). A row's `trace_id` is not reliable on the
        frozen code (an inline row carries ""), so birth time is the join."""
        return [r for r in self.all_tasks() if int(r.get("created_at") or 0) >= int(t0) - 1]

    def row(self, task_id: str) -> dict | None:
        return next((r for r in self.all_tasks() if str(r.get("id")) == str(task_id)), None)

    def artifacts(self, task_id: str) -> list[tuple[str, int]]:
        """`(slot, size)` of what `task_artifacts` holds for a row — read-only from the sandbox's own database; no
        HTTP route exposes it on the frozen code."""
        db = self.eng.workspace / "memory" / "_data" / "sandbox.db"
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                cols = [r[1] for r in con.execute("PRAGMA table_info(task_artifacts)")]
                slot = "slot" if "slot" in cols else cols[1]
                body = "payload" if "payload" in cols else cols[-1]
                rows = con.execute(f"SELECT {slot}, length({body}) FROM task_artifacts WHERE task_id = ?",
                                   (str(task_id),)).fetchall()
            finally:
                con.close()
        except sqlite3.Error as e:
            raise Infra(f"task_artifacts unreadable: {e}") from e
        return [(str(s), int(n or 0)) for s, n in rows]

    # ── reading: processes ──────────────────────────────────────────────────────────────────────────────────
    def worker_processes(self, row_id: str) -> list:
        """The worker processes of a row: the engine's descendants whose working directory is the row's scratch dir
        (`nucleo/workers/workdir.for_task` names it after the row id)."""
        import psutil
        try:
            root = psutil.Process(self.eng.process.pid)
            kids = root.children(recursive=True)
        except psutil.Error:
            return []
        out = []
        for k in kids:
            try:
                if str(row_id) in k.cwd():
                    out.append(k)
            except psutil.Error:
                continue
        return out

    # ── waiting ─────────────────────────────────────────────────────────────────────────────────────────────
    def wait_for(self, what, *, timeout: float = 180.0, every: float = 2.0, desc: str = ""):
        """Poll `what()` until it returns something truthy. A timeout returns the last value (the case decides)."""
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = what()
            if last:
                return last
            time.sleep(every)
        return last

    def wait_for_ask(self, since: int, t0: float, *, timeout: float = 210.0) -> list[dict]:
        """The `ask` events after `since`, waiting while a task born after `t0` is still alive and could still ask (a
        worker's first question may take its whole start: the memory envelope alone holds a worker up to 60 s on a
        loaded host). Returns early, empty, when nothing is alive that could ask."""
        deadline = time.time() + timeout
        grace = time.time() + 6.0
        while True:
            asks = self.asks_since(since)
            if asks:
                return asks
            if time.time() > deadline:
                return []
            if time.time() > grace and not [r for r in self.rows_since(t0) if r.get("state") in LIVE_STATES]:
                return []
            time.sleep(3.0)

    def settle_quiet(self, since: int, *, quiet_s: float = 12.0, timeout: float = 90.0) -> None:
        """Wait until no new user-visible line has appeared for `quiet_s` (or `timeout`)."""
        deadline = time.time() + timeout
        last_n, last_t = -1, time.time()
        while time.time() < deadline:
            n = len(self.lines_since(since))
            if n != last_n:
                last_n, last_t = n, time.time()
            elif time.time() - last_t >= quiet_s:
                return
            time.sleep(2.0)


def brief(ev_or_row) -> str:
    """A short, readable rendering of an event or a row for an assertion's detail."""
    if isinstance(ev_or_row, dict) and "payload" in ev_or_row:
        p = payload(ev_or_row)
        return f"#{ev_or_row.get('id')} {ev_or_row.get('kind')}|{ev_or_row.get('label')}|{str(p.get('text') or '')[:80]}"
    if isinstance(ev_or_row, dict):
        return json.dumps({k: ev_or_row.get(k) for k in ("id", "state", "origin", "kind", "title", *ROW_FIELDS)
                           if k in ev_or_row}, ensure_ascii=False, default=str)[:300]
    return str(ev_or_row)[:300]


class Check:
    """Named assertions. The first one that fails is the case's REASON — the battery's red is recorded per name."""

    def __init__(self, case: str):
        self.case = case
        self.results: list[tuple[str, bool, str]] = []
        self.measured: dict = {}

    def that(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, bool(ok), str(detail)[:600]))
        return bool(ok)

    def measure(self, name: str, value) -> None:
        """A number F0 records beside the verdict (sizes, timings) — printed with the result, never asserted here."""
        self.measured[name] = value

    @property
    def first_red(self) -> str:
        return next((n for n, ok, _ in self.results if not ok), "")

    def done(self, *, expected_red: str = "") -> None:
        """Green when every named assertion holds. In BASELINE mode (`expected_red` given — the frozen code, before
        the phase that builds the mechanism) the case passes only when it is red on exactly that assertion: red for
        the right reason. Green there, or red elsewhere, fails — the battery would not be measuring what it says."""
        if self.measured:
            print(f"[{self.case}] measured: {json.dumps(self.measured, ensure_ascii=False, default=str)}")
        red = [(n, d) for n, ok, d in self.results if not ok]
        if expected_red:
            if not red:
                raise AssertionError(f"[{self.case}] BASELINE: expected red on «{expected_red}», but every "
                                     f"assertion held — the case does not measure the missing mechanism")
            if red[0][0] != expected_red:
                raise AssertionError(f"[{self.case}] BASELINE: red on «{red[0][0]}» ({red[0][1]}), expected "
                                     f"«{expected_red}» — red for the wrong reason")
            print(f"[{self.case}] BASELINE red on «{red[0][0]}» as expected: {red[0][1]}")
            return
        if red:
            raise AssertionError(f"[{self.case}] RED on «{red[0][0]}»: {red[0][1]}"
                                 + "".join(f"\n  also red: «{n}»: {d}" for n, d in red[1:]))


def same_task_resumed(before: dict | None, after: dict | None) -> bool:
    """His answer resumed THE task that asked (V2-851 §3, decided by the Architect for the battery): a worker that asked is
    resumed by its own session id; an inline row that asked had no worker session yet — the worker its answer starts is
    born on that SAME row, so the invariant there is the row itself (same id, no new row is asserted apart)."""
    if not before or not after or str(after.get("id")) != str(before.get("id")):
        return False
    if str(before.get("kind") or "") == "inline":
        return True
    return bool(before.get("session_id")) and after.get("session_id") == before.get("session_id")

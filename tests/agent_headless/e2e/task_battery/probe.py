"""Mechanism readers for the task battery (V2-851 §9).

A case asserts MECHANISM, never the judge: (1) the events of the turn's flow (`/api/observability/flow/<trace>`),
(2) the `tasks` rows (`/api/tasks`), (3) the lines the user saw on the wall for that trace — how many and from which
source. The LLM judge, when a case wants one, only grades the prose of the final line.

INFRA is kept apart from FAIL (V2-779 F2): a turn that did not run (timeout, `ok: false`, a dead engine) raises
`Infra`, which the conftest turns into a failure whose message starts with «INFRA:». A battery red is only red for
a reason when it falls on a NAMED assertion (`Check.that`).
"""
from __future__ import annotations

import json
import time
import urllib.parse
from dataclasses import dataclass, field

from tests.platform.sandbox_engine import SandboxEngine


class Infra(RuntimeError):
    """The product was not measured: the engine, the channel or a model did not answer."""


#: The contract the battery reads, named once. F1/F2 make the engine emit these; the frozen code does not, which
#: is why the cases are red there on the assertion that names them.
ROW_FIELDS = ("session_id", "waiting_for", "ask_id", "ask", "deadline", "playbook")
EV_TASK_STATE = "task_state"      # observer kind: {task_id, state, writer} — only `circuit.settle` writes it
EV_ASK = "ask"                    # observer kind: a question shown on screen, {task_id, ask_id, text}
FINAL_STATES = ("done", "failed", "cancelled")


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

    `reply` — the turn's own line (the text channel's wall line, `wall=agent`); `ask` — a task's question on
    screen; `notify` — an out-of-band 🔔 line (`voice/proactive.notify`); `follow_up` — the turn's 🗣 follow-up;
    `notice` — the keyed notice door (`pulse/notices`). A filler is not a line: it is not kept on the wall.
    """
    p = payload(ev)
    kind = str(ev.get("kind") or p.get("kind") or "")
    label = str(ev.get("label") or p.get("label") or "")
    if kind == EV_ASK:
        return "ask"
    if p.get("wall") == "agent" or (p.get("extra") or {}).get("wall") == "agent":
        return "reply"
    if label.startswith("🗣"):
        return "follow_up"
    if label.startswith("🔔"):
        return "notice" if p.get("key") else "notify"
    return ""


@dataclass
class Turn:
    text: str
    res: dict
    trace: str
    t0: float
    t1: float


@dataclass
class Probe:
    """One engine under test plus the reads every case uses."""
    eng: SandboxEngine
    session: str = "battery"
    turns: list = field(default_factory=list)

    # ── driving ─────────────────────────────────────────────────────────────────────────────────────────────
    def say(self, text: str, *, timeout: float = 150.0) -> Turn:
        t0 = time.time()
        try:
            status, res = self.eng.post("/api/flash/say", {"text": text, "session": self.session,
                                                           "execute": True, "ingest": True}, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — a dead channel is INFRA, never a product verdict
            raise Infra(f"say({text!r}) did not answer: {type(e).__name__}: {e}") from e
        if status != 200 or not isinstance(res, dict) or not res.get("ok"):
            raise Infra(f"say({text!r}) → {status} {str(res)[:300]}")
        turn = Turn(text, res, str(res.get("trace") or ""), t0, time.time())
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

    # ── reading ─────────────────────────────────────────────────────────────────────────────────────────────
    def flow(self, trace: str) -> list[dict]:
        status, body = self.eng.get("/api/observability/flow/" + urllib.parse.quote(trace, safe="") + "?limit=2000")
        if status != 200 or not isinstance(body, dict):
            raise Infra(f"flow({trace}) → {status}")
        return list(body.get("events") or [])

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

    def lines(self, trace: str) -> list[tuple[str, dict]]:
        """The user-visible lines of a flow, in order, with their source."""
        return [(src, ev) for ev in self.flow(trace) if (src := line_source(ev))]

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


class Check:
    """Named assertions. The first one that fails is the case's REASON — the battery's red is recorded per name."""

    def __init__(self, case: str):
        self.case = case
        self.results: list[tuple[str, bool, str]] = []

    def that(self, name: str, ok: bool, detail: str = "") -> bool:
        self.results.append((name, bool(ok), str(detail)[:600]))
        return bool(ok)

    @property
    def first_red(self) -> str:
        return next((n for n, ok, _ in self.results if not ok), "")

    def done(self, *, expected_red: str = "") -> None:
        """Green when every named assertion holds. In BASELINE mode (`expected_red` given — the frozen code, before
        the phase that builds the mechanism) the case passes only when it is red on exactly that assertion: red for
        the right reason. Green there, or red elsewhere, fails — the battery would not be measuring what it says."""
        red = [(n, d) for n, ok, d in self.results if not ok]
        if expected_red:
            if not red:
                raise AssertionError(f"[{self.case}] BASELINE: expected red on «{expected_red}», but every "
                                     f"assertion held — the case does not measure the missing mechanism")
            if red[0][0] != expected_red:
                raise AssertionError(f"[{self.case}] BASELINE: red on «{red[0][0]}» ({red[0][1]}), expected "
                                     f"«{expected_red}» — red for the wrong reason")
            return
        if red:
            raise AssertionError(f"[{self.case}] RED on «{red[0][0]}»: {red[0][1]}"
                                 + "".join(f"\n  also red: «{n}»: {d}" for n, d in red[1:]))

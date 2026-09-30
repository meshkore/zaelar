"""The decision bank's harness (V2-776 A1) — one recorded turn in, one DECISION out, judged.

WHAT A CASE MEASURES. Not «did the model answer well» — that is the use cases' job and it is expensive and
flaky on quota. A bank case fixes everything the model would have said (its words, its tool calls) and the
verdicts Jev would have returned, seeds the screen and the memory the turn needs, and asks the engine ONE
question: given all that, what did you DECIDE? The answer is a line of a small grammar (`DECISIONS`) and the
judge compares it to the line the case expects. Every case is deterministic or it is not in the bank.

WHICH CHANNEL. The turn runs through `nucleo.flash.probe.run_turn`, the headless channel the use cases and
the agent-headless corpus already drive: the real prompt, the real fast lanes (action map, presence, small
talk), the real guards and the real decision seam, with `execute=False` so nothing spawns a worker or moves a
card for real. The voice provider is a parallel implementation of the same turn (V2-539's standing lesson);
the bank runs on the channel that can run headless TODAY, and joins the voice adapter the day B2 hands both
channels to `nucleo/turn/`. Until then a case green here says «the shared seam decided right», and the
wiring guards (`tests/agent_headless/unit/actionmap/…`) keep the two channels honest about carrying the
same seam.

ISOLATION. Everything the turn touches is redirected before the first import that would cache a path:
`ZAELAR_WORKSPACE`, `ZAELAR_DB`, the widget store's data dir, the observer's log dir, the language, and the
Jev switch (off — a verdict comes from the case or from nowhere). The operator's database, agenda and
credentials are never on the path. Usable from pytest and from the CLI runner alike, so it patches by hand
and restores in `finally`, which is what a disarm harness owes the product (2026-09-14, V2-669).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1]
CASES_DIR = HERE / "cases"

LANGS = ("es", "en")

# ── the grammar of a decision ─────────────────────────────────────────────────────────────────────────────
# One line per turn. `talk` is the model's own words and nothing else; `ask` is a clarifying question the
# ENGINE decided to ask (not a question the model happened to write); the rest name a mechanism and its target.
DECISIONS = re.compile(
    r"^(talk|ask|escalate|search|listings|close all|minimize|unfullscreen|fullscreen [a-z0-9_-]+"
    r"|show [a-z0-9_-]+|close [a-z0-9_-]+|read [a-z0-9_-]+|panel:[a-z_]+"
    r"|data-op [a-z0-9_-]+:[a-z_]+|music [a-z_]+)$")

# What `forbid` may name. Each one is a question the judge knows how to ask of an outcome.
FORBIDS = ("worker", "search", "show", "close", "data-op", "second-card", "model", "ask")

CASE_KEYS = {"id", "lang", "phrase", "source", "screen", "memory", "model", "brief", "expect", "also",
             "forbid", "open", "note", "file"}


def load_cases(pattern: str = "*.json") -> list[dict]:
    """Every case in `cases/`, validated, ids unique across files."""
    out: list[dict] = []
    seen: set[str] = set()
    for path in sorted(CASES_DIR.glob(pattern)):
        for raw in json.loads(path.read_text(encoding="utf-8")):
            raw = dict(raw)
            raw.setdefault("file", path.name)
            validate(raw)
            if raw["id"] in seen:
                raise ValueError(f"{path.name}: duplicate case id {raw['id']!r}")
            seen.add(raw["id"])
            out.append(raw)
    return out


def validate(case: dict) -> None:
    unknown = set(case) - CASE_KEYS
    if unknown:
        raise ValueError(f"{case.get('id')}: unknown keys {sorted(unknown)}")
    for key in ("id", "lang", "phrase", "screen", "expect", "source"):
        if key not in case:
            raise ValueError(f"{case.get('id')}: missing {key!r}")
    if case["lang"] not in LANGS:
        raise ValueError(f"{case['id']}: lang must be one of {LANGS}")
    if not DECISIONS.match(case["expect"]):
        raise ValueError(f"{case['id']}: expect {case['expect']!r} is not in the decision grammar")
    for extra in case.get("also", ()):
        if not DECISIONS.match(extra):
            raise ValueError(f"{case['id']}: also {extra!r} is not in the decision grammar")
    for f in case.get("forbid", ()):
        if f not in FORBIDS:
            raise ValueError(f"{case['id']}: forbid {f!r} is not one of {FORBIDS}")
    if not isinstance(case["screen"], dict) or set(case["screen"]) - {"open"}:
        raise ValueError(f"{case['id']}: screen must be {{'open': [...]}}")
    model = case.get("model")
    if model is not None:
        if set(model) - {"say", "tools"}:
            raise ValueError(f"{case['id']}: model must be {{say, tools}}")
        for t in model.get("tools", ()):
            if set(t) != {"name", "args"}:
                raise ValueError(f"{case['id']}: a recorded tool call is {{name, args}}")
    for key, verdict in (case.get("brief") or {}).items():
        if not (isinstance(verdict, list) and len(verdict) == 2 and isinstance(verdict[1], (int, float))):
            raise ValueError(f"{case['id']}: brief[{key!r}] must be [choice, confidence]")
    memory = case.get("memory") or {}
    if set(memory) - {"agenda", "state"}:
        raise ValueError(f"{case['id']}: memory fixtures are 'agenda' and 'state'")


# ── the outcome and its judge ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Outcome:
    case_id: str
    decision: str = ""
    also: list[str] = field(default_factory=list)   # secondary mutations the turn also produced
    action: str = ""                                # the probe's raw action string
    tool_calls: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    reply: str = ""
    model_consulted: bool = False
    cards_touched: set = field(default_factory=set)
    events: list = field(default_factory=list)
    error: str = ""
    ms: float = 0.0

    @property
    def all_decisions(self) -> list[str]:
        return [self.decision, *self.also]

    def failures(self, case: dict) -> list[str]:
        """Why this outcome does not satisfy the case. Empty means the case is green."""
        why: list[str] = []
        if self.error:
            why.append(f"turn failed: {self.error}")
        if self.decision != case["expect"]:
            why.append(f"decided {self.decision!r}, expected {case['expect']!r}")
        for extra in case.get("also", ()):
            if extra not in self.also:
                why.append(f"expected also {extra!r}, observed {self.also}")
        if case.get("model") is None and self.model_consulted:
            why.append("the model was consulted for a turn a deterministic lane owns")
        for f in case.get("forbid", ()):
            hit = {
                "worker": "escalate" in self.all_decisions,
                "search": "search" in self.all_decisions,
                "show": any(d.startswith("show ") for d in self.all_decisions),
                "close": any(d.startswith("close") for d in self.all_decisions),
                "data-op": any(d.startswith("data-op ") for d in self.all_decisions),
                "second-card": len(self.cards_touched) > 1,
                "model": self.model_consulted,
                "ask": "ask" in self.all_decisions,
            }[f]
            if hit:
                why.append(f"forbidden {f!r} happened ({self.all_decisions})")
        return why

    def as_dict(self) -> dict:
        return {"id": self.case_id, "decision": self.decision, "also": self.also, "action": self.action,
                "tool_calls": self.tool_calls, "tags": self.tags, "reply": self.reply[:200],
                "model_consulted": self.model_consulted, "cards": sorted(self.cards_touched),
                "error": self.error, "ms": round(self.ms, 1)}


def _widget_data_target(tool_calls: list) -> tuple[str, str]:
    for t in tool_calls:
        if t.get("name") == "widget_data":
            a = t.get("args") or {}
            return str(a.get("widget_id") or "").strip().lower(), str(a.get("action") or "").strip()
    return "", ""


def decision_of(res: dict, tool_calls: list) -> str:
    """Map the probe's action vocabulary onto the bank's grammar. Unknown actions come back verbatim, so a
    new mechanism shows up as a red case with its own name rather than as a silent `talk`."""
    a = str(res.get("action") or "")
    if a == "chat":
        return "talk"
    if a == "clarify":
        return "ask"
    if a == "canvas:close":
        return "close all"
    if a == "canvas:minimize" or a.startswith("canvas:minimize:"):
        return "minimize"
    if a.startswith("canvas:unfullscreen"):
        return "unfullscreen"
    if a.startswith("canvas:fullscreen:"):
        return "fullscreen " + a.split(":", 2)[2]
    if a.startswith("canvas:show:"):
        return "show " + a.split(":", 2)[2]
    if a.startswith("canvas:close:"):
        return "close " + a.split(":", 2)[2]
    if a.startswith("widget_data:"):
        _, wid, act = a.split(":", 2)
        return f"data-op {wid}:{act}"
    if a == "widget_data":
        wid, act = _widget_data_target(tool_calls)
        return f"data-op {wid}:{act}"
    if a == "read_widget":
        wid = next((str((t.get("args") or {}).get("widget_id") or "") for t in tool_calls
                    if t.get("name") == "read_widget"), "")
        return f"read {wid.strip().lower()}"
    if a == "music":
        act = next((str((t.get("args") or {}).get("action") or "play") for t in tool_calls
                    if t.get("name") == "play_music"), "play")
        return f"music {act}"
    if a in ("escalate", "search", "listings"):
        return a
    if a.startswith("panel:"):
        return a
    return a


def _secondary(res: dict, tool_calls: list, primary: str) -> tuple[list[str], set[str]]:
    """Everything else the turn did: the canvas tags and the heavy tools, minus the primary decision."""
    also: list[str] = []
    cards: set[str] = set()
    for t in res.get("tags") or []:
        act = t.get("action")
        wid = str((t.get("extra") or {}).get("id") or "").strip().lower()
        if act == "show" and wid:
            also.append(f"show {wid}")
            cards.add(wid)
        elif act == "close":
            also.append(f"close {wid}" if wid else "close all")
            if wid:
                cards.add(wid)
    names = [t.get("name") for t in tool_calls]
    if "escalate_to_slowbrain" in names:
        also.append("escalate")
    if "web_search" in names:
        also.append("search")
    if primary.startswith(("show ", "close ", "data-op ", "read ")):
        target = primary.split(" ", 1)[1].split(":", 1)[0]
        cards.add(target)
    also = [d for d in dict.fromkeys(also) if d != primary]
    return also, cards


# ── the recorded model and the recorded brief ─────────────────────────────────────────────────────────────
class RecordedModel:
    """Stands in for `FastClient`: yields the recorded words, fires the recorded tool calls, and records
    that it was consulted at all. A case without a `model` block still gets an instance — one that says
    nothing — so a lane that should have skipped the model is caught by `model_consulted`, not by a crash."""
    consulted = False
    say: str = ""
    tools: list = []

    @classmethod
    def load(cls, model: dict | None) -> None:
        cls.consulted = False
        cls.say = str((model or {}).get("say") or "")
        cls.tools = list((model or {}).get("tools") or [])

    async def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None, **_kw):
        RecordedModel.consulted = True
        if RecordedModel.say:
            yield RecordedModel.say
        for t in RecordedModel.tools:
            if on_tool_call:
                on_tool_call(t["name"], dict(t.get("args") or {}))

    async def complete(self, messages, spec=None, *args, **_kw):
        # A second pass (act repair, widget read, card commission) asks the model again. The bank answers
        # NOTHING on purpose: what is measured is the decision the engine takes with what it already has.
        RecordedModel.consulted = True
        return ""

    def describe(self, spec=None) -> str:
        return "bank/recorded"


def brief_handle(case: dict):
    """A ready Jev brief with the case's verdicts, in the exact shape `nucleo.jev.peek/read` consume."""
    verdicts = case.get("brief")
    if not verdicts:
        return None
    ev = threading.Event()
    ev.set()
    result = {key: {"choice": choice, "confidence": float(conf), "probs": {choice: float(conf)}}
              for key, (choice, conf) in verdicts.items()}
    return {"event": ev, "result": result, "_call_id": f"bank:{case['id']}", "turn_id": case["id"],
            "open_ids": [str(w) for w in case["screen"].get("open") or []]}


# ── isolation ─────────────────────────────────────────────────────────────────────────────────────────────
_ENV_KEYS = ("ZAELAR_WORKSPACE", "ZAELAR_DB", "ZAELAR_JEV", "ZAELAR_EMBED_BACKEND", "MEMORY_RERANK",
             "ZAELAR_LANGUAGE_GATE", "ZAELAR_LANGUAGE", "ZAELAR_LOG_DIR", "ZAELAR_TEST_EMBED_CLOUD")


class Isolated:
    """Everything a bank turn can reach, redirected to a temp dir, and put back afterwards."""

    def __init__(self, lang: str):
        self.lang = lang
        self.tmp = ""
        self._env: dict[str, str | None] = {}
        self._patched: list[tuple[Any, str, Any]] = []

    def _set(self, obj, name, value):
        self._patched.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def __enter__(self) -> "Isolated":
        self.tmp = tempfile.mkdtemp(prefix="zaelar-brain-")
        for k in _ENV_KEYS:
            self._env[k] = os.environ.get(k)
        os.environ.update({
            "ZAELAR_WORKSPACE": os.path.join(self.tmp, "ws"),
            "ZAELAR_DB": os.path.join(self.tmp, "zaelar.db"),
            "ZAELAR_JEV": "0",
            "ZAELAR_EMBED_BACKEND": "hash",
            "MEMORY_RERANK": "off",
            "ZAELAR_LANGUAGE_GATE": "0",
            "ZAELAR_LANGUAGE": self.lang,
            "ZAELAR_LOG_DIR": os.path.join(self.tmp, "logs"),
        })
        os.environ.pop("ZAELAR_TEST_EMBED_CLOUD", None)
        os.makedirs(os.environ["ZAELAR_WORKSPACE"], exist_ok=True)
        try:
            from memory import db as memdb, embeddings as mememb
            memdb.reset_db()
            memdb.get_db()
            mememb.reset()
            from nucleo import runstate
            runstate._state.update({"value": runstate.RUNNING, "at": 0.0, "src": "bank"})
            from widgets import store
            data_dir = os.path.join(self.tmp, "widgets")
            os.makedirs(data_dir, exist_ok=True)
            self._set(store, "DATA_DIR", data_dir)
            from nucleo.actionmap import store as amstore
            amstore.invalidate()
            from nucleo import scheduler
            self._set(scheduler, "create", lambda prompt, stamp, name="": {"ok": True, "id": "bank-job"})
            self._set(scheduler, "cancel", lambda ref: None)
            from nucleo.flash import fast_client, turn_brief, show_target, probe
            self._set(fast_client, "FastClient", RecordedModel)
            self._set(turn_brief, "ask_for_turn", lambda *a, **k: self._handle)
            self._set(turn_brief, "ask", lambda *a, **k: self._handle)
            self._set(show_target, "ask_canvas_async", lambda *a, **k: None)
            probe._SESSIONS.clear()
        except Exception:
            self.__exit__(None, None, None)
            raise
        self._handle = None
        return self

    def __exit__(self, *_exc) -> None:
        try:
            from nucleo.flash import probe
            probe._SESSIONS.clear()
        except Exception:  # noqa: BLE001
            pass
        for obj, name, old in reversed(self._patched):
            setattr(obj, name, old)
        self._patched.clear()
        try:
            from memory import db as memdb
            memdb.reset_db()
        except Exception:  # noqa: BLE001
            pass
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            from nucleo.actionmap import store as amstore
            amstore.invalidate()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── per-case seeding ──
    def seed(self, case: dict) -> None:
        from memory import api as memapi
        memapi.set_state({"open_widgets": [str(w) for w in case["screen"].get("open") or []]})
        memory = case.get("memory") or {}
        if memory.get("state"):
            memapi.set_state(dict(memory["state"]))
        for row in memory.get("agenda") or []:
            from widgets.agenda import data as agenda
            day = _relative_day(str(row.get("day", "+0")))
            payload = {"title": row["title"], "date": day.isoformat(),
                       "startTime": row.get("start", "10:00"), "endTime": row.get("end", "")}
            res = agenda.apply_action("add_meeting", {k: v for k, v in payload.items() if v})
            if res.get("ok") is False:
                raise RuntimeError(f"{case['id']}: agenda fixture refused: {res}")
        RecordedModel.load(case.get("model"))
        self._handle = brief_handle(case)


def _relative_day(spec: str) -> _dt.date:
    """`+1` = tomorrow, `+0` = today, or an ISO date — fixtures never carry a date that goes stale."""
    if spec.startswith(("+", "-")):
        return _dt.date.today() + _dt.timedelta(days=int(spec))
    return _dt.date.fromisoformat(spec)


# ── run ───────────────────────────────────────────────────────────────────────────────────────────────────
def run_case(case: dict, *, timeout_s: float = 60.0) -> Outcome:
    """One case, fully isolated, through the headless turn. Never raises for a product failure: the
    outcome carries it, so a run over the whole bank reports every red instead of stopping at the first."""
    import time as _time
    out = Outcome(case_id=case["id"])
    with Isolated(case["lang"]) as iso:
        iso.seed(case)
        from nucleo.flash import probe
        from voice import observer
        n0 = len(observer._events)
        t0 = _time.time()
        sid = f"bank:{case['id']}"
        try:
            res = asyncio.run(asyncio.wait_for(
                probe.run_turn(case["phrase"], sid=sid, ingest=False, execute=False), timeout_s))
        except Exception as e:  # noqa: BLE001
            out.error = f"{type(e).__name__}: {e}"[:300]
            res = {}
        finally:
            probe._SESSIONS.pop(sid, None)
        out.ms = (_time.time() - t0) * 1000
        out.events = [dict(e) for e in observer._events[n0:]]
        if res.get("ok") is False and not out.error:
            out.error = str(res.get("error") or "not ok")
        out.tool_calls = list(res.get("tool_calls") or [])
        out.tags = list(res.get("tags") or [])
        out.action = str(res.get("action") or "")
        reply = res.get("reply")
        out.reply = " ".join(reply) if isinstance(reply, list) else str(reply or "")
        out.model_consulted = RecordedModel.consulted
        out.decision = decision_of(res, out.tool_calls) if res else ""
        out.also, out.cards_touched = _secondary(res, out.tool_calls, out.decision)
    return out

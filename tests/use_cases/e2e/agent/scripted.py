"""A SCRIPTED use case: fixed loose sentences, each one checked against the widget's real state (V2-770).

The persona-driven cases measure how the agent handles a request the way a person gives it, and a judge scores
the round. That cannot prove a CATALOGUE of operations: a persona wanders, and a judge reads a transcript in
which «Hecho.» over an untouched agenda looks exactly like «Hecho.» over a done one. Measured live on the
agenda (2026-09-25): 3 of 13 everyday operations landed while almost every reply said it had.

So this driver says a fixed line per step — imprecise on purpose, the way people talk — and after the reply
reads the widget through the same HTTP door the rest of the harness uses (`probe_client.widget_data`) and
asks a named CHECK whether the operation really happened. A reply that is a question (a confirmation, a «which
one?») gets the answer a person would give, once, before the check is read again.

Same interface as `driver.Driver` (`opening` / `hears` / `reply` / `done`), so a scripted case runs through
the whole harness — sandbox, report, scoreboard, Observatory — and `status._state` FAILS it when any check is
red, whatever the judge scored: the checks are the mechanism, and the mechanism outranks the text.

Checks are NAMED, not lambdas, so a scenario stays plain data; dates are computed at check time from today, so
a case never expires.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

from . import probe_client


@dataclass(frozen=True)
class Step:
    say: str
    check: str = ""            # a key of CHECKS; "" = a step that is observed, not graded
    open_card: str = ""        # after this step the desktop reports this card open (a browser would)


def _today() -> dt.date:
    return dt.date.today()


def _next(wd: int, after: dt.date | None = None) -> dt.date:
    after = after or _today()
    return after + dt.timedelta(days=(wd - after.weekday()) % 7 or 7)


def _meetings(d: dict) -> list[dict]:
    return [m for m in (d.get("meetings") or []) if isinstance(m, dict)]


def _named(d: dict, *words: str) -> list[dict]:
    return [m for m in _meetings(d) if all(w.lower() in str(m.get("title") or "").lower() for w in words)]


def _series(d: dict, word: str) -> dict | None:
    return next((m for m in _named(d, word) if isinstance(m.get("repeat"), dict)), None)


def _view(d: dict) -> dict:
    return d.get("view") if isinstance(d.get("view"), dict) else {}


def _dentist_new(d):
    return any(m.get("date") == _next(3).isoformat() and m.get("startTime") == "10:00"
               for m in _named(d, "dent"))


def _piano_series(d):
    from .dates import end_of_month_ahead
    s = _series(d, "piano")
    return bool(s and s["repeat"].get("days") == [1] and s.get("startTime") == "17:00"
                and s["repeat"].get("until") == end_of_month_ahead(3).isoformat())


def _card_open_dentist(d):
    return "dent" in str((_view(d).get("open") or {}).get("title") or "").lower()


def _card_closed(d):
    return _view(d).get("close") is True


def _renamed(d):
    return bool(_named(d, "ruiz")) and not any(str(m.get("title") or "").strip().lower() in ("dentista", "dentist")
                                               for m in _meetings(d))


def _notes(d):
    return any(("radiograf" in str(m.get("notes") or "").lower() or "x-ray" in str(m.get("notes") or "").lower()
                or "xray" in str(m.get("notes") or "").lower()) for m in _named(d, "ruiz"))


def _new_hour(d):
    return any(m.get("startTime") == "11:30" for m in _named(d, "ruiz"))


def _new_end(d):
    return any(m.get("startTime") == "11:30" and m.get("endTime") == "13:00" for m in _named(d, "ruiz"))


def _one_day_moved(d):
    tue = _next(1)
    s = _series(d, "piano")
    return bool(s and tue.isoformat() in (s["repeat"].get("skip") or [])
                and any(m.get("date") == (tue + dt.timedelta(days=1)).isoformat()
                        for m in _named(d, "piano") if not isinstance(m.get("repeat"), dict)))


def _one_day_skipped(d):
    s = _series(d, "piano")
    return bool(s and (_next(1) + dt.timedelta(weeks=1)).isoformat() in (s["repeat"].get("skip") or []))


def _cut_from_a_month(d):
    from .dates import month_ahead
    s = _series(d, "piano")
    return bool(s and s["repeat"].get("until") == (month_ahead(2) - dt.timedelta(days=1)).isoformat())


def _cancelled(d):
    return not _named(d, "ruiz")


def _series_gone(d):
    return not _named(d, "piano")


CHECKS = {
    "agenda.dentist_next_thursday_10": _dentist_new,
    "agenda.piano_every_tuesday_17_for_three_months": _piano_series,
    "agenda.card_open_on_dentist": _card_open_dentist,
    "agenda.card_closed": _card_closed,
    "agenda.renamed_to_ruiz": _renamed,
    "agenda.notes_xrays": _notes,
    "agenda.starts_11_30": _new_hour,
    "agenda.ends_13_00": _new_end,
    "agenda.one_tuesday_moved_to_wednesday": _one_day_moved,
    "agenda.one_tuesday_skipped": _one_day_skipped,
    "agenda.series_ends_before_month_in_2": _cut_from_a_month,
    "agenda.ruiz_cancelled": _cancelled,
    "agenda.whole_series_gone": _series_gone,
}

# ── V2-771: a LIST handed over in one message — graded on memory, agenda and the task board ─────────────
# A check can read another source than the agenda: `(source, fn)` in CHECKS. The sources are the same HTTP
# doors the rest of the harness reads (`probe_client`), never the sandbox's files.
def _board() -> dict:
    rows = []
    for scope in ("live", "done"):
        try:
            got = probe_client._get(f"/api/tasks?scope={scope}&all=1")
        except Exception:  # noqa: BLE001
            return None
        rows += [r for r in (got.get("tasks") or got.get("rows") or []) if isinstance(r, dict)] \
            if isinstance(got, dict) else []
    lists = []
    for r in rows:
        if r.get("kind") == "lista":
            try:
                lists.append(probe_client._get(f"/api/lists/{r['id']}"))
            except Exception:  # noqa: BLE001
                pass
    return {"rows": rows, "lists": [x for x in lists if isinstance(x, dict) and x.get("ok")]}


def _memory() -> dict | None:
    try:
        return probe_client.memory_map()
    except Exception:  # noqa: BLE001
        return None


SOURCES = {"agenda": lambda: probe_client.widget_data("agenda"), "memory": _memory, "tasks": _board}


def _mem_text(d) -> str:
    import json as _json
    return _json.dumps(d, ensure_ascii=False).lower()


def _has_all(*words):
    return lambda d: all(w in _mem_text(d) for w in words)


def _has_any_each(*groups):
    return lambda d: all(any(w in _mem_text(d) for w in g) for g in groups)


def _list_closed(d):
    return bool(d and any(str((x.get("list") or {}).get("state")) in ("done", "failed") for x in d["lists"]))


def _list_clean(d):
    return bool(d and any((x.get("summary") or {}).get("n", 0) >= 2
                          and not (x.get("summary") or {}).get("failed")
                          and not (x.get("summary") or {}).get("needs_you")
                          and str((x.get("list") or {}).get("state")) == "done" for x in d["lists"]))


def _at(d, date, start, *words):
    return [m for m in _meetings(d) if m.get("date") == date and (not start or m.get("startTime") == start)
            and all(w in str(m.get("title") or "").lower() for w in words)]


def _demo():
    from .dates import demo_dates
    return {k: v.isoformat() for k, v in demo_dates().items()}


def _demo_events(d):
    D = _demo()
    want = [(D["mon"], "09:00", ("weekly",)), (D["mon"], "11:00", ("product",)), (D["mon"], "15:00", ("meshcore",)),
            (D["tue"], "10:00", ("accountant",)), (D["thu"], "13:00", ("laura",)), (D["vet"], "16:00", ("pixel",))]
    return all(_at(d, *w[:2], *w[2]) for w in want)


def _demo_span(d):
    """«Anna vacation» covers every day of the holiday, not a weekly series and not its first day only."""
    from widgets.agenda import recur
    D = _demo()
    n = (dt.date.fromisoformat(D["vac_to"]) - dt.date.fromisoformat(D["vac_from"])).days + 1
    for m in _named(d, "anna"):
        if m.get("date") == D["vac_from"]:
            days = recur.occurrences(m, D["vac_from"], D["vac_to"]) if isinstance(m.get("repeat"), dict) else []
            if len(days) == n or m.get("endDate") == D["vac_to"]:
                return True
    return False


def _demo_no_twins(d):
    """The vet visit is in the message twice (the pet section and the calendar section): ONE entry."""
    return len(_at(d, _demo()["vet"], "", "pixel")) == 1


def _workers_two_at_a_time(d):
    """No instant with three workers of the list running at once (V2-771: the pool is two)."""
    spans = [(int(r.get("started_at") or 0), int(r.get("finished_at") or 0) or 10 ** 12)
             for r in (d or {}).get("rows", []) if r.get("kind") not in ("lista",) and r.get("started_at")
             and str(r.get("origin") or "") not in ("lista", "cron", "agenda")]
    return bool(spans) and max(sum(1 for a, b in spans if a <= t < b) for t, _ in spans) <= 2


CHECKS.update({
    "lists.closed": ("tasks", _list_closed),
    "lists.closed_clean": ("tasks", _list_clean),
    "demo.assistant_is_johnny": ("memory", _has_all("johnny")),
    "demo.profile": ("memory", _has_any_each(("richard",), ("los angeles", "los ángeles"), ("meshcore",),
                                             ("england", "inglaterra"))),
    "demo.interests": ("memory", _has_any_each(("formula 1", "fórmula 1", "f1"), ("basketball", "baloncesto"),
                                               ("hiking", "senderismo"))),
    "demo.family": ("memory", _has_all("anna")),
    "demo.friends": ("memory", _has_all("oscar", "san mateo", "laura", "telegram")),
    "demo.car": ("memory", _has_all("tesla", "8abc123")),
    "demo.motorbike": ("memory", _has_all("ducati", "25d6789")),
    "demo.pet": ("memory", _has_all("pixel")),
    "demo.events": _demo_events,
    "demo.anna_vacation_span": _demo_span,
    "demo.vet_once": _demo_no_twins,
    "errands.dinner_with_pedro": lambda d: bool(_named(d, "pedro")),
    "errands.pedro_allergy": ("memory", _has_any_each(("marisco", "shellfish"))),
    "errands.two_workers_at_a_time": ("tasks", _workers_two_at_a_time),
})

#: How long a check keeps re-reading before it is red. A list takes minutes, not a reply's second.
WAITS = {"lists.closed": 1800.0, "lists.closed_clean": 60.0}

#: What a person answers to a question back — once per step, only while the check is still red.
_YES = {"es": "Sí, adelante.", "us": "Yes, go ahead."}


def check(name: str, widget: str = "agenda", *, wait_s: float | None = None,
          poll_s: float = 1.5) -> tuple[bool | None, str]:
    """(passed, why). A write may land a moment after the reply, so a red is re-read for `wait_s`. `None`
    means the source could not be read — never a pass, and never silently a product fail either."""
    fn = CHECKS.get(name)
    if fn is None:
        return False, f"unknown check «{name}»"
    source = widget
    if isinstance(fn, tuple):
        source, fn = fn
    read = SOURCES.get(source) or (lambda: probe_client.widget_data(source))
    wait_s = WAITS.get(name, 12.0) if wait_s is None else wait_s
    if wait_s > 60:
        poll_s = max(poll_s, 10.0)
    deadline = time.time() + wait_s
    while True:
        data = read()
        if data is None:
            ok, why = None, f"the {source} could not be read"
        else:
            try:
                ok, why = bool(fn(data)), ""
            except Exception as e:  # noqa: BLE001 — a check that crashes is a red, and says why
                ok, why = False, f"check raised {type(e).__name__}: {e}"
        if ok or time.time() >= deadline:
            return ok, why
        time.sleep(poll_s)


class ScriptedDriver:
    """`driver.Driver`'s interface, speaking a fixed script and grading each step against the widget."""

    def __init__(self, scenario, **_kw) -> None:
        self.scenario = scenario
        from . import dates as _dates                       # «el martes 6» is computed on every run, never written
        self.steps: list[Step] = [Step(_dates.resolve(st.say), st.check, st.open_card)
                                  for st in (s if isinstance(s, Step) else Step(*s) for s in (scenario.script or ()))]
        self.locale = getattr(scenario, "locale", "es") or "es"
        self.i = 0                 # index of the step whose reply we are waiting for
        self.turns = 0
        self.done = False
        self.role_flips = 0
        self.empty_retries = 0
        self.answered = False      # this step already had its one «sí»
        self.last_reply = ""
        self.results: list[dict] = []

    def opening(self) -> str:
        self.turns += 1
        return self.steps[0].say if self.steps else ""

    def hears(self, zaelar_text: str) -> None:
        self.last_reply = zaelar_text or ""

    def _close_step(self, ok, why: str) -> None:
        st = self.steps[self.i]
        # V2-771 — a step may carry several checks («a,b,c»): one result row each, so a report says WHICH
        # part of a list landed. The first was already read (and waited for) by the caller.
        names = [c.strip() for c in (st.check or "").split(",") if c.strip()] or [""]
        for n, name in enumerate(names):
            c_ok, c_why = (ok, why) if n == 0 else check(name)
            self.results.append({"step": self.i + 1, "said": st.say[:300], "check": name, "ok": c_ok,
                                 "why": c_why, "reply": self.last_reply[:400], "answered_yes": self.answered})
            mark = "✅" if c_ok else ("·" if c_ok is None and not name else "❌")
            print(f"    {mark} [{name or 'observed'}]{(' — ' + c_why) if c_why else ''}")
        if st.open_card:
            try:
                probe_client._post("/api/canvas/state", {"open": [st.open_card]})
            except Exception:  # noqa: BLE001
                pass
        self.i += 1
        self.answered = False

    def reply(self, *, nudge: str = "") -> str:  # noqa: ARG002 — a script takes no nudges
        st = self.steps[self.i]
        first = (st.check or "").split(",")[0].strip()
        ok, why = check(first) if first else (None, "")
        if st.check and not ok and not self.answered and self.last_reply.rstrip().endswith("?"):
            self.answered = True
            self.turns += 1
            return _YES.get(self.locale, _YES["es"])
        self._close_step(ok, why)
        if self.i >= len(self.steps):
            self.done = True
            return ""
        self.turns += 1
        return self.steps[self.i].say

    def finish(self) -> list[dict]:
        """Grade the step still pending when the conversation loop ended (the last one), and return all."""
        if self.i < len(self.steps):
            st = self.steps[self.i]
            first = (st.check or "").split(",")[0].strip()
            ok, why = check(first) if first else (None, "")
            self._close_step(ok, why)
        return self.results


def failed(results: list[dict]) -> list[dict]:
    """The graded steps that did not land (a `None` — could not read — counts: nothing was proven)."""
    return [r for r in results or [] if r.get("check") and r.get("ok") is not True]

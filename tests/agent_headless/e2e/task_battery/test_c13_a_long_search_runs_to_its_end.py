"""C13 — a long search runs to its end (V2-852): the operator's own request from his first live session on the task
engine, replayed on a sandbox of the case's own, plus the same shape in another domain.

What he saw (flows `T8·00fd` and its relaunch `T19·6012`): the browser asked his OK for a filter chip, a second results
card was shown by a non-owner, the spec «results.empty = false» was attested met at the first appended row, the pulse
asked «stop or keep going?» at 15 minutes and cancelled the task «ran out of time», and lines about the task carried
the dispatcher's number instead of the row's. Every assertion here reads the ROW, the events and the wall lines —
never the reply's words:

  (1) one `tasks` row and one worker session;
  (2) no question to the user for a navigation or filter click (no `ask`, no browser `gate_ask`, no notice of kind
      ask, the row never waits on him);
  (3) no time budget: no `worker.budget_*` on the bus, no pulse timeout line, no cancellation (nobody stopped it);
  (4) the row keeps reporting progress while it runs;
  (5) one presentation card for the task, no non-owner show;
  (6) the row's end state is the request's, not a card-presence spec (`probe.presence_only`);
  (7) the row is settled exactly once, by `settle`, `done`, after the worker's last act — and «met» is attested only
      then;
  (8) after the reply line only mouths bound to the row speak, each line once.

There is no time limit inside the product (R2). The case's own wait (`ZAELAR_C13_WAIT_S`, default 90 min) is infra: a
row still live past it is reported INFRA, with the named assertions measured so far printed beside it.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from .probe import (EV_ASK, FINAL_STATES, LIVE_STATES, WAITING_USER, WRITER_SETTLE, Infra, bridge_acts, brief,
                    line_source, payload, presence_only)
from .script import LONG_SEARCH, LONG_SEARCH_LANG, visible_rows_since, wait_worker

WAIT_S = float(os.getenv("ZAELAR_C13_WAIT_S", "5400") or 5400)
POLL_S = 10.0
#: The longest a running row may go without a new progress note or report. The pulse already DEMANDS a report after
#: 90 s unreported (`📋 informe de estado exigido`); this is three times that plus the poll — generous on purpose.
PROGRESS_GAP_S = 300.0
#: A row parked on HIS answer in this case is already the verdict — nobody here answers, and the row's own deadline is
#: days away. Past this grace the case stops following and reads what it has (it is red on (2), never INFRA).
ASKED_GRACE_S = 120.0


def _pulse_timeout_prefix() -> str:
    """The pulse's timeout-notice key prefix while the product still has one (V2-852 T06 removes the budget)."""
    try:
        from nucleo.pulse import signals
        return str(getattr(signals, "_TIMEOUT_KEY", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _follow(p, row_id: str, t_start: float) -> dict:
    """Poll the row until it ends (or the case's own wait runs out). Records what only a poll can see: every state,
    session id and wait it went through, and when its progress last moved."""
    seen = {"states": [], "sessions": set(), "waits": set(), "moves": [t_start], "notes": set(), "final": None,
            "timed_out": False, "parked_on_him": False}
    asked_since = None
    last_sig = None
    deadline = time.time() + WAIT_S
    while True:
        row = p.row(row_id)
        if row is None:
            seen["final"] = None
            break
        st = str(row.get("state") or "")
        if not seen["states"] or seen["states"][-1] != st:
            seen["states"].append(st)
        if row.get("session_id"):
            seen["sessions"].add(str(row["session_id"]))
        if row.get("waiting_for"):
            seen["waits"].add(str(row["waiting_for"]))
        prog = row.get("progress") or {}
        if isinstance(prog, str):
            try:
                prog = json.loads(prog)
            except json.JSONDecodeError:
                prog = {"note": prog}
        note = str((prog or {}).get("note") or "") if isinstance(prog, dict) else ""
        if note:
            seen["notes"].add(note)
        sig = (note, row.get("reported_at"), (prog or {}).get("done") if isinstance(prog, dict) else None,
               row.get("phase"))
        if sig != last_sig:
            last_sig = sig
            seen["moves"].append(time.time())
        if st in FINAL_STATES:
            seen["final"] = row
            break
        asked = st == "waiting" and str(row.get("waiting_for") or "") == WAITING_USER
        asked_since = (asked_since or time.time()) if asked else None
        if asked_since and time.time() - asked_since > ASKED_GRACE_S:
            seen["parked_on_him"] = True
            seen["final"] = row
            break
        if time.time() > deadline:
            seen["timed_out"] = True
            seen["final"] = row
            break
        time.sleep(POLL_S)
    seen["t_end"] = time.time()
    return seen


@pytest.mark.parametrize("variant", ["glc", "flat"])
def test_c13_a_long_search_runs_to_its_end(fresh_for, check, variant, rep):
    p = fresh_for(LONG_SEARCH_LANG)
    turn = p.say(LONG_SEARCH[variant], timeout=300.0)
    t_start = time.time()
    ws = wait_worker(p, turn.since)
    rows = visible_rows_since(p, turn.t0)
    if not rows:
        raise Infra("the request opened no row — nothing to follow")
    row_id = str(rows[0].get("id") or "")
    seen = _follow(p, row_id, t_start)
    p.settle_quiet(turn.since, quiet_s=20.0, timeout=120.0)

    evs = p.events_since(turn.since)
    final = seen["final"] or {}
    rows = visible_rows_since(p, turn.t0)
    check.measure("row", brief(final))
    check.measure("ran_s", round(seen["t_end"] - t_start))
    check.measure("states", seen["states"])
    check.measure("worker_started", bool(ws))
    check.measure("parked_on_his_answer", seen["parked_on_him"])

    # (1) one row, one worker session
    starts = [e for e in evs if str(e.get("kind") or "") == "worker_start"]
    check.that("one row and one worker session",
               len(rows) == 1 and len(starts) == 1 and len(seen["sessions"]) <= 1,
               {"rows": [brief(r) for r in rows], "worker_starts": len(starts), "sessions": sorted(seen["sessions"])})

    # (2) no question for a navigation/filter click
    asks = [e for e in evs if str(e.get("kind") or "") == EV_ASK
            or (str(e.get("kind") or "") == "widget" and str(e.get("label") or "") == "gate_ask")
            or (str(e.get("kind") or "") == "notice" and payload(e).get("extra_kind") == "ask")]
    check.that("no question for a click", not asks and WAITING_USER not in seen["waits"],
               {"asks": [brief(e) for e in asks][:6], "waits": sorted(seen["waits"])})

    # (3) no time budget: no budget topic, no timeout line, no cancellation
    budget = p.bus_topics_since(turn.t0 * 1000.0, "worker.budget")
    prefix = _pulse_timeout_prefix()
    timeout_lines = [e for e in evs if prefix and str(payload(e).get("key") or "").startswith(prefix)]
    my_states = [payload(e) for e in evs if str(e.get("kind") or "") == "task_state"
                 and str(payload(e).get("task_id") or "") == row_id]
    cancelled = [s for s in my_states if s.get("state") == "cancelled"] or (
        [final] if str(final.get("state") or "") == "cancelled" else [])
    check.that("no time budget ends or questions it", not budget and not timeout_lines and not cancelled,
               {"bus": [b["topic"] for b in budget], "timeout_lines": [brief(e) for e in timeout_lines][:3],
                "cancelled": cancelled[:2]})

    # (4) progress while it runs
    moves = sorted(seen["moves"] + [seen["t_end"]])
    gap = max((b - a for a, b in zip(moves, moves[1:])), default=0.0)
    check.measure("progress_notes", len(seen["notes"]))
    check.that("the row keeps reporting progress", bool(seen["notes"]) and gap <= PROGRESS_GAP_S + POLL_S,
               {"notes": len(seen["notes"]), "max_gap_s": round(gap)})

    # (5) one card for the task, no non-owner show
    owner = [payload(e) for e in evs if str(e.get("kind") or "") == "owner"]
    non_owner = [o for o in owner if o.get("rule") == "non_owner_show" or str(o.get("allow")) in ("False", "false")]
    shown = {str(o.get("id") or o.get("text") or "") for o in owner if o.get("rule") == "show"}
    check.that("one card for the task", not non_owner and len(shown) <= 1,
               {"non_owner": non_owner[:3], "shown": sorted(shown)})

    # (6) the end state is the request's
    spec = p.artifact(row_id, "spec") or {}
    dw = final.get("done_when") or spec.get("done_when")
    check.that("the end state is the request's", bool(dw) and not presence_only(dw),
               {"done_when": dw, "spec_source": spec.get("source")})

    # (7) settled once, by settle, done, after the worker's last act; «met» only then
    acts = bridge_acts(evs, row_id)
    last_act = max((int(a["id"]) for a in acts), default=0)
    endings = [e for e in evs if str(e.get("kind") or "") == "task_state"
               and str(payload(e).get("task_id") or "") == row_id]
    check.that("settled once by settle with done, after the last act",
               len(endings) == 1 and payload(endings[0]).get("writer") == WRITER_SETTLE
               and payload(endings[0]).get("state") == "done" and int(endings[0]["id"]) > last_act
               and str(final.get("state") or "") == "done",
               {"endings": [brief(e) for e in endings], "last_act": last_act, "acts": len(acts),
                "row_state": final.get("state")})
    met = [e for e in evs if str(e.get("kind") or "") == "verdict" and payload(e).get("verdict") == "met"]
    early = [e for e in met if int(e["id"]) < last_act]
    check.that("met is attested only when the row ends", not early,
               {"early_met": [brief(e) for e in early][:3], "last_act": last_act})

    # (8) after the reply line, only mouths bound to the row, each line once
    reply = p.reply_line(turn)
    after = [(src, e) for e in evs if reply and int(e["id"]) > int(reply["id"]) and (src := line_source(e))]
    unbound = [(s, e) for s, e in after if str(payload(e).get("task_id") or "") != row_id]
    texts = [str(payload(e).get("text") or "").strip() for _, e in after]
    repeated = sorted({t for t in texts if t and texts.count(t) > 1})
    check.that("after the reply only the row's mouths speak, once", bool(reply) and not unbound and not repeated,
               {"unbound": [f"{s}: {brief(e)}" for s, e in unbound][:6], "repeated": [t[:80] for t in repeated][:3]}
               if reply else "no reply line")

    if seen["timed_out"] and str(final.get("state") or "") in LIVE_STATES:
        for name, ok, detail in check.results:
            print(f"[{check.case}] {'ok ' if ok else 'RED'} «{name}»: {detail}")
        raise Infra(f"the row was still {final.get('state')} after the case's own wait of {WAIT_S:.0f} s")
    check.done(expected_red=check.expected)

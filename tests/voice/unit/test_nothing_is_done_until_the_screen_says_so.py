"""«Hecho.» is a report, and a report may not be spoken before the work exists (V2-743).

Session bcd4aba1, 2026-09-21, `agenda:clear_range` over 47 appointments — four events, in this order:

    i=687  2948.168  brain   ✅ acción irreversible confirmada   agenda:clear_range
    i=689  2948.169  widget  action                              agenda:clear_range     ← dispatched
    i=700  2949.026  transcript zaelar  «Hecho.»                                         ← +0.86 s
    i=706  2956.175  widget  action_failed  widget 'agenda' timed out after 8s            ← +8.0 s

The operator, right after: *«se han borrado, pero se han borrado después de, por lo menos, diez segundos,
desde que tú me dijeras que habías terminado»* — and then the rule he wants, which is what this file
protects: *«ese arnés debería haberse dado cuenta que tenía que revisar tanto la memoria como el widget de
la pantalla y no haber dicho que está hecho hasta que estuviera todo terminado. Incluso previamente le tenía
que avisar al usuario, me pongo a hacerlo ahora mismo y te aviso.»*

Three independent defects produced that one sentence, and each one gets its own assertions below:

  A. the confirm gate answered his «sí» with `data_ack` («Hecho.»), a COMPLETION, 0.86 s after dispatching;
  B. a pool timeout was read as a failure, when it is the absence of a verdict — the widget hook keeps
     running after the wait gives up, and this one finished the deletion;
  C. `report_failure` only looked at `ok is False`, so the timeout (which carries only `error`) was never
     told to him at all — while `server_api.brain_action` had been reading the same result as
     `error or ok is False` for its `action_failed` event since V2-390. Two readers, one shape, and the
     quieter one won.
"""
from __future__ import annotations

import ast
import asyncio
import os

import pytest

from nucleo.flash import data_ops, op_receipt

PROVIDER = os.path.join(os.path.dirname(__file__), "..", "..", "..",
                        "voice", "engine", "llm", "providers", "nucleo.py")

#: Verbatim from the session — what `widgets/server_api._run_widget` returns when the bounded pool gives up.
TIMEOUT = {"error": "widget 'agenda' timed out after 8s"}


# ── A · a POOL TIMEOUT IS NOT A VERDICT ────────────────────────────────────────────────────────────────

def test_a_pool_timeout_is_recognised_as_itself():
    assert op_receipt.is_pool_timeout(TIMEOUT)
    assert op_receipt.is_pool_timeout({"error": "widget 'x' timed out after 12s"})


def test_a_real_refusal_is_NOT_a_timeout():
    assert not op_receipt.is_pool_timeout({"ok": False, "error": "unknown_tab"})
    assert not op_receipt.is_pool_timeout({"ok": True})
    assert not op_receipt.is_pool_timeout(None)


def test_a_timeout_is_not_reported_as_a_failure():
    """The whole of defect B. The rows DID disappear; calling it failed would have sent him looking for a
    deletion that had already happened."""
    assert not op_receipt.failed(TIMEOUT)


def test_a_bare_error_IS_a_failure_even_without_ok_false():
    """Defect C, at the level of the predicate. `{"error": …}` with no `ok` key is what half the widget
    layer returns, and the old reading (`ok is not False`) let every one of those through in silence."""
    assert op_receipt.failed({"error": "no data module"})
    assert op_receipt.failed({"ok": False, "message": "No encuentro esa cita."})


def test_silence_is_not_success():
    assert not op_receipt.landed({})
    assert not op_receipt.landed({"error": "x"})
    assert op_receipt.landed({"ok": True})


# ── B · THE WITNESS: the screen decides what the timeout could not ─────────────────────────────────────

def test_the_witness_says_OK_when_the_view_MOVED():
    """47 rows gone from `view_data()` is the deletion, whatever the wait did."""
    assert op_receipt.verdict(TIMEOUT, before='{"meetings": 47}', after='{"meetings": 0}') == "ok"


def test_the_witness_says_FAILED_when_the_view_did_NOT_move():
    """A confirmed irreversible op that changed nothing is a failure he has to hear about, however the
    wait ended."""
    assert op_receipt.verdict(TIMEOUT, before='{"meetings": 47}', after='{"meetings": 47}') == "failed"


def test_no_witness_means_UNKNOWN_and_unknown_never_claims_success():
    """A widget with no `view_data`, or a read that threw. `unknown` is the honest answer and it is a
    distinct third outcome — its absence is why a timeout could only be reported as nothing."""
    assert op_receipt.verdict(TIMEOUT, before="", after="") == "unknown"
    assert op_receipt.verdict({}, before="a", after="b") == "unknown"


def test_an_explicit_result_never_consults_the_witness():
    """The screen only speaks where the result does not: a widget that said `ok` or refused outright is
    the authority on its own action."""
    assert op_receipt.verdict({"ok": True}, before="a", after="a") == "ok"
    assert op_receipt.verdict({"ok": False}, before="a", after="b") == "failed"


def test_the_signature_is_stable_across_key_order():
    assert op_receipt.signature({"a": 1, "b": 2}) == op_receipt.signature({"b": 2, "a": 1})


def test_the_signature_survives_something_unserialisable():
    assert isinstance(op_receipt.signature({"x": object()}), str)


# ── C · WHAT HE HEARS ──────────────────────────────────────────────────────────────────────────────────

class _Lang:
    data_ack = "Hecho."
    op_failed = "No he podido completarlo."
    op_unknown = "Lo he lanzado, pero no he podido confirmar que quedara hecho."


def test_the_widgets_own_message_wins():
    line = op_receipt.spoken_line("agenda", "clear_range",
                                  {"ok": False, "message": "No encuentro esa cita."}, "failed", _Lang)
    assert line == "No encuentro esa cita."


def test_a_raw_error_never_reaches_the_mouth_when_it_is_a_timeout():
    """V2-652: `error` is diagnostic and often addressed to the MODEL; one of those retry instructions was
    measured being read aloud as zaelar's own words. A timeout's text is ours, not his."""
    line = op_receipt.spoken_line("agenda", "clear_range", TIMEOUT, "failed", _Lang)
    assert "timed out" not in line
    assert line == _Lang.op_failed


def test_an_unknown_outcome_is_SAID_as_unknown():
    line = op_receipt.spoken_line("agenda", "clear_range", TIMEOUT, "unknown", _Lang)
    assert line == _Lang.op_unknown
    assert "Hecho" not in line


# ── D · THE SEAM: a confirmed op takes its witness BEFORE acting, and settles after ────────────────────

@pytest.fixture
def wired(monkeypatch):
    """Drives the REAL `dispatch_and_report` with the widget layer doubled at its own edge."""
    seen = {"views": [], "dispatch": None, "settled": None, "reported": None}

    async def _hook(wid, fn, caller):
        seen["views"].append(wid)
        return {"meetings": len(seen["views"])}          # a view that MOVES between the two reads

    class _Api:
        MISSING = object()
        run_widget_hook = staticmethod(_hook)

    import widgets
    monkeypatch.setattr("widgets.server_api", _Api, raising=False)

    async def _dispatch(tag, payload):
        seen["dispatch"] = (tag, payload)
        return dict(TIMEOUT)
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch, raising=False)

    async def _settle(wid, action, res, *, before):
        seen["settled"] = {"wid": wid, "action": action, "res": res, "before": before}
        return "ok"
    monkeypatch.setattr(op_receipt, "settle", _settle)

    async def _report(wid, action, res):
        seen["reported"] = (wid, action, res)
        return True
    monkeypatch.setattr(data_ops, "report_failure", _report)
    return seen


def test_a_confirmed_op_takes_its_witness_BEFORE_dispatching(wired):
    asyncio.run(data_ops.dispatch_and_report("agenda", "clear_range", {"date": "2026-09-24"}, receipt=True))
    assert wired["views"], "no `view_data` read happened — there is nothing to compare against"
    assert wired["settled"] is not None, "the receipt never settled"
    assert wired["settled"]["before"], "the BEFORE signature was empty: taken after the op, or not at all"


def test_the_receipt_OWNS_the_outcome_so_report_failure_does_not_also_speak(wired):
    """Two voices over one op is how «Hecho.» kept surviving next to a correction nobody connected to it."""
    asyncio.run(data_ops.dispatch_and_report("agenda", "clear_range", {}, receipt=True))
    assert wired["reported"] is None


def test_a_FAST_data_op_pays_no_witness_and_keeps_its_old_shape(wired):
    """Scope, deliberately narrow: the extra reads ride the confirmed path only."""
    asyncio.run(data_ops.dispatch_and_report("agenda", "add_meeting", {}))
    assert wired["views"] == [], "a fast data-op must not pay two extra widget reads"
    assert wired["settled"] is None
    assert wired["reported"] is not None, "the V2-603 correction still has to run on the fast path"


def test_report_failure_now_SEES_a_bare_error(monkeypatch):
    """Defect C at the seam. Before today this returned at its first line and the operator was told nothing."""
    told = {}
    monkeypatch.setattr(data_ops, "_dedup", lambda *_a, **_k: False)
    monkeypatch.setattr("voice.brain_notes.push", lambda note: told.setdefault("note", note))
    assert asyncio.run(data_ops.report_failure("agenda", "clear_range", {"error": "no data module"}))
    assert "no data module" in told["note"]


def test_report_failure_STAYS_QUIET_on_a_pool_timeout(monkeypatch):
    """…because the receipt owns that one, and a widget that is still working is not a widget that failed."""
    monkeypatch.setattr(data_ops, "_dedup", lambda *_a, **_k: False)
    assert not asyncio.run(data_ops.report_failure("agenda", "clear_range", dict(TIMEOUT)))


# ── E · THE GATE ANSWERS A «SÍ» WITH A START, NOT A COMPLETION ─────────────────────────────────────────

def _confirm_branch() -> str:
    """The early-confirm branch's source, read from the AST so a rename or a move cannot leave this test
    passing over code that no longer exists — the `_if_guarding` lesson from V2-741."""
    src = open(PROVIDER, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_resolve_pending_confirm":
            return ast.get_source_segment(src, node) or ""
    return ""


def test_the_confirm_branch_still_exists_where_this_test_looks():
    assert _confirm_branch(), "`_resolve_pending_confirm` is no longer called — this test measures nothing"


def test_a_YES_is_answered_with_work_started_and_never_with_data_ack():
    """Defect A. `data_ack` is «Hecho.» and it fired the instant he agreed — before the dispatch had a
    result, and 7 s before this one had any outcome at all."""
    src = open(PROVIDER, encoding="utf-8").read()
    i = src.index("_resolve_pending_confirm(_verdict_early")
    branch = src[i:i + 900]
    assert "_say().work_started" in branch, "the yes is still answered with something other than a START"
    assert "_say().data_ack" not in branch, "«Hecho.» is still being spoken before the work exists"


def test_the_confirmed_dispatch_asks_for_a_receipt():
    """Read from the AST, not from the text around the label. The first version of this test searched the
    500 characters before «widget-data-confirmed» — and stayed GREEN when the disarm deleted the keyword
    from the CALL, because the comment three lines above still said `receipt=True`. A prose match is not a
    wiring match."""
    src = open(PROVIDER, encoding="utf-8").read()
    calls = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "dispatch_and_report"
             and getattr(getattr(n.func, "value", None), "id", "") == "_data_ops"]
    assert calls, "`_data_ops.dispatch_and_report` is not called from the provider any more"
    confirmed = [c for c in calls
                 if any(k.arg == "receipt" and getattr(k.value, "value", None) is True for k in c.keywords)]
    assert confirmed, "no confirmed dispatch asks for a receipt — the outcome is unwitnessed again"


def test_work_started_exists_in_BOTH_languages_and_promises_nothing_done():
    from i18n import langs
    for code in ("es", "en"):
        lang = langs.spec(code)
        line = str(getattr(lang, "work_started", ""))
        assert line, f"{code} has no `work_started`"
        assert "Hecho" not in line and "Done" not in line, f"{code}: {line!r} still claims completion"

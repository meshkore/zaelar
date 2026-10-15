"""A failure rides along in words he can read, never the tool's own instructions (V2-781 pair 7, 2026-10-10).

«No he podido: «Piano de Abril» already repeats on these days from 2026-10-13 — this would write it twice. To drop
ONE day: cancel_meeting {title, date: that day}; …» was read to him: the refusal is written for the MODEL's retry,
and `ensure_failure_named` appended it whole. The part that says what happened stays; the op syntax goes.
"""
from __future__ import annotations

from nucleo.flash import widget_data_turn as W

MSG = ("«Piano de Abril» already repeats on these days from 2026-10-13 — this would write it twice. To drop ONE "
       "day: cancel_meeting {title, date: that day}; to end it from a day: cancel_meeting {title, from}.")


def test_the_tool_syntax_never_reaches_his_ears():
    out = W.ensure_failure_named("Hecho.", {"executed": "widget_data_failed", "message": MSG})
    assert "cancel_meeting" not in out and "{" not in out, out
    assert "would write it twice" in out, out


def test_a_plain_failure_is_still_named_whole():
    out = W.ensure_failure_named("Hecho.", {"executed": "widget_data_failed", "message": "no encuentro esa cita"})
    assert out.endswith("no encuentro esa cita"), out



def test_a_bare_done_over_a_failed_op_is_replaced_never_followed(monkeypatch):
    """agenda-everyday-edits EN (2026-10-15): «Done. I couldn't: the Calendar card didn't take it.» — a claim of what
    did not happen with the failure stapled behind it. Over an op that failed, a bare ack is replaced."""
    failed = {"executed": "widget_data_failed", "message": "no encuentro esa cita"}
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    out = W.ensure_failure_named("Done.", failed)
    assert not out.startswith("Done") and out.endswith("no encuentro esa cita"), out
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    out = W.ensure_failure_named("Hecho.", failed)
    assert not out.startswith("Hecho") and out.endswith("no encuentro esa cita"), out
    assert W.ensure_failure_named("Lo muevo al jueves.", failed).startswith("Lo muevo")

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

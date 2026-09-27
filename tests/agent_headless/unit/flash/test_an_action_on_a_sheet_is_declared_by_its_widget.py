"""An action on a CARD of an instancing widget (`results::94b220-ls1:layout`) is declared by the widget.

Measured 2026-09-27 (verification after the demo pass): «Compare them visually» over the monitor sheet ran
`results::94b220-ls1:layout` — and `action_mode` looked the id up verbatim, found no manifest, answered «not
declared», and the provider ESCALATED it: a Brain Worker for a layout switch. The engine log had been saying
`widget.data no-declarada (results::…:detail) — escalando` since the morning.
"""
from nucleo.flash import frontend


def test_the_mode_of_a_sheet_action_is_the_widgets():
    assert frontend.action_mode("results", "layout") is not None, "the premise: the widget declares it"
    assert frontend.action_mode("results::94b220-ls1", "layout") == frontend.action_mode("results", "layout")
    assert frontend.action_mode("results::94b220-ls1", "detail") == frontend.action_mode("results", "detail")


def test_the_declared_set_and_the_view_flag_follow_the_base():
    assert frontend.declared_actions("results::x") == frontend.declared_actions("results")
    assert frontend.action_is_view("results::x", "layout") == frontend.action_is_view("results", "layout")


def test_an_undeclared_action_is_still_undeclared():
    assert frontend.action_mode("results::x", "launch_rockets") is None

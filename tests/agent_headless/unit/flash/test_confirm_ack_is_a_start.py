"""A «yes» at the confirmation gate STARTS the task; it does not finish it (V2-176 front 1).

Measured in `cancel-subscription-before-charge__es` (2026-08-20 01:21), and the damage is in the operator's
own words two lines later:

    TESTER  Sí, adelante. Y avísame cuando tengas que entrar yo.
    ZAELAR  Hecho.
    TESTER  ¿Ya está cancelada del todo? No me has pedido que entre al login, ¿seguro que no te falta algo?

It understood «Hecho.» as completed, which is what it means. The judge marked it as serious («false confirmation of
execution») — and the model did not say it: `probe.py` mapped `confirm_task` to the SAME ack as a data-op
(`data_ack` = «Hecho.»), that is, the DONE ack for something that had just started.

How we got here matters: front 1 of the umbrella assumed that the boundary was in the prompt
(«I am accessing your account» vs «I am going to try to access it»). Measuring the harness's 78 archived responses,
the hypothesis does not hold: only **10 STATE** a fact versus **41 that express intent** —the model
is almost always right— and the **three** statements in runs where the mechanism recorded NOTHING (0 URLs, 0
screenshots, 0 searches) are all the same word: «Hecho.». The boundary was not in the prompt; it was in
our own phrases.
"""
from __future__ import annotations

import inspect

from voice.engine.core import langs


def _probe_ack_source() -> str:
    from nucleo.flash import probe

    return inspect.getsource(probe.run_turn)


def test_a_YES_does_not_get_the_done_ack():
    """The concrete assertion: `confirm_task` no longer shares a branch with `widget_data`."""
    src = _probe_ack_source()
    assert 'if action == "confirm_task":' in src
    assert 'if action in ("widget_data", "confirm_task"):' not in src


def test_a_yes_acknowledges_a_START_with_the_holding_line():
    src = _probe_ack_source()
    i = src.index('if action == "confirm_task":')
    branch = src[i:src.index("elif action in (", i)]      # ONLY the yes branch, not the next one
    assert "holding_line(" in branch          # «Okay, give me a moment to look at it.» — which is the truth
    # the ASSIGNMENT, not the mention: the reason for the change is explained in a comment in that same branch, and
    # searching for the standalone token would turn the comment into the failure
    assert "spoken = _lg.data_ack" not in branch


def test_but_a_NO_still_gets_it_because_a_NO_really_did_resolve():
    """The other half, and the part that keeps this from becoming «never say done»: «no, leave it» REALLY resolves
    something — the task is discarded— and there «Hecho.» is true."""
    src = _probe_ack_source()
    assert '"confirm_task_no"' in src
    i = src.index('elif action in ("widget_data", "confirm_task_no"):')
    assert "data_ack" in src[i:i + 900]


def test_and_the_yes_no_split_happens_where_the_reply_is_classified():
    """The property: the action name is decided by the operator's YES/NO, never by the success of the relaunch.

    F1 (2026-08-24) moved classification to `nucleo/turn/confirm_gates.py` (the precedence of the three gates
    is decided once, node 2.29), so the split no longer happens in this file: the probe receives
    `_ans.yes` —which IS the classified response; for the task gate, `resolve_confirm` returns `ok` equal
    to the operator's verdict— and only gives it a name. The first version of this guard matched the old literal
    and went red on the fix, not the defect."""
    src = _probe_ack_source()
    assert '"confirm_task" if _ans.yes else "confirm_task_no"' in src
    from nucleo.turn import confirm_gates as _g
    import inspect as _i
    assert "classify_reply" in _i.getsource(_g._task_gate), \
        "la clasificación del sí/no ya no vive en la puerta de tarea: ¿quién decide ahora el veredicto?"


def test_the_holding_line_never_asserts_completion():
    """What makes this change a fix rather than moving the same problem elsewhere."""
    for code in ("es", "en"):
        for line in langs.LANGUAGES[code].holding_lines:
            low = line.lower()
            assert "hecho" not in low and "done" not in low
            assert "ya está" not in low


def test_the_voice_provider_does_NOT_have_this_bug():
    """Checked before touching anything, so as not to «fix» a channel that was not failing: in the provider the short ack
    is gated by `data_done`, which is only set by the REAL dispatch of a data-op — resolving a confirmation sets
    `acted["widget"]` and not that. This is a bug in the TEXT channel, which is where the harness runs."""
    from voice.engine.llm.providers import nucleo as _provider

    src = inspect.getsource(_provider)
    i = src.index('if data_done["v"] and not spoken_text')
    assert "data_acks" in src[i:i + 600]
    assert "confirm" not in src[i:i + 600].lower()

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

from tests import voice_turn_source as _vts

import inspect

from voice.engine.core import langs


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

    src = _vts.getsource(_provider)
    i = src.index('if data_done["v"] and not spoken_text')
    assert "data_acks" in src[i:i + 600]
    assert "confirm" not in src[i:i + 600].lower()

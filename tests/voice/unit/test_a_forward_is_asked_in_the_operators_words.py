"""A forward that has to be confirmed is asked in HIS words — what, to whom, with which note (2026-10-04).

Demo pass 100, E3: «send the invoice to andrew, tell him we're already trying inworld…». The verdict was unsure,
so the stranger's-text gate (leave_gate) rightly asked first — and the question recited the manifest's own
description, in Spanish, in an English session: «Careful, this is permanent: “REENVÍA por correo un mensaje que
llegó… mándale a Quinn la factura…”». That text is written for the MODEL. `reply` and `send_to` already compose
their own question; `forward` now does too.
"""
from __future__ import annotations


def _ask(payload, lang="en"):
    from voice.engine.llm.providers import confirm_gate as cg
    from i18n import langs
    real = cg._say
    cg._say = lambda: langs.spec(lang)
    try:
        return cg._human_confirm_question("mensajeria", "forward", payload)
    finally:
        cg._say = real


def test_the_question_names_what_who_and_the_note():
    q = _ask({"contact": "Andrew", "from": "Inworld", "text": "We're already trying Inworld, please book it."})
    assert "Andrew" in q and "Inworld" in q and "already trying" in q, q
    assert "REENVÍA" not in q and "Quinn" not in q, "the model's tool description was read to the operator"
    assert q.rstrip().endswith("?")


def test_without_a_note_it_still_asks_cleanly():
    q = _ask({"contact": "Andrew", "from": "Inworld"})
    assert "Andrew" in q and "“”" not in q and "«»" not in q, q

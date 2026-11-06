"""
The two guards that cost session b70a45d0 (2026-08-14).

The operator asked to empty the calendar. It was never emptied. The complete chain of failure, with its two avoidable links:

1. **Routing**: the “promise without action” backstop escalated the request with a FIXED `kind:"web"`. A data operation
   that was purely local (“read what is in the calendar, delete it, and verify”) became a browser task:
   two browser cards that nobody asked for, the “Searching the web…” label, and—the real damage—the task became
   “the browser task”.
2. **Hack**: the worker did the right thing (read, deleted tasks, stopped at the confirmation gate for the
   irreversible action, and asked). The operator authorized it. Then the following turn emitted, in the VERY SAME
   millisecond, `answer_worker` with the authorization **and** `stop_worker`—which found the task because it was
   called “the browser task”, due to link 1. Task cancelled `ok:False`, authorization delivered to a corpse, and the
   operator was told “Okay, I’ll tell it”.

Here the two guards are fixed separately, using the session’s REAL PHRASES as test cases.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

from pathlib import Path

import pytest

NUCLEO = Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py"


# ── GUARD 2: killing requires an order — the stop verdict or the model's own call (V2-857 phase 8: the word detector
# `_says_stop` went; a sure «keep» verdict is what refuses a dragged-in stop, `test_a_clear_stop_order_stops_the_errand`).
def test_el_guarda_no_mata_a_quien_acaba_de_contestar():
    """CODE guard for the invariant: answering a worker and killing it in the same turn is inherently incoherent,
    and that happened in the session in the very same millisecond. The response wins, since it is non-destructive."""
    body = _vts.read(NUCLEO)
    i = body.index('elif name == "stop_worker":')
    block = body[i:body.index("cancel_soon", i) + 20]     # through past `cancel_soon`, which it must precede
    assert 'worker_acted["v"] == "answer"' in block, "falta el guarda: se puede volver a matar al que contestas"
    assert "model_stop(brief)" in block, "the stop gate must read the verdict before killing"
    assert "_says_stop" not in block, "no word list over his sentence decides a stop (V2-857 phase 8)"
    # Both must come BEFORE resolving and killing.
    assert block.index('worker_acted["v"] == "answer"') < block.index("cancel_soon"), \
        "el guarda tiene que actuar ANTES de cancel_soon; después ya está muerto"
    assert block.index("model_stop(brief)") < block.index("cancel_soon")


# ── GUARD 1: the classifier decides the kind, not the backstop ─────────────────────────────────────────────────

def test_looks_like_web_task_casa_esa_frase_y_por_eso_no_puede_decidir_el_kind():
    """Documents WHY it does not work as a router: its roots (`borr|lee|compr|…`) do not require any web destination,
    so it matches a request unrelated to the internet three times. It works as a TRIGGER, not as a classifier."""
    from nucleo.flash import router

    peticion = ("Vale, pues hazme un favor, lees lo que hay en la agenda. Lo borras y luego compruebas "
                "que lo hayas borrado.")
    assert router.looks_like_web_task(peticion) is True
    # And it continues doing its original job: genuine web handling.
    assert router.looks_like_web_task("entra en mi Gmail y bórrame los correos de ayer") is True

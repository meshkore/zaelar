"""V2-143 (`renew-gym-membership__es`) — a loop that never repeats a sentence, and a promise the backstop
could not see because it was about money.

Five replies in a row asking for the same missing datum («el nombre del gimnasio o la ciudad»), each one
reworded — apologising, from a new angle, politely. The live watchdog, which is an LLM, called it a loop on
sight; `dialog.repeated_replies` returned 1, because it compares SURFACE FORM and the pairwise Jaccard of those
five replies is 0.094 / 0.197 / 0.155 / 0.349 against a 0.80 threshold. Measured before touching anything.

Then the operator gave the datum («Vivo en Sevilla»), zaelar said «ahora me pongo con ello — busco los gimnasios
de Sevilla», and NOTHING fired: 0 searches, 0 browser tasks. The promise backstop was in place since V2-132 but
`looks_like_escalate_task` does not know that renewing a gym membership needs a worker — while `danger
.moves_money` returns True for that exact sentence. The signal was in the tree, unused.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import dialog
from nucleo.flash import probe
from nucleo.flash import router_guards as g


# The real replies, from the transcript.
ASKING_AGAIN = [
    "No tengo guardado cuál es tu gimnasio habitual. ¿Me dices el nombre o la ciudad donde está para poder "
    "renovar la cuota?",
    "Te entiendo perfectamente, pero no tengo acceso a un historial de pagos anteriores ni a tus datos "
    "personales guardados, así que no puedo recuperar ese número. ¿Me lo facilitas ahora?",
    "He mirado bien y de verdad no lo tengo anotado en ningún lado — ni en mi estado, ni en notas, ni en "
    "historiales. ¿De dónde eres?",
    "Tienes razón, disculpa por insistir. Para poder renovar la cuota necesito el nombre del gimnasio o la "
    "ciudad donde vives. ¿Cuál de las dos me das?",
]


def _window(replies):
    out = []
    for i, r in enumerate(replies):
        out.append({"role": "user", "content": f"turno del operador {i}"})
        out.append({"role": "assistant", "content": r})
    return out


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── the loop the word-overlap detector cannot see ───────────────────────────────────────────────────────────
def test_the_premise_the_wording_detector_really_is_blind_here():
    """Stated as an assertion so this file announces itself if it ever stops testing what it thinks."""
    assert dialog.repeated_replies(_window(ASKING_AGAIN)) < 2


def test_three_rounds_of_only_asking_is_a_loop():
    win = _window(ASKING_AGAIN)
    assert dialog.consecutive_questions(win) >= 3
    assert "ROMPE EL BUCLE" in dialog.loop_nudge(win)


def test_asking_once_and_then_acting_is_not():
    win = [{"role": "user", "content": "resérvame mesa"},
           {"role": "assistant", "content": "¿Para cuántas personas?"},
           {"role": "user", "content": "para dos"},
           {"role": "assistant", "content": "Hecho, mesa para dos a las 21:30."}]
    assert dialog.consecutive_questions(win) == 0
    assert dialog.loop_nudge(win) == ""


def test_and_two_questions_are_not_a_loop_either():
    """Asking for a missing datum is CORRECT behaviour (V2-082) and this suite scores it as such — one question
    is never a loop and two are not either."""
    win = _window(ASKING_AGAIN[:2])
    assert dialog.consecutive_questions(win) == 2
    assert dialog.loop_nudge(win) == ""


# ── spending money is real-world work ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Renueva mi cuota del gimnasio de este mes.",
    "paga la factura de la luz",
    "resérvame mesa en Casa Lucio",
    "consígueme dos entradas para el musical del sábado",
])
def test_these_need_someone_to_actually_go_and_do_it(text):
    assert g._needs_real_work(text) is True


@pytest.mark.parametrize("text", [
    "pon la factura en pantalla",          # the screen, not the world
    "enséñame la factura en pantalla",
    "muéstrame el widget de la cuota",
    "cierra el widget de la factura",
    "crea un widget para llevar mis facturas",
    "recuérdame pagar la factura el día 5",   # a note; the reminder clipping holds
    "¿qué hora es?",
    "hola",
])
def test_and_these_are_resolved_in_the_turn_itself(text):
    assert g._needs_real_work(text) is False


def test_the_goal_survives_across_the_turns_that_were_only_asking():
    win = [{"role": "user", "content": "Renueva mi cuota del gimnasio de este mes."},
           {"role": "assistant", "content": "¿Qué gimnasio?"},
           {"role": "user", "content": "el mío, el de siempre"},
           {"role": "assistant", "content": "¿Nombre o ciudad?"}]
    goal = g.escalate_goal_from_window(win, "Vivo en Sevilla.")
    assert "cuota del gimnasio" in goal      # the request…
    assert "Sevilla" in goal                 # …and the datum that unblocked it


class _PromisesToSearch:
    async def stream(self, *_a, **_kw):
        yield "Perfecto, gracias. Ahora me pongo con ello — busco los gimnasios de Sevilla y vemos cuál es el tuyo."


def test_the_promise_to_search_now_actually_starts_something(fresh_db, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _PromisesToSearch)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: False)
    sess = probe._session("t-v143")
    sess.seeded = True
    sess.window[:] = [{"role": "user", "content": "Renueva mi cuota del gimnasio de este mes."},
                      {"role": "assistant", "content": "¿Qué gimnasio?"},
                      {"role": "user", "content": "el mío, el de siempre"},
                      {"role": "assistant", "content": "¿Nombre o ciudad?"}]
    res = asyncio.run(probe.run_turn("Vivo en Sevilla.", sid="t-v143", ingest=False))
    probe._SESSIONS.pop("t-v143", None)
    assert res["action"] == "escalate"

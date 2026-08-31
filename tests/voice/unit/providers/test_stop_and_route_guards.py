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

import re
import unicodedata
from pathlib import Path

import pytest

NUCLEO = Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py"


# ── GUARD 2: killing requires the operator to have requested it ─────────────────────────────────────────────────
def _says_stop(t: str) -> bool:
    """Replica of the provider’s local detector (`_says_stop`), extracted from the source so it can be tested without
    setting up half a LiveKit session. If the source changes, `test_el_detector_del_fuente_es_este` will flag it."""
    n = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c)).lower()
    return bool(re.search(
        r"\b(par[ae]r(?:me|te|lo|la|los|las)?|par[ae]l[oa]s?|paralo|parala|"
        r"det[ei]n(?:er|lo|la|los|las|ga|gan)?|cancel(?:a|ar|alo|ala|o|en)|"
        r"anul(?:a|ar|alo|ala)|abort(?:a|ar|)|deja de|dejalo|"
        r"stop|cancel|abort|kill|halt|call it off)\b", n))


# The phrases are LITERAL session phrases (including voice transcription: “pararme”, “Cancélalo”).
@pytest.mark.parametrize("frase,puede_matar", [
    # THE INCIDENT: the turn that killed the worker did not ask to stop anything—it authorized a deletion.
    ("Sí, te autorizo a borrar toda la agenda. No el widget, los datos de la.", False),
    # The turn from TWO turns earlier, whose intent the model carried forward (and which a barge-in had cancelled).
    ("Seguramente, por error has abierto dos widgets más. Con dos navegadores que aquí no se tenían "
     "que haber abierto para nada.", False),
    # …and the stops that ARE stops, also literal session phrases (those two were correct).
    ("No, esto no era para ti, puedes pararme.", True),
    ("Cancélalo, no tenía, el mensaje no era para ti.", True),
    ("Cancélalo.", True),
    # The traps of Spanish: “para” is a preposition much more often than a verb.
    ("para nada me gusta eso", False),
    ("esto es para ti", False),
    ("es para mañana", False),
    # Unambiguous forms.
    ("detén la tarea del navegador", True),
    ("párala ya", True),
    ("deja de buscar", True),
    ("anula el proceso", True),
    ("stop the browser task", True),
    # And what must NEVER authorize a hack.
    ("enséñame la agenda", False),
    ("vacía la agenda por completo, hoy y siempre", False),
    ("borra los cuatro proyectos", False),
])
def test_matar_exige_orden_explicita_de_parar(frase, puede_matar):
    assert _says_stop(frase) is puede_matar, frase


def test_el_detector_del_fuente_es_este():
    """The detector lives in the provider (a local, non-importable function). This test compares the source REGEX with
    the one here: if someone loosens it there but not here, the cases above would cease to mean anything."""
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index("def _says_stop(")
    block = body[i:i + 1200]
    assert "par[ae]r(?:me|te|lo|la|los|las)?" in block, "cambió el regex del fuente: revisa los casos de este test"
    assert r"\bpara\b" not in block, "«para» suelto NO puede autorizar un hachazo (es preposición: «para nada»)"


def test_el_guarda_no_mata_a_quien_acaba_de_contestar():
    """CODE guard for the invariant: answering a worker and killing it in the same turn is inherently incoherent,
    and that happened in the session in the very same millisecond. The response wins, since it is non-destructive."""
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index('elif name == "stop_worker":')
    block = body[i:i + 5200]     # through past `cancel_soon`, which it must precede
    assert 'worker_acted["v"] == "answer"' in block, "falta el guarda: se puede volver a matar al que contestas"
    assert "_says_stop(text)" in block, "falta el guarda de orden explícita"
    # Both must come BEFORE resolving and killing.
    assert block.index('worker_acted["v"] == "answer"') < block.index("cancel_soon"), \
        "el guarda tiene que actuar ANTES de cancel_soon; después ya está muerto"
    assert block.index("_says_stop(text)") < block.index("cancel_soon")


# ── GUARD 1: the classifier decides the kind, not the backstop ─────────────────────────────────────────────────
def test_la_peticion_de_la_agenda_NO_es_una_tarea_web():
    """The real classifier always knew the truth: for this phrase it returns `generic`. `kind:"web"` was hardcoded
    in the backstop, which produced the two browsers and the “Searching the web…” label."""
    from nucleo import dispatch

    peticion = ("Vale, pues hazme un favor, lees lo que hay en la agenda. Lo borras y luego compruebas "
                "que lo hayas borrado.")
    assert dispatch._classify_kind(peticion) == "generic"
    assert dispatch._default_label(dispatch._classify_kind(peticion)) == "Pensando…"


def test_looks_like_web_task_casa_esa_frase_y_por_eso_no_puede_decidir_el_kind():
    """Documents WHY it does not work as a router: its roots (`borr|lee|compr|…`) do not require any web destination,
    so it matches a request unrelated to the internet three times. It works as a TRIGGER, not as a classifier."""
    from nucleo.flash import router

    peticion = ("Vale, pues hazme un favor, lees lo que hay en la agenda. Lo borras y luego compruebas "
                "que lo hayas borrado.")
    assert router.looks_like_web_task(peticion) is True
    # And it continues doing its original job: genuine web handling.
    assert router.looks_like_web_task("entra en mi Gmail y bórrame los correos de ayer") is True


def test_el_backstop_ya_no_fija_el_kind_a_web():
    body = NUCLEO.read_text(encoding="utf-8")
    i = body.index("promesa→escalada FORZADA")
    block = body[max(0, i - 2000):i + 400]
    assert '_classify_kind(text)' in block, "el backstop tiene que preguntar al clasificador"
    assert '"kind": "web"' not in block, "vuelve a estar el hardcode que abrió dos navegadores"

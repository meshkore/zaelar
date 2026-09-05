"""V2-393 — «páralo» refers to a THING, and the barge-in was swallowing it.

A hard stop skips the attention gate and **does not generate a response**: it is for silencing zaelar when it is speaking
over someone. The clitic was deliberately included in that rule, with this reasoning written down: «with a pronoun
attached, it is NO LONGER the preposition para, so it is unambiguous». True — and it confuses *unambiguous AS A VERB*
with *unambiguous ABOUT WHAT*.

Measured in `watch-a-video-not-listen-to-it` (2026-08-27 14:04), which had passed **5/5 two hours earlier**:

    tester  Pon el vídeo del tráiler de la última de Dune.
    zaelar  Ya lo tienes en pantalla: «Dune: Parte Tres | Tráiler Oficial».
    tester  Vale, se ve bien. Bájale un poco el volumen, porfa.
    zaelar  Hecho.
    tester  Ahora páralo, porfa.
    zaelar  Perdona, ¿me lo repites?

The entire turn disappeared. And the tester themselves proved that the command was clear: they repeated it in other
words —«Que pares el vídeo, porfa»— and it worked **the first time**. The guard was ours.

The remaining rule: a barge-in **has no object**; it is for silencing. The reflexive/dative («párate», «detente»)
refers to zaelar; the third-person accusative («páralo», «detenla») takes a direct object, meaning it refers to a
thing — and the router resolves that, since it has the widget's data ops for that purpose.
"""
from __future__ import annotations

import pytest

from voice import attention as A


# ── something referring to a THING no longer silences the turn ────────────────────────────────────────────────

@pytest.mark.parametrize("frase", [
    "Ahora páralo, porfa",          # the REAL phrase from the run
    "páralo",
    "párala",
    "páralos",
    "detenlo",
    "detenla",
])
def test_el_acusativo_lleva_OBJETO_y_no_es_un_barge_in(frase):
    assert A.hard_interrupt(frase) is None, "lleva objeto directo: es una orden sobre una cosa, no callarse"


# ── and something referring to ZAELAR still silences it ───────────────────────────────────────────────────────

@pytest.mark.parametrize("frase", [
    "para",                          # the ambiguous preposition, resolved by the SOFT rule (short turn)
    "párate",                        # reflexive → it is him
    "detente",
    "páreme",                        # dative → I am the one it stops speaking to
    "cállate",
    "basta",
    "silencio",
    "para ya",
])
def test_lo_que_habla_de_ZAELAR_sigue_siendo_un_stop_duro(frase):
    assert A.hard_interrupt(frase) == "stop", "la otra dirección: sin esto, arreglar el vídeo deja al operador " \
                                              "sin poder callar al agente"


def test_pararlo_TODO_sigue_siendo_global():
    """«todo» is not a specific thing: there, the object does not narrow the scope; it encompasses everything."""
    assert A.hard_interrupt("páralo todo") == "stop"
    assert A.hard_interrupt("páralas todas") == "stop"


def test_cerrar_TODO_no_se_toca():
    """The other half of the function, which this change does not touch."""
    assert A.hard_interrupt("cierra todo") == "close"


# ── V2-584: a stop verb that NAMES a thing lets the turn run ─────────────────────────────────────────────────
# This closes the gap the PREEXISTENTE test below used to assert as harm. Measured live 2026-09-05
# (session 0e3a42d6): «Para el vídeo», said twice, silenced the SPEECH and left the video playing — the
# operator complained in the transcript, and only «Pausa el vídeo» worked. The rule is structural, never a
# phrase table: DETERMINER + NOUN after the stop verb means the order is ABOUT that thing, so the model (or
# the action map) must get the turn. The barge-in upstream already silenced the voice either way.

@pytest.mark.parametrize("frase", [
    "Para el vídeo",                 # the REAL phrase from session 0e3a42d6, twice
    "para la música",
    "para el widget",
    "para la cena",                  # the sentence the old ≤4-word rule's own comment said it existed to avoid
    "stop the video",                # same shape in English — `stop` bare stays a hard stop below
])
def test_un_verbo_de_parar_con_DETERMINANTE_y_nombre_deja_correr_el_turno(frase):
    assert A.hard_interrupt(frase) is None, "nombra una COSA: la orden es sobre ella, no callarse"


def test_la_contradireccion_un_stop_sin_objeto_sigue_callando():
    """The counterweight that keeps this from loosening the barge-in: no determiner+noun → still a hard stop."""
    assert A.hard_interrupt("para por favor") == "stop"   # «por» is not a determiner
    assert A.hard_interrupt("stop") == "stop"
    assert A.hard_interrupt("para eso") == "stop"         # bare pronoun: how people silence an ongoing speech


def test_PREEXISTENTE_el_imperativo_plural_nunca_estuvo_en_la_lista():
    """«parad»/«paradme» is not among the verbs in the pattern, either before or now. Known gap, not a regression."""
    assert A.hard_interrupt("paradme") is None

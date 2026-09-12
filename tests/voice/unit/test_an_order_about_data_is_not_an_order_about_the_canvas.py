"""V2-664 — «quita los datos de la agenda» must not close the desktop, and «me vas a poner el vídeo» is an order.

Session eedf7f9b (2026-09-11), read event by event. Three defects, all in the GUARDRAILS — the V2-660/661
errand harness never fired once in that session:

  09:39:06  «Bien, me vas a poner el vídeo del Apolo 11 llegando a la luna» → the model DID call
            `play_video(query="Apolo 11 llegando a la luna")` and `canvas_license.video_license` ate it as
            context-bleed, because the media grammar spells out the infinitive of every verb it knows
            (cargar, buscar, reproducir, abrir, cambiar, repetir) EXCEPT the commonest one in Spanish:
            `pon(?:me|te|le|lo|la|gas?|ed)?` cannot reach «poner». The turn ended saying «Y ahora te pongo el
            vídeo del Apolo 11» over a player that never loaded.

  09:39:52  «Vale, quita, por favor, los datos de comidas de la agenda… todas esas entradas de la…» — an
            order to delete ROWS INSIDE the agenda — matched a close verb in one clause and a bare quantifier
            fifteen words away in ANOTHER, and closed every card he had open. Twice: the glued fragments
            re-fired it at 09:39:55.

Both halves of the close rule are implemented twice on purpose (the engine's hard interrupt and the client's
fast lane), so both are measured here — parallel implementations must not drift (V2-252/V2-555).
"""
from __future__ import annotations

import os

import pytest

from nucleo.flash import canvas_license as lic
from voice import attention

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ── the media grammar knows how Spanish actually asks for a video ────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "Bien, me vas a poner el el vídeo del del Apol once, llegando a la luna.",   # his sentence, STT verbatim
    "¿Puedes ponerme la canción de Rosalía?",
    "Voy a ponerte el documental de la luna",
    "¿me lo vas a mostrar?",
    "ponme el vídeo",                                                            # the imperative still works
    "dale al play",
])
def test_a_request_for_media_licenses_the_load(txt):
    assert lic.video_license(txt), txt


@pytest.mark.parametrize("txt", [
    "¿Por qué lo has cambiado otra vez?",     # a complaint about the past licenses nothing (V2-635)
    "Muy bien, señora.",
    "Johnny eres tonto",
    "no me pongas el vídeo",                  # negated
    "Vale, quita, por favor, los datos de comidas de la agenda",
])
def test_chatter_and_complaints_still_license_nothing(txt):
    assert not lic.video_license(txt), txt


# ── a bare quantifier is not the canvas until it says so ─────────────────────────────────────────────────
@pytest.mark.parametrize("txt", [
    "Johnny, cierra todos los widgets.",      # the order he gave at 09:38:43, which DID work
    "cierra todo",
    "ciérralo todo ya",
    "quita todas las tarjetas",
    "limpia la pantalla",
    "cierra las ventanas",
    "close everything",
])
def test_an_order_about_the_cards_still_closes_them_all(txt):
    assert attention.hard_interrupt(txt) == "close", txt


@pytest.mark.parametrize("txt", [
    # THE MEASURED SENTENCE, exactly as the fragment accumulator glued it at 09:39:52
    "Vale, quita, por favor, los datos de comidas de la agenda, Veo que varios días tengo asignada la comida,"
    " de la una a las dos, todos esos todas esas entradas de la",
    "borra todas esas entradas de la agenda",
    "quita todos los datos de la agenda",
    "elimina todas las citas de comida",
    "Cierra la pantalla completamente.",      # V2-600's fullscreen veto is untouched
    "cierra el widget de meteo",              # a NAMED close is one card, never the canvas
])
def test_an_order_about_what_is_INSIDE_a_widget_closes_nothing(txt):
    assert attention.hard_interrupt(txt) is None, txt


def test_the_quantifier_is_read_by_what_it_GOVERNS():
    """The rule is structural and needs no lexicon of intentions — this is the whole of it."""
    assert attention._quantifies_the_canvas("cierra todo")                 # governs nothing
    assert attention._quantifies_the_canvas("quitalo todo ya")             # governs a particle
    assert attention._quantifies_the_canvas("cierra todos los widgets")    # governs a card noun
    assert not attention._quantifies_the_canvas("todas esas entradas")     # governs a thing inside a widget
    assert not attention._quantifies_the_canvas("todos los datos de la agenda")


def test_a_stop_order_is_untouched():
    """The other half of `hard_interrupt` must not move: its own rules (V2-393/V2-584) are separate."""
    assert attention.hard_interrupt("silencio") == "stop"
    assert attention.hard_interrupt("para el vídeo") is None   # names a THING → the turn runs


# ── the client carries the SAME rule (parallel implementation, V2-252/V2-555) ─────────────────────────────
def test_the_canvas_fast_lane_mirrors_the_quantifier_rule():
    src = open(os.path.join(ENG, "frontend", "app", "services", "voiceCommands.js"), encoding="utf-8").read()
    assert "quantifiesTheCanvas(n)" in src, "the client fast lane must consult the same rule"
    assert "const ALL_RE   = /\\b(widgets|tarjetas|cards|" in src, \
        "the bare quantifiers must be OUT of the card-noun list — that is what fired on «todas esas entradas»"
    # V2-678 renegotiated the SHAPE, deliberately and without weakening the rule: the decision moved into
    # `closesTheWholeCanvas`, which still asks this question and now also requires the close verb and the
    # quantifier to share a CLAUSE and vetoes a negation. So the assertion moves from the old call shape to
    # the PROPERTY — the quantifier rule is consulted inside the function the closeAll branch calls, and
    # nowhere else decides it. Pinning the shape is what made this test red on a strictly stronger guard.
    i = src.index("function closesTheWholeCanvas(n)")
    body = src[i:i + 600]
    assert "quantifiesTheCanvas(c)" in body, "the canvas decision must consult the quantifier rule"
    j = src.index("if (closesTheWholeCanvas(n)) {")
    assert "desktop.closeAll()" in src[j:j + 120], "closeAll must be reached only through that decision"

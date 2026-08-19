"""V2-138 (`cancel-subscription-before-charge__es`) — cancelling costs nothing, so the money signal said no.

«Cancela mi suscripción a Netflix antes de que me cobren el día 15.» Measured before touching anything:

    danger.is_dangerous            → True   (the confirm-gate does fire, and that is correct behaviour here)
    danger.moves_money             → False  (cancelling spends nothing)
    router_guards._needs_real_work → False  ← the promise backstop could not fire for the whole cancel family
    dispatch._classify_kind        → web    (Netflix is a known site — V2-126 fixed that one)

`is_dangerous` is too WIDE to decide whether something needs a worker: it is also True for «borra el widget de
música», which is resolved inside the turn (V2-017). `moves_money` is too NARROW. The predicate of exactly the
right width was already being computed inside `is_dangerous` and never exposed.

And a second one, from the same measurement: «ANULA la suscripción de Spotify» classified `generic` — a worker
with no browser — while «CANCELA la suscripción de Spotify» classified `web`. Two causes stacked there: `anul`
was missing next to `cancel` in the task-verb list, and the music/messaging guards were excluding the site for
ANY request. Those guards exist because CONNECTING one of those accounts happens inside its own widget
(OAuth/QR) — but ending a paid commitment with that provider happens on their website like any other
cancellation.
"""
from __future__ import annotations

import pytest

from nucleo import danger
from nucleo import dispatch
from nucleo.flash import router_guards as g


# ── the predicate of the right width ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Cancela mi suscripción a Netflix antes de que me cobren el día 15.",
    "dame de baja de Movistar",
    "anula el pedido de Amazon",
    "anula la suscripción de Spotify",
    "renueva mi cuota del gimnasio",
])
def test_these_end_or_start_a_standing_commitment(text):
    assert danger.ends_a_commitment(text) is True


@pytest.mark.parametrize("text", [
    # All of these are `is_dangerous`, and none of them needs a worker — they resolve inside the turn.
    "borra el widget de música",
    "cancela la búsqueda",
    "borra la tarea del jueves",
    "elimina el evento de la agenda",
    "cierra el widget",
])
def test_and_these_do_not_even_though_some_are_irreversible(text):
    assert danger.ends_a_commitment(text) is False


def test_a_reminder_about_cancelling_is_still_a_note():
    """The same clipping as the rest of the module: «recuérdame dar de baja Netflix» asks for a NOTE, and
    gating it would leave a reminder waiting for an OK nobody was going to act on."""
    assert danger.ends_a_commitment("recuérdame dar de baja Netflix el día 14") is False


# ── the promise backstop can now fire for a cancellation ────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Cancela mi suscripción a Netflix antes de que me cobren el día 15.",
    "anula la suscripción de Spotify",
    "dame de baja de Movistar",
])
def test_a_cancellation_needs_someone_to_go_and_do_it(text):
    assert g._needs_real_work(text) is True


@pytest.mark.parametrize("text", [
    "borra el widget de música",
    "cancela la búsqueda",
    "cierra el widget",
    "pon música en Spotify",
])
def test_and_these_are_still_resolved_in_the_turn(text):
    assert g._needs_real_work(text) is False


# ── the same order with a synonym must not get a different engine ───────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "cancela la suscripción de Spotify",
    "anula la suscripción de Spotify",
    "anula mi suscripción a Netflix",
    "dame de baja de Spotify",
    "anula el pedido de Amazon",
])
def test_ending_a_commitment_with_a_named_provider_gets_a_browser(text):
    assert dispatch._classify_kind(text) == "web"


@pytest.mark.parametrize("text", [
    # The linking guards still hold: connecting one of these accounts goes through its own widget, never Chromium.
    "pon música en Spotify",
    "quita la música de Spotify",
    "conecta mi Spotify",
    "manda un whatsapp a Ana",
])
def test_but_linking_or_operating_those_accounts_still_does_not(text):
    assert dispatch._classify_kind(text) != "web"


def test_the_confirm_gate_still_fires_because_cancelling_is_irreversible():
    """The case says asking before executing is the CORRECT behaviour here, not a defect — so widening the
    routing must not have moved anything out of the gate."""
    text = "Cancela mi suscripción a Netflix antes de que me cobren el día 15."
    assert danger.is_dangerous(text) is True
    assert danger.moves_money(text) is False        # irreversible, but it costs nothing

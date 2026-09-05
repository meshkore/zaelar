"""V2-594 · the workflow table: what serves this kind of errand, and is that still true?

The rows that matter most are the NEGATIVE ones. Before this, «nobody on the mesh does wellness» was thrown
away every time, so every massage errand paid the Oracle round trip again and then paid a language model to
narrate the emptiness back.
"""
from __future__ import annotations

import time

import pytest

from nucleo import workflows as wf
from nucleo.workflows import store


@pytest.fixture(autouse=True)
def _clean():
    for d in ("wellness", "restaurant", "hotel", "train", "image", "housing"):
        wf.forget(d)
    yield
    for d in ("wellness", "restaurant", "hotel", "train", "image", "housing"):
        wf.forget(d)


# ── the key is lexical and costs nothing ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,domain", [
    ("resérvame mesa para dos en Casa Lucio", "restaurant"),
    ("quiero un masaje en Sevilla", "wellness"),
    ("hotel en Soria para el jueves", "hotel"),
    ("billete de tren a Barcelona", "train"),
    ("find a flat to rent in Madrid", "housing"),
    ("genera una imagen de un gato astronauta", "image"),
])
def test_an_errand_resolves_to_its_domain(text, domain):
    assert wf.domain_of(text) == domain


@pytest.mark.parametrize("text", ["qué hora es", "pon música", "apaga la luz", ""])
def test_something_that_is_not_an_errand_has_no_domain(text):
    """The table must stay out of the fast lane: a local action never becomes a network question."""
    assert wf.domain_of(text) == ""
    assert not wf.plan(text)


# ── the negative row is the point ─────────────────────────────────────────────────────────────────────────
def test_a_known_empty_domain_stops_asking_the_mesh():
    assert wf.plan("quiero un masaje en Sevilla").ask_mesh is True
    wf.note_empty("wellness", evidence="oracle coverage=none")
    p = wf.plan("quiero un masaje en Sevilla")
    assert p.known_empty is True and p.ask_mesh is False


def test_but_a_stale_negative_row_asks_again():
    """It expires ON PURPOSE: a new agent appears on the mesh and the answer has to be allowed to change.
    Two arrived the afternoon this was written."""
    wf.note_empty("wellness", ttl_s=1)
    time.sleep(1.1)
    p = wf.plan("quiero un masaje en Sevilla")
    assert p.known_empty is False and p.ask_mesh is True


def test_a_success_is_remembered_with_its_agent():
    wf.learn("restaurant", store.CH_MESH, target="tablescout", evidence="served", rank=10)
    p = wf.plan("resérvame mesa para dos en Casa Lucio")
    assert p.best["channel"] == store.CH_MESH and p.best["target"] == "tablescout"


def test_a_stale_success_is_not_offered_as_live():
    """The MESH row expires; the browser one does not, because it is not an observation about the outside
    world — it is what this engine already knows, and knowing it cannot go stale."""
    wf.learn("restaurant", store.CH_MESH, target="tablescout", ttl_s=1)
    time.sleep(1.1)
    channels = wf.plan("resérvame mesa para dos").channels
    assert [c for c in channels if c["channel"] == store.CH_MESH] == []


def test_learning_never_overwrites_what_the_operator_pinned():
    """A human decision outranks a measurement, the same invariant the action map holds for a disabled seed."""
    wf.learn("restaurant", store.CH_MESH, target="thefork", source="operator")
    wf.learn("restaurant", store.CH_MESH, target="tablescout")          # a later success
    assert wf.plan("resérvame mesa").best["target"] == "thefork"
    wf.note_empty("restaurant", store.CH_MESH)                           # and a later emptiness
    assert wf.plan("resérvame mesa").known_empty is False


# ── the browser channel is DERIVED from the site catalogue, never copied ──────────────────────────────────
def test_a_domain_with_a_trusted_site_offers_the_browser():
    """The catalogue has held a trusted site per category for months and that is a channel. Derived, not
    duplicated: a second inventory of trusted sites is exactly what drifted apart once already."""
    p = wf.plan("resérvame mesa para dos en Madrid")
    browser = [c for c in p.channels if c["channel"] == store.CH_BROWSER]
    assert browser and browser[0]["target"]


def test_a_live_mesh_agent_outranks_the_browser():
    wf.learn("restaurant", store.CH_MESH, target="tablescout", rank=10)
    p = wf.plan("resérvame mesa para dos en Madrid")
    assert p.best["channel"] == store.CH_MESH and p.best["target"] == "tablescout"
    assert [c["channel"] for c in p.channels][-1] == store.CH_BROWSER


def test_a_domain_the_catalogue_does_not_know_offers_no_browser():
    """Absence stays absence: there is no trusted site for «un masaje», and inventing one is the guessing the
    catalogue exists to stop."""
    assert [c for c in wf.plan("quiero un masaje en Sevilla").channels
            if c["channel"] == store.CH_BROWSER] == []


# ── what the worker is TOLD, and only when we know it ─────────────────────────────────────────────────────
def test_the_worker_prompt_names_the_agent_we_already_proved():
    from nucleo import dispatch_prompts as dp
    wf.learn("restaurant", store.CH_MESH, target="tablescout", rank=10)
    line = dp._known_route_line("resérvame mesa para dos")
    assert "tablescout" in line and "YA COMPROBADO" in line


def test_the_worker_prompt_says_when_the_mesh_is_known_empty():
    from nucleo import dispatch_prompts as dp
    wf.note_empty("wellness")
    assert "NO tiene agente" in dp._known_route_line("quiero un masaje en Sevilla")


def test_the_worker_prompt_stays_SILENT_when_nothing_is_known():
    """A prompt does not pay for an empty table. This is the line that keeps the feature free."""
    from nucleo import dispatch_prompts as dp
    assert dp._known_route_line("quiero un masaje en Sevilla") == ""
    assert dp._known_route_line("qué hora es") == ""
    assert dp._known_route_line("") == ""


# ── V2-599 · a catch-all category must not swallow the specific ones ──────────────────────────────────────
def test_a_catch_all_category_does_not_outrank_a_specific_match():
    """Measured 2026-09-05: the site catalog calls «pedir cita con el médico» `local_business`, and because
    the catalog was asked FIRST and answered, the `health` pattern never got a turn. Six unrelated Spanish
    errands — doctor, dentist, physio, hairdresser, vet, gym — collapsed into the single key `local`."""
    from nucleo.workflows import domains
    assert domains.domain_of("pedir cita con el medico") == "health"
    assert domains.domain_of("reservar hora con el dentista") == "health"
    assert domains.domain_of("pedir cita con el fisioterapeuta") == "health"


def test_the_same_errand_keys_the_same_in_both_languages():
    """The whole reason `_EXTRA` is bilingual: «a domain that only fires in one language is a cache that
    misses half the time». The catch-all broke exactly that — `pedir cita con el médico` keyed `local` while
    `book a doctor appointment` keyed `health`, so the two halves of one errand wrote to two different rows,
    and neither ever helped the other."""
    from nucleo.workflows import domains
    pairs = [("pedir cita con el medico", "book a doctor appointment"),
             ("reservar hora con el dentista", "book a dentist appointment"),
             ("billete de tren a Sevilla", "train ticket to Chicago"),
             ("alquilar un coche en Malaga", "rent a car in Denver"),
             ("donde esta mi paquete", "track my parcel")]
    for es, en in pairs:
        assert domains.domain_of(es) == domains.domain_of(en), f"asimetría ES/EN: {es!r} vs {en!r}"


def test_the_catch_all_still_answers_when_nothing_specific_matches():
    """Holding the weak category back must not throw it away: «cita en la peluquería» has no specific
    pattern, and `local` is a better key than none — a domain of "" writes no cache row at all."""
    from nucleo.workflows import domains
    assert domains.domain_of("cita en la peluqueria") == "local"


def test_a_specific_catalog_category_still_wins_immediately():
    """Only the catch-all is held back. `event_tickets` names a real vertical and keeps its priority."""
    from nucleo.workflows import domains
    assert domains.domain_of("entradas para un concierto") == "events"
    assert domains.domain_of("buscar un hotel en Madrid") == "hotel"

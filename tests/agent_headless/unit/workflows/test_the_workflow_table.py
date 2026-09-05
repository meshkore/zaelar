"""V2-583 · the workflow table: what serves this kind of errand, and is that still true?

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
    wf.learn("restaurant", store.CH_MESH, target="tablescout", ttl_s=1)
    time.sleep(1.1)
    assert wf.plan("resérvame mesa para dos").channels == []


def test_learning_never_overwrites_what_the_operator_pinned():
    """A human decision outranks a measurement, the same invariant the action map holds for a disabled seed."""
    wf.learn("restaurant", store.CH_MESH, target="thefork", source="operator")
    wf.learn("restaurant", store.CH_MESH, target="tablescout")          # a later success
    assert wf.plan("resérvame mesa").best["target"] == "thefork"
    wf.note_empty("restaurant", store.CH_MESH)                           # and a later emptiness
    assert wf.plan("resérvame mesa").known_empty is False

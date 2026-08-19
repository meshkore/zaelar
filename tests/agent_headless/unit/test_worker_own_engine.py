"""V2-152 — a worker has to talk to the engine that SPAWNED it, and nothing used to tell it which one.

Measured on `book-hotel-night-known__es`: the sandbox engine's own browser task stayed empty (`url=""`,
`shot_rev=0`) and not ONE of the owner's browser events (`navigate`, `screenshot`, `tab_open`) reached its
timeline — while the worker was really driving Booking.com. It was driving the OPERATOR'S engine, because all
six bridges resolve `ZAELAR_BASE` with a hardcoded `localhost:43917` default and nobody ever set that variable.

Two consequences, and the second is why this is not just a test-isolation nicety: a sandboxed run measures the
wrong engine (so every use case that needs a bridge was scored against a machine it never touched), and it
REACHES INTO the operator's live engine — its browser, its memory, its task cards.
"""
from __future__ import annotations

import importlib

import pytest

from nucleo import dispatch


@pytest.mark.parametrize("port,host,expected", [
    (None, None, "http://127.0.0.1:43917"),        # the historical default, now derived instead of hardcoded
    ("51234", "127.0.0.1", "http://127.0.0.1:51234"),
    ("8080", "0.0.0.0", "http://127.0.0.1:8080"),  # the wildcard bind is not a dialable address
    ("", "", "http://127.0.0.1:43917"),
])
def test_an_engine_knows_its_own_address(monkeypatch, port, host, expected):
    for k, v in (("PORT", port), ("HOST", host)):
        monkeypatch.delenv(k, raising=False) if v is None else monkeypatch.setenv(k, v)
    assert dispatch._own_base_url() == expected


# Every bridge a worker uses to talk back. If one stops honouring `ZAELAR_BASE`, handing it out stops working
# for that bridge ALONE — which is the failure mode that hides best, because the other five keep behaving.
BRIDGES = ["nucleo.nav_cli", "nucleo.mem_cli", "nucleo.worker_bridge",
           "nucleo.agent_report", "nucleo.widget_cli"]


@pytest.mark.parametrize("mod", BRIDGES)
def test_every_bridge_honours_the_address_it_is_given(monkeypatch, mod):
    monkeypatch.setenv("ZAELAR_BASE", "http://127.0.0.1:51234")
    m = importlib.reload(importlib.import_module(mod))
    try:
        assert m._BASE == "http://127.0.0.1:51234", f"{mod} ignores ZAELAR_BASE"
    finally:
        monkeypatch.delenv("ZAELAR_BASE", raising=False)
        importlib.reload(m)


@pytest.mark.parametrize("mod", BRIDGES)
def test_and_falls_back_to_the_operator_engine_when_told_nothing(monkeypatch, mod):
    """The default is not wrong — a bridge run by hand from a terminal has no other sensible guess. What was
    wrong is that it was the ONLY answer available."""
    monkeypatch.delenv("ZAELAR_BASE", raising=False)
    m = importlib.reload(importlib.import_module(mod))
    assert m._BASE.endswith(":43917")

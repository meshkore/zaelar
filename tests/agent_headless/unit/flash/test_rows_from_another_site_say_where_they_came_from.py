"""Rows delivered from another site than the one he asked for say so (V2-782) — search-buy-used-car ES, 2026-10-11.

He asked for coches.net; coches.net and Milanuncios blocked the browser; the rows came from AutoScout24, said only in
progress pings. The delivery now names the site he asked for, whether it blocked us, and where the rows came from.
"""
from __future__ import annotations

import pytest

from nucleo.flash import asked_site, delivery
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    asked_site.forget()
    delivery.forget_announced()
    yield
    asked_site.forget()


def _seed(blocked: bool) -> None:
    sheet.store.save(sheet.sheet_key("t2515"), {"title": "Coches", "items": [
        {"title": "Fiat Tipo", "price": "€ 10.490", "url": "https://www.autoscout24.es/anuncios/fiat-tipo-1"}],
        "sources": [{"name": "coches.net", "url": "https://www.coches.net/", "status": "blocked" if blocked else "ok"}]})


def test_a_blocked_site_is_named_with_where_the_rows_came_from():
    _seed(blocked=True)
    out = asked_site.note("busca anuncios de coches diésel en coches.net", ["Fiat Tipo — € 10.490"])
    assert out == "Ojo: coches.net me bloqueó el acceso, así que estos vienen de autoscout24.es."
    assert asked_site.note("busca en coches.net", ["Fiat Tipo — € 10.490"]) == "", "said once"


def test_rows_from_the_asked_site_say_nothing():
    _seed(blocked=False)
    assert asked_site.note("busca en autoscout24.es", ["Fiat Tipo — € 10.490"]) == ""
    assert asked_site.note("busca un coche diésel", ["Fiat Tipo — € 10.490"]) == "", "no site named, nothing owed"


def test_not_blocked_but_elsewhere_still_says_where(monkeypatch):
    _seed(blocked=False)
    out = asked_site.note("mira en coches.net", ["Fiat Tipo — € 10.490"])
    assert out.startswith("Ojo: de coches.net no he sacado nada") and "autoscout24.es" in out


def test_the_delivery_backstop_carries_it(monkeypatch):
    _seed(blocked=True)
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("coche diésel", ["Fiat Tipo — € 10.490"]))
    window = [{"role": "user", "content": "Busca anuncios de coches diésel en coches.net."},
              {"role": "assistant", "content": "Hecho."}, {"role": "user", "content": "¿qué te sale?"}]
    out = delivery.apply_to_reply("Te aviso en cuanto tenga algo.", window, heard_now="¿qué te sale?")
    assert "«Fiat Tipo — € 10.490»" in out and "coches.net me bloqueó el acceso" in out

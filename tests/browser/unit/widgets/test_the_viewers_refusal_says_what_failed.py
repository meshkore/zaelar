"""The viewer's refusals say WHAT failed, in his language (`show-real-photo-of-a-new-car__es`, 2026-10-14).

Its refusals carried only the model-facing `error`, so `refusal_line` fell back to the generic «la tarjeta
Imágenes no lo ha aceptado» — said twice, word for word, with nothing about what went wrong. Each refusal now
names an i18n key (`say`) that exists in every product language.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture()
def data(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.imagenes import data as d
    d.apply_action("clear")
    return d


def _refusals(d):
    return [d.apply_action("show", {"items": []}), d.apply_action("next", {}), d.apply_action("select", {"item": "1"}),
            d.apply_action("wallpaper", {}), d.apply_action("slideshow", {})]


def test_every_empty_viewer_refusal_names_a_bundle_key(data):
    bundles = {c: json.loads((ENGINE / "i18n" / "bundles" / f"{c}.json").read_text("utf-8")) for c in ("es", "en")}
    for r in _refusals(data):
        assert r["ok"] is False and r.get("say", "").startswith("widgets.imagenes."), r
        for code, b in bundles.items():
            assert b.get(r["say"]), f"{r['say']} missing in {code}"


@pytest.mark.parametrize("code,needle", [("es", "foto"), ("en", "picture")])
def test_the_operator_hears_that_line_not_the_generic_one(data, monkeypatch, code, needle):
    from i18n import langs
    from nucleo.flash import refusal_line as RL
    monkeypatch.setattr(langs, "current_code", lambda: code)
    line = asyncio.run(RL.said("imagenes", data.apply_action("show", {"items": []})))
    assert needle in line.lower() and "no llegó" not in line, line

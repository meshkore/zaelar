"""«Minimise that» with several cards open means the card ON TOP — the one that just opened.

Measured 2026-09-27 (demo pass v7, A2): the monitor search opened its sheet over the contacts and agenda cards the
INIT had left, and «Minimise that while you work» found «several cards, none at full screen» → fell through to the
model, which said «tucking it out of your way» and minimised nothing. The canvas already reports each card's z.
"""
from nucleo.actionmap import executor


def _run(monkeypatch, open_ids, layout):
    from server import voice_api
    from memory import api as memapi
    monkeypatch.setattr(voice_api, "open_instances", lambda: open_ids)
    monkeypatch.setattr(memapi, "state", lambda: {"maximized_widget": ""})
    monkeypatch.setattr(memapi, "kv_get", lambda k: {"items": layout} if k == "canvas_layout" else None)
    seen = []
    ok = executor.execute({"do": "minimize", "widget": "*"},
                          lambda kind, label, **k: seen.append((label, (k.get("extra") or {}).get("id"))),
                          phrase="Minimise that while you work.")
    return ok, seen


def test_the_card_on_top_is_the_one_minimised(monkeypatch):
    ok, seen = _run(monkeypatch, ["contactos", "agenda", "results::94b220-ls1"],
                    [{"id": "contactos", "z": "3", "min": "0"}, {"id": "agenda", "z": "4", "min": "0"},
                     {"id": "results::94b220-ls1", "z": "7", "min": "0"}])
    assert ok and ("minimize", "results::94b220-ls1") in seen, seen


def test_a_minimised_card_is_never_that(monkeypatch):
    ok, seen = _run(monkeypatch, ["agenda", "results::a"],
                    [{"id": "agenda", "z": "4", "min": "0"}, {"id": "results::a", "z": "9", "min": "1"}])
    assert ok and ("minimize", "agenda") in seen, seen


def test_a_tie_still_steps_aside(monkeypatch):
    ok, seen = _run(monkeypatch, ["agenda", "contactos"],
                    [{"id": "agenda", "z": "4", "min": "0"}, {"id": "contactos", "z": "4", "min": "0"}])
    assert ok is False and not seen

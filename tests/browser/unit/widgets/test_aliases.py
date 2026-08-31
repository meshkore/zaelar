"""V2-082 — surgical editing of widget aliases (`widgets/aliases.py`): add/remove, collision guard (widget
and system surface), canonical-name guard, lazy migration of keywords. Isolates the filesystem with a toy
manifest in tmp_path plus monkeypatching of the path and registry."""
import json

import pytest

from widgets import aliases


@pytest.fixture
def toy(tmp_path, monkeypatch):
    """A 'demo' widget with name+keywords (without `aliases` yet → tests lazy migration) and a controlled
    registry (demo + another 'vecino' widget with 'ocupado' + a 'chat' system surface)."""
    man = {"id": "demo", "title": "Demo", "keywords": ["demonio", "prueba"], "entry": "widget.js"}
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man), encoding="utf-8")

    monkeypatch.setattr(aliases, "_manifest_path", lambda wid: str(p) if aliases._safe(wid) == "demo" else "/nope")
    monkeypatch.setattr(aliases, "_load", lambda wid: (json.loads(p.read_text(encoding="utf-8")), str(p))
                        if aliases._safe(wid) == "demo" else (None, "/nope"))
    # Neighbor registry for collisions (does not touch the real catalog)
    import widgets.registry as registry
    reg = [
        {"id": "demo", "name": "Demo", "aliases": ["Demo", "demonio", "prueba"], "surface": "user"},
        {"id": "vecino", "name": "Vecino", "aliases": ["Vecino", "ocupado"], "surface": "user"},
        {"id": "chat", "name": "Chat", "aliases": ["Chat", "muro"], "surface": "system"},
    ]
    monkeypatch.setattr(registry, "registry", lambda: reg)
    monkeypatch.setattr(aliases, "_write", lambda man, path, al: p.write_text(
        json.dumps({**man, "aliases": al}, ensure_ascii=False), encoding="utf-8"))
    return p


def _aliases(p):
    return json.loads(p.read_text(encoding="utf-8")).get("aliases")


def test_add_new_alias(toy):
    r = aliases.add("demo", "banco de pruebas")
    assert r["ok"] and "banco de pruebas" in r["aliases"]
    # Lazy migration: keywords were seeded as aliases + the name
    assert "Demo" in r["aliases"] and "demonio" in r["aliases"]
    assert "banco de pruebas" in _aliases(toy)


def test_add_is_idempotent(toy):
    aliases.add("demo", "extra")
    r = aliases.add("demo", "EXTRA")            # same alias (case-insensitive) → unchanged
    assert r["ok"] and r.get("unchanged")


def test_add_collision_with_other_widget(toy):
    r = aliases.add("demo", "ocupado")          # already owned by 'vecino'
    assert not r["ok"] and r["owner"] == "vecino"


def test_add_collision_with_system_surface(toy):
    r = aliases.add("demo", "muro")             # already owned by the 'chat' surface
    assert not r["ok"] and r["owner"] == "chat"


def test_remove_alias(toy):
    aliases.add("demo", "quitable")
    r = aliases.remove("demo", "quitable")
    assert r["ok"] and "quitable" not in r["aliases"]


def test_cannot_remove_canonical_name(toy):
    r = aliases.remove("demo", "Demo")
    assert not r["ok"] and "nombre" in r["error"]


def test_add_to_unknown_widget(toy):
    r = aliases.add("fantasma", "x")
    assert not r["ok"] and "no existe" in r["error"]

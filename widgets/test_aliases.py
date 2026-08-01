"""V2-082 — edición quirúrgica de alias de widget (`widgets/aliases.py`): add/remove, guard de colisión (widget
y superficie de sistema), guard del nombre canónico, migración perezosa de keywords. Aísla el filesystem con un
manifest de juguete en tmp_path + monkeypatch de la ruta y el registro."""
import json

import pytest

from widgets import aliases


@pytest.fixture
def toy(tmp_path, monkeypatch):
    """Un widget 'demo' con name+keywords (sin `aliases` aún → prueba la migración perezosa) y un registro
    controlado (demo + otro widget 'vecino' con 'ocupado' + una superficie de sistema 'chat')."""
    man = {"id": "demo", "title": "Demo", "keywords": ["demonio", "prueba"], "entry": "widget.js"}
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man), encoding="utf-8")

    monkeypatch.setattr(aliases, "_manifest_path", lambda wid: str(p) if aliases._safe(wid) == "demo" else "/nope")
    monkeypatch.setattr(aliases, "_load", lambda wid: (json.loads(p.read_text(encoding="utf-8")), str(p))
                        if aliases._safe(wid) == "demo" else (None, "/nope"))
    # registro de vecinos para las colisiones (no toca el catálogo real)
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
    # migración perezosa: los keywords se sembraron como alias + el nombre
    assert "Demo" in r["aliases"] and "demonio" in r["aliases"]
    assert "banco de pruebas" in _aliases(toy)


def test_add_is_idempotent(toy):
    aliases.add("demo", "extra")
    r = aliases.add("demo", "EXTRA")            # mismo alias (case-insensitive) → sin cambios
    assert r["ok"] and r.get("unchanged")


def test_add_collision_with_other_widget(toy):
    r = aliases.add("demo", "ocupado")          # ya de 'vecino'
    assert not r["ok"] and r["owner"] == "vecino"


def test_add_collision_with_system_surface(toy):
    r = aliases.add("demo", "muro")             # ya de la superficie 'chat'
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

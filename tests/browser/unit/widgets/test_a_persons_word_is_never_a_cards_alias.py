"""One owner per word, and a shipped manifest is never his file (V2-854 F4).

Measured on his engine (2026-11-05): asked to «add the aliases Raquel to Rakel Karó», the model called
`manage_widget_alias` and «Raquel» became an alias of the CONTACTS card — and the door rewrote the tracked
`widgets/contactos/manifest.json` (reverted by hand). Here, on a synthetic catalog and directory:

  · a word the directory resolves to a person (an alias he gave her, or every word a whole word of her name) is
    refused at the card's door, which names the person's door (`contactos.set_alias`); a substring of a longer name,
    a group's name and a word nobody carries are not a person's;
  · a card whose folder is engine source keeps his words in the per-tenant overlay — the manifest's bytes never
    move — and the catalog, the registry and `identify` all read them; removing one of its shipped words is his
    overlay too; a card of his own (generated) keeps writing its own manifest.
"""
from __future__ import annotations

import json

import pytest

import widgets.directory  # noqa: F401 — imported before the roots move (the package path follows the roots)
import widgets.textmatch  # noqa: F401
from widgets import aliases, paths, registry, runtime

PEOPLE = [
    {"id": "c1", "kind": "person", "name": "Rakel Moreno Vidal", "favorite": True, "aliases": ["Raquel"],
     "phone": "+34 600 000 001"},
    {"id": "c2", "kind": "person", "name": "Raquel Jiménez", "phone": "+34 600 000 002"},
    {"id": "c3", "kind": "person", "name": "Manu Raquel Ortiz", "phone": "+34 600 000 003"},
    {"id": "c4", "kind": "person", "name": "Jordi Puig", "email": "jordi@example.test"},
    {"id": "c5", "kind": "person", "name": "Marisol Fuentes", "phone": "+34 600 000 005"},
    {"id": "g1", "kind": "group", "name": "Recetas", "channels": [{"platform": "whatsapp", "chatId": "1-2@g.us"}]},
]


def _widget(root, wid, title, alias_list):
    d = root / wid
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"id": wid, "title": title, "aliases": alias_list,
                                                 "entry": "widget.js"}, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    (d / "widget.js").write_text("export default {}\n", encoding="utf-8")
    return d / "manifest.json"


@pytest.fixture
def world(tmp_path, monkeypatch):
    builtin, ws = tmp_path / "engine_widgets", tmp_path / "ws"
    (ws / "widgets").mkdir(parents=True)
    monkeypatch.setattr(paths, "BUILTIN_ROOT", str(builtin))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(ws))
    monkeypatch.setattr("widgets.directory._contacts", lambda: [dict(c) for c in PEOPLE])
    shipped = _widget(builtin, "contactos", "Contactos", ["Contactos", "directorio"])
    _widget(builtin, "notas", "Notas", ["Notas", "apuntes"])
    mine = _widget(ws / "widgets", "huerto", "Huerto", ["Huerto"])
    runtime.invalidate()
    yield {"shipped": shipped, "bytes": shipped.read_bytes(), "mine": mine, "ws": ws}
    runtime.invalidate()


@pytest.mark.parametrize("word", ["Raquel", "raquel", "RAKEL MORENO", "Jordi"])
def test_a_word_that_names_a_person_is_refused_and_names_her_door(world, word):
    r = aliases.add("contactos", word)
    assert not r["ok"] and r.get("person") and r["door"] == aliases.PERSON_DOOR, r
    assert r["contacts"], "the refusal does not say whose word it is"
    assert world["shipped"].read_bytes() == world["bytes"], "the shipped manifest moved"
    assert word.lower() not in [a.lower() for a in registry.registry()[0]["aliases"] + registry.registry()[1]["aliases"]]


@pytest.mark.parametrize("word", ["Mari", "Recetas", "agenda de la casa", "Sol"])
def test_a_word_nobody_carries_a_substring_or_a_group_is_not_a_person(world, word):
    r = aliases.add("notas", word)
    assert r["ok"], r


def test_a_shipped_card_keeps_his_words_in_the_overlay_never_in_its_manifest(world):
    r = aliases.add("contactos", "mi libreta")
    assert r["ok"] and "mi libreta" in r["aliases"]
    assert world["shipped"].read_bytes() == world["bytes"], "the door rewrote a tracked manifest"
    ov = json.loads((world["ws"] / "widgets" / "_data" / "_system" / "aliases.json").read_text(encoding="utf-8"))
    assert ov["contactos"]["add"] == ["mi libreta"]
    # every reader of the catalog hears it: the catalog, the registry (collisions) and identify (opening)
    assert "mi libreta" in (runtime.get("contactos") or {}).get("aliases", [])
    assert aliases.add("notas", "mi libreta").get("owner") == "contactos", "another card could take his word"
    assert (runtime.identify("abre mi libreta") or {}).get("match") == "contactos"
    # removing a SHIPPED word is his overlay too, and the manifest still does not move
    r = aliases.remove("contactos", "directorio")
    assert r["ok"] and "directorio" not in [a.lower() for a in r["aliases"]]
    assert world["shipped"].read_bytes() == world["bytes"]
    assert "directorio" not in [a.lower() for a in (runtime.get("contactos") or {}).get("aliases", [])]


def test_his_own_card_still_writes_its_own_manifest(world):
    r = aliases.add("huerto", "mi jardín")
    assert r["ok"]
    assert "mi jardín" in json.loads(world["mine"].read_text(encoding="utf-8"))["aliases"]
    assert not (world["ws"] / "widgets" / "_data" / "_system" / "aliases.json").exists()

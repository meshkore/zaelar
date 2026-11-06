"""Every language is one folder of packs, and onboarding generates the whole folder (2026-10-21).

The words of a language lived in five shapes: a UI bundle, a Python table of spoken lines whose defaults were
Spanish, a phrasebook module, an action-map seed folder and a filler store nothing wrote. A new language got the
UI and two packs; everything the agent SAID fell back to English through a reader that also called the language
English. Now `i18n/genesis/<code>/` holds every pack of a shipped language, `i18n.init.prepare` generates the same
set for any other one, and every reader goes through `i18n.packs`.
"""
from __future__ import annotations

import asyncio
import json
import re

import pytest

from i18n import packs

SHIPPED = ("ui", "voice", "smalltalk", "actionmap")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, "_workspace_generated", lambda: tmp_path / "generated")
    from i18n import langs, runtime
    langs.invalidate()
    runtime.invalidate()
    yield tmp_path / "generated"
    langs.invalidate()
    runtime.invalidate()


def test_each_shipped_language_has_every_pack_with_the_same_shape():
    for code in packs.PRESET:
        for name in SHIPPED:
            assert packs.preset_path(code, name).is_file(), f"{code}/{name}.json is missing"
    for name in ("voice", "actionmap"):
        en, es = packs.texts(name, packs.preset(name, "en")), packs.texts(name, packs.preset(name, "es"))
        if name == "voice":
            shape = lambda flat: {re.sub(r"\.\d+(?=\.|$)", ".#", k) for k in flat}   # lists may differ in length
            assert shape(en) == shape(es), f"en/es voice packs differ: {sorted(shape(en) ^ shape(es))[:8]}"
            for k in set(en) & set(es):
                assert set(re.findall(r"\{\w+\}", en[k])) == set(re.findall(r"\{\w+\}", es[k])), f"placeholders of {k}"


def test_the_spoken_table_has_no_language_in_its_code():
    """The dataclass is the SCHEMA; a Spanish default there was a second Spanish table nobody translated."""
    from dataclasses import MISSING, fields

    from i18n.langspec import LangSpec
    for f in fields(LangSpec):
        if f.default is not MISSING and isinstance(f.default, str):
            assert f.default == "", f"LangSpec.{f.name} still defaults to words: {f.default[:40]!r}"
        if f.default is not MISSING and isinstance(f.default, tuple):
            assert f.default == (), f"LangSpec.{f.name} still defaults to words"


def test_a_language_with_nothing_generated_speaks_english_not_spanish(ws, monkeypatch):
    from i18n import langs
    (ws / "fr").mkdir(parents=True)
    packs.write_json(ws / "fr" / "ui.json", {"version": 1, "strings": {"chat.send": "Envoyer"}, "src": {}})
    monkeypatch.setenv("ZAELAR_LANGUAGE", "fr")
    assert langs.current_code() == "fr", "an onboarded language is collapsed to another"
    assert langs.spec().show_ack == packs.preset("voice", "en")["show_ack"]
    assert langs.words("weekdays") == tuple(packs.preset("voice", "en")["weekdays"])


def test_an_upgrade_translates_only_what_changed(ws, monkeypatch):
    from i18n.init import ensure, generate
    seen = []

    async def fake_translate(code, missing, register="ui"):
        seen.append(set(missing))
        return {k: f"FR {v}" for k, v in missing.items()}

    monkeypatch.setattr(generate, "translate", fake_translate)
    asyncio.run(ensure.ensure_pack("fr", "voice"))
    gen = json.loads(packs.generated_path("fr", "voice").read_text("utf-8"))
    key = next(iter(gen["src"]))
    gen["src"][key] = "an older English"
    packs.write_json(packs.generated_path("fr", "voice"), gen)
    asyncio.run(ensure.ensure_pack("fr", "voice"))
    assert seen[-1] == {key}


def test_a_pack_generated_before_the_folders_is_moved_not_regenerated(ws):
    ws.mkdir(parents=True)
    (ws / "de.json").write_text(json.dumps({"version": 1, "strings": {"chat.send": "Senden"}, "src": {}}), "utf-8")
    (ws / "de.aliases.json").write_text(json.dumps({"chat": ["unterhaltung"]}), "utf-8")
    assert packs.generated("ui", "de")["strings"]["chat.send"] == "Senden"
    assert packs.generated("aliases", "de") == {"chat": ["unterhaltung"]}
    assert not (ws / "de.json").exists() and (ws / "de" / "ui.json").is_file()

"""i18n.init.fillers + langs.pick_filler's generated-pool lookup (V2-122, 2026-08-17).

Same story as V2-101's alias pack, one step ahead of it: instead of the LLM generation call itself, this pass
scoped down to "fail gracefully for non-preset languages" (operator's explicit call) — so what's tested here is
the READ path and the fact it changes nothing for es/en today, ready for `save()` to be called by a future
generation step without touching `pick_filler()` again.
"""
from __future__ import annotations

from i18n.init import fillers
from voice.engine.core import langs


def test_read_with_nothing_generated_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fillers, "_GEN_DIR", tmp_path)
    assert fillers.read("fr") == []


def test_save_then_read_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(fillers, "_GEN_DIR", tmp_path)
    fillers.save("fr", ["Voyons…", "Hmm…", ""])   # empty strings dropped on read
    assert fillers.read("fr") == ["Voyons…", "Hmm…"]


def test_save_is_crash_safe_atomic_write(tmp_path, monkeypatch):
    monkeypatch.setattr(fillers, "_GEN_DIR", tmp_path)
    fillers.save("fr", ["Voyons…"])
    assert not (tmp_path / "fr.fillers.json.tmp").exists(), "the tmp file must be replaced, never left behind"
    assert (tmp_path / "fr.fillers.json").exists()


def test_pick_filler_prefers_the_generated_pool_when_one_exists(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs._generated_fillers", lambda code: ["SOLO ESTE"])
    assert langs.pick_filler(code="es") == "SOLO ESTE"


def test_pick_filler_falls_back_to_the_hardcoded_pool_when_nothing_generated(monkeypatch):
    monkeypatch.setattr("voice.engine.core.langs._generated_fillers", lambda code: [])
    picked = langs.pick_filler(code="es")
    assert picked in langs.spec("es").fillers


def test_generated_fillers_lookup_never_raises_and_fails_open(monkeypatch, tmp_path):
    """A corrupt/unreadable generated file must not take the lead-in filler down with it — `read()` already
    fails open (bare except), this just locks that `_generated_fillers` doesn't add a new way to blow up."""
    monkeypatch.setattr(fillers, "_GEN_DIR", tmp_path)
    (tmp_path / "es.fillers.json").write_text("not valid json{{{", encoding="utf-8")
    assert langs._generated_fillers("es") == []
    # …and the whole pick_filler call still resolves to a real phrase from the hardcoded es pool.
    picked = langs.pick_filler(code="es")
    assert picked in langs.spec("es").fillers


def test_existing_es_en_behavior_is_unchanged_with_no_generated_files(tmp_path, monkeypatch):
    """The read-order change must be invisible for both preset languages today — no generated file exists for
    either in a fresh install, so both keep drawing from exactly the same hardcoded pool as before this pass."""
    monkeypatch.setattr(fillers, "_GEN_DIR", tmp_path)
    for code in ("es", "en"):
        picked = langs.pick_filler(code=code)
        assert picked in langs.spec(code).fillers

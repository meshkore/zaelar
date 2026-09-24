"""First-run language onboarding (V2-101): the blocking modal's backend — detect.lock()'s onboarding
sequencing, the alias-pack generator, system_surfaces' additive alias lookup, and the two i18n_api escape
hatches (quick-pick chip / typed fallback) the modal offers when voice isn't an option.

Deliberately NOT covered here: `voice/engine/pipeline/agent.py`'s kickoff branch and the fail-open valve
inside `_maybe_detect_language` — both live in a large per-session closure with no extracted, importable
unit under test (same coverage shape as the rest of that file; see `tests/voice/unit/test_language_bootstrap.py`
for what IS unit-testable there). Validated by the manual smoke in the initiative doc instead."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# i18n.init.detect.lock(..., onboarding=...)
# ---------------------------------------------------------------------------

def _isolate_lock_side_effects(monkeypatch):
    """Neutralize the parts of lock() this module doesn't test (settings persistence, memory's canonical
    language, SSE emission) so each test below only exercises what it's actually asserting on."""
    import config.settings as cs
    monkeypatch.setattr(cs, "update", lambda d: None)
    from memory import api as memapi
    monkeypatch.setattr(memapi, "set_state", lambda fields: None)
    from i18n.init import detect
    monkeypatch.setattr(detect, "_should_cache", None, raising=False)


def test_onboarding_lock_for_a_preset_language_skips_translation_and_alias_generation(monkeypatch):
    """en/es are the whole point of staying fast: PRESET, so no LLM call for the bundle NOR the alias pack.
    Tracked via call lists, not a raise — both calls sit behind a broad try/except (a real safety net) that
    would silently swallow an AssertionError, masking a regression instead of failing loud on it."""
    from i18n.init import detect

    _isolate_lock_side_effects(monkeypatch)

    translate_calls = []
    from i18n.init import generate
    async def _track_translate(code, keys):
        translate_calls.append(code)
        return {}
    monkeypatch.setattr(generate, "translate", _track_translate)

    alias_calls = []
    from i18n.init import aliases
    async def _track_aliases(code):
        alias_calls.append(code)
        return {}
    monkeypatch.setattr(aliases, "ensure_aliases", _track_aliases)

    events = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: events.append((a, kw)))

    res = asyncio.run(detect.lock("es", onboarding=True))
    assert res["ok"] is True
    assert res["confirm_text"] == "Vale — ya está todo listo en tu idioma."
    assert translate_calls == [], "must not translate a PRESET language"
    assert alias_calls == [], "must not generate an alias pack for a PRESET language"
    phases = [kw.get("extra", {}).get("phase") for _, kw in events]
    assert phases == ["detected", "ready"], f"wrong order: {phases}"
    assert events[0][1]["extra"]["loading"] == "Preparando el agente, la interfaz y las comunicaciones en tu idioma…"
    # V2-732 — and it says there is NOTHING to prepare, which is what stops the frontend drawing a
    # preparing screen at all. The operator: «si no hay que hacer nada para idiomas inicializados, mejor
    # no mostrar NADA en ese caso». A step reported here would be a screen with nothing behind it.
    assert events[0][1]["extra"]["total"] == 0, events[0][1]["extra"]
    assert "progress" not in phases, "a no-op that returns in a millisecond is not progress"


def test_onboarding_lock_for_a_new_language_translates_the_loading_line_before_the_full_bundle(monkeypatch):
    """The whole point of the priority translate: the 'detected' SSE event must carry ALREADY-translated
    text, so the modal never shows a bare spinner with no words while the full bundle is still generating
    in the background. V2-672 widened it from one key to the whole set the first-run modal paints during
    that wait (the loader AND the folder step), so it returns a dict now."""
    from i18n.init import detect

    _isolate_lock_side_effects(monkeypatch)

    order = []

    async def _fake_priority_translate(code):
        order.append("priority")
        return {"onboarding.loading": "準備しています…", "onboarding.folder.skip": "スキップ"}
    monkeypatch.setattr(detect, "_priority_translate", _fake_priority_translate)

    from i18n import init as init_pkg

    async def _fake_prepare(code):
        order.append("prepare")
        return {}
    monkeypatch.setattr(init_pkg, "prepare", _fake_prepare)

    from i18n.init import aliases

    async def _fake_ensure_aliases(code):
        order.append("aliases")
        return {"code": code, "generated": 2}
    monkeypatch.setattr(aliases, "ensure_aliases", _fake_ensure_aliases)

    from i18n import runtime as rt
    monkeypatch.setattr(rt, "strings", lambda code: {"onboarding.confirmSpoken": "準備完了です。"})

    events = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: events.append((a, kw)))

    # BEFORE the lock: `_pending_steps` answers what is still missing, and locking is what stops it being
    # missing. Asking afterwards compares the denominator against a tree the lock has already changed.
    expected_total = len(detect._pending_steps("ja"))

    res = asyncio.run(detect.lock("ja", onboarding=True))

    assert order == ["priority", "prepare", "aliases"], "must translate the loading line BEFORE the slow full prepare"
    assert res["confirm_text"] == "準備完了です。"
    phases = [kw.get("extra", {}).get("phase") for _, kw in events]
    assert phases[0] == "detected" and phases[-1] == "ready", f"wrong order: {phases}"
    # V2-731/V2-732 — a language we have to BUILD is where the wait is real and the bar is worth having.
    # The denominator is whatever this language actually lacks; what is pinned is that it is NOT zero, that
    # it travels with the first event, and that every step reported matches it. (The exact number is not
    # asserted on purpose: `i18n/generated/` is not sandboxed by the root conftest — measured 2026-09-20 —
    # so a literal here would pass or fail on which languages this machine has tried before.)
    total = events[0][1]["extra"]["total"]
    assert total == expected_total >= 1, events[0][1]["extra"]
    steps = [kw["extra"]["done"] for _, kw in events if kw.get("extra", {}).get("phase") == "progress"]
    assert steps == list(range(1, len(steps) + 1)), (
        f"the steps must arrive once each and in order, never jumping backwards: {steps}")
    assert all(kw["extra"]["total"] == total for _, kw in events
               if kw.get("extra", {}).get("phase") == "progress"), "the scale must never move mid-run"
    assert all("code" not in kw["extra"] for _, kw in events
               if kw.get("extra", {}).get("phase") == "progress"), (
        "sse.js re-applies the language on any language event carrying a code — a progress report with "
        "one refetches the bundle once per step")
    assert events[0][1]["extra"]["loading"] == "準備しています…"
    assert events[0][1]["extra"]["strings"]["onboarding.folder.skip"] == "スキップ", (
        "the folder step runs DURING this wait, so its words have to travel with the same event")


def test_plain_non_onboarding_lock_never_touches_the_alias_pack(monkeypatch):
    """A manual ⚙ switch (or a repeat background detection) must stay exactly as cheap as it always was —
    alias-pack generation is scoped to the onboarding ceremony only, never a side effect of every lock()."""
    from i18n.init import detect

    _isolate_lock_side_effects(monkeypatch)

    from i18n import init as init_pkg
    monkeypatch.setattr(init_pkg, "prepare", lambda code: asyncio.sleep(0))

    alias_calls = []
    from i18n.init import aliases
    async def _track_aliases(code):
        alias_calls.append(code)
        return {}
    monkeypatch.setattr(aliases, "ensure_aliases", _track_aliases)

    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: None)

    res = asyncio.run(detect.lock("fr"))
    assert res["ok"] is True
    assert alias_calls == [], "plain (non-onboarding) lock must never generate an alias pack"


# ---------------------------------------------------------------------------
# i18n.init.aliases — the per-language voice-command alias pack
# ---------------------------------------------------------------------------

def test_ensure_aliases_generates_once_then_is_a_cheap_no_op(monkeypatch, tmp_path):
    from i18n.init import aliases

    monkeypatch.setattr(aliases, "_GEN_DIR", tmp_path)

    calls = []

    async def _fake_generate(code):
        calls.append(code)
        return {"feedback": ["フィードバック", "意見"], "chat": ["チャット"]}
    monkeypatch.setattr(asyncio, "to_thread", lambda fn, code: _fake_generate(code))

    res1 = asyncio.run(aliases.ensure_aliases("ja"))
    assert res1["generated"] == 2
    assert calls == ["ja"]

    res2 = asyncio.run(aliases.ensure_aliases("ja"))
    assert res2["generated"] == 0, "a second call must be a no-op — the pack is already on disk"
    assert calls == ["ja"], "must not re-generate"

    assert aliases.aliases_for("ja", "feedback") == ["フィードバック", "意見"]
    assert aliases.aliases_for("ja", "nonexistent-surface") == []


def test_ensure_aliases_fails_open_to_an_empty_pack(monkeypatch, tmp_path):
    from i18n.init import aliases

    monkeypatch.setattr(aliases, "_GEN_DIR", tmp_path)

    async def _boom(code):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(asyncio, "to_thread", lambda fn, code: _boom(code))

    res = asyncio.run(aliases.ensure_aliases("ar"))
    assert res["generated"] == 0
    assert aliases.aliases_for("ar", "feedback") == []


# ---------------------------------------------------------------------------
# widgets/system_surfaces.py — additive extension for a non-preset active language
# ---------------------------------------------------------------------------

def test_surfaces_extends_aliases_additively_for_a_non_preset_language(monkeypatch):
    from widgets import system_surfaces
    from i18n import runtime as rt

    monkeypatch.setattr(rt, "active_code", lambda: "ja")
    from i18n.init import aliases
    monkeypatch.setattr(aliases, "read", lambda code: {"feedback": ["フィードバック"]})

    surfaces = {s["id"]: s for s in system_surfaces.surfaces()}
    fb = surfaces["feedback"]
    assert "フィードバック" in fb["aliases"]
    assert "feedback" in fb["aliases"], "additive — the hardcoded es/en aliases must still be there"


def test_surfaces_never_touches_the_alias_pack_for_a_preset_language(monkeypatch):
    """`surfaces()` guards the alias lookup in a broad try/except (a real safety net — an unexpected error
    there must never break every voice command), so this checks the call NEVER HAPPENS via a tracking flag
    rather than a raise, which that guard would just silently swallow."""
    from widgets import system_surfaces
    from i18n import runtime as rt

    monkeypatch.setattr(rt, "active_code", lambda: "es")

    calls = []
    from i18n.init import aliases
    monkeypatch.setattr(aliases, "read", lambda code: (calls.append(code), {})[1])

    system_surfaces.surfaces()
    assert calls == [], "must not read a generated alias pack for a PRESET language"


# ---------------------------------------------------------------------------
# server/i18n_api.py — the modal's two escape hatches
# ---------------------------------------------------------------------------

def _client():
    from server.i18n_api import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_state_reports_whether_a_language_has_ever_been_chosen(monkeypatch):
    from i18n.init import detect
    monkeypatch.setattr(detect, "should_detect", lambda: True)
    r = _client().get("/api/i18n/state")
    assert r.json()["chosen"] is False

    monkeypatch.setattr(detect, "should_detect", lambda: False)
    r = _client().get("/api/i18n/state")
    assert r.json()["chosen"] is True


def test_choose_locks_onboarding_and_speaks_nothing(monkeypatch):
    """V2-765 — the click locks the language and SAYS nothing: there is no voice session behind the picker any
    more, and a proactive notice with none became a brain note repeating «ya está todo listo» after his first
    answer. The greeting of the session that starts afterwards is the first thing he hears."""
    from server import i18n_api

    captured = {}

    async def _fake_lock(code, *, onboarding=False):
        captured["code"] = code
        captured["onboarding"] = onboarding
        return {"ok": True, "code": code, "confirm_text": "Bonjour !"}
    monkeypatch.setattr(i18n_api._detect, "lock", _fake_lock)

    spoken = {}

    async def _fake_notify(title, text, **kw):
        spoken["text"] = text
    monkeypatch.setattr("voice.proactive.notify", _fake_notify)

    r = _client().post("/api/i18n/choose/fr")
    assert r.json()["ok"] is True
    assert captured == {"code": "fr", "onboarding": True}
    assert spoken == {}, "the click spoke over a session that does not exist"


def test_detect_text_classifies_then_locks_the_same_way_a_spoken_answer_would(monkeypatch):
    from server import i18n_api

    monkeypatch.setattr(i18n_api._detect, "classify", lambda text: "de")

    captured = {}

    async def _fake_lock(code, *, onboarding=False):
        captured["code"] = code
        return {"ok": True, "code": code, "confirm_text": None}
    monkeypatch.setattr(i18n_api._detect, "lock", _fake_lock)

    r = _client().post("/api/i18n/detect-text", json={"text": "Deutsch, bitte"})
    assert r.json()["ok"] is True
    assert captured["code"] == "de"


def test_detect_text_rejects_empty_input_without_calling_the_classifier(monkeypatch):
    from server import i18n_api

    def _boom(text):
        raise AssertionError("must not classify an empty/whitespace body")
    monkeypatch.setattr(i18n_api._detect, "classify", _boom)

    r = _client().post("/api/i18n/detect-text", json={"text": "  "})
    assert r.status_code == 400


def test_detect_text_reports_not_recognized_without_crashing(monkeypatch):
    from server import i18n_api

    monkeypatch.setattr(i18n_api._detect, "classify", lambda text: None)
    r = _client().post("/api/i18n/detect-text", json={"text": "asdkjhasdkjh"})
    assert r.json() == {"ok": False, "error": "not_recognized"}

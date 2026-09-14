"""A widget's NAME is a UI string, and the voice keeps answering to the one it was born with (V2-694).

The operator, on a session he had deliberately started in English: «el título de los widgets es en castellano…
una vez está inicializada la sesión en inglés, se usa en inglés». Nothing had switched his language — measured:
`stt_language` was `en` and every turn's prompt said so — the names were simply HARDCODED, in `manifest.json`,
by whoever built each widget, and V2-082 had frozen them on purpose because the voice resolver matches against
them.

That freeze is the interesting part, and it is what these cases pin. The name is now read from the bundles
(`widgets.<id>.name`), so it follows the operator's language like every other label; and BOTH spellings stay in
`aliases`, so «Messages» and «mensajería» open the same card. Translating the name without keeping the original
would have quietly retired half the vocabulary of every install that has ever spoken Castilian — a regression
with no error message anywhere, which is exactly the shape of failure this file exists to make loud.

The resolver is measured through its REAL doors (`widgets.runtime.identify`, `widgets.naming.resolve`), not by
re-reading the registry: `identify` builds its own lexical index straight off the manifests, and when this was
written it did NOT go through the registry — so with the bundles in place «messages» resolved to nothing while
resolving correctly one module over. A test that had asked the registry would have been green over that.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys

import pytest


def _with_language(code: str):
    """Reimport the widget layer under `code`. The lexical indexes are module-level caches keyed on the
    language, so the honest way to measure a language change is to make one."""
    os.environ["ZAELAR_LANGUAGE"] = code
    for name in [m for m in list(sys.modules) if m.startswith(("widgets", "i18n"))]:
        del sys.modules[name]
    from i18n import runtime as i18n_runtime
    i18n_runtime.invalidate()
    return importlib.import_module("widgets.registry"), importlib.import_module("widgets.runtime")


@pytest.fixture(autouse=True)
def _restore_language():
    """Put the module table back EXACTLY as it was — the purge above is the most expensive thing a test in
    this repo can do (2026-09-15).

    `_with_language` deletes every `widgets*`/`i18n*` entry from `sys.modules`, which is the honest way to
    measure a language change. Dropping the entries and walking away is not: the next module to import
    `widgets.store` gets a SECOND copy of it, built from scratch, whose `DATA_DIR` is recomputed at import
    time — so the session sandbox the root conftest installs is gone and the suite starts writing into the
    operator's REAL `widgets/_data`. And every test module that had already imported a widget holds the OLD
    object, so a fixture patching one copy no longer patches the one the product uses.

    MEASURED on the full run: 222 of the 229 reds in `tests/browser/unit` came from here, none of them
    reproducible in isolation, and the widget rows the suite left behind are indistinguishable from the
    operator's own. The originals are never garbage: they are held here and put back, so the purge lives and
    dies inside this file.
    """
    before = os.environ.get("ZAELAR_LANGUAGE")
    snapshot = {m: sys.modules[m] for m in list(sys.modules) if m.startswith(("widgets", "i18n"))}
    yield
    if before is None:
        os.environ.pop("ZAELAR_LANGUAGE", None)
    else:
        os.environ["ZAELAR_LANGUAGE"] = before
    for name in [m for m in list(sys.modules) if m.startswith(("widgets", "i18n"))]:
        del sys.modules[name]
    sys.modules.update(snapshot)
    try:                                           # the restored modules must re-read the restored language
        from i18n import runtime as _i18n_runtime
        _i18n_runtime.invalidate()
    except Exception:
        pass


# ── the label ────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_card_is_titled_in_the_operators_language():
    registry, _ = _with_language("en")
    rows = {r["id"]: r["name"] for r in registry.registry()}
    assert rows["mensajeria"] == "Messages", "an English session read «Mensajería» on the card — the whole report"
    assert rows["agenda"] == "Calendar"
    assert rows["torrent"] == "Downloads"

    registry, _ = _with_language("es")
    rows = {r["id"]: r["name"] for r in registry.registry()}
    assert rows["mensajeria"] == "Mensajería", "and a Castilian session must not start reading English"
    assert rows["agenda"] == "Agenda"
    assert rows["torrent"] == "Descargas"


def test_a_system_surface_is_named_in_the_operators_language_too():
    registry, _ = _with_language("es")
    rows = {r["id"]: r["name"] for r in registry.registry()}
    assert rows["config"] == "Ajustes"
    assert rows["vault"] == "Bóveda"


def test_a_widget_the_bundles_never_heard_of_keeps_its_manifest_name():
    """The fallback is not decoration: a widget the operator's own agent GENERATED has no bundle row and never
    will, and it still has to have a name."""
    registry, _ = _with_language("en")
    assert registry.display_name("widgets", "a-widget-nobody-shipped", "Mi contador") == "Mi contador"
    assert registry.display_name("surfaces", "not-a-surface", "Thing") == "Thing"


# ── the vocabulary ───────────────────────────────────────────────────────────────────────────────────────────

def test_both_spellings_open_the_same_card_in_an_english_session():
    _, runtime = _with_language("en")
    for said in ("messages", "mensajería", "mensajeria"):
        assert runtime.identify(said).get("match") == "mensajeria", f"«{said}» did not reach the card"
    for said in ("downloads", "descargas"):
        assert runtime.identify(said).get("match") == "torrent", f"«{said}» did not reach the card"


def test_the_castilian_name_is_still_an_alias_when_the_ui_is_english():
    """⚠️ Measured, and worth writing down: EVERY shipped manifest already repeats its own name as its first
    alias, so for the live catalog this property has TWO independent guards and removing the one added here
    changes nothing (the disarm came back green and was right to). The guard that can stand alone is the one
    for a manifest that does NOT repeat it — a widget the operator's agent generated, or one that only ever
    had `keywords` — so that is what is measured, with a hand-built manifest rather than a convenient one."""
    registry, _ = _with_language("en")
    ident = registry.widget_identity({"id": "mensajeria", "name": "Mensajería",
                                      "aliases": ["mis mensajes", "chats"]})
    aliases = [a.lower() for a in ident["aliases"]]
    assert ident["name"] == "Messages"
    assert "messages" in aliases and "mensajería" in aliases, (
        "the name the widget was born with must stay in its vocabulary — dropping it silently retires half the "
        f"words every Castilian install has ever used: {aliases}")


def test_the_lexical_index_follows_a_language_change_inside_one_process():
    """The engine does not restart when the operator switches language in ⚙ — it calls `settings.update`, which
    invalidates, and every index has to notice. Each of these indexes is a module-level cache, so measuring this
    by REIMPORTING the modules would measure the import and not the cache: the language moves here in place."""
    _, runtime = _with_language("es")
    assert runtime.identify("mensajería").get("match") == "mensajeria"
    assert runtime.identify("messages").get("match") is None, "precondition: English is not the Castilian vocabulary"

    from i18n import runtime as i18n_runtime
    os.environ["ZAELAR_LANGUAGE"] = "en"
    i18n_runtime.invalidate()

    assert runtime.identify("messages").get("match") == "mensajeria", (
        "after a live language change the voice still did not know the word on the card — the lexical index is "
        "cached and nothing keyed it on the language")
    assert runtime.identify("mensajería").get("match") == "mensajeria", "…and the old word must still work"


def test_a_language_with_no_row_for_a_name_falls_back_to_ENGLISH_not_to_castilian():
    """English is the manifest language of the bundles (`i18n.runtime.BASE`), so it is what an incomplete
    generated bundle degrades to. Falling back to the MANIFEST instead would hand a Swedish operator Castilian —
    a language nobody chose, arriving from a file they never saw."""
    registry, _ = _with_language("sv")           # no bundle shipped, none generated in a test workspace
    rows = {r["id"]: r["name"] for r in registry.registry()}
    assert rows["mensajeria"] == "Messages", rows["mensajeria"]
    assert rows["torrent"] == "Downloads"


def test_a_system_surface_is_reachable_by_its_translated_name():
    """⚠️ Same «two guards» shape as the widget aliases, and measured rather than assumed: almost every surface
    already lists its Castilian word in the FIXED alias table, so the translated name adds nothing for those.
    The wizard is the one whose full name («Asistente de configuración») is NOT in that table, so it is the case
    that can only pass because the surface index learned the label — which is the property that matters for a
    language we generate later, where NONE of the hardcoded aliases will be in the operator's own words."""
    _, runtime = _with_language("es")
    assert runtime.identify("asistente de configuración").get("system") == "wizard"


def test_a_GENERATED_language_renames_the_cards_and_the_vocabulary_with_them(tmp_path, monkeypatch):
    """The case the whole batch is FOR: a language nobody shipped a bundle for. `i18n.init.generate` translates
    the English manifest at onboarding, so these rows arrive with the rest of the interface and nothing here is
    special-cased for them.

    The switch happens IN PROCESS, from Castilian, on modules already imported and already holding their caches
    — which is what the ⚙ actually does. It is also the only way to close one disarm: every surface's Castilian
    AND English words are already in the FIXED alias table, so keying the surface index on the language changes
    nothing for es/en, and removing that key stayed green until a THIRD language was in play. What it buys is
    «Installationsguide» reaching the wizard, which exists nowhere but a generated bundle.
    """
    _, runtime = _with_language("es")
    registry = importlib.import_module("widgets.registry")
    assert {r["id"]: r["name"] for r in registry.registry()}["mensajeria"] == "Mensajería"
    assert runtime.identify("installationsguide").get("system") is None, "precondition: Swedish is not loaded"

    from i18n import store as i18n_store, runtime as i18n_runtime
    monkeypatch.setattr(i18n_store, "_GEN_DIR", tmp_path)
    (tmp_path / "sv.json").write_text(json.dumps({"version": 1, "src": {}, "strings": {
        "widgets.mensajeria.name": "Meddelanden",
        "surfaces.wizard.name": "Installationsguide",
    }}, ensure_ascii=False), encoding="utf-8")
    os.environ["ZAELAR_LANGUAGE"] = "sv"
    i18n_runtime.invalidate()

    rows = {r["id"]: r for r in registry.registry()}
    assert rows["mensajeria"]["name"] == "Meddelanden", "a generated language must rename the card"
    assert rows["wizard"]["name"] == "Installationsguide"
    assert rows["torrent"]["name"] == "Downloads", "…and a key it has no row for degrades to English"

    assert runtime.identify("meddelanden").get("match") == "mensajeria", \
        "the operator has to be able to SAY what the card says"
    assert runtime.identify("installationsguide").get("system") == "wizard", \
        "the SURFACE index did not rebuild — it is cached, and nothing keyed it on the language"
    assert runtime.identify("mensajería").get("match") == "mensajeria", \
        "…and the word the widget shipped with never stops working"


def test_the_workers_door_and_the_voices_door_agree():
    """`naming.resolve` (the worker bridge) went through the registry and therefore answered to a translated
    name from the first minute; `runtime.identify` (the voice) did not. Two doors into one namespace disagreeing
    about what a widget is called is the V2-555 class, so they are measured together."""
    _, runtime = _with_language("en")
    naming = importlib.import_module("widgets.naming")
    for said in ("messages", "calendar", "downloads", "browser", "files"):
        by_voice = runtime.identify(said).get("match")
        by_worker = naming.resolve(said)[0]
        assert by_voice and by_voice == by_worker, f"«{said}»: voice={by_voice!r} worker={by_worker!r}"


def test_an_ambiguous_phrase_is_read_back_with_the_label_the_operator_can_see():
    """The candidate's title is what a «¿cuál te enseño?» question says out loud (V2-605), so it is the label on
    screen and not the manifest's own wording."""
    _, runtime = _with_language("en")
    cands = runtime.identify("messages").get("candidates") or []
    assert cands and cands[0]["title"] == "Messages", cands


# ── the seam that keeps it from going stale ──────────────────────────────────────────────────────────────────

def test_the_language_seam_drops_the_cached_names():
    """`i18n.runtime.text` caches per language and `registry()` is rebuilt on every prompt compose, so without
    an explicit invalidation a language change would keep naming cards in the language just left. The check is
    on the CALL SITE: `config.settings.update` is the one door both the ⚙ and first-run detection go through."""
    src = (importlib.import_module("config.settings").__file__)
    body = open(src, encoding="utf-8").read()
    # COMMENT-STRIPPED: this file EXPLAINS the invalidation in prose right above it, so a scan of the raw source
    # stays green with the call deleted — the V2-615 trap, and this guard's own first disarm walked into it.
    body = re.sub(r"(?m)#.*$", "", body)
    i = body.index('if "stt_language" in applied')
    window = body[i:i + 1200]
    # The CALL, not the words: the branch's own `logger.warning(f"update: i18n.invalidate failed …")` contains
    # both names, so a scan for them stayed green with the call deleted — this guard's own disarm found that.
    assert "_i18n.invalidate()" in window, \
        "a language change must drop the cached bundle, or every card keeps its old name"
    assert "_wreg.refresh_state()" in window, \
        "…and refresh the registry projection the prompt reads, for the same reason"

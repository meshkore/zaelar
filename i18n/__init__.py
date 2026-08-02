"""
i18n — the multilingual subsystem (V2-089). Lets zaelar's UI + operator interaction adapt to ANY language.

Two clearly-separated sides (this is the architecture the whole subsystem is organized around):

  • i18n.runtime — EXECUTION / hot path. Import-cheap, deterministic, no LLM. Serves UI strings for the active
    language (preset bundles from i18n/bundles/, generated ones from the store), reports state, diffs what's
    missing. This is all the running server touches per request.

  • i18n.init   — INITIALIZATION. Occasional, may call an LLM (translate a new language) or STT (detect it),
    can take seconds. Runs at boot / first-run / language-switch / upgrade, behind a 'preparing language' veil.
    Preparation ("best of both worlds"): ship en+es preset; generate any other language on first contact and
    top it up on every upgrade — via ONE idempotent entry, i18n.init.prepare(code).

  • i18n.store  — persistence of GENERATED bundles (workspace, out of the repo).

Data (source of truth): i18n/bundles/en.json = English manifest (every key → English); i18n/bundles/es.json =
preset Spanish. Adding a UI string ⇒ add its key to en.json (+ es.json for the preset); every other language is
regenerated from it on next init.
"""
from __future__ import annotations

from i18n.runtime import (BASE, MANIFEST_VERSION, PRESET, active_code, available, bundle,
                          manifest, missing_keys, state, strings)

__all__ = ["BASE", "MANIFEST_VERSION", "PRESET", "active_code", "available", "bundle",
           "manifest", "missing_keys", "state", "strings"]

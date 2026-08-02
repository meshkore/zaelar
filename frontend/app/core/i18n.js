// ============================================================================
// i18n.js — runtime UI localization for the frontend (V2-089 multilingual).
//
// SINGLE SOURCE OF TRUTH = the backend JSON bundles under config/i18n/ (English
// is the base/manifest; Spanish is preset; ANY other language is generated on
// the fly by the i18n engine — see .meshkore/docs/architecture/zaelar-i18n.md).
// The frontend never hardcodes copy: it FETCHES the active bundle from
// /api/i18n/bundle/<code> and caches it in localStorage, so repeat visits paint
// instantly (no flash) while the boot veil covers the very first fetch.
//
// t(key) is REACTIVE: it reads store.lang(), so every t() used inside a dom.js
// function-prop or function-child re-renders the moment the active language
// changes (applyLang) — no page reload, no voice reconnect for the UI.
//
// Resolution order: active-language bundle → English base → the key itself.
// English is guaranteed complete (it's the manifest), so it's always a safe net.
// ============================================================================
import * as store from "./store.js?v=2";

const BUNDLES = {};            // code -> { key: string }
const _loading = {};           // code -> Promise (dedupe concurrent fetches)
const CACHE_KEY = (code) => "hb_i18n_" + code;

export function registerBundle(code, dict) { if (dict) BUNDLES[String(code)] = dict; }
export function hasBundle(code) { return !!BUNDLES[String(code)]; }
export function available() { return Object.keys(BUNDLES); }

// Hydrate synchronously from the localStorage cache at module load, so the FIRST paint already has strings
// (English base + the last active language) with zero network wait. The fetch below then reconciles.
(function hydrate() {
  for (const code of ["en", store.lang()]) {
    try { const raw = localStorage.getItem(CACHE_KEY(code)); if (raw) BUNDLES[code] = JSON.parse(raw); } catch (_) {}
  }
})();

// t(key, params?) — localized string. Reads store.lang() (reactive dependency).
export function t(key, params) {
  const code = store.lang();
  const dict = BUNDLES[code] || BUNDLES.en || {};
  let s = dict[key];
  if (s == null) s = (BUNDLES.en || {})[key];
  if (s == null) s = key;                 // last resort: show the key (visible = "needs a string")
  if (params) for (const k in params) s = s.split("{" + k + "}").join(String(params[k]));
  return s;
}

// loadBundle(code) — ensure a bundle is in memory, fetching it from the backend (which serves presets from
// config/i18n/ and generated languages the engine produced). Caches to localStorage for a flash-free next boot.
export async function loadBundle(code) {
  code = String(code || "en");
  if (_loading[code]) return _loading[code];
  _loading[code] = (async () => {
    try {
      const r = await fetch("/api/i18n/bundle/" + encodeURIComponent(code), { cache: "no-cache" });
      const d = await r.json();
      if (d && d.strings && Object.keys(d.strings).length) {
        BUNDLES[code] = d.strings;
        try { localStorage.setItem(CACHE_KEY(code), JSON.stringify(d.strings)); } catch (_) {}
      }
    } catch (_) {}
    return BUNDLES[code] || null;
  })();
  const out = await _loading[code];
  delete _loading[code];
  return out;
}

// applyLang(code) — make `code` the active UI language: load its bundle, flip the signal (re-renders every
// t() in the tree), persist the mirror for a flash-free next boot. Falls back to English if unavailable.
export async function applyLang(code) {
  code = String(code || "en");
  await loadBundle(code);
  const final = BUNDLES[code] ? code : "en";
  store.setLang(final);
  try { localStorage.setItem("hb_lang", final); } catch (_) {}
  return final;
}

// initI18n() — at boot: always have English (the fallback manifest) loaded, then reconcile the UI language with
// the backend's active language (ZAELAR_LANGUAGE is the single source of truth). t() is reactive, so any
// correction re-renders the UI in place — behind the boot veil this is invisible.
export async function initI18n() {
  loadBundle("en");                        // fallback net, fire-and-forget (cache usually already served it)
  try {
    const r = await fetch("/api/i18n/state", { cache: "no-cache" });
    const d = await r.json();
    if (d && d.active) await applyLang(d.active);
  } catch (_) { await applyLang(store.lang()); }
}

// theme.js — dark/light mode + DESIGN PROFILES + custom knobs (V2-617). Dark is the default (a full-white
// canvas at night was blinding). The dark/light signal lives in core/store.js (same pattern as micMuted/
// orbStyle: seeded from localStorage, persisted on every write). This service applies everything to the DOM:
// the `data-theme` attribute that palette.css keys off, the mobile browser-chrome color, and — new — the
// active profile's token overrides plus the user's custom knobs (accent / base font size / font), written as
// INLINE custom properties on <html> so they beat the stylesheet and repaint every token reader at once.
//
// Persistence is TWO layers, deliberately: localStorage paints instantly at boot (no flash of the wrong
// skin), and config/settings.json (via /api/settings) makes the choice durable per ACCOUNT — a cloud
// Machine's browser cache is not where a preference should live. Boot order: localStorage first, then one
// reconcile fetch; the server wins when they disagree, because it is the copy that survives a new browser.
import { theme, setTheme } from "../core/store.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import { THEMES, DEFAULT_PROFILE, customVars } from "../core/themes.js?v=1";
import * as api from "./api.js?v=2";

let _profile = localStorage.getItem("hb_theme_profile") || DEFAULT_PROFILE;
let _custom = {};
try { _custom = JSON.parse(localStorage.getItem("hb_theme_custom") || "{}") || {}; } catch (_) {}
let _appliedKeys = [];   // inline properties we set — removed before each re-apply so profiles never bleed

export const themeProfile = () => _profile;
export const themeCustom = () => ({ ..._custom });

function _apply() {
  const root = document.documentElement;
  const t = theme();
  root.dataset.theme = t;
  for (const k of _appliedKeys) root.style.removeProperty(k);
  const preset = (THEMES[_profile] || THEMES[DEFAULT_PROFILE]).vars[t] || {};
  const vars = { ...preset, ...customVars(_custom) };
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
  _appliedKeys = Object.keys(vars);
  // The browser-chrome color follows whatever --canvas RESOLVES to (profile overrides included), so the
  // phone's status bar never keeps the old skin's color after a profile swap.
  const meta = document.getElementById("themeColorMeta");
  if (meta) {
    const c = getComputedStyle(root).getPropertyValue("--canvas").trim();
    if (c) meta.content = c;
  }
}

function _persistLocal() {
  localStorage.setItem("hb_theme_profile", _profile);
  localStorage.setItem("hb_theme_custom", JSON.stringify(_custom));
}

function _persistServer() {
  // Best-effort: the account copy. A failed save costs durability, never the current session's paint.
  api.saveSettings({ theme_profile: _profile, theme_custom: _custom }).catch(() => {});
}

export function initTheme() {
  createEffect(() => {
    localStorage.setItem("hb_theme", theme());
    _apply();
  });
  // Reconcile with the account's persisted choice AFTER first paint — the server is authoritative
  // (a fresh browser has empty localStorage but the account still has its skin).
  api.getSettings().then(d => {
    const th = d && d.theme;
    if (!th) return;
    let changed = false;
    if (th.profile && THEMES[th.profile] && th.profile !== _profile) { _profile = th.profile; changed = true; }
    if (th.custom && typeof th.custom === "object"
        && JSON.stringify(th.custom) !== JSON.stringify(_custom)) { _custom = th.custom; changed = true; }
    if (changed) { _persistLocal(); _apply(); }
    // Wallpaper reconcile rides the same fetch: the server's copy wins (it survives a new browser).
    const wp = (d && typeof d.wallpaper === "object" && d.wallpaper) || {};
    if (JSON.stringify(wp) !== JSON.stringify(_wallpaper)) setWallpaper(wp.url ? wp : null, { persist: false });
  }).catch(() => {});
  _applyWallpaper();
}

export function setThemeProfile(id) {
  if (!THEMES[id]) return;
  _profile = id;
  _persistLocal(); _apply(); _persistServer();
}

export function setThemeCustom(partial) {
  // `null`/"" on a knob clears it back to the profile's own value.
  _custom = { ..._custom, ...partial };
  for (const k of Object.keys(_custom)) if (!_custom[k]) delete _custom[k];
  _persistLocal(); _apply(); _persistServer();
}

export function toggleTheme() {
  setTheme(theme() === "dark" ? "light" : "dark");
}

// ── Desktop WALLPAPER (V2-641) — a photo the voice can put behind everything. Same two-layer persistence as
// the profile: localStorage paints at boot, /api/settings makes it durable per account (the server SANITIZES
// — config/settings.py is the security seam; this regex is only the belt to its braces, because the URL is
// echoed into a CSS url("…") and a quote inside it would otherwise open a style-injection door). Applied as
// one custom property + a body class, so the CSS owns how the photo sits under the canvas glow and scrim.
const _WALL_URL_RE = /^https?:\/\/[^\s"'\\<>]+$/;
let _wallpaper = {};
try { _wallpaper = JSON.parse(localStorage.getItem("hb_wallpaper") || "{}") || {}; } catch (_) {}

export const wallpaper = () => ({ ..._wallpaper });

function _applyWallpaper() {
  const root = document.documentElement;
  const url = _wallpaper && _wallpaper.url;
  if (url && _WALL_URL_RE.test(url)) {
    root.style.setProperty("--desk-wallpaper", 'url("' + url + '")');
    document.body.classList.add("hb-wallpaper");
  } else {
    root.style.removeProperty("--desk-wallpaper");
    document.body.classList.remove("hb-wallpaper");
  }
}

export function setWallpaper(w, { persist = true } = {}) {
  _wallpaper = (w && w.url) ? { url: String(w.url), title: String(w.title || "") } : {};
  try { localStorage.setItem("hb_wallpaper", JSON.stringify(_wallpaper)); } catch (_) {}
  _applyWallpaper();
  // persist:false = the change ARRIVED from the server (SSE push after a voice order) — echoing it back
  // would be a write loop for nothing; the server already holds it.
  if (persist) api.saveSettings({ wallpaper: _wallpaper.url ? _wallpaper : null }).catch(() => {});
}

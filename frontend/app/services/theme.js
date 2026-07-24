// theme.js — dark/light mode. Dark is the default (a full-white canvas at night was blinding).
// The signal lives in core/store.js (same pattern as micMuted/orbStyle: seeded from localStorage,
// persisted on every write). This service just applies it to the DOM: a `data-theme` attribute on
// <html> that app/styles.css keys off of, plus the mobile browser-chrome color.
import { theme, setTheme } from "../core/store.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";

const META_COLOR = { dark: "#0a0f16", light: "#f6f8fb" };

export function initTheme() {
  createEffect(() => {
    const t = theme();
    document.documentElement.dataset.theme = t;
    localStorage.setItem("hb_theme", t);
    const meta = document.getElementById("themeColorMeta");
    if (meta) meta.content = META_COLOR[t] || META_COLOR.dark;
  });
}

export function toggleTheme() {
  setTheme(theme() === "dark" ? "light" : "dark");
}

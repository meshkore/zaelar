// ============================================================================
// SettingsSheet.js — «un pequeño aparato de configuración» (operator's words), and small is the specification, not
// a shortcut.
//
// The desktop's ConfigPanel.js is 35 KB and full-screen: API keys per piece, a model per module, provider balances,
// voice providers, benchmarks. That panel is for SETTING UP an installation. A phone is for USING one, and the
// difference is not screen size — it is that entering an API key on a phone keyboard, or choosing between eleven
// models by their names, is worse on a phone than on a laptop no matter how it is laid out. So this sheet carries
// only the settings whose value is highest exactly WHILE you are using the agent from your pocket:
//
//   · Language  — the whole UI switches live (V2-089), server-side, so BOTH shells follow
//   · Theme     — dark/light. On a phone this is a real setting, not a preference: it is read outdoors
//   · Captions  — subtitles on/off. The single most-used setting on a phone (silent rooms, loud streets)
//   · Speaker   — zaelar's voice output on/off, independent of the mic (V2-088: the icon is the only owner of silence)
//
// Everything heavier is not hidden, it is DELEGATED, with a row that says so and opens the real thing in the
// desktop shell. Pretending a 35 KB configuration panel fits here would produce a worse version of a thing that
// already works, which is the most expensive kind of feature.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import { toggleTheme } from "../../../app/services/theme.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";

function Toggle(label, get, onToggle) {
  return h("button", { class: () => "zm-row zm-toggle" + (get() ? " on" : ""), onClick: onToggle },
    h("span", { class: "zm-row-t" }, h("b", null, label)),
    h("span", { class: "zm-sw", "aria-hidden": "true" }),
  );
}

// Language names, for the codes this install actually has. Kept as a small map with a fall-through to the raw code
// so a language the operator GENERATED (V2-089/V2-101) still appears — as "PT" rather than "Português", which is
// worse than nothing but far better than being absent from the list.
const LANG_NAME = { en: "English", es: "Español", ca: "Català", fr: "Français", de: "Deutsch", it: "Italiano",
                    pt: "Português", nl: "Nederlands", ja: "日本語", zh: "中文" };

export function SettingsSheet() {
  const [langs, setLangs] = createSignal([]);
  // The list of installed languages is server truth, not a hardcoded constant. Fetched once when the sheet is
  // built; `available` is whatever bundles exist on THIS install.
  fetch("/api/i18n/state", { cache: "no-store" }).then(r => r.json())
    .then(st => setLangs(Array.isArray(st && st.available) ? st.available : []))
    .catch(() => {});

  // Switching language goes through POST /api/i18n/choose/{code} — the SERVER owns the active language
  // (ZAELAR_LANGUAGE), and it answers by emitting the SSE `language` event that makes every t() in BOTH shells
  // re-render. Calling applyLang() directly from here would change this browser and leave the agent — and the
  // desktop tab on the same account — speaking the old one.
  const pick = (code) => { fetch("/api/i18n/choose/" + encodeURIComponent(code), { method: "POST" }).catch(() => {}); };

  return h("section", {
    class: () => "zm-sheet zm-settings" + (store.mobileSettingsOpen() ? " open" : ""),
    "aria-hidden": () => (store.mobileSettingsOpen() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("div", { class: "zm-sheet-grab" }),
      h("h2", null, () => t("mobile.settings")),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"), onClick: () => store.setMobileSettingsOpen(false) }, "×"),
    ),

    h("div", { class: "zm-rows" },
      // ── LANGUAGE. `available()` is whatever bundles this install actually has, never a hardcoded list: a
      //    language the operator generated (V2-089/V2-101) has to appear here without anyone editing this file.
      h("label", { class: "zm-row zm-select" },
        h("span", { class: "zm-row-t" }, h("b", null, () => t("config.language"))),
        h("select", { onChange: (e) => pick(e.target.value) },
          () => langs().map((code) => h("option", {
            value: code, selected: code === store.lang() ? "" : false,
          }, LANG_NAME[code] || String(code).toUpperCase())),
        ),
      ),

      Toggle(() => t("config.theme_dark"),
        () => store.theme() === "dark",
        toggleTheme),

      Toggle(() => t("orb.captions_show"),
        () => store.captionsOn(),
        () => store.toggleCaptions()),

      Toggle(() => t("orb.speaker_unmuted"),
        () => !store.botMuted(),
        () => session.toggleBotMute()),

      // ── DELEGATED, not hidden.
      h("button", {
        class: "zm-row",
        onClick: () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); },
      },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("mobile.full_settings")),
          h("small", null, () => t("mobile.full_settings_sub")),
        ),
      ),
    ),
  );
}

// LanguageOnboarding — the first-run "which language?" blocking modal (V2-101). Sits ABOVE the boot veil
// (z-index above .boot-ovl's 100010) and follows it: main.js opens this one only once store.bootReady() is
// true AND GET /api/i18n/state says no language has EVER been explicitly chosen (`chosen:false`) — a returning
// operator, or one who already answered, never sees this again.
//
// Primarily VOICE-driven (zaelar asks the question out loud in English; the operator's spoken reply is
// detected server-side, same as any turn — see voice/engine/pipeline/agent.py's onboarding kickoff branch and
// i18n/init/detect.py::lock). But a purely voice-gated first-run blocker is a real usability trap (mic denied,
// noisy room, hard of hearing), so this modal ALSO offers a quick-pick chip row and a typed fallback — both go
// through the same server-side lock() as a spoken answer (server/i18n_api.py's /choose and /detect-text).
//
// Three phases (store.langOnboardPhase): "ask" (question + escape hatches) → "detected" (translated loading
// line while the full bundle/alias-pack generate in the background — SSE kind:"language" phase:"detected") →
// "ready" (SSE phase:"ready" closes the modal). For en/es this collapses to a blink; for anything else it's a
// real wait, deliberately without technical detail — just the one translated line.
import { h } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/language-onboarding-api.js?v=1";

// A short, common spread — not exhaustive (anything typed/spoken still works via classify()); these are just
// the fastest taps. Native-script labels so each chip reads correctly to its own speaker, not to us.
const QUICK_PICKS = [
  ["en", "English"], ["es", "Español"], ["fr", "Français"], ["de", "Deutsch"],
  ["it", "Italiano"], ["pt", "Português"], ["zh", "中文"], ["ja", "日本語"],
  ["ko", "한국어"], ["ar", "العربية"], ["hi", "हिन्दी"], ["ru", "Русский"],
];

export function LanguageOnboarding() {
  let inputEl;
  const [busy, setBusy] = createSignal(false);

  const pick = async (code) => {
    if (busy()) return;
    setBusy(true);
    await api.chooseLanguage(code).catch(() => {});
    setBusy(false);
  };

  const submitTyped = async () => {
    const text = (inputEl?.value || "").trim();
    if (!text || busy()) return;
    setBusy(true);
    const res = await api.detectLanguageText(text).catch(() => ({ ok: false }));
    setBusy(false);
    if (!res.ok && inputEl) inputEl.value = "";   // not recognized — clear, let them try again or use a chip
  };

  const askView = () => h("div", { class: "lang-onb-ask" },
    h("div", { class: "lang-onb-q" }, "Hi! What language would you like to use?"),
    h("div", { class: "lang-onb-hint" }, "Say it, or pick one below."),
    h("div", { class: "lang-onb-chips" },
      ...QUICK_PICKS.map(([code, label]) =>
        h("button", { class: "lang-onb-chip", disabled: () => busy(), onClick: () => pick(code) }, label)),
    ),
    h("div", { class: "lang-onb-typed" },
      h("input", {
        class: "lang-onb-input", ref: el => (inputEl = el), placeholder: "or type it here…",
        onKeydown: e => { if (e.key === "Enter") { e.preventDefault(); submitTyped(); } },
      }),
      h("button", { class: "lang-onb-go", disabled: () => busy(), onClick: submitTyped }, "→"),
    ),
  );

  const loadingView = () => h("div", { class: "lang-onb-loading" },
    h("div", { class: "lang-onb-spinner" }),
    h("div", { class: "lang-onb-loading-text" }, () => store.langOnboardLoading() || "…"),
  );

  return h("div", {
    class: () => "lang-onb" + (store.langOnboardOpen() ? " open" : "") +
                 (store.langOnboardPhase() === "ready" ? " gone" : ""),
    "aria-hidden": "true",
  },
    h("div", { class: "lang-onb-card" },
      () => (store.langOnboardPhase() === "ask" ? askView() : loadingView()),
    ),
  );
}

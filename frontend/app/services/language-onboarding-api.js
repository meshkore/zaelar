// ============================================================================
// language-onboarding-api.js — thin fetch wrapper for the first-run language modal (V2-101). Mirrors
// feedback-api.js's convention: no state, no UI, just the two escape hatches the modal offers when voice
// isn't an option (mic denied, noisy room, prefers keyboard) — a quick-pick chip or typed free text.
// ============================================================================

export const chooseLanguage = (code) =>
  fetch(`/api/i18n/choose/${encodeURIComponent(code)}`, { method: "POST" })
    .then(r => r.json()).catch(() => ({ ok: false }));

export const detectLanguageText = (text) =>
  fetch("/api/i18n/detect-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }).then(r => r.json()).catch(() => ({ ok: false }));

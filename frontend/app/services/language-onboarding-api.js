// ============================================================================
// language-onboarding-api.js — thin fetch wrapper for the first-run language modal (V2-101). Mirrors
// feedback-api.js's convention: no state, no UI — just the picker's own door, for when voice is not an
// option (mic denied, noisy room, prefers to tap).
//
// V2-672 dropped the TYPED free-text hatch (`POST /api/i18n/detect-text`). The endpoint is still live and
// still used by the TEXT channel's silent first-run detection (i18n/init/detect.ensure_for_text) — what
// went is this client, because the picker now uses typing to FILTER its 40 rows instead of submitting a
// sentence to the classifier. Submitting needed a prompt telling you to write something, in a language you
// may not read; filtering needs none.
// ============================================================================

export const chooseLanguage = (code) =>
  fetch(`/api/i18n/choose/${encodeURIComponent(code)}`, { method: "POST" })
    .then(r => r.json()).catch(() => ({ ok: false }));

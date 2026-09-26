// ============================================================================
// first-run.js — a FIRST RUN must not inherit a previous install's browser state (V2-735).
//
// THE FAILURE. The operator, on a freshly reset install (2026-09-20): *«cuando el sistema arranca, no
// quiero que por defecto el orbe esté metido en la barra inferior. Quiero que el orbe esté desplegado y
// que se vea el orbe grande con el pulso y todo… totalmente arrancado, porque la voz tiene que empezar a
// sonar enseguida»*. And by default it IS: `store.orbDock` defaults to "eye" and `store.powerOff` to
// false. What he was looking at was not a default — it was the PREVIOUS install's `hb_orb_dock=bar` and
// `hb_power_off=1`, still sitting in the browser.
//
// A factory reset (V2-670) starts the AGENT over: settings, memory, the workspace. It cannot reach
// `localStorage`, which lives in the browser, is per-origin, and survives everything the server can do to
// itself. So a reset install came up wearing the shape of the one before it — the orb docked in the bar,
// the voice switched off, the previous desktop's cards restored — and every one of those reads as a
// product default to somebody seeing it for the first time.
//
// WHY A WIPE AND A RELOAD, AND NOT A LIST OF SIGNALS TO RE-APPLY. The signals are seeded at module
// import, long before anything can know this is a first run: by the time `GET /api/i18n/state` answers
// `chosen:false`, `store.js` has already read the lot and `ensureVoice()` has already decided not to
// start. Re-applying them means naming them — orb dock, power, desktop layout, chat geometry, theme,
// captions, mic — and that list is the one somebody remembers (V2-727). Wiping our own namespace and
// reloading needs no list and cannot go stale.
//
// It costs one reload, ONCE, on an install that had inherited state — a genuinely new browser wipes
// nothing and reloads nothing. The guard lives in `sessionStorage` so a loop is impossible even if a key
// is rewritten between the wipe and the reload.
// ============================================================================

// Everything this product stores in the browser is under one of these. A first run has no legitimate
// state of ours — that is what makes a prefix sweep safe here and nowhere else.
const OURS = ["hb_", "zaelar_"];
const GUARD = "hb_first_run_takeover";      // sessionStorage: one attempt per tab, never persisted

export function isOurs(key) {
  return !!key && OURS.some(p => key.startsWith(p));
}

/** Remove every key this product owns. Returns what went, so the caller can tell «there was something to
 *  clear» from «this browser was already clean» without keeping a list of what matters. */
export function clearInheritedViewState(storage) {
  const gone = [];
  try {
    for (let i = storage.length - 1; i >= 0; i--) {
      const k = storage.key(i);
      if (isOurs(k)) { storage.removeItem(k); gone.push(k); }
    }
  } catch (_) { /* private window, blocked site data: there is nothing to inherit either */ }
  return gone;
}

/**
 * Call when the engine says this install has never chosen a language.
 *
 * Returns true when it wiped inherited state and asked for a reload — the caller must stop what it was
 * doing, because the page is going away. False means there was nothing to inherit (or we already tried
 * in this tab) and boot continues normally.
 */
export function takeoverOnFirstRun({ local, session, reload }) {
  try {
    if (session.getItem(GUARD)) return false;   // already attempted in this tab: never twice
    session.setItem(GUARD, "1");
  } catch (_) {
    return false;                                // no sessionStorage → no guard → do not risk a loop
  }
  const gone = clearInheritedViewState(local);
  if (!gone.length) return false;
  reload();
  return true;
}

/**
 * The same takeover for EVERY reset, not only a first run (operator, 2026-09-25): *«en cuanto hago un reset,
 * todas esas variables de estado pasan al estado inicial de cualquier instalación como si fuera de cero»* —
 * orb listening, mic and speaker on. A reset that KEEPS the language never reaches `takeoverOnFirstRun`
 * (`chosen` stays true), so the previous `hb_mic_muted=1` / `hb_bot_muted=1` / `hb_orb_dock=bar` survived it.
 *
 * `scripts/reset-memory.sh` bumps a wipe EPOCH on every reset (`GET /api/desktop/epoch`); this browser keeps
 * the last one it obeyed in `hb_wipe`. A new epoch → wipe our namespace, remember the epoch, reload once.
 * A browser that never saw an epoch and holds nothing of ours just records it — nothing to wipe, no reload.
 */
export async function takeoverOnReset({ fetchEpoch, local, session, reload }) {
  let epoch = "";
  try { epoch = String((await fetchEpoch()) || ""); } catch (_) { return false; }
  if (!epoch) return false;
  try {
    const seen = local.getItem(WIPE_KEY);
    if (seen === epoch) return false;
    // A browser that never recorded an epoch has nothing from a PREVIOUS reset to shed: whatever `hb_` keys it
    // holds were written by THIS boot, before the epoch answered. Sweeping them reloaded every fresh browser
    // once and cut its voice session (measured 2026-09-26, the demo driver). Record the epoch and go on.
    if (seen === null) { local.setItem(WIPE_KEY, epoch); return false; }
    const guard = RESET_GUARD + epoch;
    if (session.getItem(guard)) return false;     // already attempted for this epoch in this tab
    session.setItem(guard, "1");
  } catch (_) {
    return false;                                  // no storage → nothing inherited, and no loop risked
  }
  const gone = clearInheritedViewState(local).filter(k => k !== WIPE_KEY);
  try { local.setItem(WIPE_KEY, epoch); } catch (_) { /* private window */ }
  if (!gone.length) return false;
  reload();
  return true;
}

// OWNED HERE, and nowhere else (V2-773). `widgets/desktop.js::restore` reads the same epoch for its own wipe and
// records it under ITS key (`hb_desktop_epoch`): when both wrote this one, the restore that answered first left
// the takeover believing the epoch was already obeyed, and the mutes survived the reset.
const WIPE_KEY = "hb_wipe";
const RESET_GUARD = "hb_reset_takeover:";

export const _GUARD_KEY = GUARD;

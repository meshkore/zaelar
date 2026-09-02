// ============================================================================
// update/watch.js — DOES THIS TAB NEED TO RELOAD?  (V2-553)
//
// The state half of the update module: no DOM, no styling, no imports from the app beyond the reactive
// primitives. `UpdateSurface.js` renders what this decides. Both shells (desktop and mobile PWA) use it.
//
// HOW IT KNOWS. `GET /api/update` answers with the running engine's `build` (the number a person is shown)
// and its `ui_rev` (a digest of the frontend bytes the browser executes — see `update/__init__.py`). The
// FIRST answer is taken as this tab's BASELINE, because the page was served by that same process moments
// earlier, so it describes the code running in this tab. Any later answer with a different `ui_rev` means
// the running engine no longer serves what this tab is executing → reload.
//
// This is why a backend-only change does NOT nag: the build number climbs, the badge updates in place, and
// `ui_rev` never moves, so no bar appears. Exactly the operator's rule («si solo se ha tocado algo del
// backend obviamente no hace falta»), decided by measurement instead of by guessing from the version.
//
// THE RESIDUAL RACE, stated honestly: if the engine restarts with new frontend code in the ~0 s between the
// page being served and the first check, the baseline is taken from the NEW engine while the DOM is the old
// one, and this tab will not know. That is why the first check is fired the instant the module loads rather
// than on the first interval. It cannot be closed without stamping the revision into `index.html` at build
// time, which would put a build step between the operator and a file he edits by hand.
//
// WHY A POLL AND NOT THE SSE STREAM: see the note in `update/api.py`. Short version — a hidden tab is not
// polled at all, a visible one costs ~200 bytes against a fully cached dict, and it is the only mechanism
// that still works for a PWA whose tab has been backgrounded for hours.
import { createSignal } from "../core/reactive.js?v=2";

const POLL_MS = 20000;

const [build, setBuild] = createSignal(0);
const [stale, setStale] = createSignal(false);
const [info, setInfo] = createSignal(null);
export { build, stale, info };

let _baseline = null;     // the ui_rev this tab is RUNNING (first answer wins)
let _dismissed = "";      // a revision the operator waved away — until the NEXT one arrives
let _iv = null;

export async function check() {
  let s;
  try {
    const r = await fetch("/api/update", { cache: "no-store" });
    if (!r.ok) return;                       // 503 on a cold Machine, 401 mid-session: silence, never alarm
    s = await r.json();
  } catch (_) { return; }                    // engine restarting → the absence of an answer is not news
  setInfo(s);
  if (typeof s.build === "number" && s.build > 0) setBuild(s.build);
  const rev = String(s.ui_rev || "");
  // "unknown" is the module's sentinel for «I could not read my own frontend». Treating it as a change
  // would nag forever with a reload that fixes nothing.
  if (!rev || rev === "unknown") return;
  if (_baseline === null) { _baseline = rev; return; }
  setStale(rev !== _baseline && rev !== _dismissed);
}

// Waved away for THIS revision only. Deliberately not persisted: the fix for staleness is a reload, and a
// reload clears this by definition — while a dismissal remembered across reloads could hide a real update
// forever. The next different revision brings the bar straight back.
export function dismiss() {
  const s = info();
  _dismissed = (s && s.ui_rev) || "";
  setStale(false);
}

export function applyUpdate() { try { location.reload(); } catch (_) {} }

export function startUpdateWatch(ms = POLL_MS) {
  if (_iv) return;
  check();
  _iv = setInterval(() => { if (document.visibilityState !== "hidden") check(); }, ms);
  // Coming back to a tab left open for hours is the moment the answer is most likely to have changed, and
  // the moment the operator is actually looking. Check then, without shortening the interval for everyone.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") check();
  });
}

// Test seam only: lets a harness re-baseline between navigations without reloading the module.
export function __reset() { _baseline = null; _dismissed = ""; setStale(false); }

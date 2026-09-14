// ============================================================================
// daemon.js — IS THE LOCAL DAEMON THERE, AND IF NOT, WHERE DOES ONE GET IT? (V2-575 · P1)
//
// The state half of the daemon surface: no DOM, no styling. `TopBar.js` renders the dot from `iconState()`
// and `DaemonSetup.js` renders everything else from `status()`.
//
// IT TALKS TO THE ENGINE, NEVER TO 45817. The daemon speaks plain http and this page may be served over
// https, so a direct call is mixed content; it is cross-origin, so it would need CORS headers the daemon
// must never send; and its bearer token would have to reach JavaScript, which is the last place a
// credential that reads somebody's documents should be. `server/daemon_api.py` holds all three problems.
//
// THE POLL IS THE `update/watch.js` PATTERN, for the same reasons written there: a hidden tab is not polled
// at all, a visible one costs one small JSON against a dict the engine already had, and it keeps working in
// a PWA whose tab has been backgrounded for hours. The state it watches changes on a human timescale
// (somebody installs a daemon, somebody picks a folder), so 20 s is generous rather than tight.
//
// ON A CLOUD ACCOUNT the engine answers `state: "remote"`: the daemon runs on the user's computer and the
// cloud engine is in a container somewhere else, with no path between them until the relay exists (P3). The
// icon still has a job there, and it is the one the operator asked for — it is where somebody working
// against the cloud agent gets the installer for their own machine.
import { createSignal } from "../core/reactive.js?v=2";

const POLL_MS = 20000;

const [status, setStatus] = createSignal(null);
export { status };

let _iv = null;
let _last = "";   // the last payload, verbatim — see `check()`

export async function check() {
  try {
    const r = await fetch("/api/daemon/status", { cache: "no-store" });
    if (!r.ok) return;                       // engine restarting, or an older build without the route
    const s = await r.json();
    if (!s || !s.ok) return;
    // ⚠️ ONLY WHEN SOMETHING ACTUALLY CHANGED. The poll answers every 20 s with an equal-but-new object, and
    // the setup screen is a reactive child of this signal — so writing it unconditionally would rebuild that
    // subtree four times a minute and wipe whatever the user had half-typed into the folder field.
    const next = JSON.stringify(s);
    if (next === _last) return;
    _last = next;
    setStatus(s);
  } catch (_) { /* no answer is not news: the engine restarts, the tab sleeps */ }
}

// What the dot is coloured by. Deliberately NOT a fourth opinion: the engine computed `state` in
// `daemon_api.py` so that "running but no folders chosen is a warning" is decided once, and this returns
// the neutral value until the first answer arrives instead of flashing an alarm on every page load.
export function iconState() {
  const s = status();
  if (!s) return "unknown";
  return s.state || "off";
}

export function isRemote() { const s = status(); return !!s && s.state === "remote"; }
export function isConnected() { const s = status(); return !!s && !!s.reachable; }

// The installer for THIS visitor's machine, chosen by the engine from their user-agent — which is the right
// source and not `navigator.platform`: on a cloud account the engine's own platform is a Linux container,
// and a self-hoster may well be browsing from a second computer.
export function downloadFor(platform) {
  const s = status();
  if (!s || !s.downloads || !s.downloads.platforms) return null;
  const key = platform || s.platform || "";
  return s.downloads.platforms[key] || null;
}

export function platforms() {
  const s = status();
  return (s && s.downloads && s.downloads.platforms) ? s.downloads.platforms : {};
}

async function _permissions(action, path) {
  const r = await fetch(`/api/daemon/permissions/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  let body = {};
  try { body = await r.json(); } catch (_) { /* a 500 with no body is still a refusal */ }
  // The daemon's own sentence travels all the way here on purpose — it names the boundary ("that is your
  // entire home folder") and replacing it with a generic failure would leave the user with nothing to act on.
  if (!r.ok || !body.ok) return { ok: false, message: body.message || body.error || "" };
  await check();
  return { ok: true, roots: body.roots || [] };
}

export const grant  = (path) => _permissions("grant", path);
export const revoke = (path) => _permissions("revoke", path);

export function start() {
  if (_iv) return;
  check();
  _iv = setInterval(() => { if (!document.hidden) check(); }, POLL_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
}

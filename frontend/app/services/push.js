// ============================================================================
// push.js — Web Push for THIS browser, and whether this screen is an installed app (V2-796). No DOM.
//
// Shared by both shells. The server half is `server/notices_api.py` + `nucleo/pulse/notices.py`: the engine keeps ONE
// ledger of the notices it owes the operator and sends each through voice, then this browser, then «owed».
//
// Three browser rules shape this file:
//   · iOS delivers Web Push ONLY to a PWA added to the Home Screen (16.4+). In a Safari tab `PushManager` is absent,
//     so the honest offer there is «install», not «turn on notifications» — `canAsk()` says which.
//   · The permission prompt must come from a user gesture, and on iOS from inside the gesture's own call stack:
//     `enable()` calls `Notification.requestPermission()` FIRST, before awaiting anything else.
//   · Chromium raises `beforeinstallprompt` once, early, and only that event can install in one tap. It is caught at
//     module load and kept; `install()` replays it.
// ============================================================================

import { DEVICE } from "./api.js?v=2";

let _deferred = null;                       // the captured beforeinstallprompt event (Chromium only)
const _listeners = new Set();
const _emit = () => { for (const fn of _listeners) { try { fn(); } catch (_) {} } };

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); _deferred = e; _emit(); });
  window.addEventListener("appinstalled", () => { _deferred = null; _emit(); report(); });
}

export const onChange = (fn) => { _listeners.add(fn); return () => _listeners.delete(fn); };

export function os() {
  const ua = (navigator.userAgent || "").toLowerCase();
  // iPadOS 13+ reports itself as a Mac; a touch Mac is an iPad.
  if (/iphone|ipad|ipod/.test(ua) || (/macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/android/.test(ua)) return "android";
  return "desktop";
}

export const installed = () =>
  (typeof matchMedia === "function" && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;

export const supported = () =>
  "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;

export const permission = () => ("Notification" in window ? Notification.permission : "unsupported");

/** Can THIS screen be asked to turn notifications on right now (a supported browser, not yet decided)? */
export const canAsk = () => supported() && permission() === "default";

/** Is a one-tap install available (Chromium captured its prompt)? */
export const canInstall = () => !!_deferred && !installed();

export async function install() {
  const e = _deferred;
  if (!e) return false;
  _deferred = null;
  try {
    e.prompt();
    const choice = await e.userChoice;
    _emit();
    return choice && choice.outcome === "accepted";
  } catch (_) { _emit(); return false; }
}

const _b64ToBytes = (s) => {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const raw = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

async function _registration() {
  const existing = await navigator.serviceWorker.getRegistration("/");
  if (existing) return existing;
  return navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

const _shell = () => (location.pathname.startsWith("/m") ? "mobile" : "desktop");

async function _subscribe() {
  const reg = await _registration();
  await navigator.serviceWorker.ready;
  const k = await fetch("/api/push/key", { cache: "no-store" }).then((r) => r.json()).catch(() => ({}));
  if (!k || !k.key) return false;
  const want = _b64ToBytes(k.key);
  let sub = await reg.pushManager.getSubscription();
  // A subscription made against another key (the engine lost and regenerated its key) is dead at the push service:
  // replace it rather than posting one the server can never use.
  if (sub && sub.options && sub.options.applicationServerKey) {
    const have = new Uint8Array(sub.options.applicationServerKey);
    if (have.length !== want.length || have.some((b, i) => b !== want[i])) { await sub.unsubscribe(); sub = null; }
  }
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: want });
  const r = await fetch("/api/push/subscribe", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subscription: sub.toJSON(), dev: DEVICE, platform: `${_shell()}:${os()}`, installed: installed() }),
  });
  return r.ok;
}

/** Ask for permission and subscribe. MUST be called from a tap handler. Resolves to the final permission. */
export async function enable() {
  if (!supported()) return "unsupported";
  let p = Notification.permission;
  if (p === "default") p = await Notification.requestPermission();   // first, inside the gesture (iOS)
  if (p === "granted") { try { await _subscribe(); } catch (_) { /* reported below; the banner stays honest */ } }
  _emit();
  report();
  return p;
}

/** Already granted: keep the server's copy of this subscription current (silent, no prompt). */
export async function refresh() {
  if (!supported() || permission() !== "granted") return false;
  try { return await _subscribe(); } catch (_) { return false; }
}

export async function test() {
  return fetch("/api/push/test", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dev: DEVICE }),
  }).then((r) => r.json()).catch(() => ({ ok: false }));
}

/** Tell the engine what this screen is (installed? notifications allowed?), so a phone that cannot be reached is
 *  visible as such instead of silently missing every notice. */
export function report() {
  try {
    fetch("/api/push/device", {
      method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
      body: JSON.stringify({ dev: DEVICE, platform: `${_shell()}:${os()}`, installed: installed(),
        permission: permission(), supported: supported() }),
    }).catch(() => {});
  } catch (_) {}
}

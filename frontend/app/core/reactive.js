// ============================================================================
// reactive.js — minimal fine-grained reactivity with a Solid-COMPATIBLE surface.
//
// This is the single most important file for the planned migration to Solid.js:
// createSignal / createEffect / createMemo / batch / onCleanup keep the EXACT
// signatures Solid uses. To migrate, delete this file and re-point the imports:
//
//     -import { createSignal, createEffect } from "../core/reactive.js?v=2";
//     +import { createSignal, createEffect } from "solid-js";
//
// Component and service code that consumes these does NOT change.
// ============================================================================

let currentObserver = null;          // the effect currently running (dependency tracking)
let batchDepth = 0;
const pendingEffects = new Set();

// createSignal(initial) -> [read, write].  read() tracks; write(v|fn) notifies on change.
export function createSignal(initial) {
  let value = initial;
  const subscribers = new Set();
  const read = () => {
    if (currentObserver) { subscribers.add(currentObserver); currentObserver.deps.add(subscribers); }
    return value;
  };
  const write = (next) => {
    const v = typeof next === "function" ? next(value) : next;
    if (Object.is(v, value)) return v;            // no-op on unchanged value (Solid semantics)
    value = v;
    for (const ob of [...subscribers]) {          // copy: re-runs may re-subscribe
      if (batchDepth > 0) pendingEffects.add(ob); else ob.run();
    }
    return v;
  };
  return [read, write];
}

function cleanupObserver(observer) {
  for (const dep of observer.deps) dep.delete(observer);
  observer.deps.clear();
  for (const fn of observer.cleanups) { try { fn(); } catch (_) {} }
  observer.cleanups = [];
}

// createEffect(fn) — runs fn now, re-runs whenever a signal it read changes. Returns a disposer.
export function createEffect(fn) {
  const observer = {
    deps: new Set(), cleanups: [],
    run() {
      cleanupObserver(observer);
      const prev = currentObserver; currentObserver = observer;
      try { fn(); } finally { currentObserver = prev; }
    },
  };
  observer.run();
  return () => cleanupObserver(observer);
}

// untrack(fn) — reads signals WITHOUT subscribing to them. Its signature is identical to Solid's (`untrack`), so
// the planned migration above remains an import change.
//
// What it is for, with a real case behind it: an effect that READS a signal to DECIDE and then WRITES it feeds
// back into itself. This happened with the speaker—an effect read `botMuted()` to mute it when opening chat,
// remained subscribed, and pressing 🔊 retriggered it and MUTED IT AGAIN: the icon looked stuck because it reacted
// and something undid the action in the same tick (V2-087). That effect was removed entirely in V2-088—chat and
// voice are independent—so nobody uses `untrack` today; it remains because it is a Solid primitive and the right
// tool for that class of loop. Before using it, ask whether the coupling should exist at all.
export function untrack(fn) {
  const prev = currentObserver;
  currentObserver = null;
  try { return fn(); } finally { currentObserver = prev; }
}

// createMemo(fn) — derived, cached reactive value (read like a signal getter).
export function createMemo(fn) {
  const [get, set] = createSignal(undefined);
  createEffect(() => set(fn()));
  return get;
}

// batch(fn) — coalesce writes so dependent effects run once, after fn returns.
export function batch(fn) {
  batchDepth++;
  try { return fn(); }
  finally {
    if (--batchDepth === 0) {
      const queued = [...pendingEffects]; pendingEffects.clear();
      for (const ob of queued) ob.run();
    }
  }
}

// onCleanup(fn) — register teardown for the current effect (runs before re-run / on dispose).
export function onCleanup(fn) {
  if (currentObserver) currentObserver.cleanups.push(fn);
}

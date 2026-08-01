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

// untrack(fn) — lee señales SIN suscribirse a ellas. Firma idéntica a la de Solid (`untrack`), así que la
// migración prevista arriba sigue siendo un cambio de import.
//
// Para qué sirve, con un caso real detrás: un efecto que LEE una señal para DECIDIR y luego la ESCRIBE se
// retroalimenta. Pasó con el altavoz — un efecto leía `botMuted()` para silenciar al abrir el chat, quedaba
// suscrito, y al pulsar 🔊 se re-disparaba y VOLVÍA A SILENCIAR: el icono parecía bloqueado porque respondía y
// algo lo deshacía en el mismo tick (V2-087). Aquel efecto se eliminó del todo en V2-088 —chat y voz son
// independientes—, así que hoy nadie usa `untrack`; se conserva porque es primitivo de Solid y la herramienta
// correcta para esa clase de bucle. Antes de usarlo, pregúntate si el acoplamiento debería existir siquiera.
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

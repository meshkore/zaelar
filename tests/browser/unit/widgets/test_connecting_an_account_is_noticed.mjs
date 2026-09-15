// V2-700 — `ctx.connect`: the window, and the NOTICING.
//
// The operator: «se ha abierto en una pestaña nueva en lugar de en un pop-up […] no me ha gustado en la
// versión desktop que se me cambie de pestaña» and «cuando volvemos a la pantalla […] ya automáticamente
// desaparece la opción de conectar y se marca como conectado. Eso sigue sin suceder y se tiene que estar
// detectando en tiempo real».
//
// Driven directly against `desktop.js`'s own methods with a fake window/popup, because the thing under test
// is the CANVAS's behaviour — which window it opens and what it does afterwards — not any one widget's
// markup. Node only, no browser: everything here is DOM-free.

import assert from "node:assert/strict";

const engine = new URL("../../../../", import.meta.url);

// ── a desk stripped to what _connectFlow touches ─────────────────────────────────────────────────────────
async function loadDesk() {
  // desktop.js imports frontend internals; stub the module graph by hand-loading only what we need.
  const src = await (await import("node:fs/promises")).readFile(
    new URL("frontend/app/widgets/desktop.js", engine), "utf8");
  // Lift the three methods under test out of the class without booting the whole canvas: they are pure
  // logic over `this.wins` and `window`, and importing the module would drag in the DOM, the store and SSE.
  const body = src.slice(src.indexOf("  _connectOrigins()"), src.indexOf("  // V2-613 — the operator picks"));
  // A CLASS body, not an object literal: the three methods are copied VERBATIM out of desktop.js, so the
  // test runs the shipped source and a drift in it shows up here rather than being quietly re-typed.
  const Klass = new Function("return class { " + body + " };")();
  return Klass.prototype;
}

function fakeWin(opts = {}) {
  const calls = [];
  const listeners = {};
  const popup = { closed: false, location: "", close() { this.closed = true; } };
  return {
    calls, listeners, popup,
    innerWidth: opts.innerWidth ?? 1400,
    open: (url, name, features) => { calls.push({ url, name, features }); return opts.blocked ? null : popup; },
    addEventListener: (k, fn) => { (listeners[k] ||= []).push(fn); },
    removeEventListener: (k, fn) => { listeners[k] = (listeners[k] || []).filter(f => f !== fn); },
    fire: (k, ev) => (listeners[k] || []).slice().forEach(fn => fn(ev)),
    location: { origin: "https://local.zaelar.com:44317" },
  };
}

function fakeDesk(deskProto, win, { actionResult = { ok: true, url: "https://accounts.google.com/x" } } = {}) {
  const refreshes = [];
  const w = { _dataSig: "SIG0", _ctx: { action: async (n, p) => { w.lastAction = [n, p]; return actionResult; } } };
  // ⚠️ Object.create(proto), NOT Object.assign({}, proto): class methods are NON-ENUMERABLE, so assign
  // copies none of them and every call would fail as «not a function».
  const desk = Object.assign(Object.create(deskProto), {
    wins: new Map([["contactos", w]]),
    refreshData: async (id) => { refreshes.push(id); if (desk._flip) w._dataSig = "SIG1"; },
  });
  desk._win = win; desk._w = w; desk._refreshes = refreshes;
  return desk;
}

// `_connectFlow`/`_watchConnect` read the ambient `window`/`location`; give the module scope ours.
function withWindow(win, fn) {
  const prevW = globalThis.window, prevL = globalThis.location;
  globalThis.window = win; globalThis.location = win.location;
  globalThis.setInterval = globalThis.setInterval; // node's, kept
  return Promise.resolve(fn()).finally(() => { globalThis.window = prevW; globalThis.location = prevL; });
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const proto = await loadDesk();

// ── 1 · THE WINDOW ──────────────────────────────────────────────────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", { origin: "x" }, { family: "contactos" });
  assert.equal(win.calls.length, 1, "exactly one window");
  assert.equal(win.calls[0].features, "width=520,height=760",
    "THE defect he reported: without a features string the browser opens a TAB, not a popup");
  assert.equal(win.calls[0].url, "", "opened EMPTY and synchronously — a window.open after an await is blocked in silence");
  assert.equal(desk._w.lastAction[0], "connect", "and only then is the URL asked for");
  assert.equal(win.popup.location, "https://accounts.google.com/x");
  desk._w._connWatch && desk._w._connWatch();
});

await withWindow(fakeWin({ innerWidth: 420 }), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, {});
  assert.equal(win.calls[0].features, undefined,
    "on a phone a popup is not a thing the OS can honour — a tab is asked for on purpose");
  desk._w._connWatch && desk._w._connWatch();
});

// ── 2 · A REFUSAL CLOSES THE WINDOW INSTEAD OF LEAVING IT BLANK ─────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win, { actionResult: { ok: false, error: "sin app OAuth registrada" } });
  const r = await desk._connectFlow("contactos", "connect", {}, {});
  assert.equal(r.error, "sin app OAuth registrada", "the connector's own sentence reaches the card");
  assert.equal(win.popup.closed, true, "an empty window left open is litter the operator has to close");
  assert.equal(desk._refreshes.length, 0, "and nothing is watched, because nothing was started");
});

// ── 3 · THE LISTENER — the instant path ─────────────────────────────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  desk._flip = true;                                   // the engine now reports «connected»
  let done = null;
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", onDone: (ok) => { done = ok; } });
  win.fire("message", { origin: "http://127.0.0.1:43917",
                        data: { zaelar: "connector", family: "contactos", ok: true } });
  await sleep(20);
  assert.deepEqual(desk._refreshes, ["contactos"], "ONE re-read, immediately — no waiting for a poll tick");
  assert.equal(done, true, "and the card is told, so its button stops saying «Abriendo…»");
  assert.equal(win.listeners.message.length, 0, "the listener is removed: a watcher per click would pile up");
});

// ── 4 · THE MESSAGE IS A HINT, NOT THE ANSWER ──────────────────────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos" });
  win.fire("message", { origin: "https://evil.example.com",
                        data: { zaelar: "connector", family: "contactos", ok: true } });
  win.fire("message", { origin: "http://127.0.0.1:43917", data: { hello: "world" } });
  win.fire("message", { origin: "http://127.0.0.1:43917",
                        data: { zaelar: "connector", family: "agenda", ok: true } });
  await sleep(20);
  assert.equal(desk._refreshes.length, 0,
    "a foreign origin, a shapeless message and another family are all ignored");
  desk._w._connWatch && desk._w._connWatch();
});

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  desk._flip = false;                                  // the engine says the state did NOT change
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos" });
  win.fire("message", { origin: "http://127.0.0.1:43917",
                        data: { zaelar: "connector", family: "contactos", ok: true } });
  await sleep(20);
  assert.deepEqual(desk._refreshes, ["contactos"], "it goes and LOOKS…");
  assert.ok(win.listeners.message.length > 0,
    "…and keeps watching, because a forged «ok» must not end the flow on its own");
  desk._w._connWatch && desk._w._connWatch();
});

// ── 5 · THE BACKSTOP — a message that never arrives ────────────────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 15 });
  desk._flip = true;                                   // the token lands with no message and no close
  await sleep(90);
  assert.ok(desk._refreshes.length >= 1, "the poll notices on its own — a mobile tab has no opener to post");
  assert.equal(win.listeners.message.length, 0, "and it stops once the state has moved");
});

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 15 });
  win.popup.closed = true;                             // he cancelled
  await sleep(120);
  assert.ok(desk._refreshes.length >= 2,
    "a closed window is a reason to LOOK AGAIN, not an outcome — the token is written before it closes");
  assert.equal(win.listeners.message.length, 0, "and then it gives up instead of polling forever");
});

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 10, timeoutMs: 40 });
  await sleep(120);
  assert.equal(win.listeners.message.length, 0, "a watcher has a deadline: nothing runs forever");
});

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 10 });
  desk.wins.delete("contactos");                       // the operator closed the card
  await sleep(60);
  assert.equal(win.listeners.message.length, 0, "a closed card takes its watcher with it");
});

// ── 6 · ONE WATCHER PER CARD ───────────────────────────────────────────────────────────────────────────

await withWindow(fakeWin(), async function () {
  const win = globalThis.window;
  const desk = fakeDesk(proto, win);
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 999 });
  await desk._connectFlow("contactos", "connect", {}, { family: "contactos", everyMs: 999 });
  assert.equal(win.listeners.message.length, 1,
    "pressing Connect twice must not leave two watchers racing the same card");
  desk._w._connWatch && desk._w._connWatch();
});

console.log("ok — ctx.connect opens a popup, and notices in three independent ways");

// ============================================================================
// test_one_task_is_one_chip.mjs — demo 2026-10-22.
//
// The bar said «four processes» over a «Procesos» list of one. Each chip came from two sources keyed on two ids:
// the SSE `task` events name the per-process session id («1», «2», «3») and the board rows (`/api/tasks`) name the
// durable id («48ac70-1»). Every reconcile added a twin, and a task's `end` cleared only the twin the event named.
//
// It MOUNTS the real store and the real SSE handler and replays that session's life.
// Run: node tests/browser/unit/widgets/test_one_task_is_one_chip.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"], ["hb_i18n_en", JSON.stringify({})]]);
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
// The engine's live board as the stub serves it. V2-822: a `start`/`end` event makes the store re-read the board, so
// the stub answers with the board this replay is at — an empty `{}` would say «nothing runs» and clear every chip.
let board = [];
globalThis.fetch = async (u) => ({ ok: true, json: async () => (String(u).startsWith("/api/tasks") ? { tasks: board } : {}),
                                   text: async () => "" });
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null,
                        addEventListener(){}, createElement: () => ({ style:{}, classList:{ add(){}, remove(){} },
                                                                      appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

let sink = null;
globalThis.EventSource = class { constructor(){ sink = this; } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");
openSSE({ show(){}, close(){}, closeAll(){}, refreshData(){}, createWidget(){}, modifyWidget(){}, onDeleted(){},
          showConfirm(){}, hideConfirm(){}, move(){}, resize(){}, fullscreen(){}, refreshRegistry(){} });
const push = (obj) => sink.onmessage({ data: JSON.stringify(obj) });
const live = () => (store.tasks() || []).filter(t => !t.done && !t.internal);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const row = (n, title) => ({ id: `48ac70-${n}`, session: String(n), state: "running", title });

// three errands, born from their SSE events
board = [row(1, "Find three 27-inch 4K monitors"), row(2, "Bitcoin summary"), row(3, "Trip")];
push({ kind: "task", label: "start", id: "1", text: "Thinking…" });
push({ kind: "task", label: "🏷️ encargo nombrado", id: "1", text: "Find three 27-inch 4K monitors" });
push({ kind: "task", label: "start", id: "2", text: "Thinking…" });
push({ kind: "task", label: "start", id: "3", text: "Thinking…" });
assert.equal(live().length, 3);

// opening «Procesos» reconciles against the board: still three, not six
store.reconcileTasks([row(1, "Find three 27-inch 4K monitors"), row(2, "Bitcoin summary"), row(3, "Trip")]);
assert.equal(live().length, 3, `a reconcile made twins: ${JSON.stringify(live().map(t => t.id))}`);
assert.deepEqual(live().map(t => t.id).sort(), ["1", "2", "3"], "the chips keep the id the events name");

// the trip is cancelled: its own event clears its only chip
board = [row(1, "Find three 27-inch 4K monitors"), row(2, "Bitcoin summary")];
push({ kind: "task", label: "end", id: "3" });
await sleep(1200);
assert.equal(live().length, 2);
store.reconcileTasks([row(1, "Find three 27-inch 4K monitors"), row(2, "Bitcoin summary")]);
assert.equal(live().length, 2);

// twins left by an older build collapse onto the chip the events name
store.reconcileTasks([]);
await sleep(1200);
store.startTask("48ac70-1", "Find three 27-inch 4K monitors");
store.startTask("1", "Find three 27-inch 4K monitors");
store.reconcileTasks([row(1, "Find three 27-inch 4K monitors")]);
assert.deepEqual(live().map(t => t.id), ["1"]);

// a row the client never heard of is added ONCE, under the session id
store.reconcileTasks([row(1, "x"), row(7, "a new one")]);
assert.deepEqual(live().map(t => t.id).sort(), ["1", "7"]);
store.reconcileTasks([row(1, "x"), row(7, "a new one")]);
assert.equal(live().length, 2);

// an older server that sends no `session` still reconciles by its id, as before
store.reconcileTasks([{ id: "solo", state: "running", title: "old shape" }]);
assert.deepEqual(live().map(t => t.id), ["solo"]);

console.log("ok — one task is one chip");
process.exit(0);

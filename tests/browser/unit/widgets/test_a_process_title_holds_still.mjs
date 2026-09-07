// ============================================================================
// test_a_process_title_holds_still.mjs — V2-608 F7, node 4.121.
//
// THE BUG, seen by the operator on the «Procesos» tab (2026-09-07): a running errand's row began life titled
// «leyendo brickset.com…», then mutated through every phase and progress report — «Tienda oficial LEGO ES:
// descatalogado, sin botón de compra… Sigo c 1/5 · 20%» AS THE TITLE — and only settled «al cabo de no sé
// cuánto tiempo». His ask: «una vez tienes el título que define la tarea, mostramos solo el título», with the
// live activity, the state and the elapsed time underneath it.
//
// Two causes, one per layer. The store kept ONE `text` field that four writers overwrote in turn. And there is
// no `"start"` lifecycle event in the entire backend — grep it: dispatch emits `phase`, `plan`, `progress`,
// `end`, and the one-time naming event «🏷️ encargo nombrado» (V2-530) — so every chip is BORN from its first
// phase, meaning the mutable activity text WAS the title for as long as the updates kept coming.
//
// It MOUNTS the real store and the real SSE handler and replays that exact life. A source test would say the
// fields exist, not that nothing writes across them.
// Run: node tests/browser/unit/widgets/test_a_process_title_holds_still.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "es"], ["hb_i18n_es", JSON.stringify({})]]);
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "es", setAttribute(){}, style: { setProperty(){} } },
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
assert.ok(sink && typeof sink.onmessage === "function", "could not mount the SSE handler");
const push = (obj) => sink.onmessage({ data: JSON.stringify(obj) });
const row = (id) => (store.tasks() || []).find(t => String(t.id) === String(id));

// ── 1. A chip born from its first PHASE (there is no "start" event) shows the phase only as a fallback ──────
push({ kind: "task", label: "phase", id: "t1", text: "leyendo brickset.com…" });
assert.equal(row("t1").note, "leyendo brickset.com…");
assert.equal(row("t1").title, "", "a phase must never be stored as the TITLE");

// ── 2. The one-time naming event (V2-530) settles the title ─────────────────────────────────────────────────
push({ kind: "task", label: "🏷️ encargo nombrado", id: "t1", text: "Buscar tienda con el banco de Gringotts" });
assert.equal(row("t1").title, "Buscar tienda con el banco de Gringotts");

// ── 3. …and from then on, NOTHING moves it: phases, progress, plans update the note underneath ──────────────
push({ kind: "task", label: "phase", id: "t1", text: "comparando precios en Amazon" });
push({ kind: "task", label: "progress", id: "t1", text: "Tienda oficial LEGO ES: descatalogado", pct: 20, done: 1, total: 5 });
push({ kind: "task", label: "plan", id: "t1", text: "5 pasos: mirar · comparar · …" });
const t1 = row("t1");
assert.equal(t1.title, "Buscar tienda con el banco de Gringotts",
  "the title mutated with the activity — this is the exact defect the operator reported");
assert.equal(t1.note, "5 pasos: mirar · comparar · …");
assert.equal(t1.pct, 20);
assert.equal(t1.stepTag, "1/5");

// ── 4. The naming event can arrive BEFORE anything else (reconnect) and must not be downgraded ──────────────
//       — not by a phase, and not by a late `start` either. No emitter sends `start` today (grep the backend),
//       but the branch is live code in sse.js, and the day someone adds the emitter is exactly the day this
//       ordering hazard becomes reachable. A settled name never goes back to being a brief.
push({ kind: "task", label: "🏷️ encargo nombrado", id: "t2", text: "Reservar mesa en Soria" });
push({ kind: "task", label: "phase", id: "t2", text: "abriendo pestaña…" });
push({ kind: "task", label: "start", id: "t2", text: "resérvame mesa mañana en soria" });
assert.equal(row("t2").title, "Reservar mesa en Soria", "a late start downgraded the settled name to the brief");
assert.equal(row("t2").note, "abriendo pestaña…");

// ── 5. The server truth (reconcile) — ONE call with the whole live list, which is what /api/tasks returns.
//       It fills the settled name and the REAL start for a chip that lacks them, and it must NOT clobber a name
//       the 🏷️ event already delivered when its own `title` is still empty (the naming task runs in the
//       background, so the API can easily be behind the SSE). Reconcile drops whatever is not in the list — it
//       is the truth — so a scenario that reconciles twice with partial lists tests the test, not the product.
store.reconcileTasks([
  { id: "t1", goal: "quiero el set del banco de gringotts",
    title: "Buscar tienda con el banco de Gringotts", phase: "comparando", age_s: 60, status: "running" },
  { id: "t2", goal: "resérvame mesa", title: "", phase: "", age_s: 10, status: "running" },
  { id: "t3", goal: "busca un vuelo barato a Roma en octubre",
    title: "Vuelo barato a Roma", phase: "mirando aerolíneas", age_s: 300, status: "running" },
]);
assert.equal(row("t1").title, "Buscar tienda con el banco de Gringotts");
assert.equal(row("t2").title, "Reservar mesa en Soria",
  "a server row with an empty title must not erase the name the SSE already delivered");
const t3 = row("t3");
assert.equal(t3.title, "Vuelo barato a Roma", "an unknown chip is created straight from the server truth");
assert.equal(t3.note, "mirando aerolíneas");
const elapsed = Date.now() - t3.startedAt;
assert.ok(Math.abs(elapsed - 300_000) < 5_000, `startedAt must come from age_s: off by ${elapsed - 300_000}ms`);

console.log("OK — the process title holds still; the activity lives underneath it");

// ============================================================================
// asks.js — the open questions of the agent's tasks (V2-851 F1c): state and I/O, no DOM.
//
// A task that needs him to go on parks a DURABLE question on its row (`state:"waiting"`,
// `waiting_for:"user_answer"`, `ask_id`, `ask`). This module is the screen's copy of those questions:
//   · the SSE `ask` event {task_id, ask_id, text, among?, options?} adds or replaces the question of a task;
//   · the SSE `task_state` event {task_id, state} removes it once the row leaves `waiting`;
//   · `GET /api/tasks?scope=live` is the truth after a reload or a refused answer (the row, not RAM);
//   · `POST /api/tasks/{task_id}/answer {ask_id, text}` answers it — 409 means the question is no longer open.
//
// A question is identified by its `ask_id`, never by its text: a new question on the same task replaces the old
// one, and an answer always names the question it answers. Quick answers exist only when the question carries
// its own `options`; nothing here guesses them from the wording. Rendered by components/TaskAsk.js.
// ============================================================================

import { createSignal } from "./reactive.js?v=2";

// [{task_id, session, ask_id, text, title, options, among, since, sent, error, busy}] — `session` is the per-process
// id a live chip may be keyed by instead of the row id.
export const [openAsks, setOpenAsks] = createSignal([]);

const _str = (v) => (v === undefined || v === null ? "" : String(v));
const _textOf = (a) => (typeof a === "string" ? a : (a && typeof a === "object" ? _str(a.text) : ""));
const _list = (...xs) => {
  for (const x of xs) if (Array.isArray(x) && x.length) return x.map(_str).filter(s => s.trim());
  return [];
};

/** The open question a task row carries, or null when the row is not waiting on his answer. */
export function askOfRow(r) {
  if (!r || r.state !== "waiting" || r.waiting_for !== "user_answer" || !r.ask_id) return null;
  const a = r.ask && typeof r.ask === "object" ? r.ask : {};
  return { task_id: _str(r.id), session: _str(r.session), ask_id: _str(r.ask_id), text: _textOf(r.ask),
           title: _str(r.title || r.goal),
           options: _list(a.options, r.ask_options), among: _list(a.among, r.ask_among),
           since: Number(r.waiting_since) || 0, sent: "", error: false, busy: false };
}

/** SSE `ask`: the question of one task, added or replacing that task's previous one. */
export function onAsk(d) {
  const task_id = _str(d && d.task_id), ask_id = _str(d && d.ask_id);
  if (!task_id || !ask_id) return;
  setOpenAsks(xs => {
    const prev = xs.find(a => a.task_id === task_id);
    if (prev && prev.ask_id === ask_id) return xs;                 // the same question told twice
    const next = { task_id, session: _str(d.session) || (prev ? prev.session : ""), ask_id, text: _str(d.text),
                   title: _str(d.title) || (prev ? prev.title : ""),
                   options: _list(d.options), among: _list(d.among), since: Date.now() / 1000,
                   sent: "", error: false, busy: false };
    return [...xs.filter(a => a.task_id !== task_id), next];
  });
  const cur = openAsks().find(a => a.task_id === task_id);
  if (!cur.title || !cur.session) refreshAsks(false);
}

/** SSE `task_state`: a row that left `waiting` has no open question any more. */
export function onTaskState(d) {
  const task_id = _str(d && d.task_id);
  if (!task_id || d.state === "waiting") return;
  setOpenAsks(xs => (xs.some(a => a.task_id === task_id) ? xs.filter(a => a.task_id !== task_id) : xs));
}

/** The one entry from sse.js. */
export function route(d) {
  if (d && d.kind === "ask") onAsk(d);
  else if (d && d.kind === "task_state") onTaskState(d);
}

/** Read the open questions from the rows. `replace`: the rows are the truth (a reload, a refused answer);
 *  otherwise only the titles of the questions already shown are filled in. */
export async function refreshAsks(replace = true) {
  let rows;
  try {
    const r = await fetch("/api/tasks?scope=live", { cache: "no-cache" });
    const d = await r.json();
    rows = Array.isArray(d && d.tasks) ? d.tasks : [];
  } catch (_) { return; }
  const fromRows = rows.map(askOfRow).filter(Boolean);
  setOpenAsks(xs => {
    if (!replace) return xs.map(a => {
      const row = rows.find(r => _str(r.id) === a.task_id);
      return !row ? a : { ...a, title: a.title || _str(row.title || row.goal), session: a.session || _str(row.session) };
    });
    // The rows decide WHICH questions are open; what this screen already knows of the same question (that he
    // answered it a moment ago) is kept rather than offered again.
    return fromRows.map(a => {
      const prev = xs.find(p => p.task_id === a.task_id && p.ask_id === a.ask_id);
      return prev ? { ...a, title: a.title || prev.title, sent: prev.sent } : a;
    });
  });
}

let _booted = false;
/** The first surface that shows questions reads them from the rows once — the reload path. */
export function ensureAsks() {
  if (_booted) return;
  _booted = true;
  refreshAsks(true);
}

const _patch = (task_id, ask_id, fields) =>
  setOpenAsks(xs => xs.map(a => (a.task_id === task_id && a.ask_id === ask_id ? { ...a, ...fields } : a)));

/** Answer one question from the screen. Resolves to the HTTP status (0 = it never reached the engine). */
export async function answer(task_id, ask_id, text) {
  const body = _str(text).trim();
  const cur = openAsks().find(a => a.task_id === task_id && a.ask_id === ask_id);
  if (!body || !cur || cur.busy || cur.sent) return 0;
  _patch(task_id, ask_id, { busy: true, error: false });
  let status = 0;
  try {
    const r = await fetch("/api/tasks/" + encodeURIComponent(task_id) + "/answer", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ask_id, text: body }),
    });
    status = r.status;
  } catch (_) { status = 0; }
  if (status === 200) _patch(task_id, ask_id, { busy: false, sent: body });
  else if (status === 409) await refreshAsks(true);              // answered elsewhere or expired: the row decides
  else _patch(task_id, ask_id, { busy: false, error: true });
  return status;
}

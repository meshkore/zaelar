// ============================================================================
// TaskAsk.js — the task's question on screen (V2-851 F1c).
//
// A question a task parked for him is drawn in TWO places, from ONE list (core/asks.js):
//   · on the chat wall, as a line of its own under the conversation (`AskWall`), one per waiting task;
//   · on that task's entry in the processes panel (`AskSlot`, mounted by ProcessEntry), both shells.
// Each line names the task it belongs to, so two waiting tasks are never one ambiguous question. He answers
// with the field and its send button, or with a quick button when the question declared its `options`.
//
// Nodes are cached per question state and reconciled in place: a wall that repaints while he types keeps the
// field, its text and its focus. What he typed survives a repaint too (`_drafts`, by ask_id).
// ============================================================================

import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as asks from "../core/asks.js?v=1";
import { t } from "../core/i18n.js?v=1";

const _nodes = new Map();     // state key → node
const _drafts = new Map();    // ask_id → what he has typed so far
let _slotsWatched = false;

function titleOf(a) {
  if (a.title) return a.title;
  const rows = ((store.taskRows() || {}).live || []).concat(store.tasks() || []);
  const row = rows.find(r => String(r.id) === a.task_id || String(r.session || "") === a.task_id);
  return (row && (row.title || row.goal)) || t("chat.askTaskFallback");
}

function send(a, text, input) {
  const body = String(text || "").trim();
  if (!body) { if (input) input.focus(); return; }
  _drafts.delete(a.ask_id);
  asks.answer(a.task_id, a.ask_id, body);
}

function askNode(a, where) {
  const title = titleOf(a);
  const box = h("div", { class: "tq tq--" + where, "data-task": a.task_id, "data-ask": a.ask_id, "data-source": "ask",
                         role: "group", "aria-label": t("chat.askOf", { title }) });
  box.appendChild(h("div", { class: "tq-task" }, t("chat.askOf", { title })));
  if (a.among.length) {
    const names = a.among.map(id => titleOf({ task_id: id, title: "" })).join(" · ");
    box.appendChild(h("div", { class: "tq-among" }, t("chat.askAmong", { titles: names })));
  }
  box.appendChild(h("div", { class: "tq-text" }, a.text));
  if (a.sent) {
    box.appendChild(h("div", { class: "tq-sent" }, t("chat.askSent", { text: a.sent })));
    return box;
  }
  if (a.options.length) {
    box.appendChild(h("div", { class: "tq-opts" }, ...a.options.map(o =>
      h("button", { type: "button", class: "hb-btn hb-btn--secondary hb-btn--sm tq-opt", disabled: a.busy,
                    onClick: () => send(a, o, null) }, o))));
  }
  const input = h("input", { type: "text", class: "hb-input tq-input", placeholder: t("chat.askPlaceholder"),
                             "aria-label": t("chat.askPlaceholder"), disabled: a.busy });
  input.value = _drafts.get(a.ask_id) || "";
  input.addEventListener("input", () => _drafts.set(a.ask_id, input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); e.stopPropagation(); send(a, input.value, input); }
  });
  box.appendChild(h("div", { class: "tq-form" }, input,
    h("button", { type: "button", class: "hb-btn hb-btn--primary hb-btn--sm tq-send", disabled: a.busy,
                  onClick: () => send(a, input.value, input) }, t("chat.askSend"))));
  if (a.error) box.appendChild(h("div", { class: "tq-err", role: "alert" }, t("chat.askFailed")));
  return box;
}

function nodeFor(a, where) {
  const key = [where, a.task_id, a.ask_id, a.sent ? 1 : 0, a.error ? 1 : 0, a.busy ? 1 : 0, titleOf(a), store.lang()].join("|");
  if (!_nodes.has(key)) _nodes.set(key, askNode(a, where));
  return _nodes.get(key);
}

// Reconcile `box` to exactly `want`, in order, moving nothing that is already in place.
function paint(box, list, where) {
  const want = list.map(a => nodeFor(a, where));
  [...box.children].forEach(n => { if (!want.includes(n)) n.remove(); });
  want.forEach((n, i) => { if (box.children[i] !== n) box.insertBefore(n, box.children[i] || null); });
}

function _prune() {
  const live = new Set(asks.openAsks().map(a => a.ask_id));
  for (const [k, n] of _nodes) if (!live.has(n.dataset.ask) || !n.isConnected) _nodes.delete(k);
}

/** The chat wall's block of open questions — one line per waiting task. Mounted once by ChatWall. */
export function AskWall() {
  asks.ensureAsks();
  const box = h("div", { class: "tq-wall", "aria-live": "polite" });
  createEffect(() => { paint(box, asks.openAsks(), "wall"); _prune(); });
  return box;
}

// A slot is keyed by the row id or, under a live chip, by the process's session id — the question matches either.
function _paintSlot(slot) {
  const k = slot.dataset.task;
  paint(slot, asks.openAsks().filter(a => a.task_id === k || (a.session && a.session === k)), "entry");
}

/** The question of ONE task, under its entry in the processes panel. Repainted from the shared list. */
export function AskSlot(taskId) {
  asks.ensureAsks();
  const slot = h("div", { class: "tq-slot", "data-task": String(taskId || "") });
  if (!_slotsWatched) {
    _slotsWatched = true;
    createEffect(() => { asks.openAsks(); document.querySelectorAll(".tq-slot[data-task]").forEach(_paintSlot); _prune(); });
  }
  _paintSlot(slot);
  return slot;
}

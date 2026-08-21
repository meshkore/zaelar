// ============================================================================
// feedback-state.js — the ONE reading of what the feedback API just answered (V2-256).
//
// Why this is a module and not two `if`s in two components: the rule lived TWICE and only one copy
// had it. The mobile sheet closed the loop (`else setFbDone(...)`); the desktop widget's `send()` was
// a bare `if (res && res.ok) { … }` with nothing after it. On 2026-08-21 the operator pressed Send on
// the desktop, the ingestion endpoint refused the POST (HTTP 401) and the panel showed exactly nothing: no error, no thanks, the text still in the box and
// no way to tell whether it had gone out. Fourth duplicated rule found this week; same shape every
// time, and the fix is always to leave one copy.
//
// TWO readings, not one, because they answer different questions and only one of them can lie:
//
//   sendOutcome  did this message leave?  Success and failure BOTH have to say so — a form that goes
//                quiet is indistinguishable from a form that worked.
//   listOutcome  can we see the list at all?  `listFeedback()` degrades to `{ok:false, items:[]}`, and
//                painting that as "Nothing sent yet" is not a smaller truth, it is a different and
//                wrong one: it tells someone their reports were never sent when the fact is that we
//                cannot reach the service to look.
//
// `detail` carries whatever the transport already knew (the HTTP status, or a non-generic error code)
// so the visible line names a fact instead of a mood. It is deliberately terse — one parenthetical,
// never a stack trace — but it is never dropped, because "it didn't work" is the answer that costs a
// day and "(401)" is the answer that costs a minute.
// ============================================================================

/** The one short fact worth showing next to the human sentence. "" when there is genuinely nothing —
 *  never invent, never echo the generic code that every failure already carries. */
function detailOf(res) {
  if (!res || typeof res !== "object") return "";
  if (Number.isFinite(res.status)) return String(res.status);
  const err = typeof res.error === "string" ? res.error.trim() : "";
  return err && err !== "send_failed" ? err : "";
}

/** What the New tab must show after a submit. `ok:false` is a RESULT, not an absence of one. */
export function sendOutcome(res) {
  if (res && res.ok) return { ok: true, key: "feedback.thanks", detail: "" };
  return { ok: false, key: "feedback.sendError", detail: detailOf(res) };
}

/** What the Sent tab must show. `reachable:false` is why the empty key differs — see the header. */
export function listOutcome(res) {
  const reachable = !!(res && res.ok);
  const items = Array.isArray(res && res.items) ? res.items : [];
  return {
    reachable,
    items,
    emptyKey: reachable ? "feedback.emptyState" : "feedback.listUnavailable",
    detail: reachable ? "" : detailOf(res),
  };
}

/** The visible line: the translated sentence, plus the fact when there is one. `translate` is passed
 *  in (not imported) so this module stays free of the i18n graph and testable without a browser. */
export function lineFor(outcome, translate) {
  const text = translate(outcome.key);
  return outcome.detail ? `${text} (${outcome.detail})` : text;
}

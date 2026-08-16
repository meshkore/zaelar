// ============================================================================
// feedback-api.js — thin fetch wrapper over /api/feedback (server/feedback_api.py, V2-099). Kept
// separate from the shared services/api.js on purpose: this whole feature is a single, self-contained,
// removable module (button + panel + these two service files), not a seam through the general API
// surface. No state, no UI — matches the convention of the rest of services/.
// ============================================================================

export const listFeedback = () => fetch("/api/feedback", { cache: "no-store" }).then(r => r.json()).catch(() => ({ ok: false, items: [] }));

export const sendFeedback = ({ message, email = "", includeSessionEvidence = false }) =>
  fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, email, include_session_evidence: includeSessionEvidence }),
  }).then(r => r.json()).catch(() => ({ ok: false, error: "send_failed" }));

// account-link.js — the link to an account page (when ZAELAR_ACCOUNT_URL is set), built from the ONE url the engine knows (V2-785).
//
// The engine owns the url (`nucleo/energy/account.account_url`, env `ZAELAR_ACCOUNT_URL`) and hands it to the
// interface in `/api/config` and `/api/energy`. Nothing here carries its own literal: until 2026-10-22 the desktop
// had one and the phone had a RELATIVE "/account", which in a hosted deployment pointed at the agent's own origin —
// a page that does not exist. Pure, so it is tested without a browser.

/** `url` + optional `#fragment` (replacing any fragment it had). Empty url → "" (self-host: no account page). */
export function accountLink(url, fragment = "") {
  const base = String(url || "").trim().split("#")[0];
  if (!base) return "";
  return fragment ? `${base}#${fragment}` : base;
}

/** The reason the out-of-energy notice should be open for, or "" when it should not. Pure: the decision the
 *  rendered test (and anyone reading the notice) relies on. A notice the person closed stays closed for THAT
 *  reason; a new exhaustion (a different reason, or after the balance recovers and runs out again) opens it again. */
export function noticeReason(energy, closedFor = "") {
  const e = energy || {};
  if (!e.cloud || !e.exhausted) return "";
  const reason = String(e.exhausted.reason || "exhausted");
  return reason === closedFor ? "" : reason;
}

/** The reasons that mean the ACCOUNT cannot spend — the engine's `nucleo/energy/limits.py::ACCOUNT_EMPTY`, the one
 *  list both sides read (V2-801). Any other reason (a lease that could not be renewed) stopped the agent without
 *  knowing the account's state. */
export const ACCOUNT_EMPTY = new Set(["energy_denied", "balance_depleted"]);

/** Which notice to paint: "out" (the account has no Energy — copy and Top up) or "paused" (stopped, account state
 *  not claimed, no Top up). Pure. "out" needs BOTH a reason that means it AND a battery that does not contradict
 *  it: a known balance above zero never shows «your account has no Energy» (the modal once said empty while the
 *  battery showed most of the plan lit). */
export function noticeKind(energy) {
  const e = energy || {};
  const reason = String((e.exhausted && e.exhausted.reason) || "");
  const showsEnergy = !!e.known && Number(e.balance) > 0;
  return ACCOUNT_EMPTY.has(reason) && !showsEnergy ? "out" : "paused";
}

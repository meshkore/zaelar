// ============================================================================
// voiceCommands.js — front-end fast-path for voice control of the canvas.
//
// AUTHORITY = the brain (Hermes): it hears intent and emits [[show:id]]/[[close:id]]
// /[[close]] tags (and pushes data widgets). This fast-path ONLY handles EXPLICIT,
// unambiguous commands INSTANTLY (no waiting on the brain): "abre/muestra X",
// "cierra/quita/limpia [todo|X]". Subtler intent is left to the brain. All ops are
// idempotent, so the brain doing the same thing too is harmless.
// ============================================================================
import { identifyWidget } from "./api.js?v=2";

// Match by VERB STEM on accent-stripped text, so every conjugation triggers the instant local fast-path
// ("show me / show / open / close it / clear it" all hit). This is what makes "show the agenda" appear
// in ~50ms instead of waiting 2-6s for the brain's reply to carry [[show]].
const norm = s => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const OPEN_RE  = /\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|dejame ver/;   // stems (no trailing \b)
// V2-776 F (demo pass 2026-09-28): the CLOSE and MOVE branches of this lane are GONE. They were a verb table
// acting on the client before the engine read the turn, and «ok close that» proved the comment above wrong —
// «the brain doing the same thing too is harmless»: this lane closed the last card (Markets), the engine then
// read a canvas without it and its sure `close` verdict closed the NEXT card (the agenda). Two mutations for one
// order, and a rule duplicated in three places (client, attention.py, the brain) that had to be kept in step by
// hand. Closing and moving belong to the engine now: exact phrases in the action map, `close_widget` and the
// canvas verdict for the rest. OPEN stays here: it is idempotent and it is what makes a card appear in ~50 ms.

// Fire ONCE per command across the growing interim transcripts (and repeated finals): dedupe by action signature.
let _lastVoiceAct = { sig: "", ts: 0 };
function _act(sig) {
  const now = Date.now();
  if (sig === _lastVoiceAct.sig && now - _lastVoiceAct.ts < 2500) return false;
  _lastVoiceAct = { sig, ts: now }; return true;
}

// REAL-TIME reactivity: this runs on PARTIAL (interim) transcripts too, so an OPEN embedded mid-sentence executes
// the instant it's recognized — no waiting for you to stop talking (reversible, idempotent). Nothing else.
export async function handleWidgetVoice(desktop, text, isFinal) {
  if (!desktop) return;
  const n = norm(text);
  if (OPEN_RE.test(n)) {                                      // show — acts on INTERIM too (instant, mid-sentence)
    const target = await identifyWidget(text);
    if (target && _act("show:" + target)) desktop.show(target, { q: text });
  }
  // everything else — closing, moving, anything inside a card — is the engine's
}

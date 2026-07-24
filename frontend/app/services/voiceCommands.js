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
// ("enséñame / muéstrame / ábreme / ciérrala / límpiala" all hit). This is what makes "show the agenda" appear
// in ~50ms instead of waiting 2-6s for the brain's reply to carry [[show]].
const norm = s => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const OPEN_RE  = /\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|dejame ver/;   // stems (no trailing \b)
const CLOSE_RE = /\b(quit|cierr|cerr|elimin|borra|escond|ocult|limpi|despej|vaci|recog|apart|remove|close|hide|dismiss|clear)/;
// "all" scope: explicit "todo/all/everything", OR the generic PLURAL noun for the cards ("widgets", "tarjetas",
// "cards") — "close widgets" / "cierra los widgets" means the whole set. Kept PLURAL on purpose so a singular,
// named "close the meteo widget" still targets just that one (falls through to identify()).
const ALL_RE   = /\b(todo|todos|todas|all|everything|widgets|tarjetas|cards|la pantalla|el escritorio|el canvas|el mural|todo esto)/;
// MOVE: verb-ish move intent + a DIRECTION. "muévelo a la izquierda", "ponlo a la derecha", "lo quiero arriba".
// The direction gate keeps "pon el reloj" (no direction → SHOW) from being mistaken for a move.
const MOVE_RE  = /\b(muev|mueve|mover|desplaz|coloc|reubic|reajust|arrastr|move)|ponl|\bpon\b|\bquiero\b/;
const DIR_RE   = /\b(izquierd|derech|centr|medio|arrib|abaj|encim|debaj|left|right|center|middle|top|bottom)/;

// Fire ONCE per command across the growing interim transcripts (and repeated finals): dedupe by action signature.
let _lastVoiceAct = { sig: "", ts: 0 };
function _act(sig) {
  const now = Date.now();
  if (sig === _lastVoiceAct.sig && now - _lastVoiceAct.ts < 2500) return false;
  _lastVoiceAct = { sig, ts: now }; return true;
}

// REAL-TIME reactivity: this runs on PARTIAL (interim) transcripts too, so a UI command embedded mid-sentence
// executes the instant it's recognized — no waiting for you to stop talking. SHOW acts on interim (reversible,
// idempotent). CLOSE waits for the FINAL (an interim can be revised → never close on a guess).
export async function handleWidgetVoice(desktop, text, isFinal) {
  if (!desktop) return;
  const n = norm(text);
  if (DIR_RE.test(n) && MOVE_RE.test(n)) {                    // reposition — needs a direction; FINAL only (no jump on a guess)
    if (!isFinal) return;
    const where = (n.match(DIR_RE) || [""])[0];
    let target = await identifyWidget(text);
    if (!target) { const o = desktop.list(); target = o[o.length - 1]; }   // "muévelo" → last opened
    if (target && desktop.move && _act("move:" + target + ":" + where)) desktop.move(target, where);
    return;
  }
  if (CLOSE_RE.test(n)) {                                     // dismiss — only on the FINAL transcript
    if (!isFinal) return;
    if (ALL_RE.test(n)) { if (_act("closeAll")) desktop.closeAll(); return; }
    let target = await identifyWidget(text);
    if (!target) { const o = desktop.list(); target = o[o.length - 1]; }   // "quítalo" → last opened
    if (target && _act("close:" + target)) desktop.close(target);
    return;
  }
  if (OPEN_RE.test(n)) {                                      // show — acts on INTERIM too (instant, mid-sentence)
    const target = await identifyWidget(text);
    if (target && _act("show:" + target)) desktop.show(target, { q: text });
  }
  // no explicit open/close verb → leave it to the brain (it shows/pushes whatever the request needs)
}

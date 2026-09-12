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
const CLOSE_RE = /\b(quit|cierr|cerr|elimin|borra|escond|ocult|limpi|despej|vaci|recog|apart|remove|close|hide|dismiss|clear)/;
// "all" scope: the generic PLURAL noun for the cards ("widgets", "tarjetas", "cards") — "close widgets" /
// "cierra los widgets" means the whole set. Kept PLURAL on purpose so a singular, named "close the meteo
// widget" still targets just that one (falls through to identify()).
const ALL_RE   = /\b(widgets|tarjetas|cards|la pantalla|el escritorio|el canvas|el mural)/;
// V2-664 — A BARE QUANTIFIER IS NOT THE CANVAS UNTIL IT SAYS SO. This is the client half of the rule in
// `voice/attention.py::_quantifies_the_canvas` (parallel implementations must not drift — V2-252/V2-555):
// «todo/todos/todas/all» used to count anywhere in the turn, so a close verb in one clause and a quantifier
// fifteen words later in ANOTHER wiped the desktop. Measured live 2026-09-11 (session eedf7f9b): «Vale,
// quita, por favor, los datos de comidas de la agenda… todas esas entradas de la…» — an order to delete ROWS
// INSIDE the agenda — closed every card he had open. What decides is what the quantifier GOVERNS: nothing
// («cierra todo»), a particle («ciérralo todo ya») or a card noun («todos los widgets») is the canvas; any
// other noun («todas esas entradas») is a thing inside a widget.
const QUANT_RE = /\b(?:todo|toda|todos|todas|all|everything)\b(?:\s+(?:los|las|el|la|mis|tus|sus|esos|esas|estos|estas|the|my|your)\b)?(?:\s+(\w+))?/g;
const CARD_WORD_RE = /^(?:widgets?|tarjetas?|ventanas?|cards?|pantallas?|escritorios?|canvas|mural|esto|eso|abierto|abiertos)$/;
const PARTICLE_RE  = /^(?:ya|ahora|porfa|por|favor|please|now|de|una|vez|y|pero|vale|ok|anda|venga|gracias)$/;
function quantifiesTheCanvas(n) {
  QUANT_RE.lastIndex = 0;
  let m;
  while ((m = QUANT_RE.exec(n))) {
    const w = m[1] || "";
    if (!w || PARTICLE_RE.test(w) || CARD_WORD_RE.test(w)) return true;
  }
  return false;
}
// V2-678 — NEGATION + CLAUSE, the client half of `voice/attention.py::_closes_the_whole_canvas`
// (parallel implementations must not drift — V2-252/V2-555). This lane had NO negation check at all and
// asked its two questions of the WHOLE turn, so measured live 2026-09-12 (session 352268b5) it wiped the
// canvas twice in six seconds: «Close also the agenda. And reposition all the widgets.» (verb in one
// clause, quantifier in the next, where the verb is «reposition») and «I said reposition widgets. Do not
// close the widgets.» — the sentence that says not to. A false veto leaves the brain to close everything a
// second later; a false positive destroys the desktop with no undo, so this errs toward NOT firing.
const NO_CLOSE_RE = /\bno\s+(?:me\s+|lo\s+|la\s+|los\s+|las\s+)?(?:cierr|ocult|escond|apagu|quit)\w*|\b(?:do\s+not|don'?t|never)\s+(?:\w+\s){0,2}?(?:close|hide|shut|remove|clear)\b/;
const CLAUSE_SPLIT_RE = /[.;!?\n]|\sy\s|\sand\s|\spero\s|\sbut\s/;
function closesTheWholeCanvas(n) {
  for (const clause of n.split(CLAUSE_SPLIT_RE)) {
    const c = (clause || "").trim();
    if (!c || !CLOSE_RE.test(c)) continue;
    if (!(ALL_RE.test(c) || quantifiesTheCanvas(c))) continue;
    if (NO_CLOSE_RE.test(c)) continue;
    return true;
  }
  return false;
}
// FULLSCREEN VETO (V2-600 → V2-601 T-07): «cierra la pantalla completa» is about a SCREEN STATE, never a
// close-all — and the STT renders it as «…completamente» too. The veto landed in the server backstops
// (voice/attention.py::mentions_fullscreen) and this third, client-side copy of the rule kept closing the whole
// canvas: same vocabulary, mirrored here because CLOSE_RE("cierr") + ALL_RE("la pantalla") match that sentence.
const FULLSCREEN_RE = /\bpantalla\s+completa(?:mente)?\b|\bfull\s*screen\b|\bfullscreen\b/;
// MOVE: verb-ish move intent + a DIRECTION. "move it left", "put it right", "I want it up".
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
    if (!target) { const o = desktop.list(); target = o[o.length - 1]; }   // "move it" → last opened
    if (target && desktop.move && _act("move:" + target + ":" + where)) desktop.move(target, where);
    return;
  }
  if (CLOSE_RE.test(n)) {                                     // dismiss — only on the FINAL transcript
    if (!isFinal) return;
    if (FULLSCREEN_RE.test(n)) return;                        // a fullscreen mention is a screen-state order → the brain's
    if (closesTheWholeCanvas(n)) { if (_act("closeAll")) desktop.closeAll(); return; }
    if (NO_CLOSE_RE.test(n)) return;          // «do not close them» is not an order to close ONE either
    let target = await identifyWidget(text);
    if (!target) { const o = desktop.list(); target = o[o.length - 1]; }   // "remove it" → last opened
    if (target && _act("close:" + target)) desktop.close(target);
    return;
  }
  if (OPEN_RE.test(n)) {                                      // show — acts on INTERIM too (instant, mid-sentence)
    const target = await identifyWidget(text);
    if (target && _act("show:" + target)) desktop.show(target, { q: text });
  }
  // no explicit open/close verb → leave it to the brain (it shows/pushes whatever the request needs)
}

// ============================================================================
// sse.js — server-sent events stream (/events). Routes backend pushes to the
// reactive store (bot speech, latency) and to the widget desktop (show/create/
// modify/close). Transcripts feed the voice-command fast-path. The brain remains
// the authority; this just reacts to what it emits.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { handleWidgetVoice } from "./voiceCommands.js?v=3";
import { createAttentionHold } from "./attention_hold.js?v=1";
import { refreshStatus } from "./status.js?v=2";
import * as vault from "./vault.js?v=1";
import { t, applyLang } from "../core/i18n.js?v=1";
import { setWallpaper } from "./theme.js?v=2";

// V2-464 — SHOWCASE mode: ?showcase=1 in the URL. The use-case recorder (recorder.py) uses it to keep the chat
// open and the grid auto-arranged, so the video is readable without hands.
// Guarded: the frontier harness mounts this module under Node, where `location` does not exist.
const _SHOWCASE = typeof location !== "undefined" && new URLSearchParams(location.search).has("showcase");
let _arrT = null;
let _attnWinS = 12;   // last window_s seen from the gate — the ring's re-arm span (see the bot_speech branch)
const VAD_HOLD_S = 180; // V2-661: how long an active voice may hold the ring without a falling edge (engine's cap)
const BOT_HOLD_S = 600; // …and while ZAELAR talks (its `idle` edge re-arms a real window; this is the safety net)
let _voiceActive = false;   // V2-661b: his VAD is ON — his silence has not started, so no timer may be shortened

// ── V2-647: a spoken turn waits for the attention gate's verdict ─────────────────────────────────────────
// The decision itself lives in `attention_hold.js` (dependency-free, and what the tests drive); here we only
// wire it to this channel's two seams — the transcript that arrives first, and the gate's ruling that
// arrives just after. See that module for the measured session this comes from.
const _hold = createAttentionHold({
  mode: () => store.attentionMode(),
  deliver: (text, isFinal, judged) => {
    // V2-664: the canvas fast-path acts only on speech the GATE ruled directed. A fail-open release still
    // paints the wall (never lose a word) but may not open, close or move a card — see attention_hold.js.
    if (judged) handleWidgetVoice(_holdDesk, text, isFinal);
    store.pushChat({ role: "you", text });
  },
});
let _holdDesk = null;   // the canvas the delivery acts on, captured per event (sse.js has no module-level desktop)

export function holdSpokenTurn(desktop, text, isFinal) { _holdDesk = desktop; _hold.spoken(text, isFinal); }
export function settleHeldTurns(desktop, verdictText, directed) { _holdDesk = desktop; _hold.verdict(verdictText, directed); }

let es = null;

export function openSSE(desktop) {
  if (es) return;               // already subscribed: reopening would kill the live stream and lose in-flight events
  es = new EventSource("/events");
  // V2-038: on (re)connect, RECONCILE activity chips against the server's truth (GET /api/tasks reads the RAM
  // registry) → no more orphaned chips after a restart/crash. STATE leads; the UI is its mirror.
  es.onopen = () => { try { store.fetchTasks(); } catch (_) {} };
  es.onmessage = ev => {
    let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
    if (d.kind === "bot_speech") {                              // gate person-voice visuals + drive live captions + latency
      // LiveKit engine emits label "speaking"/"idle" (+ a `speaking` bool); the older engine used "started"/"stopped".
      // Prefer the explicit bool, fall back to either label vocabulary.
      const speaking = typeof d.speaking === "boolean" ? d.speaking
                     : /speaking|started/.test(String(d.label));
      store.setBotSpeaking(speaking);
      // The ring mirrors the REAL window (2026-09-09, session 0071d30e): the backend holds an open window
      // while zaelar talks and re-anchors it at its last word (attention.note_bot_speech) — but the ring's
      // timer only knew the last directed turn, so it died mid-reply and the operator read «no veo el círculo
      // verde» as deafness while the mic was in fact still his. Held while speaking, re-armed for a full
      // window on idle; a ring already off stays off (the bot's own speech never OPENS one).
      if (store.attentionHit()) store.pulseAttentionHit(speaking ? BOT_HOLD_S : _attnWinS);
      if (d.ttfa_ms != null) store.setLatency(d.ttfa_ms + " ms");
    } else if (d.kind === "vad" && d.edge) {
      // V2-661 — the window measures the operator's SILENCE, and his silence has not started while he is
      // talking. Measured 2026-09-11 (session 1cdcb08e): he spoke for 47 s without a pause and the ring went
      // dark 5 s in — the timer only knew the last verdict, and no verdict arrives mid-sentence. Held while
      // his voice is active (a long ceiling, never forever: a missed falling edge must not pin it), re-armed
      // for a full window the instant it stops. A ring already off stays off — room speech never lights it.
      _voiceActive = (d.edge === "on");
      if (store.attentionHit()) store.pulseAttentionHit(_voiceActive ? VAD_HOLD_S : _attnWinS);
    } else if (d.kind === "error") {
      console.warn("voice error:", d.label || "");              // clean screen: log only, no banner
      refreshStatus();                                          // but do reflect it in the ◉ status icon
    } else if (d.kind === "widget" && desktop) {
      // THE CANVAS NEVER OBEYS ITS OWN REPORT (V2-261). `src:"user"` marks events that ORIGINATE in the canvas:
      // `desktop._persist()` reports the open set to `/api/canvas/state`, and that route compares it with the
      // previous one and emits `widget/show|close` with «user» provenance to put the operator's manual action on
      // the timeline (V2-039 audit — previously these were SILENT actions). But that audit travels through the
      // SAME channel as the COMMANDS, so it came back here and was executed.
      //
      // Measured consequence, seen by the operator on screen: the task opens `navegador::t2`, the canvas
      // reports it, the route NORMALIZES the instance to its base (`navegador`), the diff says «navegador opened»,
      // and two seconds later an empty BASE browser card («opening tab…») appeared over the real one.
      // Evidence: `['navegador::t1'] → ['navegador::t1','navegador']`, always 2 s later. It was observed in
      // V2-047 F9 («two browsers, one blank») and only INSTRUMENTED, never closed.
      //
      // It is cut off here, at the ONLY place where both hosts (desktop and mobile) receive this, rather than in
      // the route: the audit must keep emitting with its label so observability and the Master continue counting
      // it the same way. The missing rule concerns the report, not the event: **a report of what already happened
      // is not an order**, and the sender is precisely the one who has nothing to do with it.
      const _eco = d.src === "user";
      if (d.label === "show" && d.id && !_eco) {
        desktop.show(d.id, { data: d.data });       // brain shows it (with pushed data, if any)
        // V2-464 — in showcase, each opening rearranges the grid automatically, so an unattended recording
        // remains aligned without hands. Showcase only: auto-arrangement would move things for a normal operator.
        if (_SHOWCASE) { clearTimeout(_arrT); _arrT = setTimeout(() => desktop.arrange && desktop.arrange(), 700); }
      }
      else if (d.label === "create" && d.id) desktop.createWidget(d.id, d.spec);  // brain asked to BUILD a new widget
      else if (d.label === "modify" && d.id) desktop.modifyWidget(d.id, d.change);// brain asked to EDIT an existing widget
      else if (d.label === "delete" && d.id) { desktop.onDeleted(d.id); store.setWidgetConfirm(null); }   // backend ALREADY deleted (lifecycle) → close the card + drop the cached catalog
      else if (d.label === "restore" && d.id) store.setWidgetConfirm(null);       // restore executed (V2-518 audit event; the paired "delete" closes the card)
      // V2-086: the RESERVED id "clusters" is not a card but the NATIVE tab — its Yes/No is rendered there
      // (connecting to a network is not a canvas action, and that widget no longer exists).
      else if (d.label === "confirm" && d.id === "clusters") { store.setClusterConfirm({ question: d.question }); store.setChatTab("clusters"); store.setChatOpen(true); }
      else if (d.label === "confirm-cancel" && d.id === "clusters") store.setClusterConfirm(null);
      else if (d.label === "confirm" && d.id) {                                   // irreversible action (delete/restore/data)
        desktop.showConfirm(d.id, { question: d.question, action: d.action });    // Yes/No overlay ON the card…
        // …and the SAME question in the chat thread (V2-518, house norm: no popups — questions live in the
        // conversation). One pending at a time, like the backend registry.
        store.setWidgetConfirm({ id: d.id, question: d.question || "", action: d.action || "" });
        store.setChatTab("chat"); store.setChatOpen(true);
      }
      else if (d.label === "confirm-cancel" && d.id) { desktop.hideConfirm(d.id); store.setWidgetConfirm(null); }   // resolved/cancelled elsewhere (voice/timeout)
      else if (d.label === "close" && !_eco) d.id ? desktop.close(d.id) : desktop.closeAll();
      else if (d.label === "arrange") desktop.arrange && desktop.arrange();       // V2-464: rejilla alineada (showcase/API)
      else if (d.label === "move" && d.id) desktop.move(d.id, d.where);            // reposition on the canvas (left/right/…)
      else if (d.label === "resize" && d.id) desktop.resize(d.id, d.data);          // resize a widget (HERMES-ONLY)
      else if (d.label === "fullscreen" && d.id) desktop.fullscreen(d.id);          // toggle native fullscreen
      else if (d.label === "minimize" && d.id) desktop.shrink(d.id);                // V2-635: one honest step down
      // A widget's STORED data changed (its own ctx.action, or Hermes via [[widget.data]]) — widgets/store.py is
      // the single choke point that emits this. No polling anywhere: re-fetch + re-render ONLY if that widget
      // happens to be open right now; otherwise there's nothing on screen to update.
      else if (d.label === "data" && d.id) desktop.refreshData(d.id);
      else if (d.label === "alias") desktop.refreshRegistry && desktop.refreshRegistry();  // V2-082: a name/alias changed → repaint header + panel
      // V2-641: the voice set (or cleared) the desktop WALLPAPER — the server already persisted it, so this
      // apply is persist:false (echoing it back would be a pointless write loop). Empty url = clear.
      else if (d.label === "wallpaper") setWallpaper(d.url ? { url: d.url, title: d.title || "" } : null, { persist: false });
    } else if (d.kind === "panel") {                                              // V2-079/086: the brain opens/closes the native panel (chat/processes/crons/clusters) by voice
      // 2026-08-10: it also CLOSES. `show_panel` only knew how to open, so «close the chat» had nowhere to go
      // and the turn ended with a false «okay, closed» — the operator asked five times in a row and had to close
      // it with the ✕. The chat is NATIVE UI, not a card: [[close]] does not touch it.
      if (d.label === "close") { store.setChatOpen(false); }
      else {
        // The whitelist MUST include every tab that `router._canon_panel` can return, or the backend routes it
        // correctly and the frontend drops it by opening «Chat» (this happened to `clusters` at birth, V2-086).
        const tab = ["procesos", "crons", "clusters"].includes(d.tab) ? d.tab : "chat";
        store.setChatTab(tab);
        store.setChatOpen(true);
      }
    } else if (d.kind === "filler" && d.text) {
      // Lead-in wait-filler (V2-093/V2-122): a real phrase the agent just said out loud, so it belongs in the
      // chat wall — but pushed with its own distinct marker, never as `kind:"transcript"`, so it can't be
      // confused with a real LLM-generated reply. Emitted explicitly and synchronously by lead_in_filler.py the
      // instant it's decided (always BEFORE any real reply text exists), so it lands in the right order without
      // depending on LiveKit's own conversation-item timing — the exact mechanism that caused the original bug
      // (a filler showing up AFTER an already-resolved reply).
      store.pushAgentChat("💬 " + d.text);
    } else if (d.kind === "transcript" && d.text) {
      if (d.role === "assistant") {
        // zaelar's FINAL turn text → chat wall (the HISTORY). The LIVE caption over the orb does NOT come from here
        // (this fires once, late): it's driven by LiveKit's audio-synced transcription in session-lk.js. And it must
        // NOT hit the voice-command fast-path — zaelar saying "cierro la agenda" is not the operator asking to close.
        store.pushAgentChat(d.text);
      } else {
        // isFinal gates the CLOSE fast-path (never close on a revisable guess). Voice: "transcript" = final,
        // "interim" = partial. TYPED chat/paste ("text-injected …") is DEFINITIVELY final — treat it as such, or a
        // typed "close widgets" would be seen as interim and the close fast-path would never fire.
        const isFinal = d.label === "transcript" || (d.label || "").startsWith("text-injected");
        const typed = (d.label || "").startsWith("text-injected");
        // V2-647 — THE ROOM IS NOT THE OPERATOR. The mic is always open and the attention gate decides, per
        // turn, whether the words were addressed to zaelar; that verdict travels as its own `ambient` event
        // and arrives just AFTER this transcript. Painting here unconditionally filled the wall with a
        // conversation the operator was having with somebody else (measured 23:18, session-long: every one of
        // those turns was correctly judged «no dirigido a zaelar» and answered with silence — and every one
        // of them still landed in the chat as if he had said it). So a spoken turn is HELD until the verdict
        // says it was for us; typed text bypasses the hold, being directed by construction.
        if (typed) { handleWidgetVoice(desktop, d.text, isFinal); store.pushChat({ role: "you", text: d.text }); }
        else holdSpokenTurn(desktop, d.text, isFinal);
      }
    } else if (d.kind === "alert") {                                              // hard notice (e.g. no LLM credit) → red banner
      store.showAlert(d.label || t("sse.llm_problem"));
      refreshStatus();                                                           // turn the ◉ status icon red now
      // V2-676 — a BLOCKING fault is not a banner. The engine marks it, and it carries facts (which model,
      // which key, which credentialed rung is silenced) that this client renders in the operator's own
      // language. Measured: the model ran out of credit mid-conversation and the only sign he got was one
      // sentence, spoken in Spanish, in an English session — he kept talking to an agent that could not
      // answer. The voice stops with it: a live microphone over a dead brain is the state that lies.
      // `session-lk.js` imports THIS module, so the stop is ANNOUNCED rather than called — the same shape as
      // `hb:canvas-reset`. main.js owns the voice and listens for it.
      if (d.blocking) {
        store.showFault(d.fault || { code: "no_model_credit" });
        try { document.dispatchEvent(new CustomEvent("hb:blocking-fault", { detail: d.fault || {} })); } catch (_) {}
      }
    } else if (d.kind === "ui" && d.label === "orb:attention") {                 // 🤖 mode changed — button OR voice (2026-09-09)
      store.setAttentionMode(d.state === "wakeword" ? "smart" : (d.state || "always"));
      // A mode flip closes the standing window on the ENGINE (attention.on_mode_change, 2026-09-10) — the
      // ring must not keep burning its local timer over a window that no longer exists: he measured 20+
      // seconds of orange after activating the wake-word mode. Clearing on every flip is correct in both
      // directions (in `always` the ring re-arms on the next verdict anyway).
      store.clearAttentionHit();
    } else if (d.kind === "ui" && d.label === "orb:name") {                      // renamed by voice — tooltip updates live
      if (d.name) store.setAssistantName(d.name);
    } else if (d.kind === "ambient") {                                           // attention gate verdict → the "listening to you" ring
      // V2-655 — AMBIENT SOUND DOES NOT TOUCH THE COUNTERS (operator, 2026-09-10). This used to be
      // `else store.clearAttentionHit()`: a stray word from the room turned OFF the operator's «te escucho»
      // ring while the server's window was still wide open — the client contradicting the engine about the
      // one thing the ring exists to report. The ring expires with the WINDOW, never with somebody else's
      // noise: a discarded verdict darkens it only when the engine says the window is actually closed, and
      // it never RE-ARMS a ring that is already lit (that would let room noise extend the counter from the
      // other side). The third branch exists only to re-sync a client whose local timer ran out while the
      // engine was still holding the window open — the bot_speech re-arm above cannot, since it refuses to
      // light a ring that is off.
      // V2-661b (measured 2026-09-11, session 63681d60): a DIRECTED verdict used to re-arm the ring for a
      // WINDOW — which SHORTENED the hold the `vad` branch had just set, so mid-monologue the ring died on a
      // 5 s timer while he was still talking («se ponía de naranja a gris en medio de mi conversación… yo no
      // he dejado de hablar»). Measured: last verdict 09:11:55.5, next 09:12:08.9, no VAD edge between them —
      // 13.4 s of continuous speech, ring grey from 09:12:00.5. A verdict never shortens an ACTIVE voice.
      if (d.directed) { _attnWinS = d.window_s || _attnWinS;
                        store.pulseAttentionHit(_voiceActive ? VAD_HOLD_S : _attnWinS); }
      else if (d.window_open === false) store.clearAttentionHit();
      else if (d.window_open === true && !store.attentionHit()) store.pulseAttentionHit(d.window_s || _attnWinS);
      settleHeldTurns(desktop, d.text || "", !!d.directed);                        // V2-647: and the wall obeys it
    } else if (d.kind === "language") {                                          // V2-089 P3: detected/changed language → the entire UI changes LIVE
      if (d.code) applyLang(d.code);                                             // fetches whatever the bundle has now — presets instant, a generating one falls back to English for missing keys until "ready"
      // V2-101: the first-run onboarding modal tracks phases on TOP of the plain applyLang above — "detected"
      // shows the (already-translated) loading line while the full bundle/alias-pack finish in the background,
      // "ready" closes it. A plain language switch (⚙, or a repeat detection with no onboarding) never sets
      // store.langOnboardOpen true in the first place, so these are no-ops for it.
      if (d.phase === "detected") {
        store.setLangOnboardPhase("detected");
        store.setLangOnboardLoading(d.loading || "");
        store.setLangOnboardStrings(d.strings || {});             // V2-672: the folder step's own words, early
      } else if (d.phase === "ready") {
        store.setLangOnboardPhase("ready");
        // V2-672 — the modal is NOT unmounted here any more. The folder step (where to keep the files) runs
        // while the bundle generates, so "ready" can land with an unanswered question on screen; closing on
        // it would take the question away mid-answer. The component owns the close now: it unmounts once the
        // language is ready AND nothing is still being asked.
        store.requestLangOnboardClose();
      }
    } else if (d.kind === "session" && d.label === "RESET") {                    // V2-084: reset → procesos EN BLANCO
      // The desktop closes it via the widget/close event; here we immediately empty the Processes tab (live chips
      // + history) so "we start from zero" — state/memory/widget data are preserved (backend).
      try { store.setTasks([]); store.setWorkerHistory([]); } catch (_) {}
      // NEW SESSION (2026-08-10): the backend already rotated the id and reset its observability
      // (voice/observer.py::rotate_session). Notify imperative views so they empty themselves too — otherwise
      // the observability panel would keep showing rows from the previous session over one just born blank.
      // `clearDebugBuffer()` (already called by reset) empties the RING, not the DOM.
      try { store.newSession(); } catch (_) {}
    } else if (d.kind === "task") {                                               // SlowBrain background task lifecycle
      // A deep-brain task started/finished — surface it as a liquid chip flanking the orb so the operator SEES
      // zaelar is working (widget build/modify, web task, …) and how many at once. Removed when it ends.
      // V2-608 F7 — the TITLE and the ACTIVITY are different fields now. `phase` and `plan` used to route
      // through startTask and overwrite the row's one text, so the operator watched the process TITLE mutate
      // through every phase and progress report. What names the row is `start` (the brief) and the one-time
      // naming event below (V2-530); everything else is the note underneath it.
      if (d.label === "start") store.startTask(d.id, d.text);
      else if (d.label === "end" || d.label === "cancel") store.endTask(d.id);   // V2-038: killing also clears the chip
      else if (d.label === "phase" && d.id) store.noteTask(d.id, d.text);
      else if (d.label === "progress" && d.id) store.setTaskProgress(d.id, d.text, d.pct, d.done, d.total);  // V2-059: real step/%
      else if (d.label === "plan" && d.id) store.noteTask(d.id, d.text);
      else if (d.label === "🏷️ encargo nombrado" && d.id) store.retitleTask(d.id, d.text);  // the settled NAME (V2-530)
    } else if (d.kind === "memory") {                                             // memory.updated / .query (bridged from the bus)
      // The central memory mutated (write/reinforce/pin/link/state/episode/consolidate) or was READ (query). A
      // mutation → bump so the 🧠 map refetches ONLY if open (gated on store.memOpen), real-time, zero polling.
      // A query changes no data → no refetch, only the live-observability pulse. Both carry op + affected ids.
      if (d.op !== "query") store.bumpMemory();
      store.pushMemPulse({ op: d.op || "", ids: d.ids || (d.id != null ? [d.id] : []) });
    } else if (d.kind === "secret") {                                             // secrets vault (V2-060)
      // The brain resolved a secret request. The VALUE never travels here: it is requested from /api/vault/reveal.
      if (d.label === "no_vault") store.openVault("create");
      else if (d.label === "locked") store.openVault("unlock", { mid: d.mid });   // requests passphrase / fingerprint
      else if (d.label === "reveal") {                                            // unlocked → show it
        vault.reveal(d.mid).then(r => {
          if (r && r.value != null) {
            store.openVault("reveal");                                            // (resets vaultRevealed)
            store.setVaultRevealed({ label: d.slabel || t("sse.secret_default"), value: r.value });   // …and NOW the value
          } else if (r && r.locked) store.openVault("unlock", { mid: d.mid });
        }).catch(() => {});
      }
    } else if (d.kind === "pulse") {                                              // orchestrator loop.tick (~1 Hz)
      // The server's own HEARTBEAT (nucleo/loop.py, bridged in server/__init__.py) → one beat of the orb's ECG.
      // At rest it marks the real rhythm (only checking crons/processes); tasks and turns speed it up (Ecg.js).
      store.pushPulse({ kind: "tick", n: d.n });
    } else if (d.kind === "brain" && d.wall) {
      // V2-461: the TEXT channel (probe / `POST /api/flash/say`) is also VISIBLE. It is the same conversation,
      // so it goes to the same place: voice is transcribed to the wall, the chat widget writes to it, and
      // through the API — which is how the studio rounds are conducted — until now it appeared nowhere.
      // The operator watched the agent work with a blank chat, indistinguishable from a hung agent.
      // It is distinguished by `d.wall`, not by the label text: a substring comparison is a contract visible
      // from neither side.
      // It deliberately does NOT arrive as `transcript` (see `nucleo/flash/probe_api._wall`): that branch also
      // feeds the voice-command shortcut, and a probe turn saying «close the agenda» would execute TWICE.
      if (d.wall === "you") store.pushChat({ role: "you", text: d.text });
      else store.pushAgentChat(d.text);
    } else if (d.kind === "brain" && /reply/.test(String(d.label || ""))) {       // a FlashBrain turn ended
      store.pushPulse({ kind: "turn" });                                          // → higher QRS peak in the ECG
      // …and the TEXT to the chat wall NOW (V2-116). Previously the wall was fed only by LiveKit's `transcript`, which
      // does not arrive until the conversation item closes — that is, until TTS has FINISHED speaking the
      // entire response: 5.4 s and 12.2 s measured in session b403c979, experienced by the operator as «I heard
      // it by voice and the text took a minute to appear». Here the text is already generated and complete, so
      // the wall renders it as soon as it exists; the later `transcript` is merged by prefix in `pushAgentChat` (and if
      // a barge-in truncated it, the complete version wins). SUBTITLES are untouched: they still come from
      // audio-synchronized transcription (session-lk.js), which is correct for something accompanying voice.
      if (d.text && d.role === "assistant") store.pushAgentChat(d.text);
    } else if (d.kind === "status") {                                             // server nudged us to re-read status
      refreshStatus();
    } else if (d.kind === "energy") {                                             // Energy balance → the BATTERY drops LIVE
      // The balance is pushed; there is no notice to go fetch it: the integer fits in the event, so the battery
      // drops while the worker runs, without a fetch for every spend.
      const x = d.extra || {};
      if (typeof x.balance === "number") {
        store.setEnergy({ cloud: true, known: true, balance: x.balance,
                          capacity: typeof x.capacity === "number" ? x.capacity : (store.energy() || {}).capacity });
      }
    } else if (d.kind === "run") {                                                // V2-092: the GLOBAL switch changed
      // The server (nucleo/runstate.py) holds the truth of «is the agent stopped?», and this event is how
      // ALL tabs learn it: two open windows can no longer disagree about whether anyone is on the other side.
      // Only the state is reflected; the endpoint is NOT called again (⏻ gives the order, this only obeys it).
      // Only the STATE is reflected; the main.js effect that observes `powerOff` handles bringing the voice session
      // down/up (this does not import `session`: sse.js imports session.js, and the cycle would be mutual).
      //
      // V2-092 addenda (2026-08-15): "pausing"/"resumed" are a THIRD pair of labels, not a start/stop variant —
      // a deferred stop (turn in flight) leaves the agent genuinely RUNNING underneath, so treating it as "not
      // stop → must be start" would paint ⏻ as if nothing were happening. Resolved BEFORE touching `powerOff`,
      // which that pair doesn't even touch.
      const label = String(d.label || "");
      if (label === "pausing") {
        store.setPausing(true);
      } else if (label === "resumed") {
        store.setPausing(false);
      } else {
        store.setPausing(false);
        const off = label === "stop";
        if (off !== store.powerOff()) store.setPowerOff(off);
      }
    } else if (d.kind === "notify") {                                             // proactive push (a native cron fired)
      // NO floating toast. When a voice session is live, zaelar SPEAKS it → the live caption comes from the
      // audio-synced transcription (session-lk.js), same as any turn. Here we just keep it in the chat wall as
      // history; pushAgentChat dedupes against the spoken transcript so it lands exactly once.
      store.pushAgentChat("🔔 " + d.text);
    } else if (d.kind === "cluster") {                                            // MeshKore channel
      // The chat wall is ONLY the operator ↔ zaelar channel (operator rule, 2026-07-25): cluster traffic is NOT
      // dumped here. V2-086: it is not stored anywhere in the frontend either — clusters have their OWN monitor,
      // so the «Clusters» tab only manages the connection (status, peers, counters). Any network event refreshes
      // that list; there is no conversation.
      if (store.chatOpen() && store.chatTab() === "clusters") store.fetchClusters();
    }
  };
}

// The stream lives as long as the APPLICATION does (main.js opens it at startup), not as long as the voice session:
// widget events arrive through it and must keep rendering with voice stopped or without a microphone. It remains
// an explicit escape hatch for anyone who genuinely wants to cut it; `session.stop()` NO LONGER uses it (it closed
// the operator's live screen every time voice stopped or the browser denied microphone access).
export function closeSSE() { if (es) { try { es.close(); } catch (_) {} es = null; } }

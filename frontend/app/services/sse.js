// ============================================================================
// sse.js — server-sent events stream (/events). Routes backend pushes to the
// reactive store (bot speech, latency) and to the widget desktop (show/create/
// modify/close). Transcripts feed the voice-command fast-path. The brain remains
// the authority; this just reacts to what it emits.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { handleWidgetVoice } from "./voiceCommands.js?v=2";
import { refreshStatus } from "./status.js?v=2";
import * as vault from "./vault.js?v=1";
import { t, applyLang } from "../core/i18n.js?v=1";

// V2-464 — SHOWCASE mode: ?showcase=1 in the URL. The use-case recorder (recorder.py) uses it to keep the chat
// open and the grid auto-arranged, so the video is readable without hands.
// Guarded: the frontier harness mounts this module under Node, where `location` does not exist.
const _SHOWCASE = typeof location !== "undefined" && new URLSearchParams(location.search).has("showcase");
let _arrT = null;

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
      if (d.ttfa_ms != null) store.setLatency(d.ttfa_ms + " ms");
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
      // A widget's STORED data changed (its own ctx.action, or Hermes via [[widget.data]]) — widgets/store.py is
      // the single choke point that emits this. No polling anywhere: re-fetch + re-render ONLY if that widget
      // happens to be open right now; otherwise there's nothing on screen to update.
      else if (d.label === "data" && d.id) desktop.refreshData(d.id);
      else if (d.label === "alias") desktop.refreshRegistry && desktop.refreshRegistry();  // V2-082: a name/alias changed → repaint header + panel
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
        handleWidgetVoice(desktop, d.text, isFinal);                               // SHOW acts on interim too (real-time)
        // kind "transcript" (vs "interim") is already the FINAL user turn → record it in the chat wall history.
        store.pushChat({ role: "you", text: d.text });
      }
    } else if (d.kind === "alert") {                                              // hard notice (e.g. no LLM credit) → red banner
      store.showAlert(d.label || t("sse.llm_problem"));
      refreshStatus();                                                           // turn the ◉ status icon red now
    } else if (d.kind === "language") {                                          // V2-089 P3: detected/changed language → the entire UI changes LIVE
      if (d.code) applyLang(d.code);                                             // fetches whatever the bundle has now — presets instant, a generating one falls back to English for missing keys until "ready"
      // V2-101: the first-run onboarding modal tracks phases on TOP of the plain applyLang above — "detected"
      // shows the (already-translated) loading line while the full bundle/alias-pack finish in the background,
      // "ready" closes it. A plain language switch (⚙, or a repeat detection with no onboarding) never sets
      // store.langOnboardOpen true in the first place, so these are no-ops for it.
      if (d.phase === "detected") {
        store.setLangOnboardPhase("detected");
        store.setLangOnboardLoading(d.loading || "");
      } else if (d.phase === "ready") {
        store.setLangOnboardPhase("ready");
        setTimeout(() => store.setLangOnboardOpen(false), 550);   // let the CSS fade (.gone) play, then unmount
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
      if (d.label === "start") store.startTask(d.id, d.text);
      else if (d.label === "end" || d.label === "cancel") store.endTask(d.id);   // V2-038: killing also clears the chip
      else if (d.label === "phase" && d.id) store.startTask(d.id, d.text);        // phase → refreshes the label (idempotent)
      else if (d.label === "progress" && d.id) store.setTaskProgress(d.id, d.text, d.pct, d.done, d.total);  // V2-059: real step/%
      else if (d.label === "plan" && d.id) store.startTask(d.id, d.text);          // V2-059: declared plan → refreshes the label
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

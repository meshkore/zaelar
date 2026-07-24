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

let es = null;

export function openSSE(desktop) {
  if (es) es.close();
  es = new EventSource("/events");
  // V2-038: al (re)conectar, RECONCILIA los chips de actividad contra la verdad del server (GET /api/tasks lee el
  // registro RAM) → fin de los chips huérfanos tras un reinicio/crash. El ESTADO manda; la UI es su espejo.
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
      if (d.label === "show" && d.id) desktop.show(d.id, { data: d.data });       // brain shows it (with pushed data, if any)
      else if (d.label === "create" && d.id) desktop.createWidget(d.id, d.spec);  // brain asked to BUILD a new widget
      else if (d.label === "modify" && d.id) desktop.modifyWidget(d.id, d.change);// brain asked to EDIT an existing widget
      else if (d.label === "delete" && d.id) desktop.onDeleted(d.id);             // backend ALREADY deleted (lifecycle) → close the card + drop the cached catalog
      else if (d.label === "confirm" && d.id) desktop.showConfirm(d.id, { question: d.question, action: d.action });      // irreversible action (delete/data) → Sí/No overlay ON the card
      else if (d.label === "confirm-cancel" && d.id) desktop.hideConfirm(d.id);   // confirmation resolved/cancelled elsewhere (voice/timeout)
      else if (d.label === "close") d.id ? desktop.close(d.id) : desktop.closeAll();
      else if (d.label === "move" && d.id) desktop.move(d.id, d.where);            // reposition on the canvas (izquierda/derecha/…)
      else if (d.label === "resize" && d.id) desktop.resize(d.id, d.data);          // resize a widget (HERMES-ONLY)
      else if (d.label === "fullscreen" && d.id) desktop.fullscreen(d.id);          // toggle native fullscreen
      // A widget's STORED data changed (its own ctx.action, or Hermes via [[widget.data]]) — widgets/store.py is
      // the single choke point that emits this. No polling anywhere: re-fetch + re-render ONLY if that widget
      // happens to be open right now; otherwise there's nothing on screen to update.
      else if (d.label === "data" && d.id) desktop.refreshData(d.id);
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
      store.showAlert(d.label || "⚠️ Problema con el modelo de lenguaje");
      refreshStatus();                                                           // turn the ◉ status icon red now
    } else if (d.kind === "task") {                                               // SlowBrain background task lifecycle
      // A deep-brain task started/finished — surface it as a liquid chip flanking the orb so the operator SEES
      // zaelar is working (widget build/modify, web task, …) and how many at once. Removed when it ends.
      if (d.label === "start") store.startTask(d.id, d.text);
      else if (d.label === "end" || d.label === "cancel") store.endTask(d.id);   // V2-038: matar también limpia el chip
      else if (d.label === "phase" && d.id) store.startTask(d.id, d.text);        // fase → refresca la etiqueta (idempotente)
      else if (d.label === "progress" && d.id) store.setTaskProgress(d.id, d.text, d.pct, d.done, d.total);  // V2-059: paso/% real
      else if (d.label === "plan" && d.id) store.startTask(d.id, d.text);          // V2-059: plan declarado → refresca etiqueta
    } else if (d.kind === "memory") {                                             // memory.updated / .query (bridged from the bus)
      // The central memory mutated (write/reinforce/pin/link/state/episode/consolidate) or was READ (query). A
      // mutation → bump so the 🧠 map refetches ONLY if open (gated on store.memOpen), real-time, zero polling.
      // A query changes no data → no refetch, only the live-observability pulse. Both carry op + affected ids.
      if (d.op !== "query") store.bumpMemory();
      store.pushMemPulse({ op: d.op || "", ids: d.ids || (d.id != null ? [d.id] : []) });
    } else if (d.kind === "secret") {                                             // bóveda de secretos (V2-060)
      // El cerebro resolvió una petición de secreto. El VALOR nunca viaja por aquí: se pide a /api/vault/reveal.
      if (d.label === "no_vault") store.openVault("create");
      else if (d.label === "locked") store.openVault("unlock", { mid: d.mid });   // pide passphrase / huella
      else if (d.label === "reveal") {                                            // desbloqueada → muéstralo
        vault.reveal(d.mid).then(r => {
          if (r && r.value != null) {
            store.openVault("reveal");                                            // (resetea vaultRevealed)
            store.setVaultRevealed({ label: d.slabel || "Secreto", value: r.value });   // …y AHORA el valor
          } else if (r && r.locked) store.openVault("unlock", { mid: d.mid });
        }).catch(() => {});
      }
    } else if (d.kind === "pulse") {                                              // orchestrator loop.tick (~1 Hz)
      // El LATIDO propio del server (nucleo/loop.py, puenteado en server/__init__.py) → un beat del ECG del orbe.
      // En reposo marca el ritmo real (solo revisando crons/procesos); las tareas y turnos lo aceleran (Ecg.js).
      store.pushPulse({ kind: "tick", n: d.n });
    } else if (d.kind === "brain" && /reply/.test(String(d.label || ""))) {       // un turno del FlashBrain se cerró
      store.pushPulse({ kind: "turn" });                                          // → pico QRS más alto en el ECG
    } else if (d.kind === "status") {                                             // server nudged us to re-read status
      refreshStatus();
    } else if (d.kind === "notify") {                                             // proactive push (a native cron fired)
      // NO floating toast. When a voice session is live, zaelar SPEAKS it → the live caption comes from the
      // audio-synced transcription (session-lk.js), same as any turn. Here we just keep it in the chat wall as
      // history; pushAgentChat dedupes against the spoken transcript so it lands exactly once.
      store.pushAgentChat("🔔 " + d.text);
    } else if (d.kind === "cluster") {                                            // MeshKore channel → own visual role
      // Render the CONTENT, never raw JSON. Per §4 the payload was already reduced to .text (+ .media) upstream;
      // here we just append any attachments as links so text+media show as one message. Attribution (peer/cluster/
      // direction) travels as METADATA on the chat message, not baked into the text — previously both zaelar's own
      // replies and cluster peer turns used role:"agent", distinguished only by a "🛰" prefix in the raw string, so
      // ChatWall couldn't render a peer turn differently (styling, markdown, who-said-it) from zaelar's own voice.
      const media = Array.isArray(d.media)
        ? " " + d.media.map(m => (m && m.url) ? `📎 ${m.url}` : `📎 ${(m && m.mime) || "adjunto"}`).join("  ")
        : "";
      if (d.dir === "in") store.pushChat({ role: "peer", text: d.text + media, cluster: d.cluster, peer: d.peer, dir: "in" });
      else if (d.dir === "out") store.pushChat({ role: "peer", text: d.text + media, cluster: d.cluster, peer: d.to, dir: "out" });
      else if (d.dir === "note") store.pushChat({ role: "peer", text: d.text, dir: "note" });        // zaelar's aside to you
      else store.pushChat({ role: "peer", text: d.label || "", dir: "note" });                       // join/leave/status/concluded
    }
  };
}

export function closeSSE() { if (es) { try { es.close(); } catch (_) {} es = null; } }

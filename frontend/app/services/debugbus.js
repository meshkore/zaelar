// ============================================================================
// debugbus.js — a DEDICATED subscriber to the observability stream (/events),
// independent of the voice session's own SSE (services/sse.js). It exists so the
// debug side-column shows the WHOLE event firehose even when the voice session
// never comes up (which is exactly when you need to debug). Everything zaelar
// emits via voice/observer.py lands here: transcript (user/bot), widget
// show/close/create/modify/delete, brain prompts/replies + [[deep]] escalations
// to Hermes, LLM/STT/TTS metrics (the local qwen fast layer, Kokoro, Whisper),
// connector dispatches (cluster/cron/architect/whatsapp), alerts and errors.
//
// It keeps a capped ring buffer (so a freshly-opened panel shows recent backlog)
// and fans each event out to subscribers. No rendering here — the DebugPanel owns
// the DOM. Pure pub/sub over EventSource, matching the app's service style.
// ============================================================================

let es = null;
let buf = [];
const CAP = 1000;                 // ring buffer: plenty for a live session, bounded so memory can't grow forever
const subs = new Set();           // fn(evt) — called for every new event

export function startDebugBus() {
  if (es) return;                 // idempotent: one dedicated connection is enough
  try {
    es = new EventSource("/events");
    es.onmessage = (ev) => {
      let d;
      try { d = JSON.parse(ev.data); } catch (_) { return; }
      d._rx = Date.now();         // client receive wall-clock (h:m:s.mmm in the panel)
      buf.push(d);
      if (buf.length > CAP) buf.shift();
      for (const fn of subs) { try { fn(d); } catch (_) {} }
    };
    // EventSource auto-reconnects on drop; nothing to do on error but keep it quiet.
    es.onerror = () => {};
  } catch (_) { /* no SSE support → panel simply stays empty */ }
}

export function onDebug(fn) { subs.add(fn); return () => subs.delete(fn); }
export function debugBuffer() { return buf; }
export function clearDebugBuffer() { buf = []; }

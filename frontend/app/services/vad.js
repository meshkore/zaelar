// ============================================================================
// vad.js — browser VAD turn-taking. The browser VAD is the turn authority (no
// on-screen dot; redundant with the camera). On real speech start we decide via
// the optional speaker-gate, then signal the turn over the data channel.
//
// window.vad / window.ort are provided by the vendored scripts loaded in index.html.
// Dependencies (live stream, data channel, speaker gate) are injected as getters
// so the module stays framework-agnostic and survives reconnects.
// ============================================================================

let micVad = null, turnOpen = false, _vtSeq = 0;

export function sendTurn(dc, ev) {
  // A lost turn signal leaves the server's turn stuck open (it self-heals after ~3s of silence, but the latency
  // is real) — so a failed send is NEVER silent: it goes to the console AND the server timeline via clientLog.
  if (dc && dc.readyState === "open") {
    try {
      dc.send(JSON.stringify({ label: "rtvi-ai", type: "client-message", id: "vt" + (++_vtSeq), data: { t: "vala-turn", d: { ev } } }));
      return;
    } catch (e) { console.warn("vala-turn send failed:", ev, e); }
  } else console.warn("vala-turn NOT sent (channel " + (dc ? dc.readyState : "null") + "):", ev);
  import("./api.js?v=2").then(api => api.clientLog("⚠️ vala-turn '" + ev + "' LOST", { text: "data channel " + (dc ? dc.readyState : "null") })).catch(() => {});
}

export async function startMicVAD({ getStream, getDc, getGate, onOwner }) {
  if (!window.vad || !window.ort) { console.warn("VAD not loaded"); return; }
  try {
    micVad = await vad.MicVAD.new({
      model: "v5", baseAssetPath: "/static/vad/", onnxWASMBasePath: "/static/vad/",
      getStream: async () => getStream(), pauseStream: async () => {}, resumeStream: async () => getStream(),
      ortConfig: (ort) => { ort.env.wasm.numThreads = 1; ort.env.logLevel = "error"; },
      positiveSpeechThreshold: 0.5, negativeSpeechThreshold: 0.35, minSpeechMs: 250, redemptionMs: 1100, preSpeechPadMs: 250,
      onSpeechRealStart: () => {
        let d = { pass: true };
        const gate = getGate && getGate();
        try { if (gate && gate.enabled) d = gate.decide(); } catch (_) {}
        onOwner && onOwner(d);
        if (d.pass) { sendTurn(getDc(), "start"); turnOpen = true; }   // gate OFF → always open the turn
        /* else (gate on + not owner): DON'T send to the orchestrator */
      },
      onSpeechEnd: () => { if (turnOpen) { sendTurn(getDc(), "stop"); turnOpen = false; } },
    });
    micVad.start();
  } catch (e) { console.error("VAD failed:", e); }
}

export function stopMicVAD() {
  if (micVad) { try { micVad.pause(); } catch (_) {} try { micVad.destroy && micVad.destroy(); } catch (_) {} micVad = null; }
  turnOpen = false;
}

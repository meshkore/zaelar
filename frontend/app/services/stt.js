// ============================================================================
// stt.js — BROWSER speech-to-text (Web Speech API). FREE, cross-platform (Win/Mac),
// nothing to install. Active only when the server says STT_PROVIDER=browser. The
// browser recognizes speech and we send the text (interim+final) over the data
// channel; the server's ClientSTTInjector turns it into transcriptions. Chrome/Edge.
// ============================================================================
import { showAlert } from "../core/store.js?v=2";

let rec = null;

export function startBrowserSTT(lang, { getDc, isActive }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { showAlert("Este navegador no trae reconocimiento de voz nativo. Usa Chrome/Edge, o cambia STT_PROVIDER."); return; }
  try { rec = new SR(); } catch (_) { return; }
  rec.lang = lang || "es-ES"; rec.continuous = true; rec.interimResults = true; let _n = 0;
  rec.onresult = e => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]; const text = (r[0] && r[0].transcript) || ""; if (!text) continue;
      const dc = getDc();
      if (dc && dc.readyState === "open") {
        try { dc.send(JSON.stringify({ label: "rtvi-ai", type: "client-message", id: "st" + (++_n), data: { t: "vala-stt", d: { final: r.isFinal, text } } })); } catch (_) {}
      }
    }
  };
  rec.onend = () => { if (isActive() && rec) { try { rec.start(); } catch (_) {} } };   // continuous: engine stops often → restart
  rec.onerror = () => {};                                                               // no-speech/aborted → onend restarts
  try { rec.start(); } catch (_) {}
}

export function stopBrowserSTT() { if (rec) { try { rec.onend = null; rec.stop(); } catch (_) {} rec = null; } }

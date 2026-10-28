// js/media.js — Media in a message: labels, the voice-note player, previews, and the URL linkifier (bodies are untrusted text).
// Moved verbatim out of widget.js (refactor2710-12).
import { S, tt } from "./state.js";
import { cleanBody, el } from "./dom.js";

// ── Media (V2-543) ──────────────────────────────────────────────────────────
// The bridge/connectors store `[<type> received]` as an internal English placeholder; on screen it becomes a
// human label. The bytes themselves are served by the widget's own asset route — an <img>/<audio>/<video>
// element with a same-origin src is NOT a fetch (isolation contract, same reading as navegador/imagenes).
export function mediaLabel(kind){
  switch(String(kind || "")){
    case "image":    return tt("media_image", null, "📷 Foto");
    case "video":    return tt("media_video", null, "🎥 Vídeo");
    case "audio":    return tt("media_audio", null, "🎵 Audio");
    case "ptt":      return tt("media_ptt", null, "🎤 Nota de voz");
    case "document": return tt("media_document", null, "📄 Documento");
    default:         return "";
  }
}
export const PLACEHOLDER_RE = /^\[(image|video|audio|ptt|document) received\]$/;

// V2-622 — a bare media placeholder ("[audio received]", or an empty body with a mediaType) becomes a label
// like "🎵 Audio" purely so something reads where the caption would be. Once a real media block actually
// renders below it, that label is pure noise — the player/thumbnail/link already say what it is. Only a
// REAL caption the sender actually typed still needs the text line.
export function isBareMediaLabel(body){
  const b = cleanBody(body);
  return !b || PLACEHOLDER_RE.test(b);
}

// A body that is really HTML (stored before the connector learned to read a «plain» part that is markup) is shown as
// the text it carries. DOMParser builds an INERT document: no script runs and nothing is fetched (V2-813).
export const _BLOCK_TAGS = "br,p,div,tr,li,h1,h2,h3,h4,table,blockquote";
export function markupText(b){
  const s = (b || "").trimStart();
  if(!s.startsWith("<")) return b;
  let doc;
  try { doc = new DOMParser().parseFromString(s, "text/html"); } catch(_) { return b; }
  doc.querySelectorAll("style,script,head,title").forEach(e => e.remove());
  doc.querySelectorAll(_BLOCK_TAGS).forEach(e => e.after(doc.createTextNode("\n")));
  const t = (doc.body ? doc.body.textContent : "").split("\n").map(l => l.replace(/\s+/g, " ").trim())
    .filter((l, i, a) => l || (i && a[i - 1])).join("\n").trim();
  return t && t.length < 0.6 * s.length ? t : b;
}

export function displayBody(body, mediaType){
  const b = cleanBody(body);
  const m = b.match(PLACEHOLDER_RE);
  if(m) return mediaLabel(m[1]) || b;
  if(!b && mediaType) return mediaLabel(mediaType) || "";
  return b;
}

export function fmtWhen(ts){
  const t = Number(ts||0);
  if(!t) return "";
  const d = new Date(t*1000), now = new Date();
  const hm = d.toLocaleTimeString(S.LANG, {hour:"2-digit", minute:"2-digit"});
  if(d.toDateString() === now.toDateString()) return hm;
  return d.toLocaleDateString(S.LANG, {day:"numeric", month:"short"}) + " " + hm;
}

// V2-616 F5 — a real seek control, wide, FIXED width regardless of the clip's length. The operator: WhatsApp's
// native <audio controls> lets him play/pause but not drag to a point ("no puedo avanzar hasta cierto punto"),
// and he wants it wider and shaped like a waveform, with the SAME width whether the clip is one minute or two
// hours long.
//
// The bars are DECORATIVE, not real amplitude — worth saying plainly, because a fake waveform that LOOKS
// measured is exactly the kind of "true sentence about the wrong mechanism" this codebase treats as the worst
// failure shape. A real one needs the file's raw samples (Web Audio's decodeAudioData), and getting those
// requires fetching the bytes ourselves — `fetch()`/`XMLHttpRequest` are BANNED sinks in widget.js on purpose
// (widgets/validator.py, the "no network from the client" boundary V2-557 drew): the <audio> element loads
// its own `src` through the browser's OWN media pipeline, never through code we could point anywhere else.
// A FIXED bar count (not one derived from duration) is what keeps the width constant on its own — no decode
// needed for that part at all.
export const _WAVE_BARS = 28;

export function _waveBarHeight(seed, i){
  // A small, deterministic, non-cryptographic hash: same seed+index always draws the same bar, so the shape
  // does not jitter on re-render, and two different clips still look visually distinct from each other.
  let h = 0;
  const s = seed + "#" + i;
  for(let k=0; k<s.length; k++) h = (h*31 + s.charCodeAt(k)) >>> 0;
  return 24 + (h % 76); // 24-99, as a percentage of the wave's own height
}

// V2-819 (approved design, 2026-10-27) — the waveform runs across the TOP of the bubble, as wide as the bubble and
// scrubbable; below it, one meta line: play, the duration, and the message's date and time (`when`, when the caller
// hands it over so the bubble does not print it twice).
export function audioPlayer(url, when){
  const wrap = el("div","maudio");
  const btn = document.createElement("button");
  btn.type="button"; btn.className="mapbtn"; btn.textContent="▶"; btn.title=tt("play", null, "Reproducir");
  const wave = el("div","mawave");
  const bars = [];
  for(let i=0; i<_WAVE_BARS; i++){
    const bar = el("span","mabar");
    bar.style.height = _waveBarHeight(url, i) + "%";
    bars.push(bar);
    wave.appendChild(bar);
  }
  const time = el("span","matime","0:00");
  // preload="metadata": duration has to be known for the bar to mean anything and for a drag BEFORE the first
  // play to compute a real target time — it fetches only the file's header, never the audio itself (that
  // still waits for the operator's own play/seek, same "never autoplay" contract the old native player had).
  const au = document.createElement("audio");
  au.className="maud"; au.preload="metadata"; au.src=url; au.style.display="none";
  const meta = el("div","mameta");
  meta.append(btn, time);
  if(when) meta.append(el("span","mawhen", when));
  wrap.append(wave, meta, au);

  const fmt = (s)=>{ s = Math.max(0, Math.floor(s || 0)); return Math.floor(s/60)+":"+String(s%60).padStart(2,"0"); };
  const refresh = ()=>{
    const d = au.duration;
    const known = isFinite(d) && d > 0;
    time.textContent = known ? (fmt(au.currentTime)+" / "+fmt(d)) : fmt(au.currentTime);
    const played = known ? Math.round((au.currentTime/d) * bars.length) : 0;
    bars.forEach((b,i)=> b.classList.toggle("played", i < played));
  };
  au.addEventListener("timeupdate", refresh);
  au.addEventListener("loadedmetadata", refresh);
  au.addEventListener("play", ()=>{ btn.textContent="⏸"; btn.title=tt("pause", null, "Pausar"); });
  au.addEventListener("pause", ()=>{ btn.textContent="▶"; btn.title=tt("play", null, "Reproducir"); });
  au.addEventListener("ended", ()=>{ btn.textContent="▶"; btn.title=tt("play", null, "Reproducir"); });
  btn.onclick = ()=>{ if(au.paused) au.play().catch(()=>{}); else au.pause(); };

  const seekTo = (clientX)=>{
    const d = au.duration;
    if(!isFinite(d) || d <= 0) return;         // duration not known yet — nothing to seek INTO
    const r = wave.getBoundingClientRect();
    if(!r.width) return;
    const frac = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
    au.currentTime = frac * d;
    refresh();
  };
  let dragging = false;
  wave.addEventListener("pointerdown", (e)=>{ dragging=true; try{ wave.setPointerCapture(e.pointerId); }catch{} seekTo(e.clientX); });
  wave.addEventListener("pointermove", (e)=>{ if(dragging) seekTo(e.clientX); });
  const stopDrag = (e)=>{ dragging=false; try{ wave.releasePointerCapture(e.pointerId); }catch{} };
  wave.addEventListener("pointerup", stopDrag);
  wave.addEventListener("pointercancel", stopDrag);

  refresh();
  return wrap;
}

export function mediaBlock(it, when){
  const list = it.media || [];
  if(!list.length){
    // Downloaded once and later removed from this device by the media window: say where it still is.
    return it.mediaGone ? el("span","mdoc",tt("media_gone", null, "Ya no está en este dispositivo — sigue en tu móvil")) : null;
  }
  const w = el("div","mediaw");
  list.forEach(u=>{
    const url = String((u&&u.url)||"");
    if(!url.startsWith("/widgets/")) return;             // our own asset route only, never an arbitrary origin
    const t = (u&&u.type) || it.mediaType || "";
    if(t==="image"){
      const a=document.createElement("a"); a.href=url; a.target="_blank"; a.rel="noopener";
      const img=document.createElement("img"); img.className="matt"; img.src=url;
      img.loading="lazy"; img.decoding="async"; img.alt=(u&&u.name)||tt("image_alt", null, "imagen");
      img.onerror=()=>{ a.replaceWith(el("span","mdoc",tt("image_unavailable", null, "📷 (no disponible)"))); };
      a.appendChild(img); w.appendChild(a);
    } else if(t==="video"){
      const v=document.createElement("video"); v.className="mvid"; v.controls=true; v.preload="metadata"; v.src=url;
      w.appendChild(v);
    } else if(t==="audio"||t==="ptt"){
      // The bubble's date and time go on the player's own meta line — only for the first clip, and the caller
      // learns it (`usedWhen`) so the bubble does not print them a second time.
      w.appendChild(audioPlayer(url, w.usedWhen ? "" : (when || "")));
      if(when) w.usedWhen = true;
    } else {
      const a=document.createElement("a"); a.className="mdoc"; a.href=url; a.target="_blank"; a.rel="noopener";
      a.textContent="📄 "+((u&&u.name)||tt("document_alt", null, "documento"));
      w.appendChild(a);
    }
  });
  return w.childNodes.length ? w : null;
}

export const URL_RE = /(https?:\/\/[^\s]+)/g;

// Build the message body as text nodes plus <a> for each detected URL. No innerHTML because bodies come from
// third parties and are untrusted. Normal text remains a plain TextNode.
export function linkify(container, text){
  const t = String(text==null ? "" : text);
  let last = 0, m;
  URL_RE.lastIndex = 0;
  while((m = URL_RE.exec(t))){
    if(m.index > last) container.appendChild(document.createTextNode(t.slice(last, m.index)));
    let url = m[0];
    const trail = url.match(/[),.;:!?]+$/);
    let trailStr = "";
    if(trail){ trailStr = trail[0]; url = url.slice(0, -trailStr.length); }
    const a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "lnk";
    a.textContent = url;
    container.appendChild(a);
    if(trailStr) container.appendChild(document.createTextNode(trailStr));
    last = m.index + m[0].length;
  }
  if(last < t.length) container.appendChild(document.createTextNode(t.slice(last)));
}

// Connect/disconnect without touching .env. The widget can only talk through ctx.action (isolation contract: no
// network/fetch from the client), which queues the order in the store; the server supervisor drains it and performs
// the real connect. QR/status appear by themselves on the canvas: store.py emits the SSE notice as soon as the
// supervisor saves the new state, and desktop.js repaints this same card once (never polling, never a separate
// window).

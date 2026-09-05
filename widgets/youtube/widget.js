// youtube — REAL YouTube player embedded in the canvas (an <iframe>, not a capture). Controlled by VOICE: data.py
// stores the desired command (last_cmd + cmd_seq) and state (paused/muted/volume); here we apply it to the player
// with postMessage (YouTube IFrame API, NO external library — only iframe messages). Contract: render(el, data, ctx).
// No network from JS: the <iframe> is an element, not our own request.

function injectStyles(){
  if(document.getElementById("hb-yt-css")) return;
  const s = document.createElement("style"); s.id = "hb-yt-css"; s.textContent = `
  .hb-yt{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
         width:min(680px,92vw);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
         border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:10px}
  .hb-yt-title{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622);line-height:1.3;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-meta{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.3;margin-top:-4px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-meta .hb-yt-latest{color:var(--hb-accent,#3D6FE0);font-weight:600}
  .hb-yt-frame{position:relative;width:100%;padding-top:56.25%;border-radius:12px;overflow:hidden;
               background:var(--hb-bg-soft,#0d1622)}
  .hb-yt-frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .hb-yt-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
               color:var(--hb-muted-2,#9aa7b8);font-size:13px;text-align:center;padding:0 20px}
  .hb-yt-loading{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
                 justify-content:center;gap:10px;color:var(--hb-muted,#5b6b82);font-size:13px;text-align:center;
                 padding:0 20px}
  .hb-yt-spin{width:28px;height:28px;border-radius:50%;border:3px solid var(--hb-line,#eef1f6);
              border-top-color:var(--hb-accent,#3D6FE0);animation:hbytspin .8s linear infinite}
  @keyframes hbytspin{to{transform:rotate(360deg)}}
  .hb-yt-ctrls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .hb-yt-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
             color:var(--hb-ink,#0d1622);border-radius:9px;padding:7px 12px;font-size:13px;font-weight:600;
             cursor:pointer;line-height:1}
  .hb-yt-btn:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-yt-vol{margin-left:auto;font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums}
  .hb-yt-hint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);line-height:1.35}
  .hb-yt-unmute{position:absolute;left:50%;bottom:10px;transform:translateX(-50%);display:none;
                align-items:center;gap:6px;background:rgba(0,0,0,.6);color:#fff;font-size:12.5px;
                font-weight:600;padding:6px 12px;border-radius:999px;cursor:pointer}
  .hb-yt-unmute:hover{background:rgba(0,0,0,.75)}
  .hb-yt-list{display:flex;flex-direction:column;gap:2px;border-top:1px solid var(--hb-line,#eef1f6);padding-top:8px}
  .hb-yt-listh{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:var(--hb-ink,#0d1622)}
  .hb-yt-chip{font-size:11px;color:var(--hb-accent,#3D6FE0);border:1px solid var(--hb-line,#eef1f6);
              border-radius:999px;padding:1px 8px;display:inline-flex;align-items:center;gap:5px;cursor:pointer}
  .hb-yt-row{display:flex;align-items:center;gap:8px;padding:4px 6px;border-radius:8px;cursor:pointer;min-width:0}
  .hb-yt-row:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-yt-row.playing .hb-yt-rowt{color:var(--hb-accent,#3D6FE0);font-weight:700}
  .hb-yt-rown{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;
              min-width:16px;text-align:right;flex:0 0 auto}
  .hb-yt-rowt{font-size:13px;color:var(--hb-ink,#0d1622);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
              flex:1;min-width:0}
  .hb-yt-rowc{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;
              text-overflow:ellipsis;max-width:32%;flex:0 1 auto}
  .hb-yt-rowx{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);font-size:14px;cursor:pointer;
              padding:1px 6px;border-radius:6px;line-height:1;flex:0 0 auto}
  .hb-yt-rowx:hover{color:var(--hb-risk,#e5484d)}
  .hb-yt-addrow{display:flex;gap:6px;margin-top:4px}
  .hb-yt-addinp{flex:1;min-width:0;box-sizing:border-box;border:1px solid var(--hb-line,#eef1f6);border-radius:8px;
                padding:6px 9px;font-size:12.5px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-yt-note{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);padding:1px 2px}
  `; document.head.appendChild(s);
}

function el(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// The playlist plays one after another because the PLAYER tells us the video ENDED (YouTube IFrame API over
// postMessage, `listening` handshake — same mechanism musica uses). The handler filters by the handshake `id`:
// both this widget and musica's hidden audio player listen on the same window, and without the filter one
// player's ending would advance the OTHER's queue.
let _ytEnded = null;
let _ytError = null;   // V2-401: the player refusing to play (onError) is reported back, never swallowed
if(typeof window !== "undefined" && !window.__hbYtWidgetBound){
  window.__hbYtWidgetBound = true;
  window.addEventListener("message", (ev) => {
    if(typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    if(d.id !== "hb-youtube") return;
    if(d.event === "onStateChange" && Number(d.info) === 0 && _ytEnded) _ytEnded();   // 0 = ENDED
    // onError codes: 2 bad id · 5 HTML5 error · 100 removed · 101/150 embedding disabled by the owner.
    // Without this, "This video is unavailable" on screen coexisted with a declared state that said
    // playing — and /widgets/producing, the brain and the judge all believed the declared state (V2-401).
    if(d.event === "onError" && _ytError) _ytError(d.info);
  });
}
function startListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-youtube", channel:"widget"}), "*"); }catch(_){}
}

function post(iframe, func, args){
  try{
    if(!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*");
  }catch(_){}
}

// Is the agent STOPPED? (V2-092) — with ⏻ off, this widget must NOT play anything. The case that made this necessary
// is MOUNT: the operator stopped the agent, RELOADED the page, and the video started again by itself, because the
// <iframe> is born with `autoplay=1` and nobody had told it the agent was stopped. `ctx.running` is a live canvas
// getter (widgets/desktop.js) reflecting server truth (nucleo/runstate.py).
// Read as "stopped ONLY if explicitly stated": an old ctx without the field (undefined) must not leave the player
// muted forever.
function halted(ctx){ return !!(ctx && ctx.running === false); }

// Reassert desired state in the player (idempotent) — used when loading a new video.
function applyState(iframe, data, ctx){
  if(data.muted){ post(iframe, "mute", []); }
  else { post(iframe, "unMute", []); post(iframe, "setVolume", [Number(data.volume != null ? data.volume : 70)]); }
  // Captions re-asserted HERE, not only in applyCmd, or the choice silently drops on the next `load` (V2-590).
  applyCaptions(iframe, data);
  // With the agent stopped, ALWAYS pause, whatever saved state says: this is the last line of defense in case the
  // store kept `paused:false` from before stop (or from an older engine version).
  if(data.paused || halted(ctx)) post(iframe, "pauseVideo", []);
  else post(iframe, "playVideo", []);
}

// Captions on/off (V2-590): both module names are sent — "captions" is the HTML5 player's, "cc" the
// historical one — and the player ignores the one it does not know. No track is picked: the player's own
// default/auto track is what a viewer gets clicking CC, and guessing a language here would override it.
function applyCaptions(iframe, data){
  if(data.captions){ post(iframe, "loadModule", ["captions"]); post(iframe, "loadModule", ["cc"]); }
  else { post(iframe, "unloadModule", ["captions"]); post(iframe, "unloadModule", ["cc"]); }
}

// Apply the LAST command requested by voice/click (only when cmd_seq advances).
function applyCmd(iframe, data, ctx){
  const c = data.last_cmd || "";
  // A command that would make the video play is ignored while the agent is stopped. The server already rejects them
  // in the funnel (widgets/producers.py::gate), so this only covers already saved state — but pausing too much never
  // hurts, while playing too much does.
  if(halted(ctx) && (c === "play" || c === "load" || c === "restart" || c === "unmute"
                     || c === "volume_up" || c === "set_volume"
                     || c === "next" || c === "previous" || c === "play_item")){
    post(iframe, "pauseVideo", []);
    return;
  }
  const vol = Number(data.volume != null ? data.volume : 70);
  if(c === "play") post(iframe, "playVideo", []);
  else if(c === "pause") post(iframe, "pauseVideo", []);
  else if(c === "mute") post(iframe, "mute", []);
  else if(c === "unmute"){ post(iframe, "unMute", []); post(iframe, "setVolume", [vol]); }
  else if(c === "volume_up" || c === "volume_down" || c === "set_volume"){
    post(iframe, "unMute", []); post(iframe, "setVolume", [vol]);
  }
  else if(c === "captions_on" || c === "captions_off"){ applyCaptions(iframe, data); }
  else if(c === "restart"){ post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []); }
  // A queue jump normally lands as a NEW videoId (card rebuild); when the target is the SAME video (a list
  // with the current one repeated after a manual load) nothing rebuilds — treat it as a restart.
  else if(c === "next" || c === "previous" || c === "play_item"){
    post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []);
  }
}

export function render(root, data, ctx){
  injectStyles();
  data = data || {};
  const id = data.videoId || "";
  const seq = Number(data.cmd_seq || 0);
  const loading = !!data.loading;
  const st = root._hbYt || null;

  // (Re)build the card when the video changes, or when entering/leaving "searching" state (real bug 2026-07-23:
  // without this the card looked COMPLETELY empty while load searched YouTube, with no signal).
  if(!st || st.id !== id || st.loading !== loading || !root._hbYtBuilt){
    root.className = "hb-yt";
    root.textContent = "";

    const title = el("div", "hb-yt-title", data.title || "YouTube");
    root.appendChild(title);
    const meta = el("div", "hb-yt-meta", "");            // channel · publication date (verifiable, V2-057)
    root.appendChild(meta);

    const frame = el("div", "hb-yt-frame");
    let iframe = null;
    let unmuteHint = null;
    if(loading){
      const box = el("div", "hb-yt-loading");
      box.appendChild(el("div", "hb-yt-spin"));
      box.appendChild(el("div", "", data.loading_query ? `Buscando «${data.loading_query}»…` : "Buscando…"));
      frame.appendChild(box);
    } else if(id){
      iframe = document.createElement("iframe");
      iframe.title = data.title || "YouTube";
      iframe.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
      iframe.setAttribute("allowfullscreen", "");
      // `autoplay` ONLY if the agent is running and the video was not paused. It used to be fixed to 1: when reloading
      // with the agent stopped, the video started BEFORE any pause command arrived (the 700ms below) — the start was
      // audible. Removing it from the `src` itself is the only way to avoid playing EVEN FOR AN INSTANT.
      const auto = (!data.paused && !halted(ctx)) ? 1 : 0;
      // cc_load_policy only when captions are wanted: the param covers the LOAD case robustly (a module
      // loaded before the player is ready can be ignored); the live toggle goes through applyCaptions.
      const cc = data.captions ? "&cc_load_policy=1" : "";
      const params = "enablejsapi=1&rel=0&modestbranding=1&playsinline=1&autoplay=" + auto + "&mute=1" + cc
                     + "&origin=" + encodeURIComponent(location.origin);
      iframe.src = "https://www.youtube.com/embed/" + encodeURIComponent(id) + "?" + params;
      const d0 = data, c0 = ctx;
      iframe.addEventListener("load", function(){
        startListening(iframe);
        setTimeout(function(){ applyState(iframe, d0, c0); }, 700);
      });
      frame.appendChild(iframe);
      // The browser requires a real TOUCH to give sound to an autoplay that started muted (voice-requested "unmute"
      // does not count as a user gesture and audio may stay silently blocked). This button is a real click → unlock
      // audio NOW, in the same gesture.
      unmuteHint = el("div", "hb-yt-unmute", "");
      unmuteHint.appendChild(el("span", "", "🔊"));
      unmuteHint.appendChild(el("span", "", "Toca para activar el sonido"));
      frame.appendChild(unmuteHint);
    } else {
      frame.appendChild(el("div", "hb-yt-empty", "No hay ningún vídeo cargado. Dime qué quieres ver."));
    }
    root.appendChild(frame);

    // Click controls (mirror of what can also be requested by voice).
    const ctrls = el("div", "hb-yt-ctrls");
    const btn = (label, action) => {
      const b = el("button", "hb-yt-btn", label);
      b.addEventListener("click", () => { if(ctx && ctx.action) ctx.action(action); });
      return b;
    };
    ctrls.appendChild(btn("▶︎ Play", "play"));
    ctrls.appendChild(btn("❚❚ Pausa", "pause"));
    ctrls.appendChild(btn("🔉 −", "volume_down"));
    ctrls.appendChild(btn("🔊 +", "volume_up"));
    const muteBtn = el("button", "hb-yt-btn", "🔇 Silencio");   // action/label are set on each render (toggle)
    ctrls.appendChild(muteBtn);
    const vol = el("div", "hb-yt-vol", "");
    ctrls.appendChild(vol);
    root.appendChild(ctrls);

    root.appendChild(el("div", "hb-yt-hint",
      "Por voz: «pon el vídeo de…», «añade a la lista…», «siguiente», «pausa», «sube/baja el volumen»."));

    // The PLAYLIST (V2-366): a clean LINEAR text list — title · click — no thumbnail mosaic (operator's design).
    const listBox = el("div", "hb-yt-list");
    root.appendChild(listBox);
    const addRow = el("div", "hb-yt-addrow");
    const addInp = el("input", "hb-yt-addinp");
    addInp.placeholder = "Pega un enlace de YouTube o escribe un título…";
    const addBtn = el("button", "hb-yt-btn", "＋ Añadir");
    const doAdd = () => {
      const v = (addInp.value || "").trim();
      if(!v || !ctx || !ctx.action) return;
      addInp.value = "";
      ctx.action("add", {url: v});                       // the server tries link/id first, then searches by name
    };
    addBtn.addEventListener("click", doAdd);
    addInp.addEventListener("keydown", (e) => { if(e.key === "Enter") doAdd(); });
    addRow.appendChild(addInp); addRow.appendChild(addBtn);
    root.appendChild(addRow);

    root._hbYt = { id: id, seq: seq, loading: loading };   // "load" is already covered by new src → do not re-post as command
    root._hbYtBuilt = true;
    root._hbYtEls = { iframe: iframe, title: title, meta: meta, vol: vol, muteBtn: muteBtn, unmuteHint: unmuteHint,
                      listBox: listBox };
  }

  // Dynamic refresh on EVERY render (title, verifiable metadata, mute-toggle button, volume).
  const E = root._hbYtEls || {};
  if(E.title) E.title.textContent = data.title || "YouTube";
  if(E.meta){
    const bits = [];
    if(data.channel) bits.push(data.channel);
    if(data.published) bits.push((data.latest ? "más reciente · " : "") + data.published);
    E.meta.textContent = bits.join("  ·  ");
    E.meta.style.display = bits.length ? "" : "none";
  }
  const vol0 = Number(data.volume != null ? data.volume : 70);
  if(E.muteBtn){
    E.muteBtn.textContent = data.muted ? "🔊 Sonido" : "🔇 Silencio";
    E.muteBtn.onclick = () => {
      // Direct `post` (does not go through the server: it is the REAL click that unlocks browser audio) is also gated
      // — otherwise, with the agent stopped, this button would make the video play through the back door.
      if(data.muted && !halted(ctx)){ post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute");
    };
  }
  if(E.unmuteHint){
    E.unmuteHint.style.display = data.muted ? "flex" : "none";
    E.unmuteHint.onclick = () => {
      if(!halted(ctx)){ post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action("unmute");
    };
  }
  if(E.vol) E.vol.textContent = data.muted ? "silencio" : ("vol " + (data.volume != null ? data.volume : 70));

  // The queue advances because the player told us the video ended — refreshed every render so the callback
  // always carries the CURRENT ctx. Gated on halted: a stopped agent starts no playback (V2-092).
  _ytEnded = () => { if(ctx && ctx.action && !halted(ctx)) ctx.action("ended"); };
  _ytError = (code) => { if(ctx && ctx.action) ctx.action("player_error", {code: String(code == null ? "unknown" : code)}); };

  // The list rows, re-rendered on every render (text only; the iframe is never touched by this).
  if(E.listBox){
    E.listBox.textContent = "";
    const lst = Array.isArray(data.list) ? data.list : [];
    const filt = String(data.list_filter || "").trim().toLowerCase();
    // V2-467 — the list NAME takes precedence over the generic label: if the operator called it “the afternoon
    // one,” that is what must be shown on the card so they can verify at a glance that their request was followed.
    const _nom = String(data.list_name || "").trim();
    const _rot = _nom || "Lista";
    const head = el("div", "hb-yt-listh", lst.length ? (_rot + " · " + lst.length) : _rot);
    if(filt){
      const chip = el("span", "hb-yt-chip", "filtro: «" + filt + "» ✕");
      chip.title = "Quitar el filtro";
      chip.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("filter_list", {q: ""}); });
      head.appendChild(chip);
    }
    E.listBox.appendChild(head);
    if(data.adding) E.listBox.appendChild(el("div", "hb-yt-note", "Buscando «" + data.adding + "»…"));
    const pos = Number(data.pos != null ? data.pos : -1);
    let shown = 0;
    lst.forEach((it, i) => {
      const hay = ((it.title || "") + " " + (it.channel || "")).toLowerCase();
      if(filt && hay.indexOf(filt) < 0) return;
      shown++;
      const row = el("div", "hb-yt-row" + (i === pos ? " playing" : ""));
      row.appendChild(el("span", "hb-yt-rown", i === pos ? "▶" : String(i + 1)));
      row.appendChild(el("span", "hb-yt-rowt", it.title || it.url || "—"));
      if(it.channel) row.appendChild(el("span", "hb-yt-rowc", it.channel));
      const x = el("button", "hb-yt-rowx", "✕");
      x.title = "Quitar de la lista";
      x.addEventListener("click", (e) => { e.stopPropagation(); if(ctx && ctx.action) ctx.action("remove", {item: String(i + 1)}); });
      row.appendChild(x);
      row.addEventListener("click", () => { if(ctx && ctx.action) ctx.action("play_item", {item: String(i + 1)}); });
      E.listBox.appendChild(row);
    });
    if(lst.length && filt && !shown) E.listBox.appendChild(el("div", "hb-yt-note", "Nada en la lista casa con el filtro."));
    if(!lst.length) E.listBox.appendChild(el("div", "hb-yt-note", "La lista está vacía: pega un enlace o dime «añade a la lista…»."));
  }

  // Apply the last command if the counter advanced (same video; video changes are covered by the new src).
  if(seq !== root._hbYt.seq){
    applyCmd(E.iframe, data, ctx);
    root._hbYt.seq = seq;
  }
}

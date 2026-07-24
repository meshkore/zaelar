// youtube — reproductor de YouTube REAL embebido en el canvas (un <iframe>, no una captura). Se controla por
// VOZ: data.py guarda el comando deseado (last_cmd + cmd_seq) y el estado (paused/muted/volume); aquí lo
// aplicamos al reproductor con postMessage (YouTube IFrame API, SIN librería externa — solo mensajes al iframe).
// Contrato: render(el, data, ctx). Sin red desde JS: el <iframe> es un elemento, no una petición nuestra.

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
  `; document.head.appendChild(s);
}

function el(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

function post(iframe, func, args){
  try{
    if(!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*");
  }catch(_){}
}

// Reafirma el estado deseado en el reproductor (idempotente) — se usa al cargar un vídeo nuevo.
function applyState(iframe, data){
  if(data.muted){ post(iframe, "mute", []); }
  else { post(iframe, "unMute", []); post(iframe, "setVolume", [Number(data.volume != null ? data.volume : 70)]); }
  if(data.paused) post(iframe, "pauseVideo", []);
  else post(iframe, "playVideo", []);
}

// Aplica el ÚLTIMO comando pedido por voz/click (solo cuando avanza cmd_seq).
function applyCmd(iframe, data){
  const c = data.last_cmd || "";
  const vol = Number(data.volume != null ? data.volume : 70);
  if(c === "play") post(iframe, "playVideo", []);
  else if(c === "pause") post(iframe, "pauseVideo", []);
  else if(c === "mute") post(iframe, "mute", []);
  else if(c === "unmute"){ post(iframe, "unMute", []); post(iframe, "setVolume", [vol]); }
  else if(c === "volume_up" || c === "volume_down" || c === "set_volume"){
    post(iframe, "unMute", []); post(iframe, "setVolume", [vol]);
  }
  else if(c === "restart"){ post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []); }
}

export function render(root, data, ctx){
  injectStyles();
  data = data || {};
  const id = data.videoId || "";
  const seq = Number(data.cmd_seq || 0);
  const loading = !!data.loading;
  const st = root._hbYt || null;

  // (Re)construir la tarjeta cuando cambia el vídeo, o entra/sale del estado "buscando" (bug real 2026-07-23:
  // sin esto la tarjeta se veía TOTALMENTE vacía mientras el load buscaba en YouTube, sin ninguna señal).
  if(!st || st.id !== id || st.loading !== loading || !root._hbYtBuilt){
    root.className = "hb-yt";
    root.textContent = "";

    const title = el("div", "hb-yt-title", data.title || "YouTube");
    root.appendChild(title);
    const meta = el("div", "hb-yt-meta", "");            // canal · fecha de publicación (verificable, V2-057)
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
      const params = "enablejsapi=1&rel=0&modestbranding=1&playsinline=1&autoplay=1&mute=1&origin="
                     + encodeURIComponent(location.origin);
      iframe.src = "https://www.youtube.com/embed/" + encodeURIComponent(id) + "?" + params;
      const d0 = data;
      iframe.addEventListener("load", function(){ setTimeout(function(){ applyState(iframe, d0); }, 700); });
      frame.appendChild(iframe);
      // El navegador exige un TOQUE real para dar sonido a un autoplay que empezó muted (el "unmute" pedido
      // por VOZ no cuenta como gesto de usuario y el audio puede quedarse bloqueado en silencio sin avisar).
      // Este botón sí es un click real → desbloquea el audio YA, en el mismo gesto.
      unmuteHint = el("div", "hb-yt-unmute", "");
      unmuteHint.appendChild(el("span", "", "🔊"));
      unmuteHint.appendChild(el("span", "", "Toca para activar el sonido"));
      frame.appendChild(unmuteHint);
    } else {
      frame.appendChild(el("div", "hb-yt-empty", "No hay ningún vídeo cargado. Dime qué quieres ver."));
    }
    root.appendChild(frame);

    // Controles por click (espejo de lo que también se pide por voz).
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
    const muteBtn = el("button", "hb-yt-btn", "🔇 Silencio");   // acción/cartel se fijan cada render (es un toggle)
    ctrls.appendChild(muteBtn);
    const vol = el("div", "hb-yt-vol", "");
    ctrls.appendChild(vol);
    root.appendChild(ctrls);

    root.appendChild(el("div", "hb-yt-hint",
      "Por voz: «pon el vídeo de…», «pausa», «quita el silencio», «sube/baja el volumen», «reinícialo»."));

    root._hbYt = { id: id, seq: seq, loading: loading };   // el "load" ya lo cubre el src nuevo → no re-postear como comando
    root._hbYtBuilt = true;
    root._hbYtEls = { iframe: iframe, title: title, meta: meta, vol: vol, muteBtn: muteBtn, unmuteHint: unmuteHint };
  }

  // Refresco dinámico en CADA render (título, metadatos verificables, botón de silencio-toggle, volumen).
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
      if(data.muted){ post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]); }  // click real: audio YA
      if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute");
    };
  }
  if(E.unmuteHint){
    E.unmuteHint.style.display = data.muted ? "flex" : "none";
    E.unmuteHint.onclick = () => {
      post(E.iframe, "unMute", []); post(E.iframe, "setVolume", [vol0]);
      if(ctx && ctx.action) ctx.action("unmute");
    };
  }
  if(E.vol) E.vol.textContent = data.muted ? "silencio" : ("vol " + (data.volume != null ? data.volume : 70));

  // Aplicar el último comando si avanzó el contador (mismo vídeo; el cambio de vídeo lo cubre el src nuevo).
  if(seq !== root._hbYt.seq){
    applyCmd(E.iframe, data);
    root._hbYt.seq = seq;
  }
}

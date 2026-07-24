// personalizado-reproduzca-video — reproductor de YouTube REAL embebido en el canvas (un <iframe>, no una
// captura), dedicado EN EXCLUSIVA al gol de la "Mano de Dios" de Maradona: listo para reproducirse en cuanto
// se abre la tarjeta. Se controla por VOZ: data.py guarda el comando deseado (last_cmd + cmd_seq) y el estado
// (paused/muted/volume); aquí lo aplicamos al reproductor con postMessage (YouTube IFrame API, SIN librería
// externa — solo mensajes al iframe). Contrato: render(el, data, ctx). Sin red desde JS: el <iframe> es un
// elemento, no una petición nuestra.

function injectStyles(){
  if(document.getElementById("hb-mdd-css")) return;
  const s = document.createElement("style"); s.id = "hb-mdd-css"; s.textContent = `
  .hb-mdd{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
          width:min(680px,92vw);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
          border-radius:16px;padding:14px;display:flex;flex-direction:column;gap:10px}
  .hb-mdd-title{font-size:14px;font-weight:600;color:var(--hb-ink,#0d1622);line-height:1.3;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mdd-frame{position:relative;width:100%;padding-top:56.25%;border-radius:12px;overflow:hidden;
                background:var(--hb-bg-soft,#0d1622)}
  .hb-mdd-frame iframe{position:absolute;inset:0;width:100%;height:100%;border:0}
  .hb-mdd-ctrls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .hb-mdd-btn{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
              color:var(--hb-ink,#0d1622);border-radius:9px;padding:7px 12px;font-size:13px;font-weight:600;
              cursor:pointer;line-height:1}
  .hb-mdd-btn:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-mdd-vol{margin-left:auto;font-size:12px;color:var(--hb-muted,#5b6b82);font-variant-numeric:tabular-nums}
  .hb-mdd-hint{font-size:11.5px;color:var(--hb-muted-2,#9aa7b8);line-height:1.35}
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

// Reafirma el estado deseado en el reproductor (idempotente) — se usa al cargar la tarjeta.
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
  const st = root._hbMdd || null;

  // (Re)construir la tarjeta solo al primer render (el vídeo es fijo, nunca cambia de id).
  if(!st || !root._hbMddBuilt){
    root.className = "hb-mdd";
    root.textContent = "";

    const title = el("div", "hb-mdd-title", data.title || "Gol de la Mano de Dios");
    root.appendChild(title);

    const frame = el("div", "hb-mdd-frame");
    const iframe = document.createElement("iframe");
    iframe.title = data.title || "Gol de la Mano de Dios";
    iframe.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
    iframe.setAttribute("allowfullscreen", "");
    const params = "enablejsapi=1&rel=0&modestbranding=1&playsinline=1&autoplay=1&mute=1&origin="
                   + encodeURIComponent(location.origin);
    iframe.src = "https://www.youtube.com/embed/" + encodeURIComponent(id) + "?" + params;
    const d0 = data;
    iframe.addEventListener("load", function(){ setTimeout(function(){ applyState(iframe, d0); }, 700); });
    frame.appendChild(iframe);
    root.appendChild(frame);

    // Controles por click (espejo de lo que también se pide por voz).
    const ctrls = el("div", "hb-mdd-ctrls");
    const btn = (label, action) => {
      const b = el("button", "hb-mdd-btn", label);
      b.addEventListener("click", () => { if(ctx && ctx.action) ctx.action(action); });
      return b;
    };
    ctrls.appendChild(btn("▶︎ Play", "play"));
    ctrls.appendChild(btn("❚❚ Pausa", "pause"));
    ctrls.appendChild(btn("🔉 −", "volume_down"));
    ctrls.appendChild(btn("🔊 +", "volume_up"));
    const muteBtn = el("button", "hb-mdd-btn", "🔊 Sonido");   // acción/cartel se fijan cada render (es un toggle)
    ctrls.appendChild(muteBtn);
    const vol = el("div", "hb-mdd-vol", "");
    ctrls.appendChild(vol);
    root.appendChild(ctrls);

    root.appendChild(el("div", "hb-mdd-hint",
      "Por voz: «quita el silencio», «pausa», «sube/baja el volumen», «reinícialo»."));

    root._hbMdd = { id: id, seq: seq };
    root._hbMddBuilt = true;
    root._hbMddEls = { iframe: iframe, title: title, vol: vol, muteBtn: muteBtn };
  }

  // Refresco dinámico en CADA render (botón de silencio-toggle, volumen).
  const E = root._hbMddEls || {};
  if(E.title) E.title.textContent = data.title || "Gol de la Mano de Dios";
  if(E.muteBtn){
    E.muteBtn.textContent = data.muted ? "🔊 Sonido" : "🔇 Silencio";
    E.muteBtn.onclick = () => { if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute"); };
  }
  if(E.vol) E.vol.textContent = data.muted ? "silencio" : ("vol " + (data.volume != null ? data.volume : 70));

  // Aplicar el último comando si avanzó el contador.
  if(seq !== root._hbMdd.seq){
    applyCmd(E.iframe, data);
    root._hbMdd.seq = seq;
  }
}

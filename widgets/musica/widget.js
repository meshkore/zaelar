// musica — CARA del conector de música (V2-041) con ESTÉTICA SPOTIFY (V2-058, Fase 1). Contrato: render(el, data, ctx).
// data = GET /widgets/musica/data → {mode:"spotify"|"youtube"|"idle", connected, can_connect, own_client_id_set,
//   default_available, redirect_uri, now_playing (spotify)|null, yt:{videoId,title,paused,muted,volume,cmd_seq},
//   playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track], top:[track+count],
//   view:{kind:"home|playlist|...",id}}.  ctx.action(name,payload) → POST /widgets/musica/action (JSON).
//
// Vistas: HOME (Tus listas + Más escuchadas + Recientes) y PLAYLIST (portada + tracklist). La `view` del estado
// manda lo que se pinta; play_playlist / open_view / back la cambian (data-ops del FlashBrain o clicks). Barra de
// reproducción abajo (Spotify/YouTube). REPRODUCCIÓN = el conector (ctx.action → connectors.music.control); aquí
// NO se reinventa el backend.
//
// El reproductor de YouTube-audio OCULTO se REUSA entre re-renders (host persistente `_ytHost`): reconstruir la
// vista NUNCA recarga el iframe (que reiniciaría la canción). Solo se recrea si cambia el videoId; si cambia el
// cmd_seq se aplica el comando (pausa/volumen) por postMessage. La conexión de Spotify se conserva intacta.

function injectStyles(){
  if(document.getElementById("hb-mus2-css")) return;
  const s = document.createElement("style"); s.id = "hb-mus2-css"; s.textContent = `
  .hb-mus2-root{position:relative}
  .hb-mus2{--sp-green:#1DB954;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           width:min(468px,93vw);background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
           border-radius:16px;overflow:hidden;color:var(--hb-ink,#0d1622);display:flex;flex-direction:column}
  .hb-mus2-scroll{padding:15px 15px 8px;display:flex;flex-direction:column;gap:17px;max-height:60vh;overflow:auto}
  .hb-mus2-top{display:flex;align-items:center;gap:9px}
  .hb-mus2-top b{font-size:17px;font-weight:800;letter-spacing:-.015em}
  .hb-mus2-prov{margin-left:auto;font-size:11px;color:var(--hb-muted,#5b6b82);border:1px solid var(--hb-line,#eef1f6);
                border-radius:999px;padding:3px 9px;display:flex;align-items:center;gap:5px}
  .hb-mus2-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:0 0 auto}
  .hb-mus2-dot.on{background:var(--sp-green)}
  .hb-mus2-sec{display:flex;flex-direction:column;gap:9px}
  .hb-mus2-sech{font-size:13.5px;font-weight:800;letter-spacing:-.01em}
  .hb-mus2-lists{display:flex;gap:12px;overflow-x:auto;padding-bottom:3px}
  .hb-mus2-pl{flex:0 0 auto;width:114px;cursor:pointer;display:flex;flex-direction:column;gap:7px}
  .hb-mus2-art{border-radius:10px;display:flex;align-items:center;justify-content:center;overflow:hidden;
               background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
               box-shadow:0 6px 16px rgba(0,0,0,.16)}
  .hb-mus2-art img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-pl .hb-mus2-art{width:114px;height:114px;font-size:34px}
  .hb-mus2-plname{font-size:12.5px;font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-plsub{font-size:11px;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-new .hb-mus2-art{background:var(--hb-bg-soft,#fbfdff);border:1.5px dashed var(--hb-line,#eef1f6);
                            color:var(--hb-muted,#5b6b82);box-shadow:none;font-size:30px}
  .hb-mus2-grid{display:flex;flex-direction:column;gap:1px}
  .hb-mus2-tr{display:flex;align-items:center;gap:11px;padding:7px 8px;border-radius:9px;cursor:pointer}
  .hb-mus2-tr:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-tr .hb-mus2-art{width:40px;height:40px;font-size:17px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-trn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;min-width:16px;text-align:right}
  .hb-mus2-trmeta{min-width:0;flex:1}
  .hb-mus2-trt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-tra{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-x{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);font-size:15px;cursor:pointer;
             padding:2px 7px;border-radius:7px;line-height:1;flex:0 0 auto}
  .hb-mus2-x:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-empty{font-size:12px;color:var(--hb-muted-2,#9aa7b8);padding:1px 2px}
  .hb-mus2-back{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:13px;cursor:pointer;
                display:flex;align-items:center;gap:5px;padding:0;align-self:flex-start}
  .hb-mus2-back:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-head{display:flex;gap:15px;align-items:flex-end}
  .hb-mus2-head .hb-mus2-art{width:96px;height:96px;font-size:40px;box-shadow:0 8px 20px rgba(0,0,0,.2);flex:0 0 auto}
  .hb-mus2-headmeta{display:flex;flex-direction:column;gap:7px;min-width:0}
  .hb-mus2-headk{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--hb-muted-2,#9aa7b8);
                 font-family:ui-monospace,Menlo,monospace}
  .hb-mus2-headn{font-size:22px;font-weight:800;line-height:1.08;letter-spacing:-.02em;word-break:break-word}
  .hb-mus2-playbig{align-self:flex-start;border:0;background:var(--sp-green);color:#fff;border-radius:999px;
                   padding:9px 18px 9px 15px;font-size:13.5px;font-weight:800;cursor:pointer;
                   display:inline-flex;align-items:center;gap:8px}
  .hb-mus2-playbig:disabled{opacity:.45;cursor:default}
  .hb-mus2-bar{border-top:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
               padding:10px 13px;display:flex;align-items:center;gap:11px}
  .hb-mus2-bar .hb-mus2-art{width:44px;height:44px;font-size:20px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-barmeta{min-width:0;flex:1}
  .hb-mus2-bart{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bara{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-barc{display:flex;align-items:center;gap:3px}
  .hb-mus2-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);font-size:16px;cursor:pointer;padding:5px;
                border-radius:8px;line-height:1}
  .hb-mus2-cbtn:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-cbtn.main{width:34px;height:34px;border-radius:50%;background:var(--hb-ink,#0d1622);
                     color:var(--hb-bg,#fff);display:flex;align-items:center;justify-content:center;font-size:14px}
  .hb-mus2-cbtn.main:hover{color:var(--hb-bg,#fff);opacity:.85}
  .hb-mus2-connect{display:flex;flex-direction:column;gap:8px}
  .hb-mus2-sub{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-btn{border:0;background:var(--hb-accent,#3D6FE0);color:#fff;border-radius:10px;padding:9px 13px;
               font-size:13px;font-weight:700;cursor:pointer;line-height:1;align-self:flex-start}
  .hb-mus2-btn:disabled{opacity:.5;cursor:default}
  .hb-mus2-btn.ghost{background:var(--hb-bg-soft,#fbfdff);color:var(--hb-ink,#0d1622);border:1px solid var(--hb-line,#eef1f6)}
  .hb-mus2-link{background:none;border:0;color:var(--hb-muted,#5b6b82);font-size:11.5px;cursor:pointer;
                text-decoration:underline;padding:0;align-self:flex-start}
  .hb-mus2-adv{border-top:1px solid var(--hb-line,#eef1f6);padding-top:10px;display:flex;flex-direction:column;gap:8px}
  .hb-mus2-adv summary{font-size:12px;color:var(--hb-muted,#5b6b82);cursor:pointer}
  .hb-mus2-steps{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.5;margin:0;padding-left:18px}
  .hb-mus2-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;
                background:var(--hb-bg-soft,#f4f7fb);border:1px solid var(--hb-line,#eef1f6);border-radius:7px;
                padding:4px 7px;word-break:break-all;color:var(--hb-ink,#0d1622)}
  .hb-mus2-inp{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#eef1f6);border-radius:8px;
               padding:8px 10px;font-size:13px;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622)}
  .hb-mus2-newinp{width:126px}
  .hb-mus2-audio{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;left:-9999px;top:0}
  .hb-mus2-frame{width:1px;height:1px;border:0}
  `; document.head.appendChild(s);
}

function h(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// portada: imagen (URL de Spotify) o emoji de reserva. La URL va en img.src (nunca innerHTML).
function artNode(art, fallback){
  const a = h("div", "hb-mus2-art");
  if(art){ const img = document.createElement("img"); img.src = art; img.alt = ""; a.appendChild(img); }
  else a.textContent = fallback || "🎵";
  return a;
}

function ytPost(iframe, func, args){
  try{ if(iframe && iframe.contentWindow)
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*"); }catch(_){}
}
// Asegura que el player SUENA (quita mute + fija volumen): al montar y en CADA comando → «no se oye» despierta de verdad.
function ytEnsureAudible(iframe, vol){
  ytPost(iframe, "unMute");
  ytPost(iframe, "setVolume", [Math.max(0, Math.min(100, vol||70))]);
}

// ── EVENTOS del reproductor de YouTube (V2-047 F4/F10): handshake `listening` → onReady/onStateChange(ENDED) ──
let _ytReady = null, _ytEnded = null;
function ytStartListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-musica", channel:"widget"}), "*"); }catch(_){}
}
if (typeof window !== "undefined" && !window.__hbMusicaYtBound){
  window.__hbMusicaYtBound = true;
  window.addEventListener("message", (ev) => {
    if (typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    if (d.event === "onReady" && _ytReady) _ytReady();
    else if (d.event === "onStateChange" && Number(d.info) === 0 && _ytEnded) _ytEnded();   // 0 = ENDED
  });
}

// El player OCULTO vive en un host persistente (`el._ytHost`) que NO se reconstruye al re-renderizar la vista →
// reordenar/navegar nunca reinicia la canción. Solo se recrea el iframe si cambia el videoId.
// ¿Está el agente PARADO? (V2-092) — con el ⏻ apagado la música no suena, y sobre todo no vuelve a sonar sola al
// RECARGAR la página (era el bug: el estado guardado decía «suena» y el iframe nacía con `autoplay=1`). `ctx.running`
// es un getter vivo del canvas que refleja la verdad del servidor (nucleo/runstate.py). «Parado» solo si lo dice
// explícitamente: un ctx sin el campo no puede dejar el reproductor mudo para siempre.
function halted(ctx){ return !!(ctx && ctx.running === false); }

function syncYtPlayer(el, data, ctx){
  const yt = data.yt || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  if(!yt.videoId){                                   // nada sonando por YouTube → suelta el frame
    if(el._hbFrame){ host.textContent = ""; el._hbFrame = null; el._hbVid = null; el._hbSeq = null; }
    return;
  }
  if(el._hbVid === yt.videoId && el._hbFrame){       // mismo vídeo → solo aplica el comando nuevo
    if(el._hbSeq !== yt.cmd_seq){
      el._hbSeq = yt.cmd_seq;
      if(yt.paused || stopped){ ytPost(el._hbFrame, "pauseVideo"); }
      else { ytEnsureAudible(el._hbFrame, yt.volume); ytPost(el._hbFrame, "playVideo"); }
    }
    return;
  }
  // vídeo nuevo → iframe OCULTO. ARRANQUE GARANTIZADO: mute=1 (autoplay silenciado siempre permitido) y se
  // des-silencia al instante por la API (la página ya tiene interacción del operador → el unMute se honra).
  // Con el agente parado el `autoplay` se apaga en el propio `src`: cualquier pausa posterior llegaría tarde y se
  // oiría el arranque.
  host.textContent = "";
  const frame = document.createElement("iframe");
  frame.className = "hb-mus2-frame";
  frame.allow = "autoplay";
  frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(yt.videoId)
            + "?enablejsapi=1&autoplay=" + ((yt.paused || stopped) ? 0 : 1)
            + "&mute=1&controls=0&playsinline=1&rel=0";
  frame.addEventListener("load", () => ytStartListening(frame));
  host.appendChild(frame);
  el._hbFrame = frame; el._hbVid = yt.videoId; el._hbSeq = yt.cmd_seq;
  const wake = () => {
    if(halted(ctx)){ ytPost(frame, "pauseVideo"); return; }   // se re-lee: `wake` corre en timeouts de hasta 2,6s
    ytEnsureAudible(frame, yt.volume); if(!yt.paused) ytPost(frame, "playVideo");
  };
  _ytReady = wake;                                   // el onReady REAL es el momento exacto (los timeouts respaldan)
  _ytEnded = () => { try{ ctx.action("ended"); }catch(_){} };   // F4: al terminar → avanza la cola en el servidor
  setTimeout(wake, 1200); setTimeout(wake, 2600);
}

// ── conexión de Spotify (intacta respecto a V2-041) ────────────────────────────────────────────────────────
async function doConnect(ctx, client_id, btn, adv){
  if(btn){ btn.disabled = true; btn.textContent = "Abriendo Spotify…"; }
  const res = await ctx.action("connect", client_id ? {client_id} : {});
  if(res && res.url){
    window.open(res.url, "spotify_login", "width=520,height=760");
    if(btn) btn.textContent = "Termina el login en la ventana…";
  } else {
    if(btn){ btn.disabled = false; btn.textContent = client_id ? "Conectar con mi Client ID" : "Conectar Spotify"; }
    if(res && res.need_client_id && adv) adv.open = true;
  }
}

function connectBlock(data, ctx, {compact=false} = {}){
  const frag = document.createDocumentFragment();
  let adv;
  if(data.can_connect){
    const b = h("button", compact ? "hb-mus2-link" : "hb-mus2-btn",
      compact ? "Conectar Spotify (tu biblioteca)" : "Conectar Spotify");
    b.onclick = () => doConnect(ctx, "", compact ? null : b, adv);
    frag.appendChild(b);
  }
  adv = h("details", "hb-mus2-adv");
  if(!data.can_connect) adv.open = true;
  adv.appendChild(h("summary", null, data.can_connect ? "Usar mi propia app de Spotify (avanzado)"
                                                      : "Conectar con tu app de Spotify"));
  const ol = h("ol", "hb-mus2-steps");
  ol.appendChild(h("li", null, "Entra en developer.spotify.com → Dashboard → Create app."));
  const li2 = h("li", null, "En «Redirect URIs» añade exactamente:");
  li2.appendChild(h("div", "hb-mus2-code", data.redirect_uri || "http://127.0.0.1:43917/api/spotify/callback"));
  ol.appendChild(li2);
  ol.appendChild(h("li", null, "Copia el «Client ID» y pégalo aquí:"));
  adv.appendChild(ol);
  const inp = h("input", "hb-mus2-inp"); inp.placeholder = "Tu Client ID de Spotify";
  adv.appendChild(inp);
  const b2 = h("button", "hb-mus2-btn ghost", "Conectar con mi Client ID");
  b2.onclick = () => { const v = (inp.value||"").trim(); if(v) doConnect(ctx, v, b2, adv); };
  adv.appendChild(b2);
  frag.appendChild(adv);
  return frag;
}

// ── barra de reproducción (Spotify o YouTube) ──────────────────────────────────────────────────────────────
function nowPlaying(data){
  if(data.now_playing && data.now_playing.title) return data.now_playing;
  const yt = data.yt || {};
  if(yt.videoId) return {title: yt.title || "Música", artist: "", art: "", playing: !yt.paused};
  return null;
}

function playbackBar(data, ctx){
  const bar = h("div", "hb-mus2-bar");
  const np = nowPlaying(data);
  bar.appendChild(artNode(np && np.art, "🎵"));
  const meta = h("div", "hb-mus2-barmeta");
  meta.appendChild(h("div", "hb-mus2-bart", np ? (np.title || "Música") : "Nada sonando"));
  meta.appendChild(h("div", "hb-mus2-bara", np ? (np.artist || (np.device ? np.device : "")) : "Dime «pon música» o abre una lista."));
  bar.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mk = (label, action, cls) => { const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""), label);
    b.onclick = () => ctx.action(action); return b; };     // control = fire-and-forget; el SSE re-renderiza
  ctrls.appendChild(mk("⏮", "previous"));
  const playing = !!(np && np.playing);
  ctrls.appendChild(mk(playing ? "⏸" : "▶", playing ? "pause" : "resume", "main"));
  ctrls.appendChild(mk("⏭", "next"));
  ctrls.appendChild(mk("🔉", "volume_down"));
  ctrls.appendChild(mk("🔊", "volume_up"));
  if(np) ctrls.appendChild(mk("♥", "favorite_current"));
  bar.appendChild(ctrls);
  return bar;
}

// ── filas de tracks (recientes / más-escuchadas / tracklist de una lista) ────────────────────────────────
function trackRow(t, ctx, opts){
  opts = opts || {};
  const row = h("div", "hb-mus2-tr");
  if(opts.index != null) row.appendChild(h("div", "hb-mus2-trn", opts.index));
  row.appendChild(artNode(t.art, "🎵"));
  const meta = h("div", "hb-mus2-trmeta");
  meta.appendChild(h("div", "hb-mus2-trt", t.title || t.query || "—"));
  const sub = [t.artist, (t.count ? `· ${t.count} veces` : "")].filter(Boolean).join(" ");
  if(sub) meta.appendChild(h("div", "hb-mus2-tra", sub));
  row.appendChild(meta);
  row.onclick = () => ctx.action("play", {query: t.query || [t.title, t.artist].filter(Boolean).join(" ") || t.title});
  if(opts.remove){
    const x = h("button", "hb-mus2-x", "✕"); x.title = "Quitar de la lista";
    x.onclick = (e) => { e.stopPropagation(); ctx.action("remove_from_playlist", {playlist: opts.remove, item: t.title}); };
    row.appendChild(x);
  }
  return row;
}

// ── HOME: Tus listas + Más escuchadas + Recientes ──────────────────────────────────────────────────────────
function homeView(host, data, ctx){
  const wrap = h("div", "hb-mus2");
  const scroll = h("div", "hb-mus2-scroll");

  const top = h("div", "hb-mus2-top");
  top.appendChild(h("b", null, "Tu música"));
  const prov = h("div", "hb-mus2-prov");
  const connected = !!data.connected, yt = data.yt || {};
  prov.appendChild(h("span", "hb-mus2-dot" + (connected || yt.videoId ? " on" : "")));
  prov.appendChild(h("span", null, connected ? "Spotify" : (yt.videoId ? "YouTube" : "Sin fuente")));
  top.appendChild(prov);
  scroll.appendChild(top);

  if(!connected && !yt.videoId){
    const cx = h("div", "hb-mus2-connect");
    cx.appendChild(h("div", "hb-mus2-sub",
      "Dime «pon música» o «ponme a Frank Sinatra» y suena gratis. Conecta tu Spotify (Premium) para tu biblioteca."));
    cx.appendChild(connectBlock(data, ctx, {compact:false}));
    scroll.appendChild(cx);
  }

  // Tus listas (portadas + tarjeta "Nueva lista")
  const secL = h("div", "hb-mus2-sec");
  secL.appendChild(h("div", "hb-mus2-sech", "Tus listas"));
  const lists = h("div", "hb-mus2-lists");
  (data.playlists || []).forEach(pl => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(artNode(pl.art, "🎶"));
    c.appendChild(h("div", "hb-mus2-plname", pl.name || "Lista"));
    const n = (pl.tracks || []).length;
    c.appendChild(h("div", "hb-mus2-plsub", `${n} canción${n !== 1 ? "es" : ""}`));
    c.onclick = () => ctx.action("open_view", {kind: "playlist", id: pl.id});
    lists.appendChild(c);
  });
  lists.appendChild(newListCard(lists, ctx));
  secL.appendChild(lists);
  scroll.appendChild(secL);

  // Más escuchadas
  if((data.top || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", "Más escuchadas"));
    const g = h("div", "hb-mus2-grid");
    data.top.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1)})));
    s.appendChild(g); scroll.appendChild(s);
  }

  // Recientes
  if((data.recent || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", "Recientes"));
    const g = h("div", "hb-mus2-grid");
    data.recent.slice(0, 8).forEach(t => g.appendChild(trackRow(t, ctx, {})));
    s.appendChild(g); scroll.appendChild(s);
  }

  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);
}

function newListCard(lists, ctx){
  const card = h("div", "hb-mus2-pl hb-mus2-new");
  card.appendChild(artNode(null, "＋"));
  card.appendChild(h("div", "hb-mus2-plname", "Nueva lista"));
  card.onclick = () => {
    // inline: un input reemplaza el gesto de crear; Enter/blur → create_playlist (el SSE re-renderiza a la lista).
    const box = h("div", "hb-mus2-pl");
    const inp = h("input", "hb-mus2-inp hb-mus2-newinp"); inp.placeholder = "Nombre";
    box.appendChild(inp);
    lists.insertBefore(box, card);
    inp.focus();
    let done = false;
    const submit = () => { if(done) return; const v = (inp.value||"").trim();
      if(v){ done = true; ctx.action("create_playlist", {name: v}); } else box.remove(); };
    inp.addEventListener("keydown", e => { if(e.key === "Enter") submit(); if(e.key === "Escape"){ done = true; box.remove(); } });
    inp.addEventListener("blur", submit);
  };
  return card;
}

// ── PLAYLIST: portada + tracklist ──────────────────────────────────────────────────────────────────────────
function playlistView(host, data, ctx, pl){
  const wrap = h("div", "hb-mus2");
  const scroll = h("div", "hb-mus2-scroll");

  const back = h("button", "hb-mus2-back", "‹ Volver");
  back.onclick = () => ctx.action("back");
  scroll.appendChild(back);

  const head = h("div", "hb-mus2-head");
  head.appendChild(artNode(pl.art, "🎶"));
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", "Lista"));
  hm.appendChild(h("div", "hb-mus2-headn", pl.name || "Lista"));
  const n = (pl.tracks || []).length;
  hm.appendChild(h("div", "hb-mus2-plsub", `${n} canción${n !== 1 ? "es" : ""}`));
  head.appendChild(hm);
  scroll.appendChild(head);

  const play = h("button", "hb-mus2-playbig", "▶  Reproducir");
  if(!n) play.disabled = true;
  play.onclick = () => ctx.action("play_playlist", {playlist: pl.id});
  scroll.appendChild(play);

  const g = h("div", "hb-mus2-grid");
  if(n){ (pl.tracks || []).forEach((t, i) =>
    g.appendChild(trackRow(t, ctx, {index: String(i + 1), remove: pl.id}))); }
  else { g.appendChild(h("div", "hb-mus2-empty", "Lista vacía. Dime «añade una canción a esta lista».")); }
  scroll.appendChild(g);

  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);
}

function drawView(el, data, ctx){
  const host = el._viewHost;
  host.textContent = "";
  const view = data.view || {kind: "home"};
  if(view.kind === "playlist"){
    const pl = (data.playlists || []).find(p => p.id === view.id);
    if(pl){ playlistView(host, data, ctx, pl); return; }
  }
  homeView(host, data, ctx);          // home por defecto (y para vistas de Fase 2 aún no implementadas)
}

export function render(el, data, ctx){
  injectStyles();
  data = data || {};
  if(!el._hbInit){                    // hosts persistentes: la vista se reconstruye, el player oculto NO
    el.textContent = "";
    el.className = "hb-mus2-root";
    el._viewHost = document.createElement("div");
    el._ytHost = document.createElement("div"); el._ytHost.className = "hb-mus2-audio";
    el.append(el._viewHost, el._ytHost);
    el._hbInit = true;
  }
  syncYtPlayer(el, data, ctx);
  drawView(el, data, ctx);
}

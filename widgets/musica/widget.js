// musica: face of the music connector (V2-041) with Spotify-style aesthetics (V2-058, Phase 1) + a PRO redesign
// (V2-XXX): clearer header/content separation, a floating play button ON the cover art, a per-row "now playing"
// indicator (animated bars, everywhere a track can appear — playlist, top, recent AND the bottom bar), a
// playlist header that shows a shared artist ONCE instead of repeating it in every row, and click=select /
// double-click=play on every track row. Contract:
// render(el, data, ctx).
// data = GET /widgets/musica/data -> {mode:"spotify"|"youtube"|"idle", connected, can_connect, own_client_id_set,
//   default_available, redirect_uri, now_playing (spotify)|null, yt:{videoId,title,paused,muted,volume,cmd_seq},
//   playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track], top:[track+count],
//   view:{kind:"home|playlist|...",id}}.  ctx.action(name,payload) -> POST /widgets/musica/action (JSON).
//
// Views: HOME (lists + top tracks + recent) and PLAYLIST (cover + tracklist). State `view` controls what is
// rendered; play_playlist / open_view / back change it through FlashBrain data-ops or clicks. Playback bar at the
// bottom (Spotify/YouTube). PLAYBACK = the connector (ctx.action -> connectors.music.control); do not reinvent the
// backend here.
//
// The hidden YouTube-audio player is reused between re-renders (persistent `_ytHost`): rebuilding the view never
// reloads the iframe, which would restart the song. It is recreated only when videoId changes; if cmd_seq changes,
// the pause/volume command is applied by postMessage. Spotify connection remains intact.

function injectStyles(){
  if(document.getElementById("hb-mus2-css")) return;
  const s = document.createElement("style"); s.id = "hb-mus2-css"; s.textContent = `
  .hb-mus2-root{position:relative}
  .hb-mus2{--sp-green:#1DB954;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           width:100%;box-sizing:border-box;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
           border-radius:16px;overflow:hidden;color:var(--hb-ink,#0d1622);display:flex;flex-direction:column}
  .hb-mus2-scroll{padding:15px 15px 8px;display:flex;flex-direction:column;gap:17px;max-height:60vh;overflow:auto}
  .hb-mus2-top{display:flex;align-items:center;gap:9px;padding-bottom:13px;border-bottom:1px solid var(--hb-line,#eef1f6)}
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
               box-shadow:0 6px 16px rgba(0,0,0,.16);transition:transform .15s,box-shadow .15s}
  .hb-mus2-art img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-pl .hb-mus2-art{width:114px;height:114px;font-size:34px}
  .hb-mus2-pl:hover .hb-mus2-art{transform:translateY(-2px);box-shadow:0 12px 24px rgba(0,0,0,.24)}
  .hb-mus2-plname{font-size:12.5px;font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-plsub{font-size:11px;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-new .hb-mus2-art{background:var(--hb-bg-soft,#fbfdff);border:1.5px dashed var(--hb-line,#eef1f6);
                            color:var(--hb-muted,#5b6b82);box-shadow:none;font-size:30px}
  .hb-mus2-grid{display:flex;flex-direction:column;gap:1px}
  .hb-mus2-tr{display:flex;align-items:center;gap:11px;padding:7px 8px;border-radius:9px;cursor:pointer;
              user-select:none}
  .hb-mus2-tr:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-tr.selected{background:var(--hb-bg-soft,#fbfdff);box-shadow:inset 0 0 0 1px var(--hb-line,#eef1f6)}
  .hb-mus2-tr.playing{background:rgba(29,185,84,.10)}
  .hb-mus2-tr.playing.selected{background:rgba(29,185,84,.16)}
  .hb-mus2-tr.playing .hb-mus2-trt{color:var(--sp-green)}
  .hb-mus2-tr .hb-mus2-art{width:40px;height:40px;font-size:17px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-trn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;
               min-width:16px;text-align:center;display:flex;align-items:center;justify-content:center}
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
  .hb-mus2-artwrap{position:relative;flex:0 0 auto}
  .hb-mus2-head .hb-mus2-art{width:96px;height:96px;font-size:40px;box-shadow:0 8px 20px rgba(0,0,0,.2);flex:0 0 auto}
  .hb-mus2-headmeta{display:flex;flex-direction:column;gap:7px;min-width:0}
  .hb-mus2-headk{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--hb-muted-2,#9aa7b8);
                 font-family:ui-monospace,Menlo,monospace}
  .hb-mus2-headn{font-size:22px;font-weight:800;line-height:1.08;letter-spacing:-.02em;word-break:break-word}
  .hb-mus2-playfab{position:absolute;right:8px;bottom:8px;width:46px;height:46px;border-radius:50%;
                   background:var(--sp-green);color:#fff;border:0;font-size:17px;cursor:pointer;
                   display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(0,0,0,.35);
                   transition:transform .15s}
  .hb-mus2-playfab:hover{transform:scale(1.07)}
  .hb-mus2-playfab:disabled{opacity:.4;cursor:default;box-shadow:none;transform:none}
  .hb-mus2-bar{border-top:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
               padding:10px 13px;display:flex;align-items:center;gap:11px}
  .hb-mus2-barartwrap{position:relative;flex:0 0 auto}
  .hb-mus2-bar .hb-mus2-art{width:44px;height:44px;font-size:20px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-areq{position:absolute;right:-3px;bottom:-3px;width:19px;height:19px;border-radius:50%;
                background:var(--hb-ink,#0d1622);display:flex;align-items:center;justify-content:center;
                box-shadow:0 0 0 2px var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-areq .hb-mus2-eq{width:10px;height:9px}
  .hb-mus2-areq .hb-mus2-eq span{width:2px}
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
  .hb-mus2-eq{display:flex;align-items:flex-end;gap:2px;width:14px;height:14px}
  .hb-mus2-eq span{width:3px;background:var(--sp-green);border-radius:1px;animation:hbMusEq .9s ease-in-out infinite}
  .hb-mus2-eq span:nth-child(1){height:40%;animation-delay:-.6s}
  .hb-mus2-eq span:nth-child(2){height:100%;animation-delay:-.3s}
  .hb-mus2-eq span:nth-child(3){height:65%;animation-delay:0s}
  @keyframes hbMusEq{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1)}}
  `; document.head.appendChild(s);
}

function h(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// Animated "now playing" bars — the visible signal that THIS row/mini-player is the one making sound.
function eqIcon(){
  const wrap = h("div", "hb-mus2-eq");
  wrap.appendChild(h("span")); wrap.appendChild(h("span")); wrap.appendChild(h("span"));
  return wrap;
}

// Cover art: image (Spotify URL) or fallback emoji. URL goes into img.src, never innerHTML.
function artNode(art, fallback){
  const a = h("div", "hb-mus2-art");
  if(art){ const img = document.createElement("img"); img.src = art; img.alt = ""; a.appendChild(img); }
  else a.textContent = fallback || "🎵";
  return a;
}

// Text compare for "is this the track that's playing" — accent/case-insensitive, same spirit as the server's
// own `_norm` (data.py), kept separately here because widget.js never imports server code (V2-557).
function _norm(s){
  return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

function nowPlayingMatches(t, np){
  if(!np) return false;
  const a = _norm(t.title || t.query), b = _norm(np.title);
  if(!a || !b) return false;
  const aa = _norm(t.artist), ba = _norm(np.artist);
  if(a === b) return (aa && ba) ? aa === ba : true;   // missing artist on either side: the title match is enough
  // A legacy merged title ("madonna papa don't preach", no separate artist field) played through a CONNECTED
  // provider reports its own clean, real title ("papa don't preach") — a plain equality never matches, so this
  // row would never light up for the exact case the redesign exists to fix. If the stored title ENDS with the
  // now-playing title, treat the leftover prefix as the artist and require it to agree with `np.artist` when
  // that is known — a bare suffix match with no artist to cross-check would risk lighting up an unrelated song
  // that merely ends the same way.
  if(!aa && b.length > 3 && a.endsWith(b)){
    const prefix = a.slice(0, a.length - b.length).trim();
    return !ba || prefix === ba || prefix.endsWith(ba);
  }
  return false;
}

// A playlist where every track shares the SAME artist should say that artist ONCE (the header), not on every
// row — the operator's complaint on a playlist that happened to be one Madonna album, titles like "Madonna
// Papa Don't Preach" repeated verbatim in each row. Two cases: (1) tracks already carry a proper `artist`
// field, uniformly — show it, strip nothing (`title`/`artist` were already separate). (2) legacy/free-text
// data where the artist got baked INTO `title` with no separator (a bare `query` used as the title, V2-384's
// "one call is all the model gets" combined with a search string that already had the artist inside it): if
// EVERY track's title starts with the same leading word(s) and something real is left over after them, treat
// that shared prefix as the artist for DISPLAY ONLY — the stored data is never touched, so this is always
// reversible and never invents a fact that is not already, verbatim, in every row.
function deriveArtistInfo(tracks){
  const list = tracks || [];
  const noStrip = {commonArtist: "", strip: (title) => title};
  if(list.length < 2) return noStrip;

  const artists = list.map(t => String(t.artist || "").trim());
  if(artists.every(a => a)){
    return (new Set(artists.map(_norm)).size === 1) ? {commonArtist: artists[0], strip: (t) => t} : noStrip;
  }
  if(artists.some(a => a)) return noStrip;   // mixed metadata quality (some tagged, some not) — don't guess

  const wordLists = list.map(t => String(t.title || "").trim().split(/\s+/).filter(Boolean));
  const minWords = Math.min(...wordLists.map(w => w.length));
  if(minWords < 2) return noStrip;
  let k = 0;
  for(let i = 0; i < minWords - 1; i++){       // leave at least one real word behind as the title
    const w0 = _norm(wordLists[0][i]);
    if(!w0 || !wordLists.every(w => _norm(w[i]) === w0)) break;
    k = i + 1;
  }
  if(k === 0) return noStrip;
  const commonArtist = wordLists[0].slice(0, k).join(" ");
  return {
    commonArtist,
    strip: (title) => {
      const words = String(title || "").trim().split(/\s+/);
      return words.length > k ? words.slice(k).join(" ") : title;
    },
  };
}

function ytPost(iframe, func, args){
  try{ if(iframe && iframe.contentWindow)
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*"); }catch(_){}
}
// Ensure the player is audible (unmute + set volume): on mount and every command, so "no audio" actually wakes up.
function ytEnsureAudible(iframe, vol){
  ytPost(iframe, "unMute");
  ytPost(iframe, "setVolume", [Math.max(0, Math.min(100, vol||70))]);
}

// YouTube player events (V2-047 F4/F10): `listening` handshake -> onReady/onStateChange(ENDED).
let _ytReady = null, _ytEnded = null;
function ytStartListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-musica", channel:"widget"}), "*"); }catch(_){}
}
if (typeof window !== "undefined" && !window.__hbMusicaYtBound){
  window.__hbMusicaYtBound = true;
  window.addEventListener("message", (ev) => {
    if (typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    // Only OUR hidden player (the handshake id): the youtube WIDGET's player also emits onStateChange on this
    // same window since V2-366, and without this filter a video ending would advance the MUSIC queue.
    if (d.id !== "hb-musica") return;
    if (d.event === "onReady" && _ytReady) _ytReady();
    else if (d.event === "onStateChange" && Number(d.info) === 0 && _ytEnded) _ytEnded();   // 0 = ENDED
  });
}

// The hidden player lives in a persistent host (`el._ytHost`) that is NOT rebuilt when the view re-renders, so
// reorder/navigation never restarts the song. The iframe is recreated only if videoId changes.
// Is the agent STOPPED? (V2-092): when power is off, music should not play, and especially should not start by
// itself on page reload. The bug was that saved state said "playing" and the iframe was born with `autoplay=1`.
// `ctx.running` is a live canvas getter reflecting server truth (nucleo/runstate.py). Treat it as stopped only when
// explicit; a ctx without the field must not leave the player muted forever.
function halted(ctx){ return !!(ctx && ctx.running === false); }

function syncYtPlayer(el, data, ctx){
  const yt = data.yt || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  if(!yt.videoId){                                   // nothing playing through YouTube -> release the frame
    if(el._hbFrame){ host.textContent = ""; el._hbFrame = null; el._hbVid = null; el._hbSeq = null; }
    return;
  }
  if(el._hbVid === yt.videoId && el._hbFrame){       // same video -> only apply the new command
    if(el._hbSeq !== yt.cmd_seq){
      el._hbSeq = yt.cmd_seq;
      if(yt.paused || stopped){ ytPost(el._hbFrame, "pauseVideo"); }
      else { ytEnsureAudible(el._hbFrame, yt.volume); ytPost(el._hbFrame, "playVideo"); }
    }
    return;
  }
  // New video -> hidden iframe. Guaranteed start: mute=1 because muted autoplay is always allowed, then unmute
  // immediately through the API because the page already has operator interaction. With the agent stopped,
  // `autoplay` is disabled in the `src` itself; any later pause would arrive too late and the start would be heard.
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
    if(halted(ctx)){ ytPost(frame, "pauseVideo"); return; }   // re-read because `wake` runs in timeouts up to 2.6s
    ytEnsureAudible(frame, yt.volume); if(!yt.paused) ytPost(frame, "playVideo");
  };
  _ytReady = wake;                                   // real onReady is the exact moment; timeouts back it up
  _ytEnded = () => { try{ ctx.action("ended"); }catch(_){} };   // F4: on end -> advance queue on the server
  setTimeout(wake, 1200); setTimeout(wake, 2600);
}

// Spotify connection, intact from V2-041.
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

// Playback bar (Spotify or YouTube).
function nowPlaying(data){
  if(data.now_playing && data.now_playing.title) return data.now_playing;
  const yt = data.yt || {};
  if(yt.videoId) return {title: yt.title || "Música", artist: "", art: "", playing: !yt.paused};
  return null;
}

function playbackBar(data, ctx){
  const bar = h("div", "hb-mus2-bar");
  const np = nowPlaying(data);
  const playing = !!(np && np.playing);
  const artWrap = h("div", "hb-mus2-barartwrap");
  artWrap.appendChild(artNode(np && np.art, "🎵"));
  if(playing){ const badge = h("div", "hb-mus2-areq"); badge.appendChild(eqIcon()); artWrap.appendChild(badge); }
  bar.appendChild(artWrap);
  const meta = h("div", "hb-mus2-barmeta");
  meta.appendChild(h("div", "hb-mus2-bart", np ? (np.title || "Música") : "Nada sonando"));
  meta.appendChild(h("div", "hb-mus2-bara", np ? (np.artist || (np.device ? np.device : "")) : "Dime «pon música» o abre una lista."));
  bar.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mk = (label, action, cls) => { const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""), label);
    b.onclick = () => ctx.action(action); return b; };     // control = fire-and-forget; SSE re-renders
  ctrls.appendChild(mk("⏮", "previous"));
  ctrls.appendChild(mk(playing ? "⏸" : "▶", playing ? "pause" : "resume", "main"));
  ctrls.appendChild(mk("⏭", "next"));
  ctrls.appendChild(mk("🔉", "volume_down"));
  ctrls.appendChild(mk("🔊", "volume_up"));
  if(np) ctrls.appendChild(mk("♥", "favorite_current"));
  bar.appendChild(ctrls);
  return bar;
}

// Track rows (recent / top tracks / playlist tracklist). Click SELECTS (a purely visual, ephemeral highlight —
// nothing persisted, nothing sent to the server); double-click PLAYS, like a desktop Spotify tracklist. The
// "now playing" state, by contrast, IS driven by data (`opts.playing`) and survives a re-render.
function trackRow(t, ctx, opts){
  opts = opts || {};
  const row = h("div", "hb-mus2-tr" + (opts.playing ? " playing" : ""));
  if(opts.index != null || opts.playing){
    const cell = h("div", "hb-mus2-trn");
    if(opts.playing) cell.appendChild(eqIcon());
    else cell.textContent = opts.index;
    row.appendChild(cell);
  }
  row.appendChild(artNode(t.art, "🎵"));
  const meta = h("div", "hb-mus2-trmeta");
  meta.appendChild(h("div", "hb-mus2-trt", opts.title || t.title || t.query || "—"));
  if(!opts.hideArtist){
    const sub = [t.artist, (t.count ? `· ${t.count} veces` : "")].filter(Boolean).join(" ");
    if(sub) meta.appendChild(h("div", "hb-mus2-tra", sub));
  } else if(t.count){
    meta.appendChild(h("div", "hb-mus2-tra", `${t.count} veces`));
  }
  row.appendChild(meta);
  row.onclick = () => {
    const list = row.parentElement;
    if(list) list.querySelectorAll(".hb-mus2-tr.selected").forEach(r => r.classList.remove("selected"));
    row.classList.add("selected");
  };
  row.ondblclick = () => ctx.action("play", {query: t.query || [t.title, t.artist].filter(Boolean).join(" ") || t.title});
  if(opts.remove){
    const x = h("button", "hb-mus2-x", "✕"); x.title = "Quitar de la lista";
    x.onclick = (e) => { e.stopPropagation(); ctx.action("remove_from_playlist", {playlist: opts.remove, item: t.title}); };
    x.ondblclick = (e) => e.stopPropagation();
    row.appendChild(x);
  }
  return row;
}

// HOME: lists + top tracks + recent.
function homeView(host, data, ctx){
  const wrap = h("div", "hb-mus2");
  const scroll = h("div", "hb-mus2-scroll");
  const np = nowPlaying(data);

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

  // Lists: covers + "New list" card.
  const secL = h("div", "hb-mus2-sec");
  secL.appendChild(h("div", "hb-mus2-sech", "Tus listas"));
  const lists = h("div", "hb-mus2-lists");
  (data.playlists || []).forEach(pl => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(artNode(pl.art, "🎶"));
    c.appendChild(h("div", "hb-mus2-plname", pl.name || "Lista"));
    const n = (pl.tracks || []).length;
    c.appendChild(h("div", "hb-mus2-plsub", `${n} ${n === 1 ? "canción" : "canciones"}`));
    c.onclick = () => ctx.action("open_view", {kind: "playlist", id: pl.id});
    lists.appendChild(c);
  });
  lists.appendChild(newListCard(lists, ctx));
  secL.appendChild(lists);
  scroll.appendChild(secL);

  // Top tracks.
  if((data.top || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", "Más escuchadas"));
    const g = h("div", "hb-mus2-grid");
    data.top.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), playing: nowPlayingMatches(t, np)})));
    s.appendChild(g); scroll.appendChild(s);
  }

  // Recent.
  if((data.recent || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", "Recientes"));
    const g = h("div", "hb-mus2-grid");
    data.recent.slice(0, 8).forEach(t => g.appendChild(trackRow(t, ctx, {playing: nowPlayingMatches(t, np)})));
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
    // Inline: an input replaces the create gesture; Enter/blur -> create_playlist, then SSE re-renders the list.
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

// PLAYLIST: cover (with the play button INSIDE it) + tracklist.
function playlistView(host, data, ctx, pl){
  const wrap = h("div", "hb-mus2");
  const scroll = h("div", "hb-mus2-scroll");

  const back = h("button", "hb-mus2-back", "‹ Volver");
  back.onclick = () => ctx.action("back");
  scroll.appendChild(back);

  const tracks = pl.tracks || [];
  const n = tracks.length;
  const derived = deriveArtistInfo(tracks);

  const head = h("div", "hb-mus2-head");
  const artwrap = h("div", "hb-mus2-artwrap");
  artwrap.appendChild(artNode(pl.art, "🎶"));
  const play = h("button", "hb-mus2-playfab", "▶");
  play.title = "Reproducir esta lista";
  if(!n) play.disabled = true;
  play.onclick = () => ctx.action("play_playlist", {playlist: pl.id});
  artwrap.appendChild(play);
  head.appendChild(artwrap);

  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", "Lista"));
  hm.appendChild(h("div", "hb-mus2-headn", pl.name || "Lista"));
  const subParts = [];
  if(derived.commonArtist) subParts.push(derived.commonArtist);
  subParts.push(`${n} ${n === 1 ? "canción" : "canciones"}`);
  hm.appendChild(h("div", "hb-mus2-plsub", subParts.join(" · ")));
  head.appendChild(hm);
  scroll.appendChild(head);

  const g = h("div", "hb-mus2-grid");
  const np = nowPlaying(data);
  if(n){
    tracks.forEach((t, i) => g.appendChild(trackRow(t, ctx, {
      index: String(i + 1),
      remove: pl.id,
      title: derived.commonArtist ? derived.strip(t.title) : null,
      hideArtist: !!derived.commonArtist,
      playing: nowPlayingMatches(t, np),
    })));
  } else {
    g.appendChild(h("div", "hb-mus2-empty", "Lista vacía. Dime «añade una canción a esta lista»."));
  }
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

// musica: face of the music connector (V2-041) with Spotify-style aesthetics (V2-058, Phase 1) + a PRO redesign
// (V2-XXX): clearer header/content separation, a floating play button ON the cover art, a per-row "now playing"
// indicator (animated bars, everywhere a track can appear — playlist, top, recent AND the bottom bar), a
// playlist header that shows a shared artist ONCE instead of repeating it in every row, and click=select /
// double-click=play on every track row. Contract:
// render(el, data, ctx).
// data = GET /widgets/musica/data -> {mode:"spotify"|"youtube"|"idle", connected, can_connect, own_client_id_set,
//   default_available, redirect_uri, now_playing (spotify)|null, yt:{videoId,title,artist,paused,muted,volume,
//   cmd_seq,art}, playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track],
//   top:[track+count], fav_current:bool, view:{kind:"home|playlist|...",id}}.
//   ctx.action(name,payload) -> POST /widgets/musica/action (JSON).
//
// Views: HOME (lists + top tracks + recent) and PLAYLIST (cover + tracklist). State `view` controls what is
// rendered; play_playlist / open_view / back change it through FlashBrain data-ops or clicks. Playback bar at the
// bottom (Spotify/YouTube). PLAYBACK = the connector (ctx.action -> connectors.music.control); do not reinvent the
// backend here.
//
// The hidden YouTube-audio player is reused between re-renders (persistent `_ytHost`): rebuilding the view never
// reloads the iframe, which would restart the song. It is recreated only when videoId changes; if cmd_seq changes,
// the pause/volume command is applied by postMessage. Spotify connection remains intact.
//
// COVER ART (V2-629), fast first then enhancements — never the other way round:
//  1. FREE and INSTANT: a track played through YouTube-audio already carries `art` (the video's own thumbnail,
//     set server-side the moment its videoId resolves — connectors/music/youtube_audio.py — at ZERO extra cost:
//     no fetch of ours, just a templated CDN URL the <img> tag loads on its own). Spotify tracks already carry
//     real album art from Spotify's own API. Neither ever delays "sonar rápido".
//  2. SLOW and CACHED: a track this widget never actually played (typed into a list, or a legacy row) has no
//     art. `maybeEnrich()` below asks the server for it AFTER paint, once per song per page life (`_enrichAsked`),
//     never on the play path — the server caches the answer (hit or miss) so the SAME song is never looked up
//     twice, on this machine or the next request (widgets/musica/data.py::_enrich_art).
//
// ICONS are inline SVG in the SAME visual language as the app shell (frontend/app/lib/icons.js): viewBox
// 0 0 24 24, stroke=currentColor, stroke-width 2, round caps/joins — duplicated locally because widget.js
// cannot import from frontend/app (same isolation rule V2-557 already applied to `_norm` below).

function injectStyles(){
  if(document.getElementById("hb-mus2-css")) return;
  const s = document.createElement("style"); s.id = "hb-mus2-css"; s.textContent = `
  .hb-mus2-root{position:relative}
  .hb-mus2{--sp-green:#1DB954;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           width:100%;box-sizing:border-box;background:var(--hb-bg,#fff);border:1px solid var(--hb-line,#eef1f6);
           border-radius:16px;overflow:hidden;color:var(--hb-ink,#0d1622);display:flex;flex-direction:column}
  .hb-mus2-scroll{padding:16px;display:flex;flex-direction:column;gap:18px;max-height:60vh;overflow:auto}
  .hb-mus2 svg{display:block}
  .hb-mus2-art svg{width:38%;height:38%;color:rgba(255,255,255,.92)}
  .hb-mus2-new .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}
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
  .hb-mus2-pl .hb-mus2-art{width:112px;height:112px}
  .hb-mus2-pl:hover .hb-mus2-art{transform:translateY(-2px);box-shadow:0 12px 24px rgba(0,0,0,.24)}
  .hb-mus2-plname{font-size:12.5px;font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-plsub{font-size:11px;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-new .hb-mus2-art{background:var(--hb-bg-soft,#fbfdff);border:1.5px dashed var(--hb-line,#eef1f6);
                            color:var(--hb-muted,#5b6b82);box-shadow:none}
  .hb-mus2-grid{display:flex;flex-direction:column;gap:1px}
  .hb-mus2-tr{display:flex;align-items:center;gap:11px;padding:7px 8px;border-radius:9px;cursor:pointer;
              user-select:none}
  .hb-mus2-tr:hover{background:var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-tr.selected{background:var(--hb-bg-soft,#fbfdff);box-shadow:inset 0 0 0 1px var(--hb-line,#eef1f6)}
  .hb-mus2-tr.playing{background:rgba(29,185,84,.10)}
  .hb-mus2-tr.playing.selected{background:rgba(29,185,84,.16)}
  .hb-mus2-tr.playing .hb-mus2-trt{color:var(--sp-green)}
  .hb-mus2-tr .hb-mus2-art{width:40px;height:40px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-trn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-family:ui-monospace,Menlo,monospace;
               min-width:16px;text-align:center;display:flex;align-items:center;justify-content:center}
  .hb-mus2-trmeta{min-width:0;flex:1}
  .hb-mus2-trt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-tra{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-x{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;
             padding:5px;border-radius:7px;line-height:1;flex:0 0 auto;display:flex}
  .hb-mus2-x svg{width:14px;height:14px}
  .hb-mus2-x:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-empty{font-size:12px;color:var(--hb-muted-2,#9aa7b8);padding:1px 2px}
  .hb-mus2-back{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:13px;font-weight:600;cursor:pointer;
                display:flex;align-items:center;gap:4px;padding:0;align-self:flex-start}
  .hb-mus2-back svg{width:15px;height:15px}
  .hb-mus2-back:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-head{display:flex;gap:15px;align-items:flex-end}
  .hb-mus2-artwrap{position:relative;flex:0 0 auto}
  .hb-mus2-head .hb-mus2-art{width:100px;height:100px;box-shadow:0 8px 20px rgba(0,0,0,.2);flex:0 0 auto}
  .hb-mus2-headmeta{display:flex;flex-direction:column;gap:7px;min-width:0}
  .hb-mus2-headk{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--hb-muted-2,#9aa7b8);
                 font-family:ui-monospace,Menlo,monospace}
  .hb-mus2-headn{font-size:22px;font-weight:800;line-height:1.08;letter-spacing:-.02em;word-break:break-word}
  .hb-mus2-playfab{position:absolute;right:8px;bottom:8px;width:46px;height:46px;border-radius:50%;
                   background:var(--sp-green);color:#fff;border:0;cursor:pointer;
                   display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(0,0,0,.35);
                   transition:transform .15s}
  .hb-mus2-playfab svg{width:19px;height:19px}
  .hb-mus2-playfab:hover{transform:scale(1.07)}
  .hb-mus2-playfab:disabled{opacity:.4;cursor:default;box-shadow:none;transform:none}
  .hb-mus2-bar{border-top:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
               padding:10px 13px;display:flex;align-items:center;gap:11px}
  .hb-mus2-barartwrap{position:relative;flex:0 0 auto}
  .hb-mus2-bar .hb-mus2-art{width:46px;height:46px;box-shadow:none;flex:0 0 auto}
  .hb-mus2-areq{position:absolute;right:-3px;bottom:-3px;width:19px;height:19px;border-radius:50%;
                background:var(--hb-ink,#0d1622);display:flex;align-items:center;justify-content:center;
                box-shadow:0 0 0 2px var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-areq .hb-mus2-eq{width:10px;height:9px}
  .hb-mus2-areq .hb-mus2-eq span{width:2px}
  .hb-mus2-barmeta{min-width:0;flex:1}
  .hb-mus2-bart{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bara{font-size:11.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-barc{display:flex;align-items:center;gap:5px}
  .hb-mus2-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);cursor:pointer;padding:7px;
                border-radius:8px;line-height:1;display:flex}
  .hb-mus2-cbtn svg{width:17px;height:17px}
  .hb-mus2-cbtn:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-cbtn.fav{color:var(--sp-green)}
  .hb-mus2-cbtn.fav:hover{color:var(--sp-green);opacity:.8}
  .hb-mus2-cbtn.main{width:36px;height:36px;border-radius:50%;background:var(--hb-ink,#0d1622);
                     color:var(--hb-bg,#fff);align-items:center;justify-content:center;padding:0}
  .hb-mus2-cbtn.main svg{width:15px;height:15px}
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

// ── icon set, "our line" (V2-629) ────────────────────────────────────────────────────────────────────────
// Two attribute sets, never combined on one <svg> — the HTML parser keeps the FIRST occurrence of a
// duplicate attribute and silently drops the rest, so a tag carrying both `fill="none"` (from an outline
// base) and a later `fill="currentColor"` override stays "none" forever: a solid icon that quietly rendered
// as a hairline outline, caught only by a render test asserting the resolved attribute, not by reading.
const _SW = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
           'stroke-linejoin="round"';                                            // OUTLINE icons
const _SF = 'viewBox="0 0 24 24" fill="currentColor" stroke="none"';              // SOLID icons
const ICON_NOTE      = `<svg ${_SW}><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
const ICON_PLUS       = `<svg ${_SW}><path d="M12 5v14"/><path d="M5 12h14"/></svg>`;
const ICON_BACK       = `<svg ${_SW}><path d="m15 18-6-6 6-6"/></svg>`;
const ICON_CLOSE      = `<svg ${_SW}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;
const ICON_PREV       = `<svg ${_SW}><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>`;
const ICON_NEXT       = `<svg ${_SW}><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`;
const ICON_PLAY       = `<svg ${_SF}><path d="M8 5v14l11-7z"/></svg>`;
const ICON_PAUSE      = `<svg ${_SF}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
const ICON_VOL_DOWN   = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/></svg>`;
const ICON_VOL_UP     = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const ICON_HEART      = `<svg ${_SW}><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;
const ICON_HEART_FILL = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" ` +
  `stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 ` +
  `0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;

// Raw SVG markup -> element (same trick as frontend/app/core/dom.js::raw — duplicated, widgets never import
// app-shell code).
function svgEl(markup){
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
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
  const paintFallback = () => { a.textContent = ""; a.appendChild(svgEl(fallback || ICON_NOTE)); };
  if(art){
    const img = document.createElement("img"); img.src = art; img.alt = "";
    // A dead or since-removed thumbnail (V2-629) degrades to the SAME placeholder a missing one gets,
    // instead of the browser's broken-image glyph — cheap, and it is what "a player nicer than the rest"
    // means for the one part of this that is a hotlink to somebody else's server (the V2-563 fact of life).
    img.onerror = paintFallback;
    a.appendChild(img);
  }
  // A crisp SVG placeholder instead of an emoji glyph (V2-629): an emoji font renders differently per OS —
  // the exact "looks like a different app" seam a redesign is supposed to close — an inline vector does not.
  else paintFallback();
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

// V2-638 — a track that is a FILE we hold plays HERE, in the page, through a plain <audio> against our own
// library route. It shares `_ytHost` with the hidden YouTube iframe because only one of the two can ever be
// mounted (the server clears the yt block when a local track starts), and the same memo guards (`_hbSeq`)
// keep a re-render from restarting the song — the reason the seq exists at all is that asking for the SAME
// file twice must still be two events.
function syncLocalPlayer(el, data, ctx){
  const loc = data.local || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  if(!loc.src){
    if(el._hbAudio){ host.textContent = ""; el._hbAudio = null; el._hbLocal = null; el._hbLocSeq = null; }
    return false;
  }
  if(el._hbLocal === loc.src && el._hbAudio){        // same file -> only apply the new command
    if(el._hbLocSeq !== loc.seq){
      el._hbLocSeq = loc.seq;
      if(loc.paused || stopped) el._hbAudio.pause();
      else { try{ el._hbAudio.currentTime = 0; }catch(_){} const q = el._hbAudio.play(); if(q && q.catch) q.catch(function(){}); }
    }
    return true;
  }
  host.textContent = "";
  el._hbFrame = null; el._hbVid = null; el._hbSeq = null;   // the iframe, if any, is gone with the innerHTML
  const a = document.createElement("audio");
  a.className = "hb-mus2-audio-el";
  a.preload = "metadata";
  // Our own library route only — never an arbitrary origin (the V2-620 boundary).
  if(String(loc.src).startsWith("/api/library/")) a.src = loc.src;
  if(!(loc.paused || stopped)){ const q = a.play(); if(q && q.catch) q.catch(function(){}); }
  a.addEventListener("ended", function(){ try{ ctx.action("ended"); }catch(_){} });
  host.appendChild(a);
  el._hbAudio = a; el._hbLocal = loc.src; el._hbLocSeq = loc.seq;
  return true;
}

function syncYtPlayer(el, data, ctx){
  const yt = data.yt || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  // A local file and a YouTube track can never sound at once: if one is mounted the other releases.
  if(syncLocalPlayer(el, data, ctx)) return;
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
  // yt.art/yt.artist (V2-629): the connector already resolves free cover art the instant it knows a videoId,
  // and the server splits an "Artist - Title" upload title for display — both arrive ready on `data.yt`.
  if(yt.videoId) return {title: yt.title || "Música", artist: yt.artist || "", art: yt.art || "", playing: !yt.paused};
  return null;
}

// Lazy cover-art ENRICHMENT (V2-629): asked once per (title, artist) per page life, always AFTER the row/bar
// is already on screen with its fallback icon — never on anything that would delay playback starting.
const _enrichAsked = new Set();
function maybeEnrich(t, ctx){
  if(!t || t.art) return;
  const title = (t.title || t.query || "").trim();
  if(!title) return;
  const key = _norm(title) + "|" + _norm(t.artist || "");
  if(_enrichAsked.has(key)) return;
  _enrichAsked.add(key);
  // Defensive against ANY ctx implementation, not just the desktop host's own Promise-returning one — the
  // same caution `ended` already takes two lines below (`try{ ctx.action("ended"); }catch(_){}`), extended to
  // also tolerate a return value that is not thenable at all.
  try {
    const p = ctx.action("enrich_art", {title, artist: t.artist || ""});
    if (p && typeof p.catch === "function") p.catch(() => {});
  } catch (_) {}
}

function playbackBar(data, ctx){
  const bar = h("div", "hb-mus2-bar");
  const np = nowPlaying(data);
  const playing = !!(np && np.playing);
  if(np) maybeEnrich(np, ctx);
  const artWrap = h("div", "hb-mus2-barartwrap");
  artWrap.appendChild(artNode(np && np.art, ICON_NOTE));
  if(playing){ const badge = h("div", "hb-mus2-areq"); badge.appendChild(eqIcon()); artWrap.appendChild(badge); }
  bar.appendChild(artWrap);
  const meta = h("div", "hb-mus2-barmeta");
  meta.appendChild(h("div", "hb-mus2-bart", np ? (np.title || "Música") : "Nada sonando"));
  meta.appendChild(h("div", "hb-mus2-bara", np ? (np.artist || (np.device ? np.device : "")) : "Dime «pon música» o abre una lista."));
  bar.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mkIcon = (svg, action, cls) => {                    // control = fire-and-forget; SSE re-renders
    const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(svg));
    b.onclick = () => ctx.action(action);
    return b;
  };
  ctrls.appendChild(mkIcon(ICON_PREV, "previous"));
  ctrls.appendChild(mkIcon(playing ? ICON_PAUSE : ICON_PLAY, playing ? "pause" : "resume", "main"));
  ctrls.appendChild(mkIcon(ICON_NEXT, "next"));
  ctrls.appendChild(mkIcon(ICON_VOL_DOWN, "volume_down"));
  ctrls.appendChild(mkIcon(ICON_VOL_UP, "volume_up"));
  if(np){
    // The heart is a STATE indicator, not only a button (V2-629): filled when the operator already saved this
    // song, so tapping it again (harmless — favorite_current dedupes) never contradicts what is on screen.
    const fav = !!data.fav_current;
    const heart = mkIcon(fav ? ICON_HEART_FILL : ICON_HEART, "favorite_current", fav ? "fav" : "");
    heart.title = fav ? "Ya está en Favoritos" : "Guardar en Favoritos";
    ctrls.appendChild(heart);
  }
  bar.appendChild(ctrls);
  return bar;
}

// Track rows (recent / top tracks / playlist tracklist). Click SELECTS (a purely visual, ephemeral highlight —
// nothing persisted, nothing sent to the server); double-click PLAYS, like a desktop Spotify tracklist. The
// "now playing" state, by contrast, IS driven by data (`opts.playing`) and survives a re-render.
function trackRow(t, ctx, opts){
  opts = opts || {};
  maybeEnrich(t, ctx);
  const row = h("div", "hb-mus2-tr" + (opts.playing ? " playing" : ""));
  if(opts.index != null || opts.playing){
    const cell = h("div", "hb-mus2-trn");
    if(opts.playing) cell.appendChild(eqIcon());
    else cell.textContent = opts.index;
    row.appendChild(cell);
  }
  row.appendChild(artNode(t.art, ICON_NOTE));
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
    const x = h("button", "hb-mus2-x"); x.appendChild(svgEl(ICON_CLOSE)); x.title = "Quitar de la lista";
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
    c.appendChild(artNode(pl.art, ICON_NOTE));
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
  card.appendChild(artNode(null, ICON_PLUS));
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

  const back = h("button", "hb-mus2-back"); back.appendChild(svgEl(ICON_BACK)); back.appendChild(h("span", null, "Volver"));
  back.onclick = () => ctx.action("back");
  scroll.appendChild(back);

  const tracks = pl.tracks || [];
  const n = tracks.length;
  const derived = deriveArtistInfo(tracks);

  const head = h("div", "hb-mus2-head");
  const artwrap = h("div", "hb-mus2-artwrap");
  artwrap.appendChild(artNode(pl.art, ICON_NOTE));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
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

// musica: face of the music connector (V2-041) with Spotify-style aesthetics (V2-058, Phase 1), a PRO pass
// (V2-629/V2-678) and the V2-717 redesign: the widget is ONE box (the canvas window IS the frame — no card of
// our own drawn inside it), the bar above the content is the ONE bar the house standard allows, and the song
// that is sounding OCCUPIES the card instead of hiding in a strip at the foot. Contract:
// render(el, data, ctx).
// data = GET /widgets/musica/data -> {mode:"spotify"|"youtube"|"local"|"idle", connected, can_connect,
//   own_client_id_set, default_available, redirect_uri, now_playing (spotify, with progress_ms/duration_ms)|null,
//   yt:{videoId,title,artist,paused,muted,volume,cmd_seq,art,seek:{n,to,by}},
//   local:{src,title,artist,art,paused,seq,seek:{n,to,by}},
//   playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track],
//   top:[track+count], fav_current:bool, view:{kind:"home|now|library|playlist|connect",id}}.
//   ctx.action(name,payload) -> POST /widgets/musica/action (JSON).
//
// FOUR faces, one of them adaptive (drawView): `home` is the song when something sounds and the library when
// nothing does; `now` and `library` are the same two pinned by a click or a sentence; `playlist` is a cover
// plus its tracklist; `connect` is the sources screen. PLAYBACK = the connector (ctx.action ->
// connectors.music.control); do not reinvent the backend here.
//
// THE PLAYHEAD (V2-717) belongs to whoever is making the sound, and that is why there is no position in the
// store. A local file and the hidden YouTube iframe play in THIS page and hold their own clock, so the card
// reads them directly and a drag seeks them with no server in the loop at all; Spotify plays on a device
// somewhere else, so its `progress_ms` is a photograph the card advances locally and a drag is a round trip.
// A seek asked by VOICE travels the other way — a numbered command left in the store (`seek:{n,to,by}`) that
// `applyPendingSeek` applies here, because the server has never had a playhead to move.
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
  /* V2-678 — a real player has THREE bands that never trade places: a header band, a scrolling middle,
     and a footer transport bar that is visually LIFTED off the content above it (Spotify/Amazon Music's
     own shape) instead of reading as a stray line drawn across an otherwise flat, empty rectangle. The
     mechanism is the same one already proven on the youtube widget's player tab: the widget's own root
     fills the card (height:100%) and switches OFF the card's outer scroll (the :has() rule below), so an
     internal region owns the overflow instead of the whole card growing past its frame. */
  .hb-scroll:has(> .hb-mus2-root){overflow:hidden}
  .hb-mus2-root{position:relative;height:100%;display:flex;flex-direction:column;overflow:hidden}
  /* el._viewHost — a plain, otherwise unclassed div between root and the visible card (kept unrebuilt across
     re-renders so the hidden YouTube/local-audio player never restarts, see render()) — needs its OWN place
     in the height chain: with no rule of its own it defaults to auto height, and a percentage height on ITS
     child (.hb-mus2) resolves against "auto" as though no height were set at all, which is exactly how the
     three-zone pin silently no-opped the first time this was built. */
  .hb-mus2-viewhost{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
  /* V2-717 — ONE box. The canvas already draws a window around every widget: a border, a radius and a
     background of OUR OWN inside it were a second box drawn on top of the first — «has puesto un contenedor
     exterior con el titulo y los botones, y dentro has metido otra caja como si eso fuera el widget». What
     separates the three bands now is TONE and a hairline, never a frame: the widget IS the window. */
  .hb-mus2{--sp-green:#1DB954;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
           width:100%;height:100%;min-height:0;box-sizing:border-box;background:transparent;overflow:hidden;
           color:var(--hb-ink,#0d1622);display:flex;flex-direction:column}
  /* THE ONE BAR (the window chrome is the other — the house standard, amended by V2-715). It is a ROW now,
     not a stacked header: no brand disc, no «Tu musica» under a window that already says «Musica». */
  .hb-mus2-headfix{flex:0 0 auto;background:var(--hb-bg-soft,rgba(127,127,127,.05));
                   border-bottom:1px solid var(--hb-line,#eef1f6);padding:5px 12px;min-height:32px;
                   display:flex;align-items:center;gap:10px}
  .hb-mus2-scroll{flex:1 1 auto;min-height:0;overflow:auto;padding:16px 18px;display:flex;flex-direction:column;gap:18px}
  /* A screen with ONE thing on it centres that thing instead of pinning it to the top-left corner of a big
     empty card, which is what «se ve tan vacia» was describing. */
  .hb-mus2-scroll.mid{justify-content:center;align-items:center}
  .hb-mus2 svg{display:block}
  .hb-mus2-art svg{width:38%;height:38%;color:rgba(255,255,255,.92)}
  .hb-mus2-new .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}
  .hb-mus2-top{display:flex;align-items:center;gap:9px}
  .hb-mus2-top b{font-size:18.5px;font-weight:800;letter-spacing:-.015em}
  .hb-mus2-prov{margin-left:auto;font-size:11px;color:var(--hb-muted,#5b6b82);border:1px solid var(--hb-line,#eef1f6);
                border-radius:999px;padding:3px 9px;display:flex;align-items:center;gap:5px;flex:0 0 auto;
                background:var(--hb-bg,#fff);cursor:pointer;font-family:inherit;line-height:1.5}
  .hb-mus2-prov:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-ink,#0d1622)}
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
  /* The transport bar is LIFTED off the content above it — its own background tone, a top divider PLUS a
     soft upward shadow (the exact cue Spotify/Amazon Music use so the player never reads as "a stray line
     drawn across a flat rectangle") — and never trades place with the header/scroll (flex:0 0 auto, always
     the last child of the fixed-height root). */
  .hb-mus2-bar{flex:0 0 auto;border-top:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,rgba(127,127,127,.06));
               box-shadow:0 -10px 24px -18px rgba(0,0,0,.55);padding:13px 18px;display:flex;align-items:center;gap:13px}
  .hb-mus2-barartwrap{position:relative;flex:0 0 auto}
  .hb-mus2-bar .hb-mus2-art{width:52px;height:52px;box-shadow:0 3px 10px rgba(0,0,0,.18);flex:0 0 auto}
  .hb-mus2-bar.empty .hb-mus2-art{background:var(--hb-bg,#fff);border:1.5px dashed var(--hb-line,#eef1f6);
                                  box-shadow:none;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-areq{position:absolute;right:-3px;bottom:-3px;width:19px;height:19px;border-radius:50%;
                background:var(--hb-ink,#0d1622);display:flex;align-items:center;justify-content:center;
                box-shadow:0 0 0 2px var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-areq .hb-mus2-eq{width:10px;height:9px}
  .hb-mus2-areq .hb-mus2-eq span{width:2px}
  .hb-mus2-barmeta{min-width:0;flex:1}
  /* Track title bumped 13px -> 15px per the operator's ask ("un pixel o dos más grande para que se vea
     bien") — it is the single most-read line in the whole card. */
  .hb-mus2-bart{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bara{font-size:12.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-baridle{font-size:13px;font-weight:600;color:var(--hb-muted,#5b6b82);font-style:italic}
  .hb-mus2-barc{display:flex;align-items:center;gap:6px}
  .hb-mus2-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);cursor:pointer;padding:8px;
                border-radius:8px;line-height:1;display:flex}
  .hb-mus2-cbtn svg{width:18px;height:18px}
  .hb-mus2-cbtn:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-cbtn.fav{color:var(--sp-green)}
  .hb-mus2-cbtn.fav:hover{color:var(--sp-green);opacity:.8}
  .hb-mus2-cbtn.main{width:40px;height:40px;border-radius:50%;background:var(--hb-ink,#0d1622);
                     color:var(--hb-bg,#fff);align-items:center;justify-content:center;padding:0;
                     box-shadow:0 4px 12px rgba(0,0,0,.28)}
  .hb-mus2-cbtn.main svg{width:16px;height:16px}
  .hb-mus2-cbtn.main:hover{color:var(--hb-bg,#fff);opacity:.85}
  .hb-mus2-cbtn:disabled{opacity:.32;cursor:default;pointer-events:none}
  .hb-mus2-connect{display:flex;flex-direction:column;gap:8px}
  .hb-mus2-sub{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-btn{border:0;background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-radius:10px;padding:9px 13px;
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

  /* ── V2-717 · the bar's two derived controls ───────────────────────────────────────────────────────────
     A switch with one side is not a switch: «Sonando» is only drawn while something actually sounds, the
     same rule the contacts rail follows (a section with nothing in it is not drawn). */
  .hb-mus2-seg{display:flex;gap:2px;border:1px solid var(--hb-line,#eef1f6);border-radius:999px;padding:2px;
               background:var(--hb-bg,#fff);flex:0 0 auto}
  .hb-mus2-segb{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:12px;font-weight:700;
                padding:4px 11px;border-radius:999px;cursor:pointer;display:flex;align-items:center;gap:5px;
                line-height:1;font-family:inherit}
  .hb-mus2-segb svg{width:13px;height:13px}
  .hb-mus2-segb:hover{color:var(--hb-ink,#0d1622)}
  .hb-mus2-segb.on{background:var(--hb-bg-soft,rgba(127,127,127,.10));color:var(--hb-ink,#0d1622);
                   box-shadow:inset 0 0 0 1px var(--hb-line,#eef1f6)}

  /* ── V2-717 · AHORA SUENA — the song IS the screen ─────────────────────────────────────────────────────
     «la imagen de la musica mas grande, el nombre de la cancion, el nombre del artista, la duracion, una
     barra de progreso para que yo la pueda mover... y sin nada mas». The transport stays where it was, at
     the foot: he asked for the duplication out loud («la cancion igualmente la manejo abajo»). */
  /* The hero FILLS the middle band and centres itself in it, so the cover can be sized against the height
     that is actually there: a square capped at half the band still fits the whole ficha — cover, title,
     artist, facts and scrubber — inside the card's own first footprint (468x540) with nothing to scroll.
     Sizing it by WIDTH alone put a scrollbar on the one screen that is supposed to be «sin nada más». */
  .hb-mus2-now{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
               width:100%;max-width:520px;height:100%;margin:0 auto;box-sizing:border-box}
  .hb-mus2-nowart{position:relative;height:min(68%,320px);width:auto;max-width:72%;aspect-ratio:1/1;
                  border-radius:18px;overflow:hidden;
                  flex:0 1 auto;display:flex;align-items:center;justify-content:center;
                  background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                  box-shadow:0 26px 48px -20px rgba(0,0,0,.62),0 2px 8px rgba(0,0,0,.18)}
  .hb-mus2-nowart img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-nowart svg{width:34%;height:34%;color:rgba(255,255,255,.92)}
  .hb-mus2-nowt{font-size:20px;font-weight:800;letter-spacing:-.02em;line-height:1.22;
                margin-top:clamp(10px,4%,20px);flex:0 0 auto;
                display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
                word-break:break-word}
  .hb-mus2-nowa{font-size:14px;color:var(--hb-muted,#5b6b82);margin-top:6px;white-space:nowrap;overflow:hidden;
                text-overflow:ellipsis;max-width:100%}
  .hb-mus2-nowm{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:11px;font-size:10.5px;
                letter-spacing:.1em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8);
                font-family:ui-monospace,Menlo,monospace}
  .hb-mus2-nowm .hb-mus2-eq{width:11px;height:10px}
  .hb-mus2-nowm i{font-style:normal;opacity:.45}

  /* The scrubber. It is drawn ONLY when the player can actually answer «where are we and how long is it» —
     a bar that cannot be moved, or one that would sit at zero forever, is worse than no bar (the operator's
     own rule for this batch: what is not finished must look disabled, be absent, or be clear). */
  /* The slot the scrubber lands in when the player finally answers. It needs its own width: in a centred
     flex column a bare div shrinks to its content, and a rail asking for 100% OF NOTHING is a rail 0 pixels
     wide — present, correct-looking in the DOM, and impossible to drag. Measured, not reasoned. */
  .hb-mus2-seekslot{width:100%;flex:0 0 auto}
  .hb-mus2-seek{width:100%;margin-top:clamp(12px,4%,22px);display:flex;align-items:center;gap:10px}
  .hb-mus2-time{font-size:11px;font-family:ui-monospace,Menlo,monospace;color:var(--hb-muted-2,#9aa7b8);
                min-width:40px;flex:0 0 auto;font-variant-numeric:tabular-nums}
  .hb-mus2-time.r{text-align:right}
  .hb-mus2-rail{position:relative;flex:1 1 auto;height:18px;display:flex;align-items:center;cursor:pointer;
                touch-action:none}
  .hb-mus2-railbg{position:absolute;left:0;right:0;height:4px;border-radius:999px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-fill{position:absolute;left:0;height:4px;border-radius:999px;background:var(--hb-ink,#0d1622);
                max-width:100%;transition:background .15s}
  .hb-mus2-knob{position:absolute;width:11px;height:11px;border-radius:50%;background:var(--hb-ink,#0d1622);
                box-shadow:0 1px 5px rgba(0,0,0,.45);transform:translateX(-50%);opacity:0;transition:opacity .12s}
  .hb-mus2-rail:hover .hb-mus2-fill,.hb-mus2-rail.hb-mus2-drag .hb-mus2-fill{background:var(--sp-green)}
  .hb-mus2-rail:hover .hb-mus2-knob,.hb-mus2-rail.hb-mus2-drag .hb-mus2-knob{opacity:1;background:var(--sp-green)}

  /* ── V2-717 · an empty screen still has something to say ───────────────────────────────────────────────
     «se ve tan vacia... estas un poco triste». The chips are REAL: each one plays. */
  .hb-mus2-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:13px;margin:auto;
                padding:14px 0;max-width:340px}
  .hb-mus2-herod{position:relative;width:76px;height:76px;border-radius:50%;flex:0 0 auto;
                 display:flex;align-items:center;justify-content:center;
                 background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                 box-shadow:0 14px 30px -12px rgba(0,0,0,.55)}
  .hb-mus2-herod svg{width:31px;height:31px;color:#fff}
  .hb-mus2-herod::after{content:"";position:absolute;inset:-9px;border-radius:50%;
                        border:1.5px solid var(--hb-accent,#3D6FE0);opacity:.3;animation:hbMusRing 3.2s ease-out infinite}
  @keyframes hbMusRing{0%{transform:scale(.92);opacity:.34}70%{transform:scale(1.12);opacity:0}100%{opacity:0}}
  .hb-mus2-herot{font-size:16.5px;font-weight:800;letter-spacing:-.015em}
  .hb-mus2-heros{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.5}
  .hb-mus2-chips{display:flex;flex-wrap:wrap;gap:7px;justify-content:center}
  .hb-mus2-chip{border:1px solid var(--hb-line,#eef1f6);background:var(--hb-bg-soft,#fbfdff);
                color:var(--hb-ink,#0d1622);border-radius:999px;padding:6px 12px;font-size:12px;font-weight:600;
                cursor:pointer;font-family:inherit;line-height:1.2}
  .hb-mus2-chip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
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
const ICON_LIST       = `<svg ${_SW}><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`;
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
//
// V2-717 — the SAME handshake already delivers the clock. Once `listening` is sent the embed posts
// `infoDelivery` frames carrying `currentTime` and `duration`; nothing extra is asked of it and no network
// call of ours is involved. Kept as a stamped sample (`at`) rather than a running counter so the bar can
// interpolate between frames instead of stepping, and thrown away whenever the video changes — a position
// belonging to the PREVIOUS song, painted for a quarter of a second on the new one, is a lie the eye catches.
let _ytReady = null, _ytEnded = null;
let _ytClock = {vid: "", t: 0, d: 0, at: 0};
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
    else if (d.event === "infoDelivery" && d.info && typeof d.info === "object"){
      const info = d.info;
      if (typeof info.currentTime === "number"){ _ytClock.t = info.currentTime; _ytClock.at = Date.now(); }
      if (typeof info.duration === "number" && info.duration > 0) _ytClock.d = info.duration;
    }
  });
}

// A seek asked by VOICE («adelanta un minuto», «ponla en el minuto dos») arrives as a COMMAND in the store —
// `{n, to, by}` — never as a position, because the position only exists HERE: the hidden iframe and the
// <audio> element live in this page and the server has never held a clock for them. `n` is a counter of its
// own and deliberately NOT `cmd_seq`: riding on cmd_seq would re-apply the last seek on every later pause or
// volume command, which is a song that jumps backwards every time you touch the volume.
function applyPendingSeek(el, blk, getPos, seekTo){
  const sk = blk && blk.seek;
  const n = sk ? Number(sk.n || 0) : 0;
  if(!n || el._hbSeekN === n) return;
  el._hbSeekN = n;
  const abs = (sk.to !== undefined && sk.to !== null && sk.to !== "");
  const to = abs ? Number(sk.to) : Number(getPos() || 0) + Number(sk.by || 0);
  if(isFinite(to)) seekTo(Math.max(0, to));
}

// Where the YouTube song IS, interpolated from the last sample the embed sent (see `_ytClock`). Returns null
// while the clock says nothing — a player that has not answered yet must draw NO scrubber rather than a bar
// pinned at zero that looks broken.
function ytPosition(vid, playing){
  if(!vid || _ytClock.vid !== vid || !_ytClock.at) return null;
  const drift = playing ? (Date.now() - _ytClock.at) / 1000 : 0;
  const dur = _ytClock.d || 0;
  const pos = Math.max(0, _ytClock.t + drift);
  return {pos: dur ? Math.min(pos, dur) : pos, dur};
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
    applyPendingSeek(el, loc, () => el._hbAudio.currentTime,
                     (secs) => { try{ el._hbAudio.currentTime = secs; }catch(_){} });
    if(el._hbLocSeq !== loc.seq){
      el._hbLocSeq = loc.seq;
      if(loc.paused || stopped) el._hbAudio.pause();
      else { try{ el._hbAudio.currentTime = 0; }catch(_){} const q = el._hbAudio.play(); if(q && q.catch) q.catch(function(){}); }
    }
    return true;
  }
  host.textContent = "";
  el._hbFrame = null; el._hbVid = null; el._hbSeq = null;   // the iframe, if any, is gone with the innerHTML
  el._hbSeekN = Number((loc.seek || {}).n || 0);            // a seek asked of the PREVIOUS file is not asked here
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
    applyPendingSeek(el, yt, () => { const p = ytPosition(yt.videoId, !yt.paused); return p ? p.pos : 0; },
                     (secs) => { ytPost(el._hbFrame, "seekTo", [secs, true]);
                                 _ytClock.t = secs; _ytClock.at = Date.now(); });
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
  _ytClock = {vid: yt.videoId, t: 0, d: 0, at: 0};   // a new song, a new clock — never the old song's seconds
  // A seek asked of the PREVIOUS song never reaches this one: the provider drops it when it loads a new
  // video (`_bump(yt, "load")`). So a command still standing here arrived AFTER the load — «pon X y ponla en
  // el minuto dos» in one breath — and is applied once the player answers, not discarded.
  const frame = document.createElement("iframe");
  frame.className = "hb-mus2-frame";
  frame.allow = "autoplay";
  frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(yt.videoId)
            + "?enablejsapi=1&autoplay=" + ((yt.paused || stopped) ? 0 : 1)
            + "&mute=1&controls=0&playsinline=1&rel=0";
  frame.addEventListener("load", () => ytStartListening(frame));
  host.appendChild(frame);
  el._hbFrame = frame; el._hbVid = yt.videoId; el._hbSeq = yt.cmd_seq;
  el._hbSeekN = 0;
  const wake = () => {
    if(halted(ctx)){ ytPost(frame, "pauseVideo"); return; }   // re-read because `wake` runs in timeouts up to 2.6s
    ytEnsureAudible(frame, yt.volume); if(!yt.paused) ytPost(frame, "playVideo");
    applyPendingSeek(el, yt, () => { const p = ytPosition(yt.videoId, true); return p ? p.pos : 0; },
                     (secs) => { ytPost(frame, "seekTo", [secs, true]); _ytClock.t = secs; _ytClock.at = Date.now(); });
  };
  _ytReady = wake;                                   // real onReady is the exact moment; timeouts back it up
  _ytEnded = () => { try{ ctx.action("ended"); }catch(_){} };   // F4: on end -> advance queue on the server
  setTimeout(wake, 1200); setTimeout(wake, 2600);
}

// Spotify connection, intact from V2-041.
async function doConnect(ctx, client_id, btn, adv){
  if(btn){ btn.disabled = true; btn.textContent = tt("opening_spotify", null, "Abriendo Spotify…"); }
  // V2-700 — the popup was already right here; what was missing is the NOTICING. `ctx.connect` watches
  // for the connection landing and re-reads state, so the card stops asking to connect on its own.
  const res = await ctx.connect("connect", client_id ? {client_id} : {}, {family: "musica", name: "spotify"});
  if(res && res.url){
    if(btn) btn.textContent = tt("finish_login", null, "Termina el login en la ventana…");
  } else {
    if(btn){ btn.disabled = false; btn.textContent = client_id ? tt("connect_own_id", null, "Conectar con mi Client ID") : tt("connect_spotify", null, "Conectar Spotify"); }
    if(res && res.need_client_id && adv) adv.open = true;
  }
}

function connectBlock(data, ctx, {compact=false} = {}){
  const frag = document.createDocumentFragment();
  let adv;
  if(data.can_connect){
    const b = h("button", compact ? "hb-mus2-link" : "hb-mus2-btn",
      compact ? tt("connect_spotify_lib", null, "Conectar Spotify (tu biblioteca)") : tt("connect_spotify", null, "Conectar Spotify"));
    b.onclick = () => doConnect(ctx, "", compact ? null : b, adv);
    frag.appendChild(b);
  }
  adv = h("details", "hb-mus2-adv");
  if(!data.can_connect) adv.open = true;
  adv.appendChild(h("summary", null, data.can_connect ? tt("own_app", null, "Usar mi propia app de Spotify (avanzado)")
                                                      : tt("own_app_title", null, "Conectar con tu app de Spotify")));
  const ol = h("ol", "hb-mus2-steps");
  ol.appendChild(h("li", null, tt("own_app_1", null, "Entra en developer.spotify.com → Dashboard → Create app.")));
  const li2 = h("li", null, tt("own_app_2", null, "En «Redirect URIs» añade exactamente:"));
  li2.appendChild(h("div", "hb-mus2-code", data.redirect_uri || "http://127.0.0.1:43917/api/spotify/callback"));
  ol.appendChild(li2);
  ol.appendChild(h("li", null, tt("own_app_3", null, "Copia el «Client ID» y pégalo aquí:")));
  adv.appendChild(ol);
  const inp = h("input", "hb-mus2-inp"); inp.placeholder = tt("own_app_ph", null, "Tu Client ID de Spotify");
  adv.appendChild(inp);
  const b2 = h("button", "hb-mus2-btn ghost", tt("connect_own_id", null, "Conectar con mi Client ID"));
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
  if(yt.videoId) return {title: yt.title || tt("music_fb", null, "Música"), artist: yt.artist || "", art: yt.art || "", playing: !yt.paused};
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
  const np = nowPlaying(data);
  const bar = h("div", "hb-mus2-bar" + (np ? "" : " empty"));
  const playing = !!(np && np.playing);
  if(np) maybeEnrich(np, ctx);
  const artWrap = h("div", "hb-mus2-barartwrap");
  artWrap.appendChild(artNode(np && np.art, ICON_NOTE));
  if(playing){ const badge = h("div", "hb-mus2-areq"); badge.appendChild(eqIcon()); artWrap.appendChild(badge); }
  bar.appendChild(artWrap);
  const meta = h("div", "hb-mus2-barmeta");
  // Two REAL states, never one row wearing a fake song title: an empty player is not a track called "Nada
  // sonando" (the operator's own words) — it is a plain hint, italic, with no title/artist pair at all.
  if(np){
    meta.appendChild(h("div", "hb-mus2-bart", np.title || tt("music_fb", null, "Música")));
    meta.appendChild(h("div", "hb-mus2-bara", np.artist || (np.device ? np.device : "")));
  } else {
    meta.appendChild(h("div", "hb-mus2-baridle", tt("ask_what", null, "Dime qué quieres escuchar")));
  }
  bar.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mkIcon = (svg, action, cls) => {                    // control = fire-and-forget; SSE re-renders
    const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(svg));
    if(!np) b.disabled = true;
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
    heart.title = fav ? tt("already_fav", null, "Ya está en Favoritos") : tt("save_fav", null, "Guardar en Favoritos");
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
    const x = h("button", "hb-mus2-x"); x.appendChild(svgEl(ICON_CLOSE)); x.title = tt("remove_track", null, "Quitar de la lista");
    x.onclick = (e) => { e.stopPropagation(); ctx.action("remove_from_playlist", {playlist: opts.remove, item: t.title}); };
    x.ondblclick = (e) => e.stopPropagation();
    row.appendChild(x);
  }
  return row;
}

// ── V2-717 · WHERE THE SONG IS, whoever is playing it ────────────────────────────────────────────────────
// Three players, one question. The two that play IN this page answer it themselves — a hidden <audio> and the
// hidden YouTube iframe, both with a real clock on this side of the wire. Spotify plays on a device somewhere
// else entirely, so its answer is the last `progress_ms` the server read, advanced by the local clock while
// it is playing. A source that cannot answer returns null, and then NO scrubber is drawn at all: a bar pinned
// at zero, or one that cannot be moved, is worse than no bar.
function playback(el, data, ctx){
  const loc = data.local || {};
  if(loc.src && el._hbAudio){
    const a = el._hbAudio;
    const dur = isFinite(a.duration) ? a.duration : 0;
    if(!dur) return null;                       // metadata not in yet: ask again on the next tick
    return {pos: a.currentTime || 0, dur, playing: !a.paused,
            seek: (s) => { try{ a.currentTime = s; }catch(_){} }};
  }
  const yt = data.yt || {};
  if(yt.videoId && el._hbFrame){
    const p = ytPosition(yt.videoId, !yt.paused);
    if(!p || !p.dur) return null;               // the embed has not sent a clock frame yet
    return {pos: p.pos, dur: p.dur, playing: !yt.paused,
            seek: (s) => { ytPost(el._hbFrame, "seekTo", [s, true]);
                           _ytClock.t = s; _ytClock.at = Date.now(); }};
  }
  const np = data.now_playing;
  if(np && np.duration_ms){
    const dur = Number(np.duration_ms) / 1000;
    const base = Number(np.progress_ms || 0) / 1000;
    const drift = (np.playing && el._hbNpAt) ? (Date.now() - el._hbNpAt) / 1000 : 0;
    // Spotify is the one source whose seek is a ROUND TRIP: the device is not here, so the card asks the
    // server, which asks Spotify. The bar still follows the finger locally; the truth lands on the next read.
    return {pos: Math.max(0, Math.min(dur, base + drift)), dur, playing: !!np.playing,
            seek: (s) => { try{ ctx.action("seek", {to: Math.round(s)}); }catch(_){} }};
  }
  return null;
}

function fmtTime(sec){
  if(!isFinite(sec) || sec < 0) sec = 0;
  const two = (n) => (n < 10 ? "0" : "") + n;
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60) % 60, hrs = Math.floor(sec / 3600);
  return hrs ? `${hrs}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}

// The scrubber he asked for: «una barra de progreso para que yo la pueda mover, a lo mejor si quiero
// escucharla un poco más para adelante». While the finger is down the paint follows it and the PLAYER IS NOT
// TOLD ANYTHING — one seek on release, never sixty on the way there, which is what turns a drag into a
// stuttering restart on the YouTube embed.
function seekRow(pb){
  const row = h("div", "hb-mus2-seek");
  const cur = h("div", "hb-mus2-time", "0:00");
  const rail = h("div", "hb-mus2-rail");
  rail.append(h("div", "hb-mus2-railbg"), h("div", "hb-mus2-fill"), h("div", "hb-mus2-knob"));
  const fill = rail.querySelector(".hb-mus2-fill"), knob = rail.querySelector(".hb-mus2-knob");
  const total = h("div", "hb-mus2-time r", "0:00");
  row.append(cur, rail, total);

  let dragging = false, frac = 0;
  const paint = (f, pos, dur) => {
    const pct = Math.max(0, Math.min(1, f)) * 100;
    fill.style.width = pct + "%"; knob.style.left = pct + "%";
    cur.textContent = fmtTime(pos); total.textContent = fmtTime(dur);
  };
  const fracAt = (ev) => {
    const r = rail.getBoundingClientRect();
    return r.width ? Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) : 0;
  };
  const st = () => row._pb || {pos: 0, dur: 0, seek: null};
  rail.addEventListener("pointerdown", (ev) => {
    dragging = true; frac = fracAt(ev); rail.classList.add("hb-mus2-drag");
    try{ rail.setPointerCapture(ev.pointerId); }catch(_){}
    paint(frac, frac * st().dur, st().dur);
    ev.preventDefault();
  });
  rail.addEventListener("pointermove", (ev) => {
    if(!dragging) return;
    frac = fracAt(ev); paint(frac, frac * st().dur, st().dur);
  });
  const release = () => {
    if(!dragging) return;
    dragging = false; rail.classList.remove("hb-mus2-drag");
    const s = st();
    if(s.dur && s.seek) s.seek(frac * s.dur);
  };
  rail.addEventListener("pointerup", release);
  rail.addEventListener("pointercancel", release);
  // The tick calls this four times a second. A drag in progress OWNS the paint — the player's own position is
  // still where the song is, and letting it repaint under the finger is the bar fighting the operator.
  row.update = (next) => { row._pb = next; if(!dragging) paint(next.dur ? next.pos / next.dur : 0, next.pos, next.dur); };
  row.update(pb);
  return row;
}

// The name of what is making sound — the same word the bar's chip shows, so the two never disagree.
function sourceLabel(data){
  if((data.local || {}).src) return tt("local_src", null, "Tu biblioteca");
  if(data.connected) return "Spotify";
  if((data.yt || {}).videoId) return "YouTube";
  return tt("no_source", null, "Sin fuente");
}

// ── THE ONE BAR ──────────────────────────────────────────────────────────────────────────────────────────
// The window chrome above it already carries the widget's mark, its name and the system buttons: repeating
// «Tu música» underneath was the same sentence twice, which is the complaint that opened this batch on the
// contacts card and reappeared verbatim here. What is left is what could not live anywhere else: where you
// are, and where the music comes from.
function provChip(data, ctx){
  const b = h("button", "hb-mus2-prov");
  const live = !!(data.connected || (data.yt || {}).videoId || (data.local || {}).src);
  b.appendChild(h("span", "hb-mus2-dot" + (live ? " on" : "")));
  b.appendChild(h("span", null, sourceLabel(data)));
  b.title = tt("sources", null, "Fuentes de música");
  b.onclick = () => ctx.action("open_view", {kind: "connect"});
  return b;
}

function headerBar(data, ctx, kind){
  const bar = h("div", "hb-mus2-headfix");
  if(kind === "playlist" || kind === "connect"){
    const back = h("button", "hb-mus2-back");
    back.appendChild(svgEl(ICON_BACK)); back.appendChild(h("span", null, tt("back", null, "Volver")));
    back.onclick = () => ctx.action("open_view", {kind: "library"});
    bar.appendChild(back);
  } else if(nowPlaying(data)){
    // DERIVED, like the contacts rail: a switch with one side is not a switch, it is a label. With nothing
    // sounding there is no «Sonando» to cross to, so the bar simply does not draw one.
    const seg = h("div", "hb-mus2-seg");
    const tab = (id, icon, label) => {
      const b = h("button", "hb-mus2-segb" + (kind === id ? " on" : ""));
      b.appendChild(svgEl(icon)); b.appendChild(h("span", null, label));
      b.onclick = () => ctx.action("open_view", {kind: id});
      return b;
    };
    seg.appendChild(tab("now", ICON_NOTE, tt("tab_now", null, "Sonando")));
    seg.appendChild(tab("library", ICON_LIST, tt("tab_library", null, "Tu música")));
    bar.appendChild(seg);
  }
  bar.appendChild(provChip(data, ctx));
  return bar;
}

// ── AHORA SUENA: the song IS the screen ──────────────────────────────────────────────────────────────────
// «en el centro están los datos de la ficha que te he dicho y la línea del tiempo de la canción, sin nada
// más, es decir, la canción igualmente la manejo abajo». So: art, title, artist, one line of facts, the
// scrubber — and the transport stays at the foot, duplication included, because he asked for it out loud.
function nowView(host, el, data, ctx){
  const np = nowPlaying(data);
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(data, ctx, "now"));
  const scroll = h("div", "hb-mus2-scroll mid");
  maybeEnrich(np, ctx);

  const box = h("div", "hb-mus2-now");
  const art = h("div", "hb-mus2-nowart");
  const fallback = () => { art.textContent = ""; art.appendChild(svgEl(ICON_NOTE)); };
  if(np.art){
    const img = document.createElement("img"); img.src = np.art; img.alt = "";
    img.onerror = fallback; art.appendChild(img);
  } else fallback();
  box.appendChild(art);

  box.appendChild(h("div", "hb-mus2-nowt", np.title || tt("music_fb", null, "Música")));
  box.appendChild(h("div", "hb-mus2-nowa", np.artist || tt("unknown_artist", null, "Artista desconocido")));

  const meta = h("div", "hb-mus2-nowm");
  if(np.playing) meta.appendChild(eqIcon());
  const facts = [];
  if(np.album) facts.push(np.album);
  facts.push(sourceLabel(data));
  if(np.device) facts.push(np.device);
  facts.forEach((f, i) => { if(i) meta.appendChild(h("i", null, "·")); meta.appendChild(h("span", null, f)); });
  box.appendChild(meta);

  // The scrubber has a SLOT of its own, always present and usually empty: the YouTube embed sends its first
  // clock frame a second or two after the card is already painted, and the tick fills the slot the moment it
  // arrives. Drawing a disabled bar in the meantime, or re-rendering the whole card when the clock lands,
  // were the two worse answers.
  const slot = h("div", "hb-mus2-seekslot");
  box.appendChild(slot);
  scroll.appendChild(box);
  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);

  const tick = () => {
    const pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ if(slot.firstChild) slot.textContent = ""; return; }
    if(!slot.firstChild) slot.appendChild(seekRow(pb));
    else slot.firstChild.update(pb);
  };
  tick();
  el._hbTick = setInterval(tick, 250);          // a local clock, no network — cleared by drawView on re-render
}

// ── TU MÚSICA: lists + most played + recent ──────────────────────────────────────────────────────────────
function libraryView(host, data, ctx){
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(data, ctx, "library"));
  const scroll = h("div", "hb-mus2-scroll");
  const np = nowPlaying(data);
  const bare = !(data.playlists || []).length && !(data.top || []).length && !(data.recent || []).length;

  if(bare){
    scroll.classList.add("mid");
    scroll.appendChild(emptyHero(data, ctx));
    wrap.appendChild(scroll);
    wrap.appendChild(playbackBar(data, ctx));
    host.appendChild(wrap);
    return;
  }

  // Lists: covers + "New list" card.
  const secL = h("div", "hb-mus2-sec");
  secL.appendChild(h("div", "hb-mus2-sech", tt("your_playlists", null, "Tus listas")));
  const lists = h("div", "hb-mus2-lists");
  (data.playlists || []).forEach(pl => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(artNode(pl.art, ICON_NOTE));
    c.appendChild(h("div", "hb-mus2-plname", pl.name || tt("playlist", null, "Lista")));
    const n = (pl.tracks || []).length;
    c.appendChild(h("div", "hb-mus2-plsub", `${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`));
    c.onclick = () => ctx.action("open_view", {kind: "playlist", id: pl.id});
    lists.appendChild(c);
  });
  lists.appendChild(newListCard(lists, ctx));
  secL.appendChild(lists);
  scroll.appendChild(secL);

  // Top tracks.
  if((data.top || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", tt("most_played", null, "Más escuchadas")));
    const g = h("div", "hb-mus2-grid");
    data.top.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), playing: nowPlayingMatches(t, np)})));
    s.appendChild(g); scroll.appendChild(s);
  }

  // Recent.
  if((data.recent || []).length){
    const s = h("div", "hb-mus2-sec");
    s.appendChild(h("div", "hb-mus2-sech", tt("recent", null, "Recientes")));
    const g = h("div", "hb-mus2-grid");
    data.recent.slice(0, 8).forEach(t => g.appendChild(trackRow(t, ctx, {playing: nowPlayingMatches(t, np)})));
    s.appendChild(g); scroll.appendChild(s);
  }

  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);
}

// An empty library is the FIRST thing a new operator sees, and it used to be the words «Tus listas» over a
// dashed square in the corner of a large, dark, otherwise empty card — «como puedes ver, está un poco triste
// al verse tan vacía». Every chip here is real: it plays.
function emptyHero(data, ctx){
  const hero = h("div", "hb-mus2-hero");
  const disc = h("div", "hb-mus2-herod");
  disc.appendChild(svgEl(ICON_NOTE));
  hero.appendChild(disc);
  hero.appendChild(h("div", "hb-mus2-herot", tt("empty_title", null, "Aquí vivirá tu música")));
  hero.appendChild(h("div", "hb-mus2-heros",
    tt("empty_sub", null, "Pídeme una canción y suena al momento. Lo que escuches irá apareciendo aquí, en Recientes y en Más escuchadas.")));
  const chips = h("div", "hb-mus2-chips");
  [tt("ex_1", null, "Pon música"), tt("ex_2", null, "Ponme a Frank Sinatra"), tt("ex_3", null, "Pon jazz tranquilo")]
    .forEach(q => {
      const c = h("button", "hb-mus2-chip", q);
      c.onclick = () => ctx.action("play", {query: q});
      chips.appendChild(c);
    });
  hero.appendChild(chips);
  const lists = h("div", "hb-mus2-lists");
  lists.appendChild(newListCard(lists, ctx));
  hero.appendChild(lists);
  return hero;
}

function newListCard(lists, ctx){
  const card = h("div", "hb-mus2-pl hb-mus2-new");
  card.appendChild(artNode(null, ICON_PLUS));
  card.appendChild(h("div", "hb-mus2-plname", tt("new_playlist", null, "Nueva lista")));
  card.onclick = () => {
    // Inline: an input replaces the create gesture; Enter/blur -> create_playlist, then SSE re-renders the list.
    const box = h("div", "hb-mus2-pl");
    const inp = h("input", "hb-mus2-inp hb-mus2-newinp"); inp.placeholder = tt("name_ph", null, "Nombre");
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

// ── FUENTES: the connectors screen ───────────────────────────────────────────────────────────────────────
// The Spotify block used to sit in the middle of the library, where it was the first thing the eye met on a
// card that had not been asked anything yet. It is a screen of its own now, behind the source chip — the
// same shape the contacts card took in V2-715, and the same reason: the connector is not the content.
function connectView(host, data, ctx){
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(data, ctx, "connect"));
  const scroll = h("div", "hb-mus2-scroll");
  const sec = h("div", "hb-mus2-sec");
  sec.appendChild(h("div", "hb-mus2-sech", tt("sources", null, "Fuentes de música")));
  sec.appendChild(h("div", "hb-mus2-sub", tt("free_source", null,
    "YouTube suena gratis y sin cuenta: ya está listo, no hay nada que conectar.")));
  if(data.connected){
    sec.appendChild(h("div", "hb-mus2-sub", tt("spotify_on", null,
      "Spotify está conectado: tu biblioteca y tus dispositivos ya están disponibles.")));
    const d = h("button", "hb-mus2-btn ghost", tt("disconnect", null, "Desconectar Spotify"));
    d.onclick = () => ctx.action("disconnect");
    sec.appendChild(d);
  } else {
    sec.appendChild(h("div", "hb-mus2-sub", tt("connect_hint", null,
      "Dime «pon música» o «ponme a Frank Sinatra» y suena gratis. Conecta tu Spotify (Premium) para tu biblioteca.")));
    sec.appendChild(connectBlock(data, ctx, {compact: false}));
  }
  scroll.appendChild(sec);
  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);
}

// PLAYLIST: cover (with the play button INSIDE it) + tracklist.
function playlistView(host, data, ctx, pl){
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(data, ctx, "playlist"));
  const scroll = h("div", "hb-mus2-scroll");

  const tracks = pl.tracks || [];
  const n = tracks.length;
  const derived = deriveArtistInfo(tracks);

  const head = h("div", "hb-mus2-head");
  const artwrap = h("div", "hb-mus2-artwrap");
  artwrap.appendChild(artNode(pl.art, ICON_NOTE));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
  play.title = tt("play_playlist", null, "Reproducir esta lista");
  if(!n) play.disabled = true;
  play.onclick = () => ctx.action("play_playlist", {playlist: pl.id});
  artwrap.appendChild(play);
  head.appendChild(artwrap);

  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("playlist", null, "Lista")));
  hm.appendChild(h("div", "hb-mus2-headn", pl.name || tt("playlist", null, "Lista")));
  const subParts = [];
  if(derived.commonArtist) subParts.push(derived.commonArtist);
  subParts.push(`${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`);
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
    g.appendChild(h("div", "hb-mus2-empty", tt("playlist_empty", null, "Lista vacía. Dime «añade una canción a esta lista».")));
  }
  scroll.appendChild(g);

  wrap.appendChild(scroll);
  wrap.appendChild(playbackBar(data, ctx));
  host.appendChild(wrap);
}

// Which face of the card is showing. `home` is the ADAPTIVE one and the default: with something sounding it
// is the song, with nothing sounding it is the library — which is exactly what the operator described
// («cuando no estamos reproduciendo… me gustaría ver la canción en toda la pantalla del widget»). The two
// explicit kinds exist so that a click, or a sentence, can cross over and STAY there.
function drawView(el, data, ctx){
  const host = el._viewHost;
  if(el._hbTick){ clearInterval(el._hbTick); el._hbTick = null; }
  host.textContent = "";
  const view = data.view || {kind: "home"};
  let kind = (view.kind || "home").toLowerCase();
  if(kind === "nowplaying") kind = "now";                       // the pre-V2-717 spelling, never implemented
  if(kind === "playlist"){
    const pl = (data.playlists || []).find(p => p.id === view.id);
    if(pl){ playlistView(host, data, ctx, pl); return; }
  }
  if(kind === "connect"){ connectView(host, data, ctx); return; }
  // A hero with nothing in it would be the emptiest screen of all: when the song ends while the card sits on
  // «Sonando», it falls back to the library instead of showing a frame around silence.
  if((kind === "now" || kind === "home") && nowPlaying(data)){ nowView(host, el, data, ctx); return; }
  libraryView(host, data, ctx);
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.musica."+key, params); if(s && s!=="widgets.musica."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  data = data || {};
  // V2-717 — WHEN this Spotify reading was taken. Spotify plays on a device that is not here, so `progress_ms`
  // is a photograph, not a clock: the scrubber advances it locally from the instant the photograph arrived,
  // and a NEW photograph (a different song, or a position that moved) restarts the count. Without the stamp
  // the bar would either freeze between reads or drift further from the truth the longer the card stayed open.
  const _np = data.now_playing || null;
  const _npKey = _np ? [_np.title, _np.artist, _np.progress_ms, _np.playing].join("|") : "";
  if(el._hbNpKey !== _npKey){ el._hbNpKey = _npKey; el._hbNpAt = Date.now(); }
  if(!el._hbInit){                    // hosts persistentes: la vista se reconstruye, el player oculto NO
    el.textContent = "";
    el.className = "hb-mus2-root";
    el._viewHost = document.createElement("div"); el._viewHost.className = "hb-mus2-viewhost";
    el._ytHost = document.createElement("div"); el._ytHost.className = "hb-mus2-audio";
    el.append(el._viewHost, el._ytHost);
    el._hbInit = true;
  }
  syncYtPlayer(el, data, ctx);
  drawView(el, data, ctx);
}

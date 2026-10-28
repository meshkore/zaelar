// musica: face of the music connector (V2-041) — Spotify-style lists (V2-058), a PRO pass (V2-629/V2-678), the
// V2-717 redesign (the widget is ONE box: the canvas window IS the frame; the bar above the content is the ONE bar
// the house standard allows; the song that is sounding OCCUPIES the card) and V2-795: the card does what a player
// does — a queue you can see and edit, shuffle and repeat, a volume you can mute, list management (rename, delete,
// reorder, play from a song, shuffle a list), a heart on every row, a search over the catalogue with artist and
// album pages — and the content is SECTIONED: each shelf is a quiet panel one rung up the elevation ladder
// (V2-689), never a frame around the whole card. Contract: render(el, data, ctx).
// data = GET /widgets/musica/data -> {mode:"spotify"|"youtube"|"local"|"idle", connected, can_connect,
//   own_client_id_set, default_available, redirect_uri, now_playing (spotify, with progress_ms/duration_ms,
//   shuffle, repeat)|null, yt:{videoId,title,artist,paused,muted,volume,cmd_seq,art,seek:{n,to,by},queue,shuffle,
//   repeat}, local:{src,title,artist,art,paused,seq,seek:{n,to,by}},
//   playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track],
//   top:[track+count], fav_current:bool, fav:{id,name}, modes:{shuffle,repeat,supported},
//   queue:{items,editable,source}, volume:{level,muted}, browse:{search,artist,album},
//   view:{kind:"home|now|library|queue|playlist|search|artist|album|connect",id}}.
//   ctx.action(name,payload) -> POST /widgets/musica/action (JSON).
//
// Faces (drawView): `home` is ADAPTIVE — the song when something sounds, the library when nothing does; `now` and
// `library` pin either; `queue`, `playlist`, `search`, `artist`, `album` and `connect` are screens of their own.
// PLAYBACK = the connector (ctx.action -> connectors.music); nothing here reinvents a backend, and nothing here
// touches the network: the catalogue answers arrive in the store (`browse`) and are painted from there.
//
// THE PLAYHEAD (V2-717) belongs to whoever is making the sound, and that is why there is no position in the
// store. A local file and the hidden YouTube iframe play in THIS page and hold their own clock, so the card reads
// them directly and a drag seeks them with no server in the loop; Spotify plays on a device somewhere else, so its
// `progress_ms` is a photograph the card advances locally and a drag is a round trip. A seek asked by VOICE
// travels the other way — a numbered command in the store (`seek:{n,to,by}`) that `applyPendingSeek` applies.
//
// The hidden YouTube-audio player is reused between re-renders (persistent `_ytHost`): rebuilding the view never
// reloads the iframe, which would restart the song.
//
// ICONS are inline SVG in the SAME visual language as the app shell (frontend/app/lib/icons.js), duplicated
// locally because widget.js cannot import from frontend/app.
//

import { albumView, artistView, searchView } from "./js/browse.js";
import { nowPlaying } from "./js/controls.js";
import { syncYtPlayer } from "./js/players.js";
import { playlistView, queueView } from "./js/playlist.js";
import { bindT } from "./js/shared.js";
import { CSS } from "./js/style.js";
import { connectView, libraryView, nowView } from "./js/views.js";

function injectStyles(){
  if(document.getElementById("hb-mus2-css")) return;
  const s = document.createElement("style"); s.id = "hb-mus2-css"; s.textContent = CSS; document.head.appendChild(s);
}

// Which face of the card is showing. `home` is ADAPTIVE and the default: the song when something sounds, the
// library when nothing does. The tick that paints the two progress lines is ONE interval for the whole face.
function drawView(el, data, ctx){
  if(el._hbTick){ clearInterval(el._hbTick); el._hbTick = null; }
  const ae = document.activeElement;
  const hadFocus = !!(ae && ae.classList && ae.classList.contains("hb-mus2-sinp") && el.contains(ae));
  el._hbTickers = [];
  el._viewHost.textContent = "";
  el.querySelectorAll(".hb-mus2-menu").forEach(m => m.remove());
  const view = data.view || {kind: "home"};
  let kind = (view.kind || "home").toLowerCase();
  if(kind === "nowplaying") kind = "now";                       // the pre-V2-717 spelling, never implemented
  if(kind !== "search") el._hbDraft = null;
  el._hbFocusSearch = kind === "search" && (hadFocus || el._hbLastKind !== "search");
  el._hbLastKind = kind;
  if(kind === "playlist"){
    const pl = (data.playlists || []).find(p => p.id === view.id);
    if(pl) playlistView(el, data, ctx, pl);
    else libraryView(el, data, ctx);
  }
  else if(kind === "connect") connectView(el, data, ctx);
  else if(kind === "queue") queueView(el, data, ctx);
  else if(kind === "search") searchView(el, data, ctx);
  else if(kind === "artist" && ((data.browse || {}).artist || {}).artist) artistView(el, data, ctx);
  else if(kind === "album" && ((data.browse || {}).album || {}).album) albumView(el, data, ctx);
  // A hero with nothing in it would be the emptiest screen of all: when the song ends while the card sits on
  // «Sonando», it falls back to the library instead of showing a frame around silence.
  else if((kind === "now" || kind === "home") && nowPlaying(data)) nowView(el, data, ctx);
  else libraryView(el, data, ctx);
  const tick = () => el._hbTickers.forEach(f => { try{ f(); }catch(_){} });
  tick();
  if(el._hbTickers.length) el._hbTick = setInterval(tick, 250);   // a local clock, no network
}

export function render(el, data, ctx){
  bindT(ctx);
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

// musica — the TRANSPORT: what is playing, where the song is, the scrubber, the playback bar and its progress and
// volume rows (refactor2710-12 T-03).
import { _ytClock, soundRow, ytPosition, ytPost } from "./players.js";
import { ICON_HEART, ICON_HEART_FILL, ICON_NEXT, ICON_NOTE, ICON_PAUSE, ICON_PLAY, ICON_PREV,
  ICON_REPEAT, ICON_REPEAT_ONE, ICON_SHUFFLE, ICON_VOL_OFF, ICON_VOL_UP, _norm, artNode, eqIcon,
  fire, h, svgEl, tt } from "./shared.js";

// Playback bar (Spotify or YouTube).
export function nowPlaying(data){
  if(data.now_playing && data.now_playing.title) return data.now_playing;
  const yt = data.yt || {};
  // yt.art/yt.artist (V2-629): the connector already resolves free cover art the instant it knows a videoId,
  // and the server splits an "Artist - Title" upload title for display — both arrive ready on `data.yt`.
  if(yt.videoId) return {title: yt.title || tt("music_fb", null, "Música"), artist: yt.artist || "", art: yt.art || "", playing: !yt.paused};
  // V2-795 — a file of the agent's own library is the third thing that can be sounding (V2-638), and the bar
  // showed nothing while it played.
  const loc = data.local || {};
  if(loc.src) return {title: loc.title || tt("music_fb", null, "Música"), artist: loc.artist || "", art: loc.art || "", playing: !loc.paused};
  return null;
}

// Lazy cover-art ENRICHMENT (V2-629): asked once per (title, artist) per page life, always AFTER the row/bar
// is already on screen with its fallback icon — never on anything that would delay playback starting.
export const _enrichAsked = new Set();
export function maybeEnrich(t, ctx){
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

// ── V2-717 · WHERE THE SONG IS, whoever is playing it ────────────────────────────────────────────────────
// Three players, one question. The two that play IN this page answer it themselves — a hidden <audio> and the
// hidden YouTube iframe, both with a real clock on this side of the wire. Spotify plays on a device somewhere
// else entirely, so its answer is the last `progress_ms` the server read, advanced by the local clock while
// it is playing. A source that cannot answer returns null, and then NO scrubber is drawn at all: a bar pinned
// at zero, or one that cannot be moved, is worse than no bar.
export function playback(el, data, ctx){
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

export function fmtTime(sec){
  if(!isFinite(sec) || sec < 0) sec = 0;
  const two = (n) => (n < 10 ? "0" : "") + n;
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60) % 60, hrs = Math.floor(sec / 3600);
  return hrs ? `${hrs}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}

// The scrubber he asked for: «una barra de progreso para que yo la pueda mover, a lo mejor si quiero
// escucharla un poco más para adelante». While the finger is down the paint follows it and the PLAYER IS NOT
// TOLD ANYTHING — one seek on release, never sixty on the way there, which is what turns a drag into a
// stuttering restart on the YouTube embed.
export function seekRow(pb){
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
// A song the card SEES playing is reported once per page life (internal `played`): a song started by voice never
// crossed the card's own play path, so Recent and Most played would never hear of it otherwise.
export const _reported = new Set();
export function reportPlayed(np, ctx){
  if(!np || !np.title) return;
  const key = _norm(np.title) + "|" + _norm(np.artist);
  if(_reported.has(key)) return;
  _reported.add(key);
  fire(ctx, "played", {title: np.title, artist: np.artist || "", art: np.art || ""});
}

// ── THE TRANSPORT ────────────────────────────────────────────────────────────────────────────────────────
export function playbackBar(el, data, ctx){
  const np = nowPlaying(data);
  const bar = h("div", "hb-mus2-bar" + (np ? "" : " empty"));
  const playing = !!(np && np.playing);
  if(np){ maybeEnrich(np, ctx); reportPlayed(np, ctx); }
  const tap = soundRow(el, data);                    // V2-812: the browser keeps it silent → the tap that fixes it
  if(tap) bar.appendChild(tap);
  const row = h("div", "hb-mus2-barrow");
  bar.appendChild(row);
  const artWrap = h("div", "hb-mus2-barartwrap");
  artWrap.appendChild(artNode(np && np.art, ICON_NOTE));
  if(playing){ const badge = h("div", "hb-mus2-areq"); badge.appendChild(eqIcon()); artWrap.appendChild(badge); }
  row.appendChild(artWrap);
  const meta = h("div", "hb-mus2-barmeta");
  // Two REAL states, never one row wearing a fake song title (V2-667): idle is a plain hint, no title/artist.
  if(np){
    meta.appendChild(h("div", "hb-mus2-bart", np.title || tt("music_fb", null, "Música")));
    meta.appendChild(h("div", "hb-mus2-bara", np.artist || (np.device ? np.device : "")));
  } else {
    meta.appendChild(h("div", "hb-mus2-baridle", tt("ask_what", null, "Dime qué quieres escuchar")));
  }
  row.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mk = (svg, action, cls, payload, title) => {          // control = fire-and-forget; SSE re-renders
    const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(svg));
    if(title){ b.title = title; b.setAttribute("aria-label", title); }
    if(!np) b.disabled = true;
    b.onclick = () => fire(ctx, action, payload);
    return b;
  };
  const md = data.modes || {};
  const modesOk = !!md.supported;
  const shuf = mk(ICON_SHUFFLE, "shuffle", "mode" + (md.shuffle ? " on" : ""), {on: !md.shuffle},
                  tt("shuffle", null, "Aleatorio"));
  if(!modesOk) shuf.disabled = true;
  const rep = md.repeat || "off";
  const nextRep = rep === "off" ? "all" : (rep === "all" ? "one" : "off");
  const repB = mk(rep === "one" ? ICON_REPEAT_ONE : ICON_REPEAT, "repeat", "mode" + (rep !== "off" ? " on" : ""),
                  {mode: nextRep}, tt("repeat_" + rep, null, rep === "one" ? "Repetir la canción"
                                                           : (rep === "all" ? "Repetir la cola" : "Repetir: no")));
  if(!modesOk) repB.disabled = true;
  ctrls.appendChild(shuf);
  ctrls.appendChild(mk(ICON_PREV, "previous"));
  ctrls.appendChild(mk(playing ? ICON_PAUSE : ICON_PLAY, playing ? "pause" : "resume", "main"));
  ctrls.appendChild(mk(ICON_NEXT, "next"));
  ctrls.appendChild(repB);
  row.appendChild(ctrls);
  if(np){
    const side = h("div", "hb-mus2-barside");
    // The heart is a STATE indicator (V2-629): filled when the song is already saved.
    const fav = !!data.fav_current;
    const heart = mk(fav ? ICON_HEART_FILL : ICON_HEART, "favorite_current", fav ? "fav" : "", undefined,
                     fav ? tt("already_fav", null, "Ya está en Favoritos") : tt("save_fav", null, "Guardar en Favoritos"));
    side.appendChild(heart);
    row.appendChild(side);
    bar.appendChild(progressRow(el, data, ctx, mk));
  }
  return bar;
}

// THE PROGRESS ROW (V2-795): elapsed · a rail you click or drag · total, then the volume as a bar you can see.
// Same rules as the big scrubber: the rail and the times appear only once the player says where the song is,
// the shared tick paints them, a drag owns the paint and asks for ONE seek on release — so a voice `seek`, which
// moves the player, shows up here on the next tick. The volume slider is the provider's own level (`data.volume`,
// the same number voice volume_up/down/set_volume move), so a re-render after any of them puts it where it is.
export function progressRow(el, data, ctx, mk){
  const row = h("div", "hb-mus2-barprog");
  const cur = h("div", "hb-mus2-bartime", ""), tot = h("div", "hb-mus2-bartime r", "");
  const rail = h("div", "hb-mus2-barrail");
  const fill = h("b"), knob = h("u");
  rail.append(h("i"), fill, knob);
  row.append(cur, rail, tot);
  let dragging = false, frac = 0, pb = null;
  const paint = (f) => { const pct = Math.max(0, Math.min(1, f)) * 100;
                         fill.style.width = pct + "%"; knob.style.left = pct + "%"; };
  const fracAt = (ev) => { const r = rail.getBoundingClientRect();
                           return r.width ? Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) : 0; };
  rail.addEventListener("pointerdown", (ev) => { if(!pb) return; dragging = true; frac = fracAt(ev);
    rail.classList.add("hb-mus2-drag"); try{ rail.setPointerCapture(ev.pointerId); }catch(_){}
    paint(frac); cur.textContent = fmtTime(frac * pb.dur); ev.preventDefault(); });
  rail.addEventListener("pointermove", (ev) => { if(!dragging) return; frac = fracAt(ev); paint(frac);
                                                cur.textContent = fmtTime(frac * pb.dur); });
  const release = () => { if(!dragging) return; dragging = false; rail.classList.remove("hb-mus2-drag");
                          if(pb && pb.dur && pb.seek) pb.seek(frac * pb.dur); };
  rail.addEventListener("pointerup", release);
  rail.addEventListener("pointercancel", release);
  const show = (on) => { [cur, rail, tot].forEach(x => { x.style.visibility = on ? "" : "hidden"; }); };
  show(false);
  el._hbTickers.push(() => {
    pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ show(false); return; }
    show(true);
    if(dragging) return;
    paint(pb.pos / pb.dur);
    cur.textContent = fmtTime(pb.pos); tot.textContent = fmtTime(pb.dur);
  });

  const vol = data.volume || {};
  const muted = !!vol.muted;
  row.appendChild(mk(muted ? ICON_VOL_OFF : ICON_VOL_UP, "set_volume", "", {mute: !muted},
                     muted ? tt("unmute", null, "Quitar silencio") : tt("mute", null, "Silenciar")));
  const localLevel = el._hbAudio ? Math.round((el._hbAudio.volume || 0) * 100) : null;
  const level = vol.level != null ? vol.level : localLevel;
  const sl = h("input", "hb-mus2-vol"); sl.type = "range"; sl.min = "0"; sl.max = "100";
  sl.value = String(muted ? 0 : (level != null ? level : 70));
  sl.title = tt("volume", null, "Volumen") + " · " + sl.value + "%";
  sl.setAttribute("aria-label", tt("volume", null, "Volumen"));
  sl.oninput = () => { sl.title = tt("volume", null, "Volumen") + " · " + sl.value + "%"; };
  sl.onchange = () => {
    fire(ctx, "set_volume", {level: Number(sl.value)});
    if(el._hbAudio){ try{ el._hbAudio.volume = Number(sl.value) / 100; }catch(_){} }
  };
  row.appendChild(sl);
  return row;
}

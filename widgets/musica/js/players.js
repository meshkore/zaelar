// musica — the two players that sound IN this page: the hidden YouTube iframe (its clock and its sound report) and
// the local <audio> (refactor2710-12 T-03).
import { h, tt } from "./shared.js";

export function ytPost(iframe, func, args){
  try{ if(iframe && iframe.contentWindow)
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*"); }catch(_){}
}
// Ensure the player is audible (unmute + set volume): on mount and every command, so "no audio" actually wakes up.
export function ytEnsureAudible(iframe, vol){
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
export let _ytReady = null, _ytEnded = null;
// V2-812 — what the page player REALLY does with the sound. A phone browser may keep a muted-autoplay start silent
// (refuse the unmute, or never start) until a tap on the page. The embed says so in its own `infoDelivery`
// (`muted`, `playerState`); the card reports it as `player_audio` and shows a tap row while it lasts.
export let _ytSound = null;                   // per-render reporter: (info) → `player_audio` when it disagrees with the store
export let _ytLoadedAt = 0;                   // when the current song's frame was mounted: a silence inside the grace is not a verdict
export const _SOUND_GRACE_MS = 2500;
export let _ytClock = {vid: "", t: 0, d: 0, at: 0};
export function ytStartListening(iframe){
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
      if (_ytSound && (typeof info.muted === "boolean" || typeof info.playerState === "number")) _ytSound(info);
    }
  });
}

// A seek asked by VOICE («adelanta un minuto», «ponla en el minuto dos») arrives as a COMMAND in the store —
// `{n, to, by}` — never as a position, because the position only exists HERE: the hidden iframe and the
// <audio> element live in this page and the server has never held a clock for them. `n` is a counter of its
// own and deliberately NOT `cmd_seq`: riding on cmd_seq would re-apply the last seek on every later pause or
// volume command, which is a song that jumps backwards every time you touch the volume.
export function applyPendingSeek(el, blk, getPos, seekTo){
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
export function ytPosition(vid, playing){
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
export function halted(ctx){ return !!(ctx && ctx.running === false); }

// V2-638 — a track that is a FILE we hold plays HERE, in the page, through a plain <audio> against our own
// library route. It shares `_ytHost` with the hidden YouTube iframe because only one of the two can ever be
// mounted (the server clears the yt block when a local track starts), and the same memo guards (`_hbSeq`)
// keep a re-render from restarting the song — the reason the seq exists at all is that asking for the SAME
// file twice must still be two events.
export function syncLocalPlayer(el, data, ctx){
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

// V2-812 — the page player's real sound against what the store wants. Silent = the player reports itself muted, or
// not playing (state other than 1 playing / 3 buffering), past the grace, while sound is wanted. Heard clears it.
export function bindSoundReport(el, data, ctx){
  const yt = data.yt || {};
  let sent = "";
  _ytSound = (info) => {
    if(!ctx || !ctx.action || halted(ctx) || !yt.videoId || yt.paused || yt.muted) return;
    const state = Number(info.playerState);
    const silent = info.muted === true || (typeof info.playerState === "number" && state !== 1 && state !== 3);
    if(silent && Date.now() - _ytLoadedAt < _SOUND_GRACE_MS) return;
    if(silent === !!yt.audio_blocked) return;
    const key = yt.videoId + "|" + silent + "|" + (yt.cmd_seq || 0);
    if(key === sent) return;
    sent = key;
    try{ const q = ctx.action("player_audio", {muted: silent, videoId: yt.videoId}); if(q && q.catch) q.catch(() => {}); }catch(_){}
  };
}

// A TAP is the only thing a phone browser accepts as permission to sound: the player is unmuted and started inside
// that same gesture. Any tap on the page does it while the block lasts; the row below names it.
export function unlockSound(el, data){
  const yt = data.yt || {};
  if(!el._hbFrame) return;
  ytEnsureAudible(el._hbFrame, yt.volume);
  ytPost(el._hbFrame, "playVideo");
}
export function armSoundUnlock(el, data){
  if(el._hbUnlockArmed || typeof document === "undefined") return;
  el._hbUnlockArmed = true;
  const go = () => {
    el._hbUnlockArmed = false;
    document.removeEventListener("pointerdown", go, true);
    unlockSound(el, el._hbData || data);
  };
  document.addEventListener("pointerdown", go, true);
}
export function soundRow(el, data){
  const yt = data.yt || {};
  if(data.mode !== "youtube" || !yt.audio_blocked || yt.paused || yt.muted) return null;
  const b = h("button", "hb-mus2-tapsound", "🔈 " + tt("tap_sound", null, "Toca aquí para que suene en esta pantalla"));
  b.onclick = () => unlockSound(el, data);
  return b;
}

export function syncYtPlayer(el, data, ctx){
  const yt = data.yt || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  el._hbData = data;
  bindSoundReport(el, data, ctx);
  if(yt.audio_blocked && !yt.paused && !stopped) armSoundUnlock(el, data);
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
  _ytLoadedAt = Date.now();
  _ytReady = wake;                                   // real onReady is the exact moment; timeouts back it up
  _ytEnded = () => { try{ ctx.action("ended"); }catch(_){} };   // F4: on end -> advance queue on the server
  setTimeout(wake, 1200); setTimeout(wake, 2600);
}

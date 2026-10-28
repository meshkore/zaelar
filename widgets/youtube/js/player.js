// youtube widget — the player funnel: the IFrame API listener, post(), state/command application, the frame.
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { Y } from "./state.js";
import { el, halted, tt } from "./shared.js";

export const _SOUND_GRACE_MS = 1500;
// The page may give a cross-origin player sound only after a real gesture (sticky user activation). Without one,
// trying to unmute an autoplaying video can pause it — so the card keeps it playing muted and says so instead.
export function pageMayPlaySound(){
  try{ const ua = navigator.userActivation; return !ua || !!ua.hasBeenActive; }catch(_){ return true; }
}
// Any real gesture on the page unlocks sound: the player is unmuted in that same gesture, once.
export function armSoundUnlock(vol){
  if(Y.unlockArmed || typeof document === "undefined") return;
  Y.unlockArmed = true;
  const go = () => {
    Y.unlockArmed = false;
    document.removeEventListener("pointerdown", go, true);
    document.removeEventListener("keydown", go, true);
    if(Y.plNow){ post(Y.plNow, "unMute", []); post(Y.plNow, "setVolume", [vol]); }
  };
  document.addEventListener("pointerdown", go, true);
  document.addEventListener("keydown", go, true);
}
if(typeof window !== "undefined" && !window.__hbYtWidgetBound){
  window.__hbYtWidgetBound = true;
  window.addEventListener("message", (ev) => {
    if(typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    if(d.id !== "hb-youtube") return;
    if(d.event === "onStateChange" && Number(d.info) === 0 && Y.ytEnded) Y.ytEnded();   // 0 = ENDED
    // onError codes: 2 bad id · 5 HTML5 error · 100 removed · 101/150 embedding disabled by the owner.
    // Without this, "This video is unavailable" on screen coexisted with a declared state that said
    // playing — and /widgets/producing, the brain and the judge all believed the declared state (V2-401).
    if(d.event === "onError" && Y.ytError) Y.ytError(d.info);
    // V2-604 — the definition of the video. The results page does not publish it (measured: only 4K carries
    // a badge at all), so the player is the ONLY honest source, and this is the only moment it exists. Read
    // from the `infoDelivery` the player already sends because we asked to listen; reported ONCE per video,
    // because that stream repeats several times a second and each report is a store write.
    if(d.event === "infoDelivery" && d.info && d.info.availableQualityLevels && Y.ytQuality){
      const vid = String(d.info.videoData && d.info.videoData.video_id || "");
      const key = vid || "current";
      if(key !== Y.qSeen){ Y.qSeen = key; Y.ytQuality(d.info.availableQualityLevels, vid); }
    }
    if(d.event === "infoDelivery" && d.info && typeof d.info.muted === "boolean" && Y.ytAudio){
      Y.ytAudio(d.info.muted, String(d.info.videoData && d.info.videoData.video_id || ""));
    }
  });
}
export function startListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-youtube", channel:"widget"}), "*"); }catch(_){}
}

// The ONE funnel every control path goes through (applyState, applyCmd, applyCaptions and the render tail).
// V2-638 — it now speaks to a plain <video> as well as to the YouTube embed, translating the IFrame API's
// vocabulary into media-element operations. Teaching the funnel instead of the five call sites is what keeps
// local/torrent playback from needing a parallel copy of every control (the V2-539 "wire both channels" trap,
// avoided by having only one wire): pause, volume, seek and the queue jump all work unchanged.
export function post(target, func, args){
  try{
    if(!target) return;
    if(String(target.tagName || "").toLowerCase() === "video"){
      const a = args || [];
      if(func === "playVideo"){ const p = target.play(); if(p && p.catch) p.catch(function(){}); }
      else if(func === "pauseVideo") target.pause();
      else if(func === "mute") target.muted = true;
      else if(func === "unMute") target.muted = false;
      else if(func === "setVolume") target.volume = Math.max(0, Math.min(100, Number(a[0]) || 0)) / 100;
      else if(func === "seekTo") target.currentTime = Math.max(0, Number(a[0]) || 0);
      // loadModule/unloadModule are captions: a local file carries no track list we can switch, so there is
      // nothing honest to do — silently ignored rather than faked.
      return;
    }
    if(!target.contentWindow) return;
    if(func === "unMute") Y.soundAsked = Date.now();      // V2-791: the grace before a muted report is a verdict
    target.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*");
  }catch(_){}
}

// V2-791 — sound ordered on a page that has had no gesture: unmuting an autoplaying cross-origin player now could
// PAUSE it. It keeps playing muted, the card REPORTS the block (`player_audio` → `audio_blocked`), and the first
// gesture anywhere on the page gives it sound. True when it is holding the player silent.
export function holdSilent(iframe, data){
  if(pageMayPlaySound() || !iframe || !iframe.contentWindow) return false;
  if(Y.ytAudio) Y.ytAudio(true, "");
  armSoundUnlock(Number(data.volume != null ? data.volume : 70));
  return true;
}

// Reassert desired state in the player (idempotent) — used when loading a new video.
export function applyState(iframe, data, ctx){
  if(data.muted){ post(iframe, "mute", []); }
  else if(holdSilent(iframe, data)){ post(iframe, "mute", []); }      // V2-791: no gesture yet (see holdSilent)
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
export function applyCaptions(iframe, data){
  if(data.captions){ post(iframe, "loadModule", ["captions"]); post(iframe, "loadModule", ["cc"]); }
  else { post(iframe, "unloadModule", ["captions"]); post(iframe, "unloadModule", ["cc"]); }
}

// Apply the LAST command requested by voice/click (only when cmd_seq advances).
export function applyCmd(iframe, data, ctx){
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
  // V2-791 — a voice order is no gesture: on a page that has had none, the block is REPORTED (holdSilent) rather
  // than the store left claiming a sound the player cannot have; the next gesture on the page completes it.
  else if(c === "unmute" || c === "volume_up" || c === "volume_down" || c === "set_volume"){
    if(data.muted || !holdSilent(iframe, data)){ post(iframe, "unMute", []); post(iframe, "setVolume", [vol]); }
  }
  else if(c === "captions_on" || c === "captions_off"){ applyCaptions(iframe, data); }
  else if(c === "restart"){ post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []); }
  // A queue jump normally lands as a NEW videoId (card rebuild); when the target is the SAME video (a list
  // with the current one repeated after a manual load) nothing rebuilds — treat it as a restart.
  else if(c === "next" || c === "previous" || c === "play_item"){
    post(iframe, "seekTo", [0, true]); post(iframe, "playVideo", []);
  }
}

// The player element for the video being built: a <video> for our own streams, the YouTube embed otherwise,
// or the «searching» / placeholder face (moved out of render(), refactor2710-12 T-03).
export function buildFrame(data, ctx, loading, isStream, src, id){
  const frame = el("div", "hb-yt-frame");
  let iframe = null;
  let video = null;
  let unmuteHint = null;
  if(loading){
    const box = el("div", "hb-yt-loading");
    box.appendChild(el("div", "hb-yt-spin"));
    box.appendChild(el("div", "", data.loading_query ? tt("searching_q", {q:data.loading_query}, `Buscando «${data.loading_query}»…`) : tt("searching", null, "Buscando…")));
    frame.appendChild(box);
  } else if(isStream){
    // V2-638 — a file we hold (library) or one still arriving (torrent). Same element either way: the
    // difference is only which route serves the bytes, and both answer Range, so seeking works on both.
    // The src is set ONCE here and never re-assigned on a re-render (the V2-124/4.19 rule) — the rebuild
    // key above is what changes it, by rebuilding the card.
    video = document.createElement("video");
    video.className = "hb-yt-video";
    video.controls = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.title = data.title || "";
    // Our own routes only — never an arbitrary origin (the mensajeria boundary, V2-620).
    if(src.startsWith("/api/library/") || src.startsWith("/api/torrent/")) video.src = src;
    if(!data.paused && !halted(ctx)){ try{ video.play().catch(function(){}); }catch(_){} }
    const c1 = ctx;
    video.addEventListener("ended", function(){ try{ c1.action("ended"); }catch(_){} });
    frame.appendChild(video);
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
    unmuteHint.appendChild(el("span", "", tt("tap_unmute", null, "Toca para activar el sonido")));
    frame.appendChild(unmuteHint);
  }
  else {
    // V2-632 — the PLACEHOLDER: with no video the player tab still shows WHERE the video will live
    // (operator: «que se vea que ese es el lugar donde eso se va a representar»).
    const ph = el("div", "hb-yt-empty");
    const inner = el("div", "");
    inner.appendChild(el("div", "hb-yt-empt-ico", "▶"));
    inner.appendChild(el("div", "", tt("no_video_hint", null, "Sin vídeo — di «pon el vídeo de…» o busca desde Inicio.")));
    ph.appendChild(inner);
    frame.appendChild(ph);
  }
  return {frame, iframe, video, unmuteHint};
}

export function bindReporters(data, ctx, id, PL){
  const vol0 = Number(data.volume != null ? data.volume : 70);
  // The queue advances because the player told us the video ended — refreshed every render so the callback
  // always carries the CURRENT ctx. Gated on halted: a stopped agent starts no playback (V2-092).
  Y.ytEnded = () => { if(ctx && ctx.action && !halted(ctx)) ctx.action("ended"); };
  // V2-634: the report names WHICH video failed — the store swaps the current one for the next playable
  // candidate, and a late onError for an already-replaced video must not be attributed to its successor.
  Y.ytError = (code) => { if(ctx && ctx.action) ctx.action("player_error",
      {code: String(code == null ? "unknown" : code), videoId: id || ""}); };
  Y.ytQuality = (levels, vid) => {
    if(ctx && ctx.action) ctx.action("player_quality", {levels: Array.isArray(levels) ? levels : [], videoId: vid || ""});
  };
  // V2-791 — the player's real sound against what the store says was ordered. Sound wanted and the player still
  // muted past the grace → `audio_blocked` (the hint stays, the brain is told); heard → the flag clears.
  Y.plNow = PL;
  if(data.audio_blocked && !data.muted && data.videoId && !halted(ctx)) armSoundUnlock(vol0);
  Y.ytAudio = (playerMuted, vid) => {
    if(!ctx || !ctx.action || halted(ctx) || !data.videoId) return;
    if(vid && vid !== data.videoId) return;
    let report = null;
    if(playerMuted && !data.muted && !data.audio_blocked){
      if(Date.now() - Y.soundAsked < _SOUND_GRACE_MS && pageMayPlaySound()) return;
      report = true;
    } else if(!playerMuted && (data.audio_blocked || data.muted)){
      report = false;
    }
    if(report === null) return;
    const key = data.videoId + "|" + report + "|" + (data.cmd_seq || 0);
    if(key === Y.audioSent) return;
    Y.audioSent = key;
    ctx.action("player_audio", {muted: report, videoId: data.videoId});
  };
}

// youtube widget — the control bar and the now-playing lines (title, block notice, metadata).
// Part of the client split out of widget.js (refactor2710-12 T-03); widget.js stays the entry with render().
import { ICON_PREV, ICON_NEXT, ICON_PLAY, ICON_PAUSE, ICON_VOL_DOWN, ICON_VOL_UP, ICON_MUTED, svgEl, el,
  halted, tt } from "./shared.js";
import { post } from "./player.js";

export function buildControls(ctx, body){
  // Click controls (mirror of what can also be requested by voice) - ICON buttons since V2-636
  // («no sé si es necesario el texto Play en un botón de play»), the music widget's bar language.
  const ctrls = el("div", "hb-yt-ctrls");
  const icbtn = (cls, markup, titleTxt, action) => {
    const b = el("button", "hb-yt-cbtn" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(markup));
    b.title = titleTxt;
    if(action) b.addEventListener("click", () => { if(ctx && ctx.action) ctx.action(action); });
    return b;
  };
  ctrls.appendChild(icbtn("", ICON_PREV, tt("prev", null, "Anterior"), "previous"));
  const playBtn = icbtn("main", ICON_PLAY, tt("play", null, "Play"));  // face + action follow data.paused on each render
  ctrls.appendChild(playBtn);
  ctrls.appendChild(icbtn("", ICON_NEXT, tt("next", null, "Siguiente"), "next"));
  ctrls.appendChild(icbtn("", ICON_VOL_DOWN, tt("vol_down", null, "Bajar volumen"), "volume_down"));
  ctrls.appendChild(icbtn("", ICON_VOL_UP, tt("vol_up", null, "Subir volumen"), "volume_up"));
  const muteBtn = icbtn("", ICON_MUTED, tt("mute", null, "Silencio"));  // face/action are set on each render (toggle)
  ctrls.appendChild(muteBtn);
  const vol = el("div", "hb-yt-vol", "");
  ctrls.appendChild(vol);
  body.appendChild(ctrls);

  body.appendChild(el("div", "hb-yt-hint", tt("voice_hint", null,
    "Por voz: «pon el vídeo de…», «búscame vídeos de…» (salen en Inicio), «reproduce el tercero», «siguiente», «pausa», «sigue a este canal».")));
  return {playBtn, muteBtn, vol};
}

export function paintPlayer(E, data, ctx, id, PL){
  if(E.title) E.title.textContent = data.title || (id ? "YouTube" : tt("no_video", null, "Sin vídeo"));
  if(E.blockMsg){
    const bn = data.blocked_notice || {};
    let msg = "";
    if(bn.kind === "swapped")
      msg = tt("blocked_swapped", {from: bn.from || "", to: bn.to || ""},
               "«{from}» está bloqueado por su propietario para reproducirse aquí — pongo el siguiente: «{to}».");
    else if(bn.kind === "explicit")
      msg = tt("blocked_explicit", {from: bn.from || ""},
               "Su propietario bloquea la reproducción fuera de YouTube — este vídeo solo puede verse allí.");
    else if(bn.kind === "channel_blocked")     // a pasted link from a channel he blocked: it plays, and says so
      msg = tt("blocked_channel_link", {channel: bn.channel || ""},
               "Lo pongo porque lo has pegado tú, aunque es de «{channel}», un canal que tienes bloqueado.");
    else if(bn.kind === "exhausted")
      msg = tt("blocked_exhausted", {from: bn.from || ""},
               "«{from}» está bloqueado por su propietario y no encontré sustituto — dime otra búsqueda.");
    E.blockMsg.textContent = msg;
    E.blockMsg.style.display = msg ? "" : "none";
  }
  if(E.meta){
    const bits = [];
    if(data.channel) bits.push(data.channel);
    if(data.published) bits.push(data.latest ? tt("latest_date", {date: data.published}, "más reciente · {date}") : data.published);
    E.meta.textContent = bits.join("  ·  ");
    E.meta.style.display = bits.length ? "" : "none";
  }
  const vol0 = Number(data.volume != null ? data.volume : 70);
  if(E.playBtn){
    // ONE toggle, like the music bar: face shows what a click will DO (paused -> play triangle).
    E.playBtn.textContent = "";
    E.playBtn.appendChild(svgEl(data.paused ? ICON_PLAY : ICON_PAUSE));
    E.playBtn.title = data.paused ? tt("play", null, "Play") : tt("pause", null, "Pausa");
    E.playBtn.onclick = () => { if(ctx && ctx.action) ctx.action(data.paused ? "play" : "pause"); };
  }
  if(E.muteBtn){
    E.muteBtn.textContent = "";
    E.muteBtn.appendChild(svgEl(data.muted ? ICON_VOL_UP : ICON_MUTED));
    E.muteBtn.title = data.muted ? tt("sound", null, "Sonido") : tt("mute", null, "Silencio");
    E.muteBtn.onclick = () => {
      // Direct `post` (does not go through the server: it is the REAL click that unlocks browser audio) is also gated
      // — otherwise, with the agent stopped, this button would make the video play through the back door.
      if(data.muted && !halted(ctx)){ post(PL, "unMute", []); post(PL, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action(data.muted ? "unmute" : "mute");
    };
  }
  if(E.unmuteHint){
    // V2-791 — also while the browser keeps an ORDERED sound silent: the hint is the honest state of the player.
    E.unmuteHint.style.display = (data.muted || (data.audio_blocked && data.videoId)) ? "flex" : "none";
    E.unmuteHint.onclick = () => {
      if(!halted(ctx)){ post(PL, "unMute", []); post(PL, "setVolume", [vol0]); }
      if(ctx && ctx.action) ctx.action("unmute");
    };
  }
  if(E.vol) E.vol.textContent = data.muted ? "—" : ((data.volume != null ? data.volume : 70) + "%");
}

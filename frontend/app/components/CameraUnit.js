// CameraUnit — draggable camera + voice-control unit (top-left by default). Camera
// preview with the voice spectrum (#viz) OVERLAID inside it (Google-Meet style); when
// the camera is off the SAME square stays, showing a crossed-camera icon centred. The
// control row below carries the mic + camera toggles and, set apart, the chat toggle.
import { h, raw } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import { makeDraggable } from "../lib/draggable.js?v=2";

const DRAG_SVG = `<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><circle cx="2.5" cy="2.5" r="1.3"/><circle cx="7" cy="2.5" r="1.3"/><circle cx="11.5" cy="2.5" r="1.3"/><circle cx="2.5" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11.5" cy="7" r="1.3"/><circle cx="2.5" cy="11.5" r="1.3"/><circle cx="7" cy="11.5" r="1.3"/><circle cx="11.5" cy="11.5" r="1.3"/></svg>`;
const MIC_SVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const CAM_SVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M15 10l6-3v10l-6-3"/></svg>`;
const CHAT_SVG = `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
// big crossed-out camera shown centred inside the square when the camera is off
const CAMOFF_SVG = `<svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M15 10l6-3v10l-6-3"/><path d="M2 2l20 20"/></svg>`;

export function CameraUnit() {
  let meEl, dragEl;
  const me = h("div", { id: "me", ref: el => (meEl = el), class: () => "me" + (store.camOff() ? " cam-off" : "") },
    h("div", { class: "cam" },
      // muted MUST be set as the .muted PROPERTY, not the attribute: this <video> carries the mic's audio track
      // (srcObject = the mic+cam stream), and a JS-set `muted` attribute is ignored by Chrome → it would play your
      // own mic back through the speakers (the "echo"). Setting el.muted here is what actually silences local playback.
      h("video", { id: "cam", ref: el => { el.muted = true; session.attachVideo(el); }, autoplay: true, playsinline: true, muted: true }),
      h("div", { class: "camoff", style: { display: () => (store.camOff() ? "flex" : "none") } }, raw(CAMOFF_SVG)),
      h("div", { id: "camph", class: "camph", style: { display: () => (!store.started() && !store.camOff() ? "flex" : "none") } }, "camera off"),
      h("canvas", { id: "viz" }),                                  // voice spectrum, overlaid along the bottom edge
      h("button", { class: "drag", id: "drag", ref: el => (dragEl = el), title: "Move" }, raw(DRAG_SVG)),
    ),
    h("div", { class: "ctrl" },
      h("button", {
        class: () => "mtog" + (store.micMuted() ? " off" : ""), id: "micToggle",
        title: () => (store.micMuted() ? "Turn on mic" : "Mute mic"), "aria-label": "Mute mic",
        onClick: () => session.toggleMic(),
      }, raw(MIC_SVG)),
      h("button", {
        class: () => "mtog" + (store.camOff() ? " off" : ""), id: "camToggle",
        title: () => (store.camOff() ? "Turn on camera" : "Turn off camera"), "aria-label": "Turn off camera",
        onClick: () => session.toggleCam(),
      }, raw(CAM_SVG)),
      h("div", { class: "ctrl-sp" }),                              // spacer: sets the chat toggle apart
      h("button", {
        class: () => "mtog chat" + (store.chatOpen() ? " active" : ""), id: "chatToggle",
        title: "Text chat with the agent", "aria-label": "Open chat",
        onClick: () => store.setChatOpen(!store.chatOpen()),
      }, raw(CHAT_SVG)),
    ),
    h("div", {
      id: "spk", title: "Your voice recognition · click to retrain",
      class: () => "spk" + (store.spk().show ? " show" : "") + (store.spk().other ? " other" : ""),
      html: () => store.spk().html, onClick: () => session.retrain(),
    }),
  );
  makeDraggable(meEl, dragEl, "hb_pos_cam", "tl");   // drag ONLY by the move grip (the dots icon), not the whole box
  return me;
}

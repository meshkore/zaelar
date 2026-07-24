// ChatWall — text channel to the agent, for when you'd rather type than talk. Toggled by the chat icon in the
// CameraUnit (store.chatOpen). Messages you send go through session.sendText → data channel → the server's
// ClientTextInjector, which turns them into a normal user turn (so the agent replies by voice as usual).
//
// WINDOW BEHAVIOUR (V2-062): MOVABLE (drag by the header) + RESIZABLE from ANY edge/corner (8 handles, lib/
// resizable.js — native CSS `resize` only gave the bottom-right corner) + DOCKABLE: drag it to the far left/right
// edge and it snaps to a FULL-HEIGHT side column (the rest is empty canvas); drag the header away to pop back to a
// floating window. Floating geometry persists under FLOAT_KEY; the docked side+width under DOCK_KEY. First open
// auto-places like a widget (below the camera if it fits, else beside it, else on top).
//
// A Ctrl+V anywhere on the page (see main.js) ALSO feeds this channel — pasted text reaches the agent even while
// this panel is hidden; it just shows up here, recorded, the next time you open it.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=2";
import { makeResizable } from "../lib/resizable.js?v=1";
import { CLOSE_ICON } from "../lib/icons.js?v=1";
import { renderMarkdownLite } from "../lib/markdown-lite.js?v=1";

const SEND_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`;
const FLOAT_KEY = "hb_chat_float", DOCK_KEY = "hb_chat_dock";
const DOCK_PX = 34, MIN_W = 260, MIN_H = 200, DOCK_MIN_W = 240, DOCK_DEF_W = 340;

const _num = (v, d) => (typeof v === "number" && isFinite(v) ? v : d);
function loadFloat() {
  try { const s = JSON.parse(localStorage.getItem(FLOAT_KEY) || "null"); if (s && s.w && s.h) return s; } catch (_) {}
  return null;
}
function loadDock() {
  try { const d = JSON.parse(localStorage.getItem(DOCK_KEY) || "null"); if (d && (d.side === "left" || d.side === "right")) return d; } catch (_) {}
  return null;
}

// Send a message both to the agent and to the on-screen log. Used by the input AND by the paste handler.
export function submitChat(text) {
  const t = (text || "").trim(); if (!t) return;
  session.sendText(t);
  store.pushChat({ role: "you", text: t });
}

// Auto-place like a widget: below the camera unit if it fits, else to its right, else overlapping (on top).
function placeWall(el) {
  const pad = 14, gap = 14, me = document.querySelector("#me");
  const r = me ? me.getBoundingClientRect() : { left: 18, right: 230, top: 16, bottom: 216 };
  const w = el.offsetWidth || 320, hh = el.offsetHeight || Math.min(innerHeight * 0.6, 520);
  const set = (x, y) => { el.style.right = "auto"; el.style.bottom = "auto"; el.style.left = Math.max(pad, x) + "px"; el.style.top = Math.max(pad, y) + "px"; };
  if (r.bottom + gap + hh <= innerHeight - pad) return set(r.left, r.bottom + gap);   // 1) below the camera
  if (r.right + gap + w <= innerWidth - pad) return set(r.right + gap, r.top);        // 2) beside it (right)
  set(Math.min(r.left, innerWidth - w - pad), r.top);                                 // 3) no room → on top
}

export function ChatWall() {
  let listEl, inputEl, headEl, wallEl, previewEl = null;
  let dockSide = null;                         // null | "left" | "right"
  let floatGeo = loadFloat();                  // {left,top,w,h} of the FLOATING window (last known)

  const send = () => { if (!inputEl) return; submitChat(inputEl.value); inputEl.value = ""; inputEl.focus(); };

  const wall = h("div", { id: "chatwall", ref: el => (wallEl = el), class: () => "chatwall" + (store.chatOpen() ? " open" : "") },
    h("div", { class: "cw-head", ref: el => (headEl = el) },
      h("span", { class: "cw-title" }, "Chat"),
      h("button", { class: "cw-x hb-icbtn", title: "Cerrar", onClick: () => store.setChatOpen(false) }, raw(CLOSE_ICON)),
    ),
    h("div", { class: "cw-list", ref: el => (listEl = el) }),
    h("div", { class: "cw-input" },
      h("textarea", {
        ref: el => (inputEl = el), rows: 1, placeholder: "Escribe al agente…",
        onKeydown: e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } },
      }),
      h("button", { class: "cw-send", title: "Enviar", onClick: send }, raw(SEND_SVG)),
    ),
  );

  // MODO CHAT = VOZ OFF (V2-054 T1.1/T1.2): al ABRIR el chat apagamos la voz de zaelar — icono del altavoz a OFF
  // (mute cliente) + señal al server para NO sintetizar TTS. Al CERRAR, restauramos el estado del altavoz PREVIO.
  let _prevMuted = null;
  createEffect(() => {
    const open = store.chatOpen();
    if (open) {
      if (_prevMuted === null) _prevMuted = store.botMuted();
      if (!store.botMuted()) session.toggleBotMute();
      session.setVoiceOutput(false);
    } else if (_prevMuted !== null) {
      if (store.botMuted() !== _prevMuted) session.toggleBotMute();
      // BUG real 2026-07-23: aquí ponía `setVoiceOutput(!_prevMuted)` — acoplaba la síntesis TTS del SERVER (una
      // cosa) al mute del altavoz del CLIENTE (otra cosa totalmente independiente). Si el operador ya tenía el
      // 🔊 apagado ANTES de abrir el chat (o si `hb_bot_muted` venía "1" de una sesión anterior en localStorage),
      // `_prevMuted` era `true` → al cerrar el chat se llamaba `setVoiceOutput(false)` OTRA VEZ → la síntesis se
      // quedaba apagada en el server para el resto de la sesión, y NADA en la UI la reactivaba (el icono 🔊 solo
      // toca el mute del cliente, nunca `setVoiceOutput`) — exactamente "sigue transcribiendo pero no habla".
      // El chat cerrado SIEMPRE debe restaurar la síntesis del server; el mute del altavoz es un asunto aparte.
      session.setVoiceOutput(true);
      _prevMuted = null;
    }
    setReserve();          // closing releases the reserved strip; reopening while docked re-applies it
  });

  // ── geometría: flotante ↔ dock ────────────────────────────────────────────────────────────────────────────
  function defaultFloat() { return { left: 18, top: 232, w: 320, h: Math.min(Math.round(innerHeight * 0.6), 520) }; }

  function applyFloat(geo) {
    floatGeo = geo || floatGeo || defaultFloat();
    dockSide = null;
    wallEl.classList.remove("docked", "dock-left", "dock-right");
    wallEl.style.right = "auto"; wallEl.style.bottom = "auto";
    wallEl.style.left = _num(floatGeo.left, 18) + "px"; wallEl.style.top = _num(floatGeo.top, 232) + "px";
    wallEl.style.width = _num(floatGeo.w, 320) + "px"; wallEl.style.height = _num(floatGeo.h, 480) + "px";
    try { localStorage.setItem(FLOAT_KEY, JSON.stringify(floatGeo)); localStorage.removeItem(DOCK_KEY); } catch (_) {}
    setReserve();
  }

  function saveFloatFromEl() {
    const r = wallEl.getBoundingClientRect();
    floatGeo = { left: Math.round(r.left), top: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    dockSide = null;
    try { localStorage.setItem(FLOAT_KEY, JSON.stringify(floatGeo)); localStorage.removeItem(DOCK_KEY); } catch (_) {}
    setReserve();
  }

  function applyDock(side, w) {
    dockSide = side;
    const width = Math.max(DOCK_MIN_W, _num(w, DOCK_DEF_W));
    wallEl.classList.add("docked");
    wallEl.classList.toggle("dock-left", side === "left");
    wallEl.classList.toggle("dock-right", side === "right");
    // top/bottom/height are forced full-height by CSS (.chatwall.docked !important); here only the WIDTH + side.
    wallEl.style.height = ""; wallEl.style.top = ""; wallEl.style.bottom = "";
    wallEl.style.width = width + "px";
    if (side === "left") { wallEl.style.left = "0px"; wallEl.style.right = "auto"; }
    else { wallEl.style.left = "auto"; wallEl.style.right = "0px"; }
    try { localStorage.setItem(DOCK_KEY, JSON.stringify({ side, w: width })); } catch (_) {}
    setReserve();
  }

  // dock preview bar while dragging near an edge
  function showPreview(side) {
    if (!side) return hidePreview();
    if (!previewEl) { previewEl = document.createElement("div"); previewEl.className = "hb-dock-preview"; document.body.appendChild(previewEl); }
    const w = (loadDock() || {}).w || DOCK_DEF_W;
    previewEl.style.width = Math.max(DOCK_MIN_W, w) + "px";
    previewEl.classList.toggle("left", side === "left");
    previewEl.classList.toggle("right", side === "right");
    previewEl.style.display = "block";
  }
  function hidePreview() { if (previewEl) previewEl.style.display = "none"; }

  // RESERVA de espacio: cuando el chat está ABIERTO y acoplado, el escritorio se desplaza a la zona libre (clases
  // + vars que consume styles.css, mismo patrón que --dbg-w). Se libera al flotar, cerrar o des-acoplar.
  function setReserve() {
    const root = document.documentElement, body = document.body;
    body.classList.remove("chatdock-l", "chatdock-r");
    if (store.chatOpen() && dockSide) {
      const w = Math.round(wallEl.offsetWidth || DOCK_DEF_W);
      root.style.setProperty("--chatdock-l", dockSide === "left" ? w + "px" : "0px");
      root.style.setProperty("--chatdock-r", dockSide === "right" ? w + "px" : "0px");
      body.classList.add(dockSide === "left" ? "chatdock-l" : "chatdock-r");
    } else {
      root.style.setProperty("--chatdock-l", "0px");
      root.style.setProperty("--chatdock-r", "0px");
    }
  }

  // ── MOVABLE by the header, with dock/undock ───────────────────────────────────────────────────────────────
  headEl.style.touchAction = "none";
  let drag = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0, pid = null, preview = null;
  headEl.addEventListener("pointerdown", e => {
    if (e.target.closest(".cw-x")) return;             // the close button is not a drag handle
    drag = true; moved = false; pid = e.pointerId; sx = e.clientX; sy = e.clientY;
  });
  headEl.addEventListener("pointermove", e => {
    if (!drag) return;
    if (!moved) {
      if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) <= 4) return;
      moved = true; wallEl.classList.add("hb-dragging");
      try { headEl.setPointerCapture(pid); } catch (_) {}
      wallEl.style.right = "auto"; wallEl.style.bottom = "auto";
      if (dockSide) {                                  // UNDOCK: pop back to a floating box, recentred under pointer
        const g = floatGeo || defaultFloat();
        wallEl.classList.remove("docked", "dock-left", "dock-right");
        wallEl.style.width = g.w + "px"; wallEl.style.height = g.h + "px";
        dockSide = null; setReserve();                 // release the reserved strip as it becomes floating
        ox = Math.max(0, Math.min(e.clientX - g.w / 2, innerWidth - g.w));
        oy = Math.max(0, Math.min(e.clientY - 16, innerHeight - g.h));
        sx = e.clientX; sy = e.clientY;                // deltas start fresh from here
      } else {                                         // normal float drag: keep the box under the grab point
        const rr = wallEl.getBoundingClientRect();
        ox = rr.left; oy = rr.top;                     // sx/sy stay from pointerdown → 1:1 tracking
      }
    }
    const x = Math.max(0, Math.min(ox + (e.clientX - sx), innerWidth - wallEl.offsetWidth));
    const y = Math.max(0, Math.min(oy + (e.clientY - sy), innerHeight - wallEl.offsetHeight));
    wallEl.style.left = x + "px"; wallEl.style.top = y + "px";
    preview = (e.clientX <= DOCK_PX) ? "left" : (e.clientX >= innerWidth - DOCK_PX) ? "right" : null;
    showPreview(preview);
  });
  const endDrag = () => {
    if (!drag) return; drag = false; wallEl.classList.remove("hb-dragging");
    if (!moved) return;
    hidePreview();
    if (preview) applyDock(preview, (loadDock() || {}).w || Math.round(wallEl.offsetWidth));
    else saveFloatFromEl();
    preview = null;
  };
  headEl.addEventListener("pointerup", endDrag);
  headEl.addEventListener("pointercancel", endDrag);

  // ── RESIZABLE from any edge/corner. Docked: only the inner edge is live (CSS) → it sets the column width. ──
  makeResizable(wallEl, {
    minW: MIN_W, minH: MIN_H,
    onChange: (rect) => {
      if (dockSide) {
        const width = Math.max(DOCK_MIN_W, Math.round(rect.width));
        wallEl.style.width = width + "px"; wallEl.style.top = ""; wallEl.style.bottom = ""; wallEl.style.height = "";
        if (dockSide === "left") { wallEl.style.left = "0px"; wallEl.style.right = "auto"; }
        else { wallEl.style.left = "auto"; wallEl.style.right = "0px"; }
        try { localStorage.setItem(DOCK_KEY, JSON.stringify({ side: dockSide, w: width })); } catch (_) {}
        setReserve();                                  // column width changed → update the reserved strip
      } else {
        saveFloatFromEl();
      }
    },
  });

  // ── restore geometry ────────────────────────────────────────────────────────────────────────────────────
  // ABRIR = SIEMPRE ventana flotante (lo que el operador espera). El dock es un GESTO de sesión (arrastrar al
  // borde), no un estado que se restaura roto al recargar. Restauramos la última posición/tamaño flotante, o
  // auto-colocamos como un widget la primera vez.
  let placed = false;
  if (floatGeo) { applyFloat(floatGeo); placed = true; }

  // keep a docked column full-height on viewport resize (CSS handles height; width/side stay)
  window.addEventListener("resize", () => { if (dockSide) applyDock(dockSide, wallEl.offsetWidth); });
  setReserve();                                        // apply the reserved strip if we restored a docked state

  // reactive message list: rebuild on every change, then pin to the latest message. Text is rendered through a
  // dependency-free markdown-lite formatter (bold/code/lists) — most SlowBrain/cluster-peer output is markdown and
  // used to show up as raw asterisks/dashes. Cluster peer turns (role:"peer") get their own bubble style + a small
  // attribution label (who/cluster), since they used to share the "agent" bubble with zaelar's own replies.
  createEffect(() => {
    const msgs = store.chatMsgs(); if (!listEl) return;
    listEl.replaceChildren(...msgs.map(m => {
      const cls = m.role === "peer" ? "peer" : m.role === "agent" ? "agent" : m.role === "sys" ? "sys" : "you";
      const bubble = h("div", { class: "cw-msg " + cls });
      if (m.role === "peer" && (m.dir === "in" || m.dir === "out")) {
        const who = m.dir === "out" ? `🛰 → ${m.peer || "?"}` : `🛰 ${m.peer || "?"}`;
        bubble.appendChild(h("div", { class: "cw-msg-from" }, m.cluster ? `${who} · ${m.cluster}` : who));
      } else if (m.role === "peer") {
        bubble.appendChild(h("div", { class: "cw-msg-from" }, "🛰"));
      }
      bubble.appendChild(raw(`<div class="cw-msg-body">${renderMarkdownLite(m.text)}</div>`));
      return bubble;
    }));
    listEl.scrollTop = listEl.scrollHeight;
  });

  // on first open with NO saved geometry: auto-place like a widget, then focus the input
  createEffect(() => {
    if (!store.chatOpen()) return;
    if (!placed) requestAnimationFrame(() => { placeWall(wallEl); placed = true; });
    if (inputEl) inputEl.focus();
  });

  return wall;
}

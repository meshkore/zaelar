// ChatWall — panel vertical del agente con TRES pestañas (V2-079): «Chat» (escribir al agente), «Procesos»
// (Brain Workers vivos + histórico de lo ejecutado hoy/ayer/hace días) y «Crons» (tareas programadas). Toggled by
// store.chatOpen; la pestaña activa vive en store.chatTab (así el botón ⏰ del orbe puede abrirlo directo en «Crons»).
// El chat va por session.sendText → data channel → ClientTextInjector (turno de usuario normal, el agente responde
// por voz). Antes esto era solo el muro de chat; «Procesos» y «Crons» le dan al operador PERSPECTIVA de lo que el
// sistema está haciendo y ha hecho (los hexágonos son el "ahora"; esta pestaña es "ahora + histórico").
//
// WINDOW BEHAVIOUR (V2-062): MOVABLE (drag by the header) + RESIZABLE from ANY edge/corner (8 handles, lib/
// resizable.js) + DOCKABLE: drag it to the far left/right edge and it snaps to a FULL-HEIGHT side column. Floating
// geometry persists under FLOAT_KEY; the docked side+width under DOCK_KEY.
//
// A Ctrl+V anywhere on the page (see main.js) ALSO feeds the chat channel — pasted text reaches the agent even
// while this panel is hidden; it shows up here the next time you open it.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import { makeResizable } from "../lib/resizable.js?v=1";
import { CLOSE_ICON, TRASH_ICON } from "../lib/icons.js?v=1";
import { renderMarkdownLite } from "../lib/markdown-lite.js?v=1";
import { t } from "../core/i18n.js?v=1";

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

// tiempo relativo compacto para el histórico de procesos (finished_at en epoch segundos, como Python time.time()).
function ago(ts) {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - Number(ts));
  if (s < 60) return t("chat.agoNow");
  if (s < 3600) return t("chat.agoMinutes", { n: Math.floor(s / 60) });
  if (s < 86400) return t("chat.agoHours", { n: Math.floor(s / 3600) });
  const d = Math.floor(s / 86400);
  return d === 1 ? t("chat.agoYesterday") : t("chat.agoDays", { n: d });
}

export function ChatWall() {
  let listEl, inputEl, headEl, wallEl, previewEl = null;
  let schedEl, cnameEl, cpromptEl;             // refs del formulario de crear cron (pestaña Crons)
  let dockSide = null;                         // null | "left" | "right"
  let floatGeo = loadFloat();                  // {left,top,w,h} of the FLOATING window (last known)

  const send = () => { if (!inputEl) return; submitChat(inputEl.value); inputEl.value = ""; inputEl.focus(); };

  // ── Pestaña PROCESOS: vivos (store.tasks, SSE) arriba + histórico (store.workerHistory, ledger) debajo ──────
  const liveRow = (task) => {
    const icon = task.waiting ? "waiting" : task.paused ? "paused" : "run";
    const gl = task.waiting ? "⏳" : task.paused ? "⏸" : "●";
    return h("div", { class: "cw-proc-row live " + icon },
      h("span", { class: "cw-proc-dot" }, gl),
      h("div", { class: "cw-proc-main" },
        h("div", { class: "cw-proc-goal" }, task.text || t("chat.working")),
        h("div", { class: "cw-proc-meta" }, (typeof task.pct === "number" && task.pct >= 0 ? task.pct + "% · " : "") + t("chat.running")),
      ),
    );
  };
  const histRow = (e) => {
    // `interrumpido` = se la llevó por delante un reinicio (rehidratación, nucleo/rehydrate.py). Tiene su propio
    // glifo porque antes CUALQUIER estado desconocido caía a "done" con un ✓: una tarea que murió a medias se
    // pintaba como terminada con éxito. Un registro que miente es peor que no tenerlo.
    const st = e.status === "error" ? "error" : e.status === "cancelled" ? "cancelled"
             : e.status === "interrumpido" ? "cut" : (e.ok || e.status === "done") ? "done" : "done";
    const gl = st === "error" ? "✕" : st === "cancelled" ? "⊘" : st === "cut" ? "✂" : "✓";
    const meta = [e.kind, ago(e.finished_at)].filter(Boolean).join(" · ");
    return h("div", { class: "cw-proc-row hist " + st },
      h("span", { class: "cw-proc-dot" }, gl),
      h("div", { class: "cw-proc-main" },
        h("div", { class: "cw-proc-goal" }, e.goal || e.kind || e.id),
        h("div", { class: "cw-proc-meta" }, meta + (e.cron ? t("chat.fromCron", { name: e.cron }) : "")),
      ),
    );
  };
  const procBody = () => {
    const live = store.tasks() || [];
    const hist = (store.workerHistory() || []).filter(e => !live.some(t => String(t.id) === String(e.id)));
    if (!live.length && !hist.length) {
      return h("div", { class: "cw-empty" }, () => t("chat.procEmpty"));
    }
    const out = [];
    if (live.length) out.push(h("div", { class: "cw-proc-sec" }, () => t("chat.sectionRunning")), ...live.map(liveRow));
    if (hist.length) out.push(h("div", { class: "cw-proc-sec" }, () => t("chat.sectionHistory")), ...hist.map(histRow));
    return out;
  };

  // ── Pestaña CRONS: lista + crear/borrar (funde el antiguo CronPanel; misma API /api/cron) ───────────────────
  const refreshCrons = async () => { const r = await api.cronList(); store.setCronJobs(r.jobs || []); };
  const cronRemove = async (ref) => { await api.cronAction("remove", ref); await refreshCrons(); };
  const cronAdd = async () => {
    const schedule = (schedEl.value || "").trim(); if (!schedule) return;
    await api.cronCreate({ schedule, prompt: (cpromptEl.value || "").trim(), name: (cnameEl.value || "").trim() });
    schedEl.value = cpromptEl.value = cnameEl.value = "";
    await refreshCrons();
  };
  const cronRow = (j) => h("div", { class: "cron-row" },
    h("div", { class: "cron-main" },
      h("div", { class: "cron-name" }, j.name || j.id),
      h("div", { class: "cron-meta" }, `${j.schedule || "?"} · ${j.paused ? t("chat.paused") : (j.state || t("chat.active"))}` +
        (j.last_status ? t("chat.cronLast", { status: j.last_status }) : "")),
      j.prompt ? h("div", { class: "cron-prompt" }, j.prompt) : null,
    ),
    h("div", { class: "cron-btns" },
      h("button", { class: "cron-b hb-icbtn danger", title: () => t("chat.delete"), onClick: () => cronRemove(j.id) }, raw(TRASH_ICON)),
    ),
  );

  // Una fila de la pestaña CLUSTERS (V2-086). Muestra lo que el operador pidió y nada más: nombre, si estamos
  // dentro, quién hay, y cuánto se ha hablado. El cluster_id se enseña porque NO es secreto (viaja en la propia
  // URL de invitación) y es lo que permite reconocer de cuál se trata; el token nunca sale del backend.
  const clusterRow = (c) => h("div", { class: "cl-row" },
    h("div", { class: "cl-main" },
      h("div", { class: "cl-name" },
        h("span", { class: () => "cl-dot" + (c.connected ? " on" : "") }),
        c.name,
        c.public ? h("span", { class: "cl-badge" }, () => t("chat.public")) : null,
      ),
      h("div", { class: "cl-meta" },
        (c.connected ? t("chat.connected") : t("chat.disconnected"))
        + (c.handle ? t("chat.clusterAs", { handle: c.handle }) : "")
        + (c.online && c.online.length
            ? (c.online.length > 1
                ? t("chat.clusterPeers", { n: c.online.length, list: c.online.join(", ") })
                : t("chat.clusterPeer", { n: c.online.length, list: c.online.join(", ") }))
            : t("chat.clusterNobody"))
        + t("chat.clusterMsgs", { n: c.msgs || 0 })),
      c.cluster_id ? h("div", { class: "cl-id" }, c.cluster_id) : null,
    ),
    h("div", { class: "cl-btns" },
      c.connected
        ? h("button", { class: "cl-b", title: () => t("chat.disconnectBtn"), onClick: () => store.clusterDisconnect(c.name) }, () => t("chat.disconnectBtn"))
        : h("button", { class: "cl-b on", title: () => t("chat.connectBtn"), onClick: () => store.clusterConnect(c.name) }, () => t("chat.connectBtn")),
    ),
  );

  const wall = h("div", { id: "chatwall", ref: el => (wallEl = el), class: () => "chatwall tab-" + store.chatTab() + (store.chatOpen() ? " open" : "") },
    h("div", { class: "cw-head", ref: el => (headEl = el) },
      h("div", { class: "cw-tabs" },
        h("button", { class: () => "cw-tab" + (store.chatTab() === "chat" ? " on" : ""), onClick: () => store.setChatTab("chat") }, () => t("chat.tabChat")),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "procesos" ? " on" : ""), onClick: () => store.setChatTab("procesos") }, () => t("chat.tabProcesses")),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "crons" ? " on" : ""), onClick: () => store.setChatTab("crons") }, () => t("chat.tabCrons")),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "clusters" ? " on" : ""), onClick: () => store.setChatTab("clusters") }, () => t("chat.tabClusters")),
      ),
      h("button", { class: "cw-x hb-icbtn", title: () => t("chat.close"), onClick: () => store.setChatOpen(false) }, raw(CLOSE_ICON)),
    ),
    // CHAT
    h("div", { class: "cw-list", ref: el => (listEl = el) }),
    // PROCESOS
    h("div", { class: "cw-proc" }, procBody),
    // CRONS
    h("div", { class: "cw-crons" },
      h("div", { class: "cron-list" },
        () => (store.cronJobs().length
          ? store.cronJobs().map(cronRow)
          : h("div", { class: "cw-empty" }, () => t("chat.cronsEmpty"))),
      ),
      h("div", { class: "cron-add" },
        h("input", { ref: el => (schedEl = el), class: "cron-in", placeholder: () => t("chat.cronWhenPlaceholder") }),
        h("input", { ref: el => (cnameEl = el), class: "cron-in", placeholder: () => t("chat.cronNamePlaceholder") }),
        h("textarea", { ref: el => (cpromptEl = el), class: "cron-in", rows: 2,
          placeholder: () => t("chat.cronPromptPlaceholder") }),
        h("button", { class: "cron-create", onClick: cronAdd }, () => t("chat.scheduleBtn")),
      ),
    ),
    // CLUSTERS (V2-086) — la RED, nativa. Administración de conexiones, no conversación: los clusters tienen su
    // propio monitor, así que aquí solo se ve a qué red estamos enganchados, con quién y cuánto tráfico ha habido.
    h("div", { class: "cw-clusters" },
      // Confirmación de CONECTAR: gate determinista. Sin un «sí» explícito aquí no se abre ningún socket, por
      // convincente que fuera el texto que lo pidió (V2-064 → V2-086: cambia dónde se pinta, no la garantía).
      () => (store.clusterConfirm()
        ? h("div", { class: "cl-confirm" },
            h("div", { class: "cl-q" }, store.clusterConfirm().question || t("chat.clusterConfirmQ")),
            h("div", { class: "cl-cbtns" },
              h("button", { class: "cl-b on", onClick: () => store.clusterConfirmResolve(true) }, () => t("chat.yesConnect")),
              h("button", { class: "cl-b", onClick: () => store.clusterConfirmResolve(false) }, () => t("chat.no")),
            ))
        : null),
      h("div", { class: "cl-list" },
        () => (store.clusters().length
          ? store.clusters().map(clusterRow)
          : h("div", { class: "cw-empty" }, () => t("chat.clustersEmpty"))),
      ),
    ),
    // INPUT (solo Chat — CSS lo oculta en las otras pestañas)
    h("div", { class: "cw-input" },
      h("textarea", {
        ref: el => (inputEl = el), rows: 1, placeholder: () => t("chat.messagePlaceholder"),
        onKeydown: e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } },
      }),
      h("button", { class: "cw-send", title: () => t("chat.send"), onClick: send }, raw(SEND_SVG)),
    ),
  );

  // Al ENTRAR en una pestaña, refresca sus datos (los vivos ya llegan por SSE; el histórico/crons se piden aquí).
  createEffect(() => {
    const t = store.chatTab();
    if (!store.chatOpen()) return;
    if (t === "procesos") { store.fetchTasks(); store.fetchWorkerHistory(); }
    else if (t === "crons") refreshCrons();
    else if (t === "clusters") store.fetchClusters();
  });
  // Cuando cambian los procesos vivos (una tarea acaba) y estamos mirando «Procesos», refresca el histórico para
  // que la que acaba de terminar baje del bloque "en marcha" al "histórico".
  createEffect(() => {
    store.tasks();
    if (store.chatOpen() && store.chatTab() === "procesos") store.fetchWorkerHistory();
  });

  // CHAT y VOZ son INDEPENDIENTES (V2-088). Abrir este panel NO toca el altavoz, y silenciar el altavoz no toca
  // este panel. Se retira el «modo chat = voz off» de V2-054: partía de que abrir el chat significaba «quiero
  // leer en vez de escuchar», y es FALSO — el panel tiene cuatro pestañas y el operador entra a mirar PROCESOS,
  // CRONS o CLUSTERS sin querer callar a nadie. Cortarle la voz por asomarse a una lista es una decisión que el
  // sistema no tiene por qué tomar por él, y encima le costó una sesión entera creyendo que el TTS estaba roto.
  //
  // Quién silencia: SOLO el icono 🔊 (`session.toggleBotMute`, que avisa al server). Un interruptor, un dueño.
  // El chat NO es un modo, es una VISTA MÁS: la respuesta aparece ahí igual que en los subtítulos y en la voz,
  // las tres a la vez — `pushAgentChat` cuelga del transcript del asistente, que es independiente del audio.
  createEffect(() => {
    store.chatOpen();      // única dependencia: la geometría reservada depende de si está abierto
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

  // RESERVA de espacio: cuando el chat está ABIERTO y acoplado, el escritorio se desplaza a la zona libre.
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
    if (e.target.closest(".cw-x") || e.target.closest(".cw-tab")) return;   // botones (cerrar/pestañas) no arrastran
    drag = true; moved = false; pid = e.pointerId; sx = e.clientX; sy = e.clientY;
  });
  headEl.addEventListener("pointermove", e => {
    if (!drag) return;
    if (!moved) {
      if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) <= 4) return;
      moved = true; wallEl.classList.add("hb-dragging");
      try { headEl.setPointerCapture(pid); } catch (_) {}
      wallEl.style.right = "auto"; wallEl.style.bottom = "auto";
      if (dockSide) {
        const g = floatGeo || defaultFloat();
        wallEl.classList.remove("docked", "dock-left", "dock-right");
        wallEl.style.width = g.w + "px"; wallEl.style.height = g.h + "px";
        dockSide = null; setReserve();
        ox = Math.max(0, Math.min(e.clientX - g.w / 2, innerWidth - g.w));
        oy = Math.max(0, Math.min(e.clientY - 16, innerHeight - g.h));
        sx = e.clientX; sy = e.clientY;
      } else {
        const rr = wallEl.getBoundingClientRect();
        ox = rr.left; oy = rr.top;
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
        setReserve();
      } else {
        saveFloatFromEl();
      }
    },
  });

  // ── restore geometry ────────────────────────────────────────────────────────────────────────────────────
  let placed = false;
  if (floatGeo) { applyFloat(floatGeo); placed = true; }

  window.addEventListener("resize", () => { if (dockSide) applyDock(dockSide, wallEl.offsetWidth); });
  setReserve();

  // reactive CHAT message list: rebuild on every change, then pin to the latest message.
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

  // on first open with NO saved geometry: auto-place like a widget, then focus the input (solo en Chat)
  createEffect(() => {
    if (!store.chatOpen()) return;
    if (!placed) requestAnimationFrame(() => { placeWall(wallEl); placed = true; });
    if (inputEl && store.chatTab() === "chat") inputEl.focus();
  });

  return wall;
}

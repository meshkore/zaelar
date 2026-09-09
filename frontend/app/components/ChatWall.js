// ChatWall — vertical agent panel with FIVE tabs (grown from three at V2-079): “Chat” (write to the agent),
// “Processes” (live Brain Workers + history of what ran today/yesterday/a few days ago), “Crons” (scheduled
// tasks), “Clusters” (V2-086, the native MeshKore network), and “Conectores” (V2-561/V2-526, every connector
// by category — built + wishlist). Toggled by store.chatOpen; the active tab lives in store.chatTab (so the
// orb’s ⏰ button can open it directly on “Crons”). Chat goes through session.sendText → data channel →
// ClientTextInjector (normal user turn; the agent responds by voice). “Processes”/“Crons”/“Clusters”/
// “Conectores” give the operator PERSPECTIVE and REACH beyond conversation (the hexagons are the "now";
// this panel is "now + history + the rest of the system").
//
// WINDOW BEHAVIOUR (V2-062): MOVABLE (drag by the header) + RESIZABLE from ANAnd edge/corner (8 handles, lib/
// resizable.js) + DOCKABLE: drag it to the far left/right edge and it snaps to a FULL-HEIGHT side column. Floating
// geometry persists under FLOAT_KEY; the docked side+width under DOCK_KEY.
//
// A Ctrl+V anywhere on the page (see main.js) ALSO feeds the chat channel — pasted text reaches the agent even
// while this panel is hidden; it shows up here the next time you open it.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import * as feedbackApi from "../services/feedback-api.js?v=1";
import { makeResizable } from "../lib/resizable.js?v=1";
import { CLOSE_ICON, TRASH_ICON, MESSAGE_SQUARE_ICON, ACTIVITY_ICON, CLOCK_ICON, SERVER_ICON, LINK_ICON } from "../lib/icons.js?v=1";
import { renderMarkdownLite } from "../lib/markdown-lite.js?v=1";
import { t } from "../core/i18n.js?v=1";

// V2-561/V2-526 — stable family order (mensajeria -> musica -> archivos -> infra, matching
// connectors/registry.py's descriptors() order), any other family (e.g. a catalog-only "agenda" wishlist
// entry) sorted after, alphabetically, so a family nobody expects does not jump to the top.
const CONN_FAMILY_ORDER = ["mensajeria", "musica", "fotos", "archivos", "infra"];
const connFamilyRank = (f) => { const i = CONN_FAMILY_ORDER.indexOf(f); return i < 0 ? 99 : i; };

const SEND_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`;
// V2-621 — the ONE map from a tab id to its label key: the header's standing name (`.cw-tabname`) and each
// tab button's own label read the same entry, so they cannot drift apart.
const TAB_LABEL = { chat: "chat.tabChat", procesos: "chat.tabProcesses", crons: "chat.tabCrons",
                    clusters: "chat.tabClusters", conectores: "chat.tabConnectors" };
const FLOAT_KEY = "hb_chat_float", DOCK_KEY = "hb_chat_dock", OPEN_KEY = "hb_chat_open";

// WHETHER IT WAS OPEN survives a reload too (V2-550). Its GEOMETRY already did — floating rect under
// FLOAT_KEY, docked side+width under DOCK_KEY — so the operator's report («refresh and the chat wall does not
// stay where it was») was precise in a way worth keeping: the position was never the part that was lost. The
// panel simply came back CLOSED, every time, because `store.chatOpen` is a signal born `false`, and reopening
// it then restored the geometry correctly — which is why it looked like the position was fine but the window
// «moved». Canvas cards have persisted open+position since the beginning; this is the one surface on the
// desktop that did not, and it is the one he keeps open all day.
//
// The TAB travels with it: coming back to a panel he had left on «Procesos» and finding «Chat» is the same
// loss one level down. Kept in localStorage next to the geometry it belongs with, not in the canvas layout —
// this is a native panel, not a card, and splitting one window's state across two stores is how they drift.
function loadOpen() {
  try {
    const s = JSON.parse(localStorage.getItem(OPEN_KEY) || "null");
    if (s && typeof s === "object") return { open: !!s.open, tab: String(s.tab || "chat") };
  } catch (_) {}
  return { open: false, tab: "chat" };
}

function saveOpen() {
  try { localStorage.setItem(OPEN_KEY, JSON.stringify({ open: !!store.chatOpen(), tab: store.chatTab() })); }
  catch (_) {}
}

// A server-side wipe («reset») must reach this too: `desktop.restore()` owns the wipe epoch and calls this, so
// a blank desktop is genuinely blank instead of one panel that outlived the reset.
export function forgetChatPlacement() {
  try { localStorage.removeItem(OPEN_KEY); } catch (_) {}
  store.setChatOpen(false);
}
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

// Compact relative time for process history (finished_at in epoch seconds, like Python time.time()).
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
  let schedEl, cnameEl, cpromptEl;             // refs for the create-cron form (Crons tab)
  let dockSide = null;                         // null | "left" | "right"
  let dockW = DOCK_DEF_W;                      // the docked column's INTENDED width (see setReserve)
  let lastDockSide = (loadDock() || {}).side || "left";   // where the ⧉ toggle docks a floating box (V2-621)
  let undockEl = null;                         // the box↔column MODE TOGGLE (visible in both shapes, V2-621)
  // `dockSide` is a plain variable a reactive binding would read exactly once (the V2-608 lesson) — this
  // SIGNAL mirrors it for the toggle's reactive title/glyph, written only by setReserve.
  const [isDocked, setIsDocked] = createSignal(false);
  let floatGeo = loadFloat();                  // {left,top,w,h} of the FLOATING window (last known)
  // Reopen exactly as it was left. Done HERE, at construction, so the first paint already has it: flipping the
  // signal later would show the desktop for a frame and then drop a panel on top of it.
  const _wasOpen = loadOpen();
  if (_wasOpen.open) { store.setChatTab(_wasOpen.tab); store.setChatOpen(true); }

  // V2-646 — NOTHING IS LISTENING, SO NOTHING IS SENT (operator, 2026-09-09): «estaba el agente parado y me
  // he puesto a escribir… si lo mando y nadie está escuchando se pierde». It did: `session.sendText` queues
  // the text and calls `start()`, but with the server's ⏻ OFF that start REFUSES (its own gate), so the
  // message sat in the pending queue forever while the wall showed it as sent and the composer was cleared —
  // he had to retype it from scratch. The composer now refuses in that ONE state («off»), keeps the text
  // where he wrote it, and says why. `starting` is NOT blocked: there the queue really does flush on connect.
  const canSend = () => store.agentState() !== "off";
  const send = () => { if (!inputEl || !canSend()) return; submitChat(inputEl.value); inputEl.value = ""; inputEl.focus(); };

  // ── PROCESSES tab: live items (store.tasks, SSE) above + history (store.workerHistory, ledger) below ──────
  // V2-608 F7 — the row is STRUCTURED, and its first line holds still (operator, 2026-09-07): «el proceso que
  // hemos iniciado es buscar una tienda que venda este producto — una vez tienes el título que define la tarea,
  // mostramos solo el título». The name IS the errand's name (V2-530, shared with the flow board and the
  // worker); what the worker is doing right now lives underneath it, and the state/progress/elapsed on a third
  // line. Before this, phases and progress reports overwrote the one text the row had, so its title visibly
  // mutated for minutes and only «settled» when the updates stopped.
  const [nowS, setNowS] = createSignal(Date.now());
  setInterval(() => setNowS(Date.now()), 15000);        // elapsed ticks by the quarter minute; the wall is app-lived
  const dur = (ms) => {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return s + " s";
    const m = Math.floor(s / 60);
    return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + (m % 60) + " min";
  };
  const liveRow = (task) => {
    const icon = task.waiting ? "waiting" : task.paused ? "paused" : "run";
    const gl = task.waiting ? "⏳" : task.paused ? "⏸" : "●";
    const title = (task.title || "").trim() || (task.note || "").trim() || t("chat.working");
    const note = (task.note || "").trim();
    const state = task.waiting ? t("chat.waitingYou") : task.paused ? t("chat.paused") : t("chat.running");
    const meta = [
      state,
      task.stepTag || "",
      (typeof task.pct === "number" && task.pct >= 0 ? task.pct + "%" : ""),
      task.startedAt ? t("chat.procElapsed", { t: dur(nowS() - task.startedAt) }) : "",
      task.startedAt ? t("chat.procSince", {
        t: new Date(task.startedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }) : "",
    ].filter(Boolean).join(" · ");
    return h("div", { class: "cw-proc-row live " + icon },
      h("span", { class: "cw-proc-dot" }, gl),
      h("div", { class: "cw-proc-main" },
        h("div", { class: "cw-proc-goal" }, title),
        // The activity is shown only while it says something the title does not — a note that merely repeats
        // the name would be the same text twice, a few pixels apart.
        (note && note !== title) ? h("div", { class: "cw-proc-note" }, note) : null,
        h("div", { class: "cw-proc-meta" }, meta),
      ),
    );
  };
  const histRow = (e) => {
    // `interrumpido` = a restart terminated it (rehydration, nucleo/rehydrate.py). It has its own
    // glyph because previously ANY unknown state fell through to "done" with a ✓: a task that died halfway was
    // painted as successfully completed. A record that lies is worse than having no record.
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

  // ── CRONS tab: list + create/delete (merges the former CronPanel; same /api/cron API) ───────────────────
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

  // A row in the CLUSTERS tab (V2-086). Shows only what the operator asked for: name, whether we are
  // inside, who is there, and how much has been said. cluster_id is shown because it is NOT secret (it travels in the
  // invitation URL) and is what identifies which cluster this is; the token never leaves the backend.
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

  // ── CONNECTORS tab (V2-561, implementing V2-526): every connector by category, built + wishlist ────────
  // `live` = connectors/registry.py's descriptors() (real state); `wish` = the NOT-live half
  // (connectors/catalog.py's planned/not-possible manifests). Two independent, cheap fetches merged here by
  // `family` — never a new widget, never a model call, never more than what a GET already returns.
  const [connCatalog, setConnCatalog] = createSignal({ live: [], wish: [] });
  const [connRequested, setConnRequested] = createSignal(new Set());
  const refreshConnectors = async () => {
    const [live, wish] = await Promise.all([api.getConnectors(), api.getConnectorCatalog()]);
    setConnCatalog({ live: (live && live.connectors) || [], wish: (wish && wish.catalog) || [] });
  };
  // "Conectar" on a built-but-disconnected row hands off to the CREDENTIAL surface (V2-083's ConfigPanel
  // "conectores" tab) rather than connecting from here — the same voice/hands boundary V2-520 already pins:
  // this tab is for browsing and asking, never for holding a form.
  const openConnectorConfig = () => { store.setConfigInitialTab("conectores"); store.setConfigOpen(true); };
  // "Lo quiero" on a PLANNED entry: a request the receiving side can COUNT, so it carries the manifest `id`
  // as a fixed, machine-written prefix rather than anything the operator typed — free text cannot be
  // grouped. Once per session per id (the row itself shows it was sent instead of inviting a second click).
  const requestConnector = async (m) => {
    if (connRequested().has(m.id)) return;
    setConnRequested(new Set([...connRequested(), m.id]));
    try { await feedbackApi.sendFeedback({ message: `[conector:${m.id}] Lo quiero: ${m.label}` }); }
    catch (_) { /* best-effort; the row already reflects the attempt and nothing here blocks the tab */ }
  };

  const connLiveRow = (c) => h("div", { class: "cl-row" },
    h("div", { class: "cl-main" },
      h("div", { class: "cl-name" },
        h("span", { class: () => "cl-dot" + (c.connected ? " on" : "") }),
        c.label || c.id,
      ),
      h("div", { class: "cl-meta" }, c.connected ? t("chat.connected") : t("chat.disconnected")),
    ),
    h("div", { class: "cl-btns" },
      c.connected ? null : h("button", { class: "cl-b on", onClick: openConnectorConfig }, () => t("chat.connectBtn")),
    ),
  );

  const connWishRow = (m) => {
    const impossible = m.state === "not-possible";
    const requested = connRequested().has(m.id);
    return h("div", { class: "cl-row" + (impossible ? " cn-imposs" : ""), title: impossible ? (m["why-not"] || "") : "" },
      h("div", { class: "cl-main" },
        h("div", { class: "cl-name" }, h("span", { class: "cl-dot" }), m.label || m.id),
        h("div", { class: "cl-meta" },
          impossible ? t("chat.connWishlistImpossible") : t("chat.connWishlistPlanned")),
      ),
      h("div", { class: "cl-btns" },
        impossible ? null
          : h("button", { class: "cl-b" + (requested ? "" : " on"), disabled: requested,
                          onClick: () => requestConnector(m) },
              () => t(requested ? "chat.connWantedBtn" : "chat.connWantBtn")),
      ),
    );
  };

  const connFamilySections = () => {
    const { live, wish } = connCatalog();
    const families = new Map();
    for (const c of live) {
      const f = c.family || "infra";
      if (!families.has(f)) families.set(f, { live: [], wish: [] });
      families.get(f).live.push(c);
    }
    for (const m of wish) {
      const f = m.family || "infra";
      if (!families.has(f)) families.set(f, { live: [], wish: [] });
      families.get(f).wish.push(m);
    }
    const order = [...families.keys()].sort((a, b) => connFamilyRank(a) - connFamilyRank(b) || a.localeCompare(b));
    if (!order.length) return [h("div", { class: "cw-empty" }, () => t("chat.connEmpty"))];
    const out = [];
    for (const fam of order) {
      // t() returns the KEY itself when a string is missing (truthy) — never `|| fam` here (V2-538 already
      // paid for that exact trap). Every family that can appear (mensajeria/musica/archivos/infra/agenda)
      // has a real bundle entry below instead.
      out.push(h("div", { class: "cn-fam" }, () => t("chat.connFamily." + fam)));
      const { live: famLive, wish: famWish } = families.get(fam);
      famLive.forEach(c => out.push(connLiveRow(c)));
      famWish.forEach(m => out.push(connWishRow(m)));
    }
    return out;
  };

  // The dock classes are set IMPERATIVELY by applyDock/applyFloat, and this binding rewrites the whole
  // className whenever the tab or the open flag changes — so it silently wiped `docked`/`dock-left` while the
  // `dockSide` variable stayed set. The wall then rendered as a floating panel at left:0 and still reserved a
  // full column: the operator's screenshot of 2026-09-07, a floating chat with the entire desk pushed right.
  // Reproduced headless: classes `chatwall tab-chat open`, geometry top:232 h:480, `--chatdock-l: 420px`.
  // Reproducing the dock state here is what makes the two writers agree instead of racing (V2-608).
  const dockClass = () => (dockSide ? " docked dock-" + dockSide : "");
  // `narrow` is a SIGNAL read by the class binding, never a classList write: the binding rebuilds the whole
  // className on any tab/open change and would wipe an imperative class — the exact V2-608 dock-class trap,
  // which this file has now paid for twice.
  const [narrow, setNarrow] = createSignal(false);
  const wall = h("div", { id: "chatwall", ref: el => (wallEl = el), class: () => "chatwall tab-" + store.chatTab() + (store.chatOpen() ? " open" : "") + dockClass() + (narrow() ? " cw-narrow" : "") },
    h("div", { class: "cw-head", ref: el => (headEl = el) },
      // V2-621 — the header reads «active tab NAME (fixed min-width) | five icon tabs | ⧉ ×» (operator,
      // 2026-09-08). The standing name says WHERE you are once the tabs are icons; CSS hides it when the
      // wall is wide enough for every tab to carry its own label beside its icon («si se amplían los
      // anchos se ve el icono y la desc al lado»).
      h("div", { class: "cw-tabname" }, () => t(TAB_LABEL[store.chatTab()] || "chat.tabChat")),
      // Each tab carries an ICON + a LABEL: wide, both show side by side; narrow (the wall's own
      // ResizeObserver toggles `cw-narrow`), the labels give way and the header's standing name takes
      // over — V2-619/V2-621. Never a clipped word.
      h("div", { class: "cw-tabs" },
        h("button", { class: () => "cw-tab" + (store.chatTab() === "chat" ? " on" : ""), title: () => t("chat.tabChat"), onClick: () => store.setChatTab("chat") }, raw(MESSAGE_SQUARE_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabChat"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "procesos" ? " on" : ""), title: () => t("chat.tabProcesses"), onClick: () => store.setChatTab("procesos") }, raw(ACTIVITY_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabProcesses"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "crons" ? " on" : ""), title: () => t("chat.tabCrons"), onClick: () => store.setChatTab("crons") }, raw(CLOCK_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabCrons"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "clusters" ? " on" : ""), title: () => t("chat.tabClusters"), onClick: () => store.setChatTab("clusters") }, raw(SERVER_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabClusters"))),
        h("button", { class: () => "cw-tab" + (store.chatTab() === "conectores" ? " on" : ""), title: () => t("chat.tabConnectors"), onClick: () => store.setChatTab("conectores") }, raw(LINK_ICON), h("span", { class: "cw-tab-label" }, () => t("chat.tabConnectors"))),
      ),
      // MODE TOGGLE — the box↔column switch, visible in BOTH shapes (operator, 2026-09-08: «en la box se
      // tienen que ver tb los 2 icons a la derecha, para pasar el formato box a columna»). Docked, it gives
      // the floating panel back («se minimiza la barra y vuelve a aparecer el widget del chat», 2026-09-07 —
      // still needed because the AGENT can open the wall docked); floating, it docks a full-height column on
      // the side it last occupied. The × beside it only ever CLOSES.
      h("button", { class: "cw-undock hb-icbtn", ref: el => (undockEl = el),
                    title: () => t(isDocked() ? "chat.undock" : "chat.dock"),
                    onClick: () => { if (dockSide) applyFloat(floatGeo || defaultFloat());
                                     else applyDock(lastDockSide, (loadDock() || {}).w || DOCK_DEF_W); } },
        () => (isDocked() ? "⧉" : "◫")),
      h("button", { class: "cw-x hb-icbtn", title: () => t("chat.close"), onClick: () => store.setChatOpen(false) }, raw(CLOSE_ICON)),
    ),
    // CHAT
    h("div", { class: "cw-list", ref: el => (listEl = el) }),
    // WIDGET confirmation (V2-518) — house rule: no popups; a pending question (delete /
    // restore / irreversible data operation) is shown IN the conversation with Yes/No, and answered here or by voice.
    // Mirror of the cluster gate below; same backend record (widgets/confirm.py), one at a time.
    () => (store.widgetConfirm()
      ? h("div", { class: "cl-confirm cw-wconfirm" },
          h("div", { class: "cl-q" }, store.widgetConfirm().question || t("chat.widgetConfirmQ")),
          h("div", { class: "cl-cbtns" },
            h("button", { class: "cl-b on", onClick: () => store.widgetConfirmResolve(true) }, () => t("chat.yes")),
            h("button", { class: "cl-b", onClick: () => store.widgetConfirmResolve(false) }, () => t("chat.no")),
          ))
      : null),
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
    // CLUSTERS (V2-086) — the native NETWORK. Connection administration, not conversation: clusters have their
    // own monitor, so here we only show which network we are connected to, with whom, and how much traffic there has been.
    h("div", { class: "cw-clusters" },
      // CONNECT confirmation: deterministic gate. Without an explicit “yes” here no socket is opened, no matter
      // how convincing the text that requested it is (V2-064 → V2-086: changes where it is shown, not the guarantee).
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
    // CONECTORES (V2-561, implementing V2-526) — every connector by category: built (live, from the
    // registry) grouped with the wishlist (planned/not-possible, from the catalog). No new widget, no new
    // orb entry — this tab IS the "browse and ask" surface the design doc calls for.
    h("div", { class: "cw-conn" },
      h("div", { class: "cl-list" }, () => connFamilySections()),
    ),
    // INPUT (Chat only — CSS hides it in the other tabs)
    h("div", { class: "cw-input" },
      h("textarea", {
        // rows:3 — the composer is for WRITING (V2-619, operator: «ya de base debería tener dos o tres
        // líneas de altura»); CSS gives it the matching min-height so a profile's type scale keeps the ratio.
        ref: el => (inputEl = el), rows: 3, placeholder: () => t("chat.messagePlaceholder"),
        onKeydown: e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } },
      }),
      h("button", { class: () => "cw-send" + (canSend() ? "" : " off"), disabled: () => !canSend(),
                    title: () => t(canSend() ? "chat.send" : "chat.sendAgentOff"), onClick: send },
        raw(SEND_SVG)),
    ),
  );

  // When ENTERING a tab, refresh its data (live items already arrive via SSE; history/crons are requested here).
  createEffect(() => {
    const t = store.chatTab();
    if (!store.chatOpen()) return;
    if (t === "procesos") { store.fetchTasks(); store.fetchWorkerHistory(); }
    else if (t === "crons") refreshCrons();
    else if (t === "clusters") store.fetchClusters();
    else if (t === "conectores") refreshConnectors();
  });
  // When live processes change (a task finishes) while we are viewing “Processes”, refresh the history so
  // the task that just finished moves from the "running" block to "history".
  createEffect(() => {
    store.tasks();
    if (store.chatOpen() && store.chatTab() === "procesos") store.fetchWorkerHistory();
  });

  // CHAT and VOICE are INDEPENDENT (V2-088). Opening this panel does NOT affect the speaker, and muting the speaker does not affect
  // this panel. The “chat mode = voice off” behavior from V2-054 is removed: it assumed opening chat meant “I want to
  // read instead of listen”, and that is FALSE — the panel has four tabs, and the operator may inspect PROCESSES,
  // CRONS, or CLUSTERS without wanting to silence anyone. Cutting off the voice merely by looking at a list is a decision the
  // system has no reason to make on its own, and it even cost an entire session that thought TTS was broken.
  //
  // Who mutes: ONLY the 🔊 icon (`session.toggleBotMute`, which notifies the server). One switch, one owner.
  // Chat is NOT a mode; it is an ADDITIONAL VIEW: the response appears there just as in subtitles and voice,
  // all three at once — `pushAgentChat` hangs off the assistant transcript, which is independent of the audio.
  createEffect(() => {
    store.chatOpen();      // sole dependency: reserved geometry depends on whether it is open
    setReserve();          // closing releases the reserved strip; reopening while docked re-applies it
  });

  // Remember open/closed + which tab, on every change — including the ones the ENGINE makes (a proactive push
  // opens the wall by SSE, `[[close]]` shuts it). Those are as much «where he left it» as a click is.
  createEffect(() => { store.chatOpen(); store.chatTab(); saveOpen(); });

  // V2-619/V2-621: below this width the five tabs cannot all carry icon+label, so the labels give way to
  // the icons and the header's standing tab NAME takes over (CSS keys off `cw-narrow`). Measured on the wall
  // itself, so a dock resize, a float resize and a profile's larger type all take the same door. 660, not
  // V2-619's 580: wide tabs now keep their icons BESIDE the labels (~24px more per tab).
  const TABS_NARROW_BELOW = 660;
  try {
    new ResizeObserver(() => {
      if (wallEl.offsetWidth > 0) setNarrow(wallEl.offsetWidth < TABS_NARROW_BELOW);
    }).observe(wallEl);
  } catch (_) {}

  // ── geometry: floating ↔ dock ────────────────────────────────────────────────────────────────────────────
  function defaultFloat() { return { left: 18, top: 232, w: 320, h: Math.min(Math.round(innerHeight * 0.6), 520) }; }

  function applyFloat(geo) {
    floatGeo = geo || floatGeo || defaultFloat();
    dockSide = null; dockW = DOCK_DEF_W;
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
    lastDockSide = side;                        // the ⧉ toggle re-docks a floating box to this side (V2-621)
    const width = Math.max(DOCK_MIN_W, _num(w, DOCK_DEF_W));
    dockW = width;
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

  // SPACE RESERVATION: when chat is OPEN and docked, the desktop shifts into the free area.
  function setReserve() {
    const root = document.documentElement, body = document.body;
    body.classList.remove("chatdock-l", "chatdock-r");
    if (store.chatOpen() && dockSide) {
      // The INTENDED width, not the measured one. `offsetWidth` is 0 while the wall is still unlaid-out — which
      // is exactly the case on the restore path — so this used to reserve the 340px default for a 420px column
      // and leave an 80px band of desk hidden underneath it (measured 2026-09-07, V2-608). Measure only as a
      // fallback, for the resize drag, where the element is on screen and the pointer is the authority.
      const w = Math.round(dockW || wallEl.offsetWidth || DOCK_DEF_W);
      root.style.setProperty("--chatdock-l", dockSide === "left" ? w + "px" : "0px");
      root.style.setProperty("--chatdock-r", dockSide === "right" ? w + "px" : "0px");
      body.classList.add(dockSide === "left" ? "chatdock-l" : "chatdock-r");
    } else {
      root.style.setProperty("--chatdock-l", "0px");
      root.style.setProperty("--chatdock-r", "0px");
    }
    // The mode toggle's face is driven from HERE and nowhere else. Its first shape was a reactive `class`
    // binding on `dockSide` — a plain variable, not a signal, so it evaluated once at build time and the
    // button stayed hidden forever (measured: `undockVisible: false` with the wall fully docked). Every path
    // that changes `dockSide` already calls setReserve(), so mirroring it into the signal here is the one
    // place that cannot be forgotten (V2-621: the button now shows in BOTH shapes and only its face flips).
    setIsDocked(!!dockSide);
    // V2-608 — SAY SO. `#desk` follows these vars in CSS, but the widget cards live on `.hb-stage` (inset:0) in
    // viewport coordinates, so nothing moved them: the operator docked the chat left, the desk shrank underneath
    // his cards, and the one on the right was cut off by the window edge with no way to reach it. The desktop
    // listens and refits everything into the canvas that is left. Same shape as the rail's `hb:rail-resized`.
    try { document.dispatchEvent(new CustomEvent("hb:canvas-resized", { detail: { side: dockSide } })); } catch (_) {}
  }

  // ── MOVABLE by the header, with dock/undock ───────────────────────────────────────────────────────────────
  headEl.style.touchAction = "none";
  let drag = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0, pid = null, preview = null;
  headEl.addEventListener("pointerdown", e => {
    if (e.target.closest(".cw-x") || e.target.closest(".cw-tab") || e.target.closest(".cw-undock")) return;   // buttons do not drag
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
        dockW = width;
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
  // V2-464 — SHOWCASE mode (?showcase=1): chat starts OPEN and DOCKED on the left, so an unattended
  // recording shows the conversation without anyone touching anything. Before the saved float: in the studio,
  // persisted geometry belongs to another session and a half-positioned floating chat covers the cards.
  const _showcase = new URLSearchParams(location.search).has("showcase");
  // V2-608 — THE SAVED DOCK IS RESTORED FIRST. It was written on every dock (DOCK_KEY, as this file's header
  // has said since V2-062) and then never read back except to seed the preview width, so `floatGeo` — which
  // `applyDock` does NOT clear — always won and the wall came back FLOATING. Measured on the real page: dock
  // left, reload, and it returns at left:18 w:320 with `hb_chat_dock` still holding {side:"left",w:420} and
  // `--chatdock-l` back to 0px. V2-550 fixed «it does not come back where it was» for the floating wall; this is
  // the same report for the docked one, and it is the shape the operator actually uses.
  const savedDock = loadDock();
  if (_showcase) {
    applyDock("left", (savedDock || {}).w || DOCK_DEF_W);
    placed = true;
    store.setChatOpen(true);
  } else if (savedDock) { applyDock(savedDock.side, savedDock.w); placed = true; }
  else if (floatGeo) { applyFloat(floatGeo); placed = true; }

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

  // on first open with NO saved geometry: auto-place like a widget, then focus the input (Chat only)
  createEffect(() => {
    if (!store.chatOpen()) return;
    if (!placed) requestAnimationFrame(() => { placeWall(wallEl); placed = true; });
    if (inputEl && store.chatTab() === "chat") inputEl.focus();
  });

  return wall;
}

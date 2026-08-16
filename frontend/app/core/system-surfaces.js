// system-surfaces.js — LISTA CANÓNICA de las SUPERFICIES NATIVAS del frontend (V2-080).
//
// Estos son los "widgets de SISTEMA": UI nativa, fija e INTOCABLE. NO son widgets del catálogo (`widgets/<id>/`):
// el generador y el ciclo de vida (`widgets/lifecycle.py`) SOLO tocan `widgets/<id>/`, nunca esto. El usuario no
// los crea, edita ni borra. Se distinguen de los WIDGETS DE USUARIO (los del catálogo, aunque los distribuyamos de
// serie), que sí son variables, creados por y para el usuario — igual que los conectores.
//
// Esta es la ÚNICA fuente de verdad de "qué es nativo": `main.js` MONTA desde aquí (no hay lista duplicada). Cada
// superficie se pinta distinto (chrome del escritorio, panel acoplable, overlay, modal, banner…) pero TODA es
// frontend nativo. Al añadir una superficie nativa nueva, va AQUÍ (y `main.js` la monta sola).
//
// Campos por entrada:
//   id      — identificador estable de la superficie de sistema
//   comp    — el componente (factory) que la construye
//   target  — dónde se monta: "desk" (chrome DENTRO de #desk, se desplaza al acoplar el chat) | "body" (por encima)
//   phase   — "scaffold" (andamiaje del escritorio, orden load-bearing) | "overlay" (el resto)
//   kind    — para qué sirve / cómo se ve (documental): canvas-bg · chrome · panel · overlay · modal · transient
//   toggle  — cómo se abre/gestiona (documental): señal de store o control que lo dispara
//   label   — nombre legible (descriptivo)
//   name    — NOMBRE canónico por el que se abre por voz/texto (V2-082)
//   aliases — nombres/k-words alternativos por los que se reconoce (V2-082). FIJOS y HARDCODEADOS: el front es
//             "el cuerpo", su genética viene programada; el usuario NO puede editar estos alias (a diferencia de
//             los widgets de usuario, cuyos alias sí son editables). Un objeto de sistema NUNCA es un "widget":
//             decir "el widget de X" jamás resuelve a una de estas superficies (ver widgets/runtime.py::identify).
//             `null` = superficie no dirigible por voz (transitoria/andamiaje); no entra al resolver de nombres.
import { ActivityStrip } from "../components/ActivityStrip.js?v=2";
import { Alert } from "../components/Alert.js?v=2";
import { BenchmarksPanel } from "../components/BenchmarksPanel.js?v=1";
import { BootOverlay } from "../components/BootOverlay.js?v=2";
import { ChatWall } from "../components/ChatWall.js?v=5";
import { ConfigPanel } from "../components/ConfigPanel.js?v=2";
import { ConnStatus } from "../components/ConnStatus.js?v=2";
import { DebugPanel } from "../components/DebugPanel.js?v=4";
import { FeedbackWidget } from "../components/FeedbackWidget.js?v=1";
import { MemoryMap } from "../components/MemoryMap.js?v=2";
import { Orb } from "../components/Orb.js?v=3";
import { StatusPanel } from "../components/StatusPanel.js?v=2";
import { TopBar } from "../components/TopBar.js?v=3";
import { VaultModal } from "../components/VaultModal.js?v=1";
import { WizardModal } from "../components/WizardModal.js?v=1";

// El ORDEN es el de montaje real en el DOM (importa para el apilado). scaffold primero, luego overlay.
export const SYSTEM_SURFACES = [
  // ── ANDAMIAJE del escritorio (dentro de #desk; posición load-bearing entre .canvas y #wstage) ──
  { id: "activity-strip", comp: ActivityStrip, target: "desk", phase: "scaffold", kind: "canvas-bg",
    toggle: "store.tasks (SSE)", label: "Activity honeycomb (background hexagons)",
    name: null, aliases: null },
  // ── CHROME del escritorio (dentro de #desk; se desplaza al acoplar el chat) ──
  // NOTA: `name` es DISPLAY (inglés, lo ve el usuario). `aliases` son k-words de RECONOCIMIENTO por voz: se
  // mantienen en castellano Y en inglés porque el asistente es multilingüe con el operador (no son texto visible).
  // «camera» (CameraUnit) OCULTADA a petición del operador (2026-08-09), para simplificar el cuenco — NO borrada:
  // `components/CameraUnit.js` se queda archivada tal cual (código intacto, solo desenchufada de aquí). Su mic
  // toggle y su botón de abrir el chat se trasladaron al ojo (Orb.js, dos slots que quedaron libres al mover ⏰/☾).
  { id: "orb",        comp: Orb,          target: "desk", phase: "overlay", kind: "chrome",
    toggle: "always visible (the eye + 7 controls + subtitles)", label: "Orb (zaelar personified)",
    name: "Orb", aliases: ["orbe", "orb", "el ojo", "ojo", "controles", "subtitulos", "subtítulos",
      "the eye", "eye", "controls", "subtitles"] },
  { id: "topbar",     comp: TopBar,       target: "desk", phase: "overlay", kind: "chrome",
    toggle: "always visible (◉ status · ⌗ docs · ◷ debug · ⚙ · 🧭 · Reset)", label: "Top bar",
    name: null, aliases: null },
  { id: "connstatus", comp: ConnStatus,   target: "desk", phase: "overlay", kind: "chrome",
    toggle: "always visible (connection line)", label: "Connection status",
    name: null, aliases: null },
  // ── PANELES / OVERLAYS / MODALES (a nivel de body, por encima del escritorio) ──
  // OJO: el chat tiene 4 pestañas (Chat/Procesos/Crons/Clusters). "abre el chat" → pestaña Chat; "procesos",
  // "crons" y "clusters" (la RED MeshKore, V2-086) son las OTRAS, ruteadas por la tool show_panel
  // (router._canon_panel) — sus sinónimos viven ahí, no aquí, para no duplicar. Estos alias abren la superficie
  // del chat (pestaña por defecto). La red es NATIVA a propósito: es infraestructura del sistema (la conexión al
  // exterior), no un widget de usuario — por eso vive junto a Procesos/Crons y no en el catálogo.
  { id: "chat",       comp: ChatWall,     target: "body", phase: "overlay", kind: "panel",
    toggle: "store.chatOpen + store.chatTab (Chat/Processes/Crons/Clusters)",
    label: "Chat + Processes + Crons + Clusters (4 tabs)",
    name: "Chat", aliases: ["chat", "muro", "muro de texto", "muro de chat", "escribirte", "hablarte por texto",
      "conversacion", "conversación", "el chat contigo", "wall", "text wall", "chat wall"] },
  { id: "status",     comp: StatusPanel,  target: "body", phase: "overlay", kind: "panel",
    toggle: "store.statusOpen (◉)", label: "System status panel",
    name: "Status", aliases: ["estado", "estado del sistema", "status", "panel de estado", "salud del sistema",
      "system status", "health"] },
  { id: "config",     comp: ConfigPanel,  target: "body", phase: "overlay", kind: "fullscreen",
    toggle: "store.configOpen (⚙)", label: "Settings (API/model per piece, voice, balances)",
    name: "Settings", aliases: ["config", "configuracion", "configuración", "ajustes", "preferencias",
      "settings", "opciones", "preferences", "options"] },
  { id: "benchmarks", comp: BenchmarksPanel, target: "body", phase: "overlay", kind: "modal",
    toggle: "from Settings → Fast brain", label: "Benchmarks (why these models?)",
    name: "Benchmarks", aliases: ["benchmarks", "por que estos modelos", "por qué estos modelos", "comparativa",
      "why these models", "comparison"] },
  { id: "debug",      comp: DebugPanel,   target: "body", phase: "overlay", kind: "panel",
    toggle: "store.debugOpen (◷)", label: "Debug / observability (logging, timeline, traces)",
    name: "Debug", aliases: ["debug", "depuracion", "depuración", "logs", "logging", "trazas", "timeline",
      "observabilidad", "traces", "observability"] },
  { id: "memory-map", comp: MemoryMap,    target: "body", phase: "overlay", kind: "overlay",
    toggle: "store.memOpen (🧠)", label: "Memory map (state · short · long · graph)",
    name: "Memory map", aliases: ["memoria", "mapa de memoria", "mapa de la memoria", "tu memoria",
      "recuerdos", "memory", "memory map", "memories"] },
  { id: "wizard",     comp: WizardModal,  target: "body", phase: "overlay", kind: "modal",
    toggle: "store.wizardOpen (🧭, and auto on first run)", label: "First-run wizard",
    name: "Setup wizard", aliases: ["wizard", "asistente", "primer arranque", "configuracion inicial",
      "configuración inicial", "setup", "setup wizard", "first run", "onboarding"] },
  { id: "vault",      comp: VaultModal,   target: "body", phase: "overlay", kind: "modal",
    toggle: "SSE events kind:secret · window.zaelar.vault()", label: "Secrets vault (🔐)",
    name: "Vault", aliases: ["boveda", "bóveda", "secretos", "vault", "contraseñas", "caja fuerte",
      "secrets", "passwords", "safe"] },
  // V2-100 (2026-08-16): floating "send feedback to the developers" launcher + panel. Self-contained —
  // its own components/services files, ONLY these two lines register it into the app shell.
  { id: "feedback",   comp: FeedbackWidget, target: "body", phase: "overlay", kind: "panel",
    toggle: "store.feedbackOpen (floating launcher, bottom-right)", label: "Send feedback to the developers",
    name: "Feedback", aliases: ["feedback", "sugerencia", "sugerencias", "comentarios", "opinion",
      "opinión", "suggestion", "suggestions", "comments"] },
  // ── TRANSITORIOS (banner / velo de arranque) ──
  { id: "alert",      comp: Alert,        target: "body", phase: "overlay", kind: "transient",
    toggle: "store.showAlert (hard notice, e.g. no model balance)", label: "Notice banner",
    name: null, aliases: null },
  { id: "boot",       comp: BootOverlay,  target: "body", phase: "overlay", kind: "transient",
    toggle: "store.bootReady (startup veil)", label: "Startup splash",
    name: null, aliases: null },
];

const _IDS = new Set(SYSTEM_SURFACES.map(s => s.id));

// ¿`id` es una superficie NATIVA de sistema? (frente a un widget de usuario del catálogo). Fuente única para
// cualquier guard futuro que necesite distinguir sistema vs usuario en el frontend.
export function isSystemSurface(id) { return _IDS.has(String(id || "")); }

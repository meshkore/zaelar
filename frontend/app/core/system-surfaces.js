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
import { CameraUnit } from "../components/CameraUnit.js?v=2";
import { ChatWall } from "../components/ChatWall.js?v=5";
import { ConfigPanel } from "../components/ConfigPanel.js?v=1";
import { ConnStatus } from "../components/ConnStatus.js?v=2";
import { DebugPanel } from "../components/DebugPanel.js?v=4";
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
    toggle: "store.tasks (SSE)", label: "Panal de actividad (hexágonos de fondo)",
    name: null, aliases: null },
  // ── CHROME del escritorio (dentro de #desk; se desplaza al acoplar el chat) ──
  { id: "camera",     comp: CameraUnit,   target: "desk", phase: "overlay", kind: "chrome",
    toggle: "siempre visible (mic/cámara + botón de chat)", label: "Cámara y micrófono del usuario",
    name: "Cámara y micrófono", aliases: ["camara", "cámara", "microfono", "micrófono", "mic", "webcam"] },
  { id: "orb",        comp: Orb,          target: "desk", phase: "overlay", kind: "chrome",
    toggle: "siempre visible (el ojo + 7 controles + subtítulos)", label: "Orbe (zaelar personificado)",
    name: "Orbe", aliases: ["orbe", "orb", "el ojo", "ojo", "controles", "subtitulos", "subtítulos"] },
  { id: "topbar",     comp: TopBar,       target: "desk", phase: "overlay", kind: "chrome",
    toggle: "siempre visible (◉ estado · ⌗ docs · ◷ debug · ⚙ · 🧭 · Reset)", label: "Barra superior",
    name: null, aliases: null },
  { id: "connstatus", comp: ConnStatus,   target: "desk", phase: "overlay", kind: "chrome",
    toggle: "siempre visible (línea de conexión)", label: "Estado de conexión",
    name: null, aliases: null },
  // ── PANELES / OVERLAYS / MODALES (a nivel de body, por encima del escritorio) ──
  // OJO: el chat tiene 3 pestañas (Chat/Procesos/Crons). "abre el chat" → pestaña Chat; "lista de tareas/procesos"
  // y "crons/lista del cron" son las OTRAS pestañas, ruteadas por la tool show_panel (router._canon_panel) — sus
  // sinónimos viven ahí, no aquí, para no duplicar. Estos alias abren la superficie del chat (pestaña por defecto).
  { id: "chat",       comp: ChatWall,     target: "body", phase: "overlay", kind: "panel",
    toggle: "store.chatOpen + store.chatTab (Chat/Procesos/Crons)", label: "Chat + Procesos + Crons (3 pestañas)",
    name: "Chat", aliases: ["chat", "muro", "muro de texto", "muro de chat", "escribirte", "hablarte por texto",
      "conversacion", "conversación", "el chat contigo"] },
  { id: "status",     comp: StatusPanel,  target: "body", phase: "overlay", kind: "panel",
    toggle: "store.statusOpen (◉)", label: "Panel de estado del sistema",
    name: "Estado", aliases: ["estado", "estado del sistema", "status", "panel de estado", "salud del sistema"] },
  { id: "config",     comp: ConfigPanel,  target: "body", phase: "overlay", kind: "fullscreen",
    toggle: "store.configOpen (⚙)", label: "Configuración (API/modelo por pieza, voz, saldos)",
    name: "Configuración", aliases: ["config", "configuracion", "configuración", "ajustes", "preferencias",
      "settings", "opciones"] },
  { id: "benchmarks", comp: BenchmarksPanel, target: "body", phase: "overlay", kind: "modal",
    toggle: "desde Config → Cerebro rápido", label: "Benchmarks (¿por qué estos modelos?)",
    name: "Benchmarks", aliases: ["benchmarks", "por que estos modelos", "por qué estos modelos", "comparativa"] },
  { id: "debug",      comp: DebugPanel,   target: "body", phase: "overlay", kind: "panel",
    toggle: "store.debugOpen (◷)", label: "Debug / observabilidad (logging, timeline, trazas)",
    name: "Debug", aliases: ["debug", "depuracion", "depuración", "logs", "logging", "trazas", "timeline",
      "observabilidad"] },
  { id: "memory-map", comp: MemoryMap,    target: "body", phase: "overlay", kind: "overlay",
    toggle: "store.memOpen (🧠)", label: "Mapa de la memoria (estado · corto · largo · grafo)",
    name: "Mapa de la memoria", aliases: ["memoria", "mapa de memoria", "mapa de la memoria", "tu memoria",
      "recuerdos"] },
  { id: "wizard",     comp: WizardModal,  target: "body", phase: "overlay", kind: "modal",
    toggle: "store.wizardOpen (🧭, y auto en primer arranque)", label: "Wizard de primer arranque",
    name: "Asistente de configuración", aliases: ["wizard", "asistente", "primer arranque", "configuracion inicial",
      "configuración inicial"] },
  { id: "vault",      comp: VaultModal,   target: "body", phase: "overlay", kind: "modal",
    toggle: "eventos SSE kind:secret · window.zaelar.vault()", label: "Bóveda de secretos (🔐)",
    name: "Bóveda", aliases: ["boveda", "bóveda", "secretos", "vault", "contraseñas", "caja fuerte"] },
  // ── TRANSITORIOS (banner / velo de arranque) ──
  { id: "alert",      comp: Alert,        target: "body", phase: "overlay", kind: "transient",
    toggle: "store.showAlert (aviso duro, p.ej. sin saldo de modelo)", label: "Banner de aviso",
    name: null, aliases: null },
  { id: "boot",       comp: BootOverlay,  target: "body", phase: "overlay", kind: "transient",
    toggle: "store.bootReady (velo de arranque)", label: "Splash de arranque",
    name: null, aliases: null },
];

const _IDS = new Set(SYSTEM_SURFACES.map(s => s.id));

// ¿`id` es una superficie NATIVA de sistema? (frente a un widget de usuario del catálogo). Fuente única para
// cualquier guard futuro que necesite distinguir sistema vs usuario en el frontend.
export function isSystemSurface(id) { return _IDS.has(String(id || "")); }

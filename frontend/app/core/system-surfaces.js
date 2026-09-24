// system-surfaces.js — CANONICAL LIST of the frontend's NATIVE SURFACES (V2-080).
//
// These are the "SYSTEM widgets": native, fixed, UNTOUCHABLE UI. They are NOT catalog widgets (`widgets/<id>/`):
// the generator and lifecycle (`widgets/lifecycle.py`) touch ONLY `widgets/<id>/`, never this. Users do not create,
// edit, or delete them. They differ from USER WIDGETS (catalog items, even when shipped by default), which are
// variable and created by and for the user—like connectors.
//
// This is the ONLY source of truth for "what is native": `main.js` MOUNTS from here (there is no duplicate list).
// Each surface renders differently (desktop chrome, dockable panel, overlay, modal, banner…), but ALL are native
// frontend. When adding a native surface, put it HERE (and `main.js` mounts it automatically).
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
import { Alert } from "../components/Alert.js?v=2";
import { BenchmarksPanel } from "../components/BenchmarksPanel.js?v=1";
import { BootOverlay } from "../components/BootOverlay.js?v=2";
import { ChatWall } from "../components/ChatWall.js?v=5";
import { ConfigPanel } from "../components/ConfigPanel.js?v=2";
import { DaemonSetup } from "../components/DaemonSetup.js?v=1";
import { DebugPanel } from "../components/DebugPanel.js?v=4";
import { FeedbackWidget } from "../components/FeedbackWidget.js?v=1";
import { FaultModal } from "../components/FaultModal.js?v=1";
import { LanguageOnboarding } from "../components/LanguageOnboarding.js?v=1";
import { MemoryMap } from "../components/MemoryMap.js?v=2";
import { Orb } from "../components/Orb.js?v=3";
import { StatusPanel } from "../components/StatusPanel.js?v=2";
import { TopBar } from "../components/TopBar.js?v=3";
import { VaultModal } from "../components/VaultModal.js?v=1";
import { WizardModal } from "../components/WizardModal.js?v=1";
import { WidgetRail } from "../components/WidgetRail.js?v=2";
import { UpdateSurface } from "../update/UpdateSurface.js?v=1";

// The ORDER is the actual DOM mount order (it matters for stacking). Scaffold first, then overlay.
export const SYSTEM_SURFACES = [
  // El PANAL DE ACTIVIDAD (hexágonos de fondo, V2-039) se RETIRÓ el 2026-08-20 por decisión del operador
  // (V2-233 D): el relato de lo que está pasando vive en UN sitio por encargo — la pestaña «Proceso» de la
  // superficie donde va a aterrizar el resultado, y la pestaña «Procesos» del chat para todo lo demás. Tres
  // superficies contando el mismo hecho no es redundancia inofensiva: obliga a mantener tres y a mirar tres.
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
  // V2-537 — the widget rail: one chip per open card (always on top), ▦ auto-arrange, minimize/show all.
  // Not voice-addressable in v1 (like the top bar); it only shows itself while at least one card is open.
  // V2-538→V2-623 — DOCKED: a bar that owns the BOTTOM edge (Desktop.railBand() keeps cards out of it),
  // foldable to a thin border that unfolds on click; the fold survives a reload.
  { id: "wrail",      comp: WidgetRail,   target: "desk", phase: "overlay", kind: "chrome",
    toggle: "auto (visible while any widget card is open)", label: "Widget rail",
    name: null, aliases: null },
  // V2-542 — the bottom-left CONNECTION LINE is GONE, at the operator's request: «ya tenemos una barra a la
  // izquierda, las opciones principales arriba a la derecha… no hace falta más mierda en pantalla». Nothing was
  // lost by deleting it. Connection health was already the ◉ dot up top — `overallStatus()` is
  // worst(server, THIS browser's voice connection, offline), so the beacon reads the very same `store.conn()`
  // the line did, and blinks besides. The mic LEVEL was already the orb (its `--vu` is `store.micLevel()`).
  // The two selectors moved to ⚙ → Voz, where a device choice belongs; only reply latency lost its chip, and
  // the real per-turn timings live in ◷ with far more detail than «resp — ms».
  // ── PANELES / OVERLAYS / MODALES (a nivel de body, por encima del escritorio) ──
  // NOTE: the wall has FIVE tabs (Chat / Procesos / Clusters / Conectores / Apps — V2-761). V2-728 merged the former
  // «Procesos» and «Crons» into one tab with four sub-tabs (En curso · Hechos · Periódicos · Programados):
  // they were the same object seen twice, a commission the brain is carrying out and one with a clock on it.
  // "abre el chat" → the Chat tab; «procesos»/«jobs», «crons» and «clusters» (the MeshKore NETWORK,
  // V2-086) are the others, routed by the `show_panel` tool (`router._canon_panel`) — its synonyms live
  // there and not here, so there is one list. The old names still work: `store.setChatTab` maps them onto
  // «Procesos» and the right sub-tab. V2-744: the tab is PROCESOS, id included — «tareas»/«tasks» now mean
  // the operator's OWN lists, which live in the AGENDA widget and are reached by `show_tasks`, not here.
  // The network is NATIVE on purpose: it is system infrastructure (the link to the outside), not a user
  // widget — which is why it sits beside Procesos and not in the catalog.
  { id: "chat",       comp: ChatWall,     target: "body", phase: "overlay", kind: "panel",
    toggle: "store.chatOpen + store.chatTab (Chat/Jobs/Clusters/Connectors/Apps)",
    label: "Chat + Jobs + Clusters + Connectors + Apps (5 tabs)",
    name: "Chat", aliases: ["chat", "muro", "muro de texto", "muro de chat", "escribirte", "hablarte por texto",
      "conversacion", "conversación", "el chat contigo", "wall", "text wall", "chat wall"] },
  // V2-761 — «Apps»: the widget catalogue, a TAB of the wall (Sistema · Custom), not a component of its own —
  // `phase: "tab"` is never mounted (main.js mounts only scaffold/overlay). It is listed so the voice can NAME
  // it: «ábreme las apps / la lista de widgets / el catálogo de widgets» resolves here and the provider opens
  // the wall on this tab. The aliases are MULTI-WORD on purpose where a single word would be a near-miss of
  // something else: the resolver's voice tolerance fuzzes single-word aliases, and a bare «aplicaciones»
  // would catch «abre la APLICACIÓN de música» and open this list instead of the music card.
  { id: "apps",       comp: null,         target: "body", phase: "tab", kind: "panel",
    toggle: "store.chatTab = apps (ChatWall's Apps tab)", label: "Apps — the widget catalogue (System · Custom)",
    name: "Apps", aliases: ["apps", "widgets", "mis apps", "mis widgets", "las apps", "los widgets", "lista de apps", "lista de widgets", "catalogo de apps", "catálogo de apps", "catalogo de widgets", "catálogo de widgets", "las aplicaciones", "mis aplicaciones", "lista de aplicaciones", "widgets disponibles", "apps disponibles", "my apps", "my widgets", "app list", "widget list", "app catalog", "widget catalog", "the applications",
      "catalogo de aplicaciones", "catálogo de aplicaciones", "apps customizadas", "widgets customizados", "apps personalizadas", "widgets personalizados", "mis apps customizadas", "mis widgets customizados"] },
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
  // V2-676 — the BLOCKING fault. Sibling of `alert` and deliberately separate: a banner is what a dry model
  // chain used to get, and the operator walked past it for two minutes while talking to an agent that could
  // not answer. This one covers the screen, stops the voice and carries a button into the settings. Not
  // voice-addressable: it appears when the agent cannot speak, so «open the fault» could never be said.
  { id: "fault",      comp: FaultModal,   target: "body", phase: "overlay", kind: "modal",
    toggle: "store.showFault (the agent cannot work — e.g. no model credit)", label: "Blocking fault",
    name: null, aliases: null },
  { id: "boot",       comp: BootOverlay,  target: "body", phase: "overlay", kind: "transient",
    toggle: "store.bootReady (startup veil)", label: "Startup splash",
    name: null, aliases: null },
  // V2-553 — the UPDATE CHANNEL: the «there is a new version, click to reload» bar (top, above everything).
  // Self-contained in `app/update/`: this line is the ONLY place the app knows it exists, which is the
  // constraint the operator set for it. Not voice-addressable — «open the update» is not a thing to open;
  // it is either there or it is not. The always-on version badge that used to sit here too was retired from
  // the scene in V2-666 («quítalo de la escena») — ConfigPanel.js now shows the build number, only while
  // Settings is open, reading the same `update/watch.js` signals.
  { id: "update",     comp: UpdateSurface, target: "body", phase: "overlay", kind: "transient",
    toggle: "auto (bar when the served frontend differs from the one running)",
    label: "Update bar",
    name: null, aliases: null },
  // V2-101 (2026-08-16): first-run "which language?" blocking modal — the SECOND veil, right after the boot
  // veil lifts, shown only once (GET /api/i18n/state's `chosen` flag). Not voice-addressable — you can't "open"
  // a one-time onboarding gate by name.
  { id: "lang-onboarding", comp: LanguageOnboarding, target: "body", phase: "overlay", kind: "modal",
    toggle: "store.langOnboardOpen (first-run only, closes on SSE language phase:ready)",
    label: "First-run language onboarding",
    name: null, aliases: null },
  // V2-575 P1 (2026-09-14): the 🖥 local-daemon screen — install it, and choose which folders it may read.
  // `name: null` because it is not voice-addressable: "open the daemon" is not a sentence anybody says, and
  // the thing behind the icon is an install step plus a permission grant, both of which are deliberate
  // clicks by design (see the component's own note on why this is a full screen and not a dismissible modal).
  { id: "daemon-setup", comp: DaemonSetup, target: "body", phase: "overlay", kind: "fullscreen",
    toggle: "store.daemonSetupOpen (🖥 icon in the TopBar)",
    label: "Local daemon: install and folder permissions",
    name: null, aliases: null },
];

const _IDS = new Set(SYSTEM_SURFACES.map(s => s.id));

// Is `id` a NATIVE system surface? (as opposed to a catalog user widget). Single source for any future guard that
// needs to distinguish system from user in the frontend.
export function isSystemSurface(id) { return _IDS.has(String(id || "")); }

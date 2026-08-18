// ============================================================================
// store.js — app-wide reactive state as signals (the Solid createStore/context
// equivalent). SERVICES write these; COMPONENTS read them via effects. No DOM
// here, no business logic — just the shared state the UI reacts to.
//
// Persisted bits (mic muted, camera off, orb style, voice gate) seed from
// localStorage so the UI reflects the user's last choice before a stream exists.
// ============================================================================
import { createSignal } from "./reactive.js?v=2";

// ---- active UI language (V2-089 multilingual) — the single signal every t() reads. Seeds instantly from the
// localStorage mirror (no flash for returning operators), then initI18n() reconciles against the backend's
// active language (ZAELAR_LANGUAGE). Flipping it re-renders every localized string in the tree, live. ----
export const [lang, setLang]           = createSignal(localStorage.getItem("hb_lang") || "en");

export const [started, setStarted]     = createSignal(false);   // a live session is up
export const [starting, setStarting]   = createSignal(false);   // session is connecting
export const [conn, setConn]           = createSignal({ label: "—", ok: false });
export const [latency, setLatency]     = createSignal("— ms");  // reply time-to-first-audio

// Boot overlay gate: false blocks the UI on first load (agents booting, voice connecting, memory composing). Flips
// true on the room-scoped "ready" signal from the agent, or a safety timeout — see session-lk.js. Stays true across
// later reconnects (only the very first boot blocks).
export const [bootReady, setBootReady] = createSignal(false);
// Boot PHASE — the ordered startup milestones the splash animates through (one cluster of the synaptic
// constellation per phase). Advanced by REAL signals: the frontend reports "voz" (mic + room up); the backend
// reports "memoria"/"reflejo" over the "vl2" data channel; "listo" = init done (ready), just before zaelar greets.
// Single source of truth for both the animation and the caption. See components/boot-anim.js + BootOverlay.js.
export const BOOT_PHASES = ["encendiendo", "voz", "memoria", "reflejo", "listo"];
export const [bootPhase, setBootPhase] = createSignal("encendiendo");

export const [theme, setTheme]         = createSignal(localStorage.getItem("hb_theme") || "dark");  // "dark" | "light" — dark by default (night-friendly)

export const [micMuted, setMicMuted]   = createSignal(localStorage.getItem("hb_mic_muted") === "1");
export const [camOff, setCamOff]       = createSignal(localStorage.getItem("hb_cam_off") === "1");
export const [botMuted, setBotMuted]   = createSignal(localStorage.getItem("hb_bot_muted") === "1");  // silence zaelar's voice OUTPUT (agent keeps running)

// ⏻ POWER (V2-039 «ojo»): apagado EXPLÍCITO de la sesión de voz por el operador — la única excepción al always-on.
// Persistido: un apagado deliberado sobrevive al refresh; main.js NO auto-(re)conecta mientras esté apagado.
//
// V2-092: este signal ya NO es la verdad, es el ESPEJO LOCAL de una verdad que vive en el servidor
// (`nucleo/runstate.py`, `GET /api/run`). El motivo es el fallo que lo destapó: parado el agente, un vídeo seguía
// reproduciéndose y al recargar arrancaba solo. Con el interruptor únicamente aquí, el backend —widgets,
// background, crons— no tenía a quién preguntar si el operador había parado, y este localStorage es per-navegador
// y per-origen: el mismo zaelar por dos puertos eran dos agentes con opiniones distintas sobre si estaban vivos.
// Ahora: el ⏻ ORDENA al servidor (POST /api/run/stop|start), y el servidor NOTIFICA (SSE `run`) → todas las
// pestañas convergen. El localStorage se queda como arranque instantáneo sin esperar la red.
export const [powerOff, setPowerOffRaw] = createSignal(localStorage.getItem("hb_power_off") === "1");
export const setPowerOff = (off) => { setPowerOffRaw(off); localStorage.setItem("hb_power_off", off ? "1" : "0"); };

// STAMP OF THE OPERATOR'S LAST ⏻ COMMAND (2026-08-14, real failure captured by the operator).
// The server reconciliation in main.js is ASYNCHRONOUS, and on a machine waking from cold it takes seconds.
// If the operator presses ⏻ inside that window, the reply — a snapshot of the state BEFORE the click — landed
// afterwards and set `powerOff` again, tearing down the very session the operator had just asked for. It is the
// classic last-write-wins failure between two clocks: the SLOWEST message won, not the NEWEST one.
// With this stamp the seeding can ask "has the operator commanded anything since I went to fetch this?" and stay
// quiet when the answer is yes. NOT touched by the SSE `run` event: that one IS the server's truth and must win.
export const [powerCmdAt, setPowerCmdAt] = createSignal(0);
export const markPowerCommand = () => setPowerCmdAt(Date.now());

// ⏻ PAUSING (V2-092 addenda, 2026-08-15): a stop requested while a turn's model call is REALLY in flight
// (`nucleo/runstate.py`'s `_inflight`) doesn't cut anything mid-way — it's DEFERRED until that turn ends on its
// own, never on a timer. Meanwhile the agent keeps genuinely running underneath (nothing has been frozen): this
// is just the signal for ⏻ to show that (amber blink) instead of lying by painting itself already off. Set by
// the `run` SSE event (label "pausing"/"resumed") — reaches EVERY tab alike, whether or not it clicked ⏻.
export const [pausing, setPausing] = createSignal(false);

export const [botSpeaking, setBotSpeaking] = createSignal(false);            // gates person-voice visuals
export const [micBlocked, setMicBlocked]   = createSignal({ show: false, msg: "" });  // 🚫 ring over the orb
export const [micLevel, setMicLevel]       = createSignal(0);               // true mic RMS (0..1) for the meter

// ── ¿ESTÁ VIVO EL AGENTE? UNA sola respuesta, derivada — no un signal más que mantener ────────────────────────
// Nace de un fallo real y caro (sesión del operador, 2026-08-10). Cada icono del orbe decidía su aspecto a partir
// de una señal DISTINTA, y ninguna significaba «el agente está funcionando»:
//   · `powerOff` es la INTENCIÓN persistida del operador, no la realidad;
//   · `started` es la realidad, pero no lo miraba nadie para pintar.
// Con `powerOff=false` y la sesión CAÍDA (micrófono denegado, sala perdida, un fallo de arranque) el micro, el
// altavoz y el ⏻ seguían pintados en azul. El operador estuvo un buen rato hablándole a un agente muerto: «como
// yo veía el micrófono encendido, el del altavoz encendido y el de la transcripción encendida, pensaba que estabas
// operativo». No era un fallo de audio: era un estado invisible.
//
// Five states — the fifth (V2-092 addenda, 2026-08-15) is ANOTHER transition, not a made-up state: a stop
// requested with a turn in flight that the server defers until it ends on its own (see `pausing` above). It goes
// BEFORE `off` on purpose: underneath, the agent keeps genuinely running while it lasts, so painting it already
// off would be the same visual lie that `stalled` exists to correct.
//   pausing  → stop requested, waiting for the in-flight turn to end (or for the operator to cancel it).
//   off      → the operator stopped it (⏻). Everything must look and be FROZEN.
//   starting → coming up (connecting room/mic). Neither alive nor stopped: in transit.
//   live     → a session REALLY in progress. The only thing that authorizes painting anything as "on".
//   stalled  → should be on and ISN'T. This is the one that didn't exist; now it's visible.
export const agentState = () => {
  if (pausing()) return "pausing";
  if (powerOff()) return "off";
  if (started()) return "live";
  // `!bootReady()` cubre el hueco del ARRANQUE: entre que la página carga y que `session.start()` marca
  // `starting`, no hay nada puesto todavía — sin esto, cada carga abriría en «stalled» (todo en alarma) durante
  // unos instantes. `bootReady` solo es falso en el primer arranque, así que una sesión que se cae DESPUÉS sí
  // cae en «stalled», que es lo que se quiere ver.
  if (starting() || !bootReady()) return "starting";
  return "stalled";
};
// Único predicado que deben usar las vistas para decidir si algo puede leerse como «activo».
export const agentLive = () => agentState() === "live";

export const [voices, setVoices]       = createSignal([]);
export const [voiceIdx, setVoiceIdx]   = createSignal(0);
export const [voiceFlash, setVoiceFlash] = createSignal({ text: "", show: false });   // transient "🗣 <voice>" label

// ---- live captions (zaelar's speech crawling above the orb) ----
// captionsOn = the 📝 toggle under the orb (default ON). captionSeg = a STREAMING transcription segment from
// LiveKit (RoomEvent.TranscriptionReceived), delivered incrementally IN SYNC with the agent's audio playback —
// { id, text (cumulative for that segment), final }. Seq bumps so the caption component reacts to every update.
// LIVE ONLY — the chat wall keeps the history.
export const [captionsOn, setCaptionsOn] = createSignal(localStorage.getItem("hb_captions_on") !== "0");
export const [captionSeg, setCaptionSeg] = createSignal(null);
let _capSeq = 0;
export const pushCaptionSeg = (id, text, final) => setCaptionSeg({ id, text: text || "", final: !!final, seq: ++_capSeq });
export const toggleCaptions = () => {
  const next = !captionsOn(); setCaptionsOn(next); localStorage.setItem("hb_captions_on", next ? "1" : "0");
  return next;
};

export const [orbStyle, setOrbStyle]   = createSignal(localStorage.getItem("zaelar_orb") || "pro");  // "pro" | "friendly"
export const [gateOn, setGateOn]       = createSignal(localStorage.getItem("zaelar_gate") === "1");  // speaker filter (opt-in)
export const [spk, setSpk]             = createSignal({ show: false, text: "", kind: "" });           // owner-voice indicator

export const [alert, setAlert]         = createSignal(null);   // { msg, onClick } | null  → top banner

// ---- proactive notifications (orchestrator loop / scheduled task fired → zaelar reaches out) ----
// No floating toast: a proactive push surfaces as a live caption over the orb + a chat-wall entry (see sse.js).
export const [cronOpen, setCronOpen]   = createSignal(false);  // cron manager panel visible?
export const [cronJobs, setCronJobs]   = createSignal([]);     // [{id,name,schedule,state,paused,...}]

// ---- background activity indicators (liquid blobs FLANKING the orb, left & right) ----
// Every in-flight SlowBrain task (widget build/modify, web task, memory, deep reasoning) becomes ONE liquid blob +
// a short gerund label ("Creando un widget…") placed in a PRECISE zone to the LEFT or RIGHT of the orb — never on
// top of the orb, the captions above it, or the connection line at the bottom-left (that scattered-everywhere
// layout was the operator's complaint). New tasks alternate sides (balance left↔right) and STACK vertically inside
// their zone. Fed by SSE "task" events (kind "task", label start/end) from nucleo/dispatch.py. Side + breathing
// phase are frozen at start so the blob doesn't jump on re-render. On end it flashes "done", then clears.
// NOT a floating toast — it's ambient background-activity, no message content, tied to the canvas.
export const [tasks, setTasks] = createSignal([]);   // [{ id, text, done, side:'l'|'r', delay, hue }]
export const startTask = (id, text) => setTasks(xs => {
  if (xs.some(t => t.id === id)) return xs.map(t => t.id === id ? { ...t, text: text || t.text, done: false } : t);
  const live = xs.filter(t => !t.done);                   // balance across the two zones by ACTIVE count
  const onLeft = live.filter(t => t.side === "l").length;
  const onRight = live.filter(t => t.side === "r").length;
  const side = onLeft <= onRight ? "l" : "r";             // fill the emptier side first (ties → left)
  const delay = -(Math.random() * 3).toFixed(2);          // desync the slow breathing so they don't pulse in unison
  const hue = Math.round((Math.random() * 2 - 1) * 38);   // ±38° hue-rotate → each blob a slightly different tint
  return [...xs, { id, text: text || "Working…", done: false, side, delay, hue }];  // …same cool blue-teal gama
});
export const endTask = (id) => {
  setTasks(xs => xs.map(t => t.id === id ? { ...t, done: true } : t));   // settle to a solid teal dot…
  setTimeout(() => setTasks(xs => xs.filter(t => t.id !== id)), 1100);   // …then it clears
};
// V2-059: PROGRESO estructurado del brain worker → el chip muestra la nota + paso/% (el ring del hexágono queda
// para después; lo que importa es el dato). pct −1 = desconocido. Crea el chip si aún no existe (idempotente).
export const setTaskProgress = (id, note, pct, done, total) => setTasks(xs => {
  const tag = (total ? ` ${Math.min(done || 0, total)}/${total}` : "") + (pct >= 0 ? ` · ${pct}%` : "");
  const text = ((note || "").trim() || "Working…") + tag;
  if (!xs.some(t => t.id === id)) return [...xs, { id, text, done: false, side: "l", delay: 0, hue: 0, pct }];
  return xs.map(t => t.id === id ? { ...t, text, pct } : t);
});
// V2-038: RECONCILIA los chips contra la VERDAD (GET /api/tasks lee el registro RAM del server). Al (re)conectar,
// un reinicio/crash del server pudo dejar chips huérfanos (una tarea matada que nunca emitió `end`) → aquí se
// dropan los que ya no existen y se marca `waiting` el que espera respuesta del operador. Fin de la pieza inconexa.
// 2026-08-18: y se FILTRA por `status` en vez de dar por vivo todo lo que venga. El server ya no manda tareas
// terminadas (`dispatch.active_sessions` las filtra), pero este lado no puede depender de eso: cada fila que
// entra aquí se pinta «en curso», así que una `done` que se colara resucitaría el chip fantasma que veníamos de
// arreglar — y encima TAPA su propia fila ✓ del histórico (ChatWall descarta del histórico los ids que están
// vivos). Dos guardas para la misma verdad, en los dos lados de la costura.
const _isLive = (s) => !s || !s.status || s.status === "queued" || s.status === "running";
export const reconcileTasks = (sessions) => {
  const live = new Map((sessions || []).filter(_isLive).map(s => [String(s.id), s]));
  setTasks(xs => {
    // conserva/actualiza los vivos; marca done (→ clear) los que ya no están en la verdad
    const kept = xs.filter(t => t.done || live.has(String(t.id))).map(t => {
      const s = live.get(String(t.id));
      return s ? { ...t, text: (s.phase || t.text) + (s.paused ? " (paused)" : ""),
                   waiting: (s.waiting_on === "user"), paused: !!s.paused } : t;
    });
    const known = new Set(kept.map(t => String(t.id)));
    const added = [];
    let i = kept.filter(t => !t.done).length;
    for (const [id, s] of live) {
      if (known.has(id)) continue;
      added.push({ id, text: (s.phase || s.goal || "Working…") + (s.paused ? " (paused)" : ""), done: false,
                   side: (i++ % 2 === 0) ? "l" : "r", delay: 0, hue: 0,
                   waiting: (s.waiting_on === "user"), paused: !!s.paused });
    }
    return [...kept, ...added];
  });
};
export const fetchTasks = async () => {
  try {
    const r = await fetch("/api/tasks", { cache: "no-cache" });
    const d = await r.json();
    reconcileTasks(d.sessions || []);
  } catch (_) {}
};

// V2-079: HISTÓRICO de Brain Workers TERMINADOS (ledger durable) — la pestaña «Procesos» del ChatWall lo pinta
// bajo los vivos (store.tasks) para dar perspectiva de lo hecho hoy/ayer/hace días. Se refresca al abrir la
// pestaña y cuando una tarea acaba (SSE task:end).
export const [workerHistory, setWorkerHistory] = createSignal([]);  // [{id,kind,goal,status,finished_at,...}]

// SESIÓN DE TRABAJO en curso (2026-08-10). Un Reset deliberado abre una sesión NUEVA en el backend
// (voice/observer.py::rotate_session: id nuevo + observabilidad a cero). Este contador sube en cada RESET y es la
// señal que usan las vistas IMPERATIVAS —la columna de observabilidad, que pinta sus filas a mano y no re-renderiza
// por datos— para vaciarse. Sin él, tras un Reset el panel seguía mostrando las filas de la sesión anterior: el
// backend había empezado en blanco y la pantalla no, que es la peor de las dos mentiras posibles.
export const [sessionEpoch, bumpSessionEpoch] = createSignal(0);
export const newSession = () => bumpSessionEpoch(n => n + 1);
export const fetchWorkerHistory = async () => {
  try {
    const r = await fetch("/api/workers/history", { cache: "no-cache" });
    const d = await r.json();
    setWorkerHistory(Array.isArray(d.history) ? d.history : []);
  } catch (_) {}
};

// V2-086: CONEXIONES A CLUSTERS — nativo, 4ª pestaña del ChatWall. La red (hoy MeshKore; mañana quizá otros
// proveedores) es infraestructura del sistema, no un widget de usuario: por eso vive junto a Procesos y Crons y
// NO en el catálogo. Lista los clusters de los que hay CREDENCIALES (conectados o no) con su estado y tráfico.
// Deliberadamente SIN conversación: los clusters tienen su propio monitor, aquí solo se administra la conexión.
export const [clusters, setClusters] = createSignal([]);  // [{name,connected,handle,online[],public,msgs,...}]
export const fetchClusters = async () => {
  try {
    const r = await fetch("/api/meshkore/status", { cache: "no-cache" });
    const d = await r.json();
    setClusters(Array.isArray(d.clusters) ? d.clusters : []);
  } catch (_) { setClusters([]); }
};
// Confirmación Sí/No de CONECTAR a un cluster (V2-086). Vive aquí y se pinta en la pestaña «Clusters» porque la
// red no es una tarjeta del canvas. El gate es determinista y NO se puede saltar: por muy convincente que sea un
// bloque de texto pegado, sin un «sí» explícito del operador no se abre ningún socket.
export const [clusterConfirm, setClusterConfirm] = createSignal(null);   // {question} | null
export const clusterConfirmResolve = async (ok) => {
  setClusterConfirm(null);
  try { await fetch("/api/meshkore/confirm", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ ok: !!ok }) }); } catch (_) {}
  await fetchClusters();
};
export const clusterConnect = async (name) => {
  try { await fetch("/api/meshkore/connect", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ name }) }); } catch (_) {}
  await fetchClusters();
};
export const clusterDisconnect = async (name) => {
  try { await fetch("/api/meshkore/disconnect", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ name }) }); } catch (_) {}
  await fetchClusters();
};

// ---- memory map (🧠 the "map of zaelar's memory": state + short/long term + concept graph, V2-014) ----
// memOpen = the 🧠 icon in the orb bowl toggles the full-screen visualizer. memBump increments on every
// `memory.updated` SSE push (bridged from the bus in server/__init__.py) so the map refetches LIVE, no polling.
// Configuración full-screen (V2-043): elegir API/modelo por pieza + resumen de APIs con saldo. Abierta por el ⚙.
export const [configOpen, setConfigOpen] = createSignal(false); // config area overlay visible?
export const [benchmarksOpen, setBenchmarksOpen] = createSignal(false); // benchmarks screen (opened FROM config)
export const [apiSummary, setApiSummary] = createSignal([]);     // [{key,enables,set,state,detail,balance?}] — saldos
export const [apiAlerts, setApiAlerts]   = createSignal([]);     // subconjunto warn/error para el diálogo de estado

export const [memOpen, setMemOpen]     = createSignal(false);  // memory map overlay visible?
export const [memBump, setMemBump]     = createSignal(0);      // ticks on each memory.updated (real-time refresh)
export const bumpMemory = () => setMemBump(n => n + 1);

// ---- feedback widget (V2-099: floating "send feedback to the developers" launcher + panel) ----
export const [feedbackOpen, setFeedbackOpen] = createSignal(false);         // panel visible?
export const [feedbackTab, setFeedbackTab]   = createSignal("new");        // "new" | "sent"
export const [feedbackItems, setFeedbackItems] = createSignal([]);         // [{id,message,status,reply_text,created_at}]
export const [feedbackSending, setFeedbackSending] = createSignal(false);  // POST in flight?
// Live observability (V2-014): the latest memory pulse {op, ids} — per-node tint (write=green,
// overwrite=amber, query=blue). Separate from memBump so a query (no data change → no refetch) still tints.
export const [memPulse, setMemPulse]   = createSignal(null);
export const pushMemPulse = (ev) => setMemPulse(ev);

// ---- language onboarding (V2-101): first-run blocking modal — "ask" (English question, voice or quick-pick) →
// "detected" (translated loading line while the full bundle/alias-pack generate) → "ready" (unblocks). Gated
// open by main.js reading GET /api/i18n/state's `chosen` field once bootReady() flips; closed by the "ready"
// SSE phase. Never reopened once closed — a returning operator switching language via ⚙ does NOT go through
// this (that path already applies live without blocking anything).
export const [langOnboardOpen, setLangOnboardOpen]   = createSignal(false);
export const [langOnboardPhase, setLangOnboardPhase] = createSignal("ask");   // "ask" | "detected" | "ready"
export const [langOnboardLoading, setLangOnboardLoading] = createSignal(""); // translated onboarding.loading text

// ---- MOBILE SHELL (V2-124) — signals owned by the mobile PWA shell (frontend/mobile/), never read by the
// desktop. They live HERE, in the shared store, and not in a store of their own, for the reason that governs the
// whole mobile split: there is ONE truth about this agent. Power, energy, chat, tasks and language are already
// here and both shells read the same signals; a second store would be a second truth, and a state that can lie
// is the failure this codebase has paid for more than once. These three are simply the surfaces that only exist
// on a phone — the desktop has a top bar and a floating launcher instead of a bottom menu.
export const [mobileMenuOpen, setMobileMenuOpen]         = createSignal(false);   // ☰ sheet: account · profile · feedback · settings
export const [mobileSettingsOpen, setMobileSettingsOpen] = createSignal(false);   // the small settings sheet, opened FROM the menu
// The voice lock (server/livekit_api.py: ONE live voice session per machine). When the phone finds it HELD by
// another surface, it must not fight, retry in a loop, or paint itself live: it says so and offers to take the
// voice over. null = no conflict. See mobile/app/main.js.
export const [mobileVoiceHeld, setMobileVoiceHeld]       = createSignal(false);

// ---- bóveda de secretos (V2-060): modal NATIVO (crear/desbloquear por passphrase o passkey; mostrar el valor) ----
export const [vaultOpen, setVaultOpen]       = createSignal(false);
export const [vaultMode, setVaultMode]       = createSignal("unlock");   // "create" | "unlock" | "reveal" | "manage"
export const [vaultStatus, setVaultStatus]   = createSignal({ exists: false, unlocked: false, methods: [], secret_count: 0 });
export const [vaultPendingMid, setVaultPendingMid] = createSignal(null); // secreto a mostrar tras desbloquear
export const [vaultRevealed, setVaultRevealed] = createSignal(null);     // { label, value } tras revelar (efímero)
export const [vaultMsg, setVaultMsg]         = createSignal("");         // mensaje/estado dentro del modal
// abre el modal en un modo; opts.mid = secreto pendiente de mostrar tras desbloqueo
export const openVault = (mode, opts = {}) => {
  setVaultMode(mode || "unlock");
  setVaultPendingMid(opts.mid != null ? opts.mid : null);
  setVaultRevealed(null); setVaultMsg("");
  setVaultOpen(true);
};
export const closeVault = () => { setVaultOpen(false); setVaultRevealed(null); setVaultPendingMid(null); setVaultMsg(""); };

// ---- heartbeat / ECG (V2-039): el ELECTROCARDIOGRAMA del orbe. `pulse` late en cada beat que llega por SSE — un
// `loop.tick` REAL del loop orquestador (~1 Hz en reposo = el latido propio del server, revisando crons/procesos)
// o el cierre de un turno del FlashBrain (un pico QRS más alto). El componente Ecg lo lee + tasks()/botSpeaking()
// para el RITMO (en reposo lento y regular; con tareas/turnos en marcha acelera). Fed por sse.js. seq fuerza la
// reactividad en cada latido aunque el payload se repita.
export const [pulse, setPulse] = createSignal(null);
let _pulseSeq = 0;
export const pushPulse = (ev = {}) => setPulse({ ...ev, seq: ++_pulseSeq });

// ---- HARD reset confirmation (botón Reset del TopBar) ----
// El Reset es destructivo (para todos los procesos de fondo + congela el trabajo en curso en la memoria de estado),
// así que pide confirmación antes de disparar session.resetHard(). true = diálogo visible.
export const [resetConfirmOpen, setResetConfirmOpen] = createSignal(false);
// V2-063: reset con checkboxes (Memoria/Credenciales) — el server se reinicia solo; true mientras esperamos
// que vuelva a responder, para pintar un overlay "reiniciando…" en vez de dejar la app en un estado roto.
export const [restarting, setRestarting] = createSignal(false);

// ---- wizard de primer arranque (perfiles local/cloud + detector de capacidades, V2-040). Se auto-abre en el
// primer arranque (config sin validar) y es reabrible desde el TopBar (🧭). ----
export const [wizardOpen, setWizardOpen] = createSignal(false);

// ---- perfil CLOUD: en una cuenta de pago (cloud_profile del /api/config, = ZAELAR_USER_ID puesto) el header se
// reduce a tema + perfil; en self-host es siempre false y el header no cambia (cero regresión). Lo siembra main.js
// al arrancar desde /api/config. ----
export const [cloudProfile, setCloudProfile] = createSignal(false);        // ¿cuenta cloud? (header reducido)
export const [accountOpen, setAccountOpen]   = createSignal(false);        // panel de cuenta (icono perfil, solo cloud)

// ---- SALDO DE ENERGY (la PILA de la barra superior, solo cloud). `known:false` = todavía no sabemos el saldo, que
// NO es lo mismo que cero: la pila se pinta apagada, nunca vacía. Lo siembra main.js desde /api/energy y lo refresca
// el SSE (`kind:"energy"`) cada vez que el agente gasta, así baja EN VIVO sin que nadie pregunte. ----
export const [energy, setEnergy] = createSignal({ cloud: false, known: false, balance: null, capacity: null });

// ---- system status (ⓘ panel: Hermes / voz / LLM / STT / TTS / cluster · credit + health) ----
export const [statusOpen, setStatusOpen] = createSignal(false);            // status panel visible?
export const [status, setStatus]         = createSignal({ overall: "unknown", items: [] });

// ---- debug / observability side-column (resizable right column, fed by the SSE /events bus) ----
export const [debugOpen, setDebugOpen]   = createSignal(localStorage.getItem("hb_debug_open") === "1");
export const [debugWidth, setDebugWidth] = createSignal(Math.max(300, parseInt(localStorage.getItem("hb_debug_w") || "460", 10)));

// ---- chat wall (text channel to the agent) ----
export const [chatOpen, setChatOpen]   = createSignal(false);  // chat wall panel visible?
export const [chatTab, setChatTab]     = createSignal("chat");  // V2-079/086: "chat"|"procesos"|"crons"|"clusters"
export const [chatMsgs, setChatMsgs]   = createSignal([]);     // [{ role:"you"|"agent", text }]
// TOPE (2026-07-23, petición del operador): sin límite, un hilo largo (p.ej. horas hablando con un agente de
// cluster por WebSocket) crece sin fin — y ChatWall reconstruye TODO el DOM desde `chatMsgs()` en cada push
// (`listEl.replaceChildren(...msgs.map(...))`), así que miles de líneas congelarían el frontend. Se recorta a
// los últimos N en el store (una sola fuente de verdad) en vez de en el componente, para que ningún consumidor
// futuro de `chatMsgs` pueda pasarse por alto el límite. Es solo el buffer de RENDER; la memoria real (corto/
// largo plazo) sigue su propio camino en `memory/`, ya gestionado — este tope es un cinturón de seguridad del
// frontend, no una capa de memoria.
const CHAT_CAP = 100;
const _capChat = xs => xs.length > CHAT_CAP ? xs.slice(xs.length - CHAT_CAP) : xs;
export const pushChat = (m) => setChatMsgs(xs => _capChat([...xs, m]));
// Agent line for the history, DEDUPED: proactive pushes arrive on two channels (SSE "notify" + the agent's own
// transcript when it speaks the same text) — collapse an immediate repeat (ignoring a leading 🔔).
// 2026-08-18 (V2-116): el dedup compara por PREFIJO, no por igualdad exacta, y limpia también el marcador 💬.
// Motivo: la respuesta se empuja al muro en cuanto el modelo la genera (fluidez — antes había que esperar a que
// LiveKit cerrase el item de conversación, o sea a que el TTS TERMINARA de hablarla: 5-12 s medidos, y el
// operador lo vivió como «la he oído por voz y el texto ha tardado un minuto»). El `transcript` de LiveKit llega
// después con el MISMO texto y tiene que fundirse con el ya pintado; y si un barge-in cortó la locución a medias,
// llega TRUNCADO — con igualdad exacta saldrían dos burbujas, una completa y una a medias. Se conserva la más
// larga (lo que el agente quiso decir), que es la que sirve de historial.
const _CHAT_MARKERS = /^(?:🔔|💬)\s*/;
export const pushAgentChat = (text) => {
  const norm = s => (s || "").replace(_CHAT_MARKERS, "").trim();
  setChatMsgs(xs => {
    const last = xs[xs.length - 1];
    if (last && last.role === "agent") {
      const a = norm(last.text), b = norm(text);
      if (a && b && (a === b || a.startsWith(b))) return xs;          // ya está (o lo nuevo es una versión corta)
      if (a && b && b.startsWith(a)) {                                 // lo nuevo AMPLÍA lo ya pintado → sustituye
        return _capChat([...xs.slice(0, -1), { role: "agent", text }]);
      }
    }
    return _capChat([...xs, { role: "agent", text }]);
  });
};

// Convenience helpers used across services (mirror the old showAlert/hideAlert/setConn).
export const showAlert = (msg, onClick) => setAlert({ msg, onClick });
export const hideAlert = () => setAlert(null);
export const setConnState = (label, ok = false) => setConn({ label, ok });

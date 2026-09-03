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

// ⏻ POWER (V2-039 «ojo»): EXPLICIT shutdown of the voice session by the operator — the only exception to always-on.
// Persisted: a deliberate shutdown survives refresh; main.js does NOT auto-(re)connect while it is off.
//
// V2-092: this signal is NO LONGER the truth; it is the LOCAL MIRROR of a truth that lives on the server
// (`nucleo/runstate.py`, `GET /api/run`). The reason was the failure that exposed it: with the agent stopped, a video kept
// playing and restarting made it start on its own. With the switch only here, the backend —widgets,
// background, crons— had no one to ask whether the operator had stopped it, and this localStorage is per-browser
// and per-origin: the same zaelar on two ports were two agents with different opinions about whether they were alive.
// Now: ⏻ COMMANDS the server (POST /api/run/stop|start), and the server NOTIFIES (SSE `run`) → all
// tabs converge. localStorage remains for instant startup without waiting for the network.
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

// ── IS THE AGENT ALIVE? ONE single derived answer — not another signal to maintain ────────────────────────
// It arose from a real and costly failure (operator session, 2026-08-10). Each orb icon decided its appearance from
// a DIFFERENT signal, and none meant «the agent is running»:
//   · `powerOff` is the operator's persisted INTENTION, not reality;
//   · `started` is reality, but nobody checked it for rendering.
// With `powerOff=false` and the session DOWN (microphone denied, room lost, a startup failure), the mic,
// speaker, and ⏻ were still rendered blue. The operator spent quite a while talking to a dead agent: «because
// I saw the microphone on, the speaker on, and the transcription on, so I thought you were
// I saw the microphone on, the speaker on, and the transcription on, I thought you were operational». It was not
// an audio failure: it was an invisible state.
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
  // `!bootReady()` covers the STARTUP gap: between the page loading and `session.start()` setting
  // `starting`, nothing has been set yet — without this, every load would open in «stalled» (everything in alarm)
  // for a few moments. `bootReady` is false only on the first startup, so a session that goes down AFTERWARD does
  // fall into «stalled», which is what should be shown.
  if (starting() || !bootReady()) return "starting";
  return "stalled";
};
// The only predicate views should use to decide whether something can be read as «active».
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
  return [...xs, { id, text: text || "Working…", done: false, side, delay, hue }];  // …same cool blue-teal range
});
export const endTask = (id) => {
  setTasks(xs => xs.map(t => t.id === id ? { ...t, done: true } : t));   // settle to a solid teal dot…
  setTimeout(() => setTasks(xs => xs.filter(t => t.id !== id)), 1100);   // …then it clears
};
// V2-059: STRUCTURED progress from the brain worker → the chip shows the note + step/% (the hexagon ring comes
// later; the data is what matters). pct −1 = unknown. Creates the chip if it does not yet exist (idempotent).
export const setTaskProgress = (id, note, pct, done, total) => setTasks(xs => {
  const tag = (total ? ` ${Math.min(done || 0, total)}/${total}` : "") + (pct >= 0 ? ` · ${pct}%` : "");
  const text = ((note || "").trim() || "Working…") + tag;
  if (!xs.some(t => t.id === id)) return [...xs, { id, text, done: false, side: "l", delay: 0, hue: 0, pct }];
  return xs.map(t => t.id === id ? { ...t, text, pct } : t);
});
// V2-038: RECONCILE the chips against the TRUTH (GET /api/tasks reads the server's RAM record). Upon (re)connecting,
// a server restart/crash may have left orphaned chips (a killed task that never emitted `end`) → here we
// drop those that no longer exist and mark `waiting` for the one awaiting the operator's response. End of the disconnected piece.
// 2026-08-18: also FILTER by `status` instead of assuming everything received is alive. The server no longer sends completed tasks
// (`dispatch.active_sessions` filters them), but this side cannot depend on that: every row entering here is rendered «in progress»,
// so a leaked `done` would resurrect the ghost chip we had just fixed — and would also COVER its own ✓ history row (ChatWall
// discards from history the ids that are alive). Two guards for the same truth, on both sides of the seam.
const _isLive = (s) => !s || !s.status || s.status === "queued" || s.status === "running";
export const reconcileTasks = (sessions) => {
  const live = new Map((sessions || []).filter(_isLive).map(s => [String(s.id), s]));
  setTasks(xs => {
    // preserve/update the live ones; mark done (→ clear) those no longer in the truth
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

// V2-079: HISTORY of COMPLETED Brain Workers (durable ledger) — the ChatWall «Processes» tab renders it
// below the live ones (store.tasks) to provide perspective on what was done today/yesterday/days ago. It refreshes when the
// tab opens and when a task ends (SSE task:end).
export const [workerHistory, setWorkerHistory] = createSignal([]);  // [{id,kind,goal,status,finished_at,...}]

// CURRENT WORK SESSION (2026-08-10). A deliberate Reset opens a NEW session in the backend
// (voice/observer.py::rotate_session: new id + observability reset to zero). This counter rises on every RESET and is the
// signal used by IMPERATIVE views —the observability column, which renders its rows manually and does not re-render
// from data— to clear themselves. Without it, after a Reset the panel kept showing rows from the previous session: the
// backend had started blank while the screen had not, the worse of the two possible lies.
export const [sessionEpoch, bumpSessionEpoch] = createSignal(0);
export const newSession = () => bumpSessionEpoch(n => n + 1);
export const fetchWorkerHistory = async () => {
  try {
    const r = await fetch("/api/workers/history", { cache: "no-cache" });
    const d = await r.json();
    setWorkerHistory(Array.isArray(d.history) ? d.history : []);
  } catch (_) {}
};

// V2-086: CLUSTER CONNECTIONS — native, ChatWall's 4th tab. The network (MeshKore today; perhaps other providers
// tomorrow) is system infrastructure, not a user widget: that is why it lives alongside Processes and Crons and
// NOT in the catalog. Lists clusters for which CREDENTIALS exist (connected or not), with their status and traffic.
// Deliberately WITHOUT conversation: clusters have their own monitor; this only manages the connection.
export const [clusters, setClusters] = createSignal([]);  // [{name,connected,handle,online[],public,msgs,...}]
export const fetchClusters = async () => {
  try {
    const r = await fetch("/api/meshkore/status", { cache: "no-cache" });
    const d = await r.json();
    setClusters(Array.isArray(d.clusters) ? d.clusters : []);
  } catch (_) { setClusters([]); }
};
// Yes/No confirmation to CONNECT to a cluster (V2-086). It lives here and renders in the «Clusters» tab because the
// network is not a canvas card. The gate is deterministic and CANNOT be bypassed: no matter how convincing a pasted
// block of text is, no socket opens without an explicit «yes» from the operator.
// V2-518 — pending WIDGET confirmation (delete / restore / irreversible data-op), mirrored into the chat
// thread per the house norm: no popups — a question renders IN the conversation with Yes/No, answerable
// there or by voice. Fed by the same SSE "confirm"/"confirm-cancel" events that paint the card overlay.
export const [widgetConfirm, setWidgetConfirm] = createSignal(null);     // {id, question, action} | null
export const widgetConfirmResolve = async (ok) => {
  const c = widgetConfirm(); setWidgetConfirm(null);
  if (!c) return;
  try { await fetch(`/widgets/${c.id}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ ok: !!ok }) }); } catch (_) {}
};

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
// Full-screen configuration (V2-043): choose API/model per component + API balance summary. Opened by ⚙.
export const [configOpen, setConfigOpen] = createSignal(false); // config area overlay visible?
// V2-561 — which of ConfigPanel's OWN tabs to land on the next time it opens (its tab state is a private
// closure variable, not store-backed: there was no way from outside to say "open on Conectores"). Consumed
// ONCE by ConfigPanel's own open-effect and cleared right after, so it never sticks past the request that
// asked for it — a stale value here would keep re-forcing the tab on every later ⚙ click.
export const [configInitialTab, setConfigInitialTab] = createSignal(null);
export const [benchmarksOpen, setBenchmarksOpen] = createSignal(false); // benchmarks screen (opened FROM config)
export const [apiSummary, setApiSummary] = createSignal([]);     // [{key,enables,set,state,detail,balance?}] — saldos
export const [apiAlerts, setApiAlerts]   = createSignal([]);     // warn/error subset for the status dialog

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

// ---- secret vault (V2-060): NATIVE modal (create/unlock by passphrase or passkey; show the value) ----
export const [vaultOpen, setVaultOpen]       = createSignal(false);
export const [vaultMode, setVaultMode]       = createSignal("unlock");   // "create" | "unlock" | "reveal" | "manage"
export const [vaultStatus, setVaultStatus]   = createSignal({ exists: false, unlocked: false, methods: [], secret_count: 0 });
export const [vaultPendingMid, setVaultPendingMid] = createSignal(null); // secret to show after unlocking
export const [vaultRevealed, setVaultRevealed] = createSignal(null);     // { label, value } after revealing (ephemeral)
export const [vaultMsg, setVaultMsg]         = createSignal("");         // message/status inside the modal
// opens the modal in a mode; opts.mid = secret pending display after unlocking
export const openVault = (mode, opts = {}) => {
  setVaultMode(mode || "unlock");
  setVaultPendingMid(opts.mid != null ? opts.mid : null);
  setVaultRevealed(null); setVaultMsg("");
  setVaultOpen(true);
};
export const closeVault = () => { setVaultOpen(false); setVaultRevealed(null); setVaultPendingMid(null); setVaultMsg(""); };

// ---- heartbeat / ECG (V2-039): the orb's ELECTROCARDIOGRAM. `pulse` beats on every beat arriving via SSE — a
// `loop.tick` REAL from the orchestrator loop (~1 Hz at rest = the server's own heartbeat, checking crons/processes)
// or the completion of a FlashBrain turn (a higher QRS spike). The Ecg component reads it + tasks()/botSpeaking()
// for the RHYTHM (slow and regular at rest; faster with tasks/turns running). Fed by sse.js. seq forces
// reactivity on every beat even when the payload repeats.
export const [pulse, setPulse] = createSignal(null);
let _pulseSeq = 0;
export const pushPulse = (ev = {}) => setPulse({ ...ev, seq: ++_pulseSeq });

// ---- HARD reset confirmation (TopBar Reset button) ----
// Reset is destructive (stops all background processes + freezes current work in the state memory),
// so it requests confirmation before triggering session.resetHard(). true = dialog visible.
export const [resetConfirmOpen, setResetConfirmOpen] = createSignal(false);
// V2-063: reset with checkboxes (Memory/Credentials) — the server restarts itself; true while we wait
// for it to respond again, so we render a "restarting…" overlay instead of leaving the app in a broken state.
export const [restarting, setRestarting] = createSignal(false);

// ---- first-start wizard (local/cloud profiles + capability detector, V2-040). It opens automatically on the
// first startup (unvalidated config) and can be reopened from the TopBar (🧭). ----
export const [wizardOpen, setWizardOpen] = createSignal(false);

// ---- CLOUD profile: in a paid account (cloud_profile from /api/config, = ZAELAR_USER_ID set), the header is
// reduced to theme + profile; in self-host it is always false and the header does not change (zero regression). main.js seeds it
// al arrancar desde /api/config. ----
export const [cloudProfile, setCloudProfile] = createSignal(false);        // cloud account? (reduced header)
export const [accountOpen, setAccountOpen]   = createSignal(false);        // account panel (profile icon, cloud only)

// ---- ENERGY BALANCE (the top-bar BATTERY, cloud only). `known:false` = we do not know the balance yet, which is
// NOT the same as zero: the battery renders dimmed, never empty. main.js seeds it from /api/energy and SSE refreshes
// it (`kind:"energy"`) whenever the agent spends, so it drops LIVE without anyone asking. ----
export const [energy, setEnergy] = createSignal({ cloud: false, known: false, balance: null, capacity: null });

// ---- system status (ⓘ panel: Hermes / voz / LLM / STT / TTS / cluster · credit + health) ----
export const [statusOpen, setStatusOpen] = createSignal(false);            // status panel visible?
export const [status, setStatus]         = createSignal({ overall: "unknown", items: [] });

// ---- debug / observability side-column (resizable right column, fed by the SSE /events bus) ----
export const [debugOpen, setDebugOpen]   = createSignal(localStorage.getItem("hb_debug_open") === "1");
export const [debugWidth, setDebugWidth] = createSignal(Math.max(300, parseInt(localStorage.getItem("hb_debug_w") || "460", 10)));

// ---- chat wall (text channel to the agent) ----
export const [chatOpen, setChatOpen]   = createSignal(false);  // chat wall panel visible?
export const [chatTab, setChatTab]     = createSignal("chat");  // V2-079/086/561: "chat"|"procesos"|"crons"|"clusters"|"conectores"
export const [chatMsgs, setChatMsgs]   = createSignal([]);     // [{ role:"you"|"agent", text }]
// CAP (2026-07-23, operator request): without a limit, a long thread (e.g. hours talking with a
// cluster over WebSocket) grows without end — and ChatWall rebuilds the ENTIRE DOM from `chatMsgs()` on every push
// (`listEl.replaceChildren(...msgs.map(...))`), so thousands of lines would freeze the frontend. It is trimmed to
// the last N in the store (a single source of truth) rather than in the component, so no future consumer
// of `chatMsgs` can overlook the limit. This is only the RENDER buffer; real memory (short-/
// long-term) follows its own path in `memory/`, already managed — this cap is a frontend safety belt,
// not a memory layer.
const CHAT_CAP = 100;
const _capChat = xs => xs.length > CHAT_CAP ? xs.slice(xs.length - CHAT_CAP) : xs;
export const pushChat = (m) => setChatMsgs(xs => _capChat([...xs, m]));
// Agent line for the history, DEDUPED: proactive pushes arrive on two channels (SSE "notify" + the agent's own
// transcript when it speaks the same text) — collapse an immediate repeat (ignoring a leading 🔔).
// 2026-08-18 (V2-116): dedup compares by PREFIX, not exact equality, and also removes the 💬 marker.
// Reason: the response is pushed to the wall as soon as the model generates it (fluency — previously we had to wait for
// LiveKit close the conversation item, that is, until TTS FINISHED speaking it: 5-12 seconds measured, and the
// the operator experienced it as «I heard it by voice and the text took a minute»). LiveKit's `transcript` arrives
// afterward with the SAME text and must merge with what is already rendered; and if a barge-in cut the speech short,
// it arrives TRUNCATED — exact equality would produce two bubbles, one complete and one partial. The longer one
// is kept (what the agent intended to say), as it is the useful history.
const _CHAT_MARKERS = /^(?:🔔|💬)\s*/;
export const pushAgentChat = (text) => {
  const norm = s => (s || "").replace(_CHAT_MARKERS, "").trim();
  setChatMsgs(xs => {
    const last = xs[xs.length - 1];
    if (last && last.role === "agent") {
      const a = norm(last.text), b = norm(text);
      if (a && b && (a === b || a.startsWith(b))) return xs;          // already present (or the new one is a shorter version)
      if (a && b && b.startsWith(a)) {                                 // the new one EXTENDS what is rendered → replace
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

// ============================================================================
// sse.js — server-sent events stream (/events). Routes backend pushes to the
// reactive store (bot speech, latency) and to the widget desktop (show/create/
// modify/close). Transcripts feed the voice-command fast-path. The brain remains
// the authority; this just reacts to what it emits.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { handleWidgetVoice } from "./voiceCommands.js?v=2";
import { refreshStatus } from "./status.js?v=2";
import * as vault from "./vault.js?v=1";
import { t, applyLang } from "../core/i18n.js?v=1";

// V2-464 — modo ESCAPARATE: ?showcase=1 en la URL. Lo usa el grabador de casos de uso (recorder.py): chat
// abierto y rejilla auto-ordenada, para que el vídeo salga legible sin manos.
const _SHOWCASE = new URLSearchParams(location.search).has("showcase");
let _arrT = null;

let es = null;

export function openSSE(desktop) {
  if (es) return;               // ya suscrito: reabrir tiraría el stream vivo y perdería los eventos en vuelo
  es = new EventSource("/events");
  // V2-038: al (re)conectar, RECONCILIA los chips de actividad contra la verdad del server (GET /api/tasks lee el
  // registro RAM) → fin de los chips huérfanos tras un reinicio/crash. El ESTADO manda; la UI es su espejo.
  es.onopen = () => { try { store.fetchTasks(); } catch (_) {} };
  es.onmessage = ev => {
    let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
    if (d.kind === "bot_speech") {                              // gate person-voice visuals + drive live captions + latency
      // LiveKit engine emits label "speaking"/"idle" (+ a `speaking` bool); the older engine used "started"/"stopped".
      // Prefer the explicit bool, fall back to either label vocabulary.
      const speaking = typeof d.speaking === "boolean" ? d.speaking
                     : /speaking|started/.test(String(d.label));
      store.setBotSpeaking(speaking);
      if (d.ttfa_ms != null) store.setLatency(d.ttfa_ms + " ms");
    } else if (d.kind === "error") {
      console.warn("voice error:", d.label || "");              // clean screen: log only, no banner
      refreshStatus();                                          // but do reflect it in the ◉ status icon
    } else if (d.kind === "widget" && desktop) {
      // EL CANVAS NUNCA OBEDECE SU PROPIO INFORME (V2-261). `src:"user"` marca los eventos que NACEN del canvas:
      // `desktop._persist()` reporta el conjunto abierto a `/api/canvas/state`, y esa ruta compara con el anterior
      // y emite `widget/show|close` con procedencia «user» para dejar la acción manual del operador en la línea de
      // tiempo (auditoría V2-039 — antes eran acciones SILENCIOSAS). Pero esa auditoría viaja por el MISMO canal
      // que las ÓRDENES, así que volvía aquí y se ejecutaba.
      //
      // Consecuencia medida, y el operador la vio en pantalla: la tarea abre `navegador::t2`, el canvas lo
      // reporta, la ruta NORMALIZA la instancia a su base (`navegador`), el diff dice «se ha abierto navegador» y
      // dos segundos después aparecía una tarjeta de navegador BASE vacía («abriendo pestaña…») encima de la real.
      // Evidencia: `['navegador::t1'] → ['navegador::t1','navegador']`, siempre 2 s después. Estaba visto desde
      // V2-047 F9 («two browsers, one blank») y solo INSTRUMENTADO, nunca cerrado.
      //
      // Se corta aquí, en el ÚNICO sitio por el que los dos hosts (escritorio y móvil) reciben esto, y no en la
      // ruta: la auditoría necesita seguir emitiendo con su etiqueta para que la observabilidad y el Master la
      // sigan contando igual. La regla es la que faltaba, no el evento: **un informe de lo que ya pasó no es una
      // orden**, y el que lo mandó es justamente quien no tiene nada que hacer con él.
      const _eco = d.src === "user";
      if (d.label === "show" && d.id && !_eco) {
        desktop.show(d.id, { data: d.data });       // brain shows it (with pushed data, if any)
        // V2-464 — en showcase cada apertura re-ordena la rejilla sola, para que una grabación desatendida
        // salga alineada sin manos. Solo en showcase: al operador normal un auto-orden le movería lo suyo.
        if (_SHOWCASE) { clearTimeout(_arrT); _arrT = setTimeout(() => desktop.arrange && desktop.arrange(), 700); }
      }
      else if (d.label === "create" && d.id) desktop.createWidget(d.id, d.spec);  // brain asked to BUILD a new widget
      else if (d.label === "modify" && d.id) desktop.modifyWidget(d.id, d.change);// brain asked to EDIT an existing widget
      else if (d.label === "delete" && d.id) desktop.onDeleted(d.id);             // backend ALREADY deleted (lifecycle) → close the card + drop the cached catalog
      // V2-086: el id RESERVADO "clusters" no es una tarjeta sino la pestaña NATIVA — su Sí/No se pinta ahí
      // (conectarse a una red no es una acción de canvas, y ese widget ya no existe).
      else if (d.label === "confirm" && d.id === "clusters") { store.setClusterConfirm({ question: d.question }); store.setChatTab("clusters"); store.setChatOpen(true); }
      else if (d.label === "confirm-cancel" && d.id === "clusters") store.setClusterConfirm(null);
      else if (d.label === "confirm" && d.id) desktop.showConfirm(d.id, { question: d.question, action: d.action });      // irreversible action (delete/data) → Sí/No overlay ON the card
      else if (d.label === "confirm-cancel" && d.id) desktop.hideConfirm(d.id);   // confirmation resolved/cancelled elsewhere (voice/timeout)
      else if (d.label === "close" && !_eco) d.id ? desktop.close(d.id) : desktop.closeAll();
      else if (d.label === "arrange") desktop.arrange && desktop.arrange();       // V2-464: rejilla alineada (showcase/API)
      else if (d.label === "move" && d.id) desktop.move(d.id, d.where);            // reposition on the canvas (izquierda/derecha/…)
      else if (d.label === "resize" && d.id) desktop.resize(d.id, d.data);          // resize a widget (HERMES-ONLY)
      else if (d.label === "fullscreen" && d.id) desktop.fullscreen(d.id);          // toggle native fullscreen
      // A widget's STORED data changed (its own ctx.action, or Hermes via [[widget.data]]) — widgets/store.py is
      // the single choke point that emits this. No polling anywhere: re-fetch + re-render ONLY if that widget
      // happens to be open right now; otherwise there's nothing on screen to update.
      else if (d.label === "data" && d.id) desktop.refreshData(d.id);
      else if (d.label === "alias") desktop.refreshRegistry && desktop.refreshRegistry();  // V2-082: cambió un nombre/alias → repinta header + panel
    } else if (d.kind === "panel") {                                              // V2-079/086: el cerebro abre/cierra el panel nativo (chat/procesos/crons/clusters) por voz
      // 2026-08-10: también se CIERRA. `show_panel` solo sabía abrir, así que «cierra el chat» no tenía a dónde ir
      // y el turno acababa en un «vale, cerrado» que era falso — el operador lo pidió cinco veces seguidas y tuvo
      // que cerrarlo él con la ✕. El chat es UI NATIVA, no una tarjeta: [[close]] no lo toca.
      if (d.label === "close") { store.setChatOpen(false); }
      else {
        // La lista blanca DEBE incluir toda pestaña que `router._canon_panel` sepa devolver, o el backend rutea
        // bien y el frontend lo tira al suelo abriendo «Chat» (le pasó a `clusters` al nacer, V2-086).
        const tab = ["procesos", "crons", "clusters"].includes(d.tab) ? d.tab : "chat";
        store.setChatTab(tab);
        store.setChatOpen(true);
      }
    } else if (d.kind === "filler" && d.text) {
      // Lead-in wait-filler (V2-093/V2-122): a real phrase the agent just said out loud, so it belongs in the
      // chat wall — but pushed with its own distinct marker, never as `kind:"transcript"`, so it can't be
      // confused with a real LLM-generated reply. Emitted explicitly and synchronously by lead_in_filler.py the
      // instant it's decided (always BEFORE any real reply text exists), so it lands in the right order without
      // depending on LiveKit's own conversation-item timing — the exact mechanism that caused the original bug
      // (a filler showing up AFTER an already-resolved reply).
      store.pushAgentChat("💬 " + d.text);
    } else if (d.kind === "transcript" && d.text) {
      if (d.role === "assistant") {
        // zaelar's FINAL turn text → chat wall (the HISTORY). The LIVE caption over the orb does NOT come from here
        // (this fires once, late): it's driven by LiveKit's audio-synced transcription in session-lk.js. And it must
        // NOT hit the voice-command fast-path — zaelar saying "cierro la agenda" is not the operator asking to close.
        store.pushAgentChat(d.text);
      } else {
        // isFinal gates the CLOSE fast-path (never close on a revisable guess). Voice: "transcript" = final,
        // "interim" = partial. TYPED chat/paste ("text-injected …") is DEFINITIVELY final — treat it as such, or a
        // typed "close widgets" would be seen as interim and the close fast-path would never fire.
        const isFinal = d.label === "transcript" || (d.label || "").startsWith("text-injected");
        handleWidgetVoice(desktop, d.text, isFinal);                               // SHOW acts on interim too (real-time)
        // kind "transcript" (vs "interim") is already the FINAL user turn → record it in the chat wall history.
        store.pushChat({ role: "you", text: d.text });
      }
    } else if (d.kind === "alert") {                                              // hard notice (e.g. no LLM credit) → red banner
      store.showAlert(d.label || t("sse.llm_problem"));
      refreshStatus();                                                           // turn the ◉ status icon red now
    } else if (d.kind === "language") {                                          // V2-089 P3: idioma detectado/cambiado → toda la UI cambia EN VIVO
      if (d.code) applyLang(d.code);                                             // fetches whatever the bundle has now — presets instant, a generating one falls back to English for missing keys until "ready"
      // V2-101: the first-run onboarding modal tracks phases on TOP of the plain applyLang above — "detected"
      // shows the (already-translated) loading line while the full bundle/alias-pack finish in the background,
      // "ready" closes it. A plain language switch (⚙, or a repeat detection with no onboarding) never sets
      // store.langOnboardOpen true in the first place, so these are no-ops for it.
      if (d.phase === "detected") {
        store.setLangOnboardPhase("detected");
        store.setLangOnboardLoading(d.loading || "");
      } else if (d.phase === "ready") {
        store.setLangOnboardPhase("ready");
        setTimeout(() => store.setLangOnboardOpen(false), 550);   // let the CSS fade (.gone) play, then unmount
      }
    } else if (d.kind === "session" && d.label === "RESET") {                    // V2-084: reset → procesos EN BLANCO
      // El escritorio lo cierra el evento widget/close; aquí vaciamos la pestaña Procesos (chips vivos + histórico)
      // al instante para que "empecemos de cero" — estado/memoria/datos de widgets se conservan (backend).
      try { store.setTasks([]); store.setWorkerHistory([]); } catch (_) {}
      // SESIÓN NUEVA (2026-08-10): el backend ya rotó el id y dejó su observabilidad a cero
      // (voice/observer.py::rotate_session). Avisamos a las vistas imperativas para que se vacíen también — si no,
      // el panel de observabilidad seguiría mostrando las filas de la sesión anterior sobre una sesión que acaba
      // de nacer en blanco. `clearDebugBuffer()` (que ya se llamaba desde el reset) vacía el ANILLO, no el DOM.
      try { store.newSession(); } catch (_) {}
    } else if (d.kind === "task") {                                               // SlowBrain background task lifecycle
      // A deep-brain task started/finished — surface it as a liquid chip flanking the orb so the operator SEES
      // zaelar is working (widget build/modify, web task, …) and how many at once. Removed when it ends.
      if (d.label === "start") store.startTask(d.id, d.text);
      else if (d.label === "end" || d.label === "cancel") store.endTask(d.id);   // V2-038: matar también limpia el chip
      else if (d.label === "phase" && d.id) store.startTask(d.id, d.text);        // fase → refresca la etiqueta (idempotente)
      else if (d.label === "progress" && d.id) store.setTaskProgress(d.id, d.text, d.pct, d.done, d.total);  // V2-059: paso/% real
      else if (d.label === "plan" && d.id) store.startTask(d.id, d.text);          // V2-059: plan declarado → refresca etiqueta
    } else if (d.kind === "memory") {                                             // memory.updated / .query (bridged from the bus)
      // The central memory mutated (write/reinforce/pin/link/state/episode/consolidate) or was READ (query). A
      // mutation → bump so the 🧠 map refetches ONLY if open (gated on store.memOpen), real-time, zero polling.
      // A query changes no data → no refetch, only the live-observability pulse. Both carry op + affected ids.
      if (d.op !== "query") store.bumpMemory();
      store.pushMemPulse({ op: d.op || "", ids: d.ids || (d.id != null ? [d.id] : []) });
    } else if (d.kind === "secret") {                                             // bóveda de secretos (V2-060)
      // El cerebro resolvió una petición de secreto. El VALOR nunca viaja por aquí: se pide a /api/vault/reveal.
      if (d.label === "no_vault") store.openVault("create");
      else if (d.label === "locked") store.openVault("unlock", { mid: d.mid });   // pide passphrase / huella
      else if (d.label === "reveal") {                                            // desbloqueada → muéstralo
        vault.reveal(d.mid).then(r => {
          if (r && r.value != null) {
            store.openVault("reveal");                                            // (resetea vaultRevealed)
            store.setVaultRevealed({ label: d.slabel || t("sse.secret_default"), value: r.value });   // …y AHORA el valor
          } else if (r && r.locked) store.openVault("unlock", { mid: d.mid });
        }).catch(() => {});
      }
    } else if (d.kind === "pulse") {                                              // orchestrator loop.tick (~1 Hz)
      // El LATIDO propio del server (nucleo/loop.py, puenteado en server/__init__.py) → un beat del ECG del orbe.
      // En reposo marca el ritmo real (solo revisando crons/procesos); las tareas y turnos lo aceleran (Ecg.js).
      store.pushPulse({ kind: "tick", n: d.n });
    } else if (d.kind === "brain" && d.wall) {
      // V2-461: el canal de TEXTO (probe / `POST /api/flash/say`) también se VE. Es la misma conversación,
      // así que va al mismo sitio: por voz se transcribe al muro, por el widget de chat se escribe en él, y
      // por la API — que es como se conducen las rondas del plató — hasta hoy no aparecía en ninguna parte.
      // El operador miraba trabajar al agente con el chat en blanco, que es indistinguible de un agente
      // colgado. Se distingue por `d.wall` y no por el texto del label: una comparación de subcadenas es un
      // contrato que no se ve desde ninguno de los dos lados.
      // NO llega como `transcript` A PROPÓSITO (ver `nucleo/flash/probe_api._wall`): esa rama alimenta además
      // el atajo de órdenes por voz, y un turno del probe que diga «cierra la agenda» se ejecutaría DOS veces.
      if (d.wall === "you") store.pushChat({ role: "you", text: d.text });
      else store.pushAgentChat(d.text);
    } else if (d.kind === "brain" && /reply/.test(String(d.label || ""))) {       // un turno del FlashBrain se cerró
      store.pushPulse({ kind: "turn" });                                          // → pico QRS más alto en el ECG
      // …y el TEXTO al muro de chat YA (V2-116). Antes el muro solo se alimentaba del `transcript` de LiveKit, que
      // no llega hasta que el item de conversación se cierra — o sea hasta que el TTS ha TERMINADO de hablar la
      // respuesta entera: 5,4 s y 12,2 s medidos en la sesión b403c979, y el operador lo vivió como «la he oído
      // por voz y el texto ha tardado un minuto en aparecer». Aquí el texto ya está generado y completo, así que
      // el muro lo pinta en cuanto existe; el `transcript` posterior se funde por prefijo en `pushAgentChat` (y si
      // un barge-in lo truncó, gana el completo). Los SUBTÍTULOS no se tocan: siguen viniendo de la transcripción
      // sincronizada con el audio (session-lk.js), que es lo correcto para algo que acompaña a la voz.
      if (d.text && d.role === "assistant") store.pushAgentChat(d.text);
    } else if (d.kind === "status") {                                             // server nudged us to re-read status
      refreshStatus();
    } else if (d.kind === "energy") {                                             // saldo de Energy → la PILA baja EN VIVO
      // Se empuja el saldo, no se avisa de que hay que ir a buscarlo: el número entero cabe en el evento y así la
      // pila baja mientras el worker trabaja, sin un fetch por cada gasto.
      const x = d.extra || {};
      if (typeof x.balance === "number") {
        store.setEnergy({ cloud: true, known: true, balance: x.balance,
                          capacity: typeof x.capacity === "number" ? x.capacity : (store.energy() || {}).capacity });
      }
    } else if (d.kind === "run") {                                                // V2-092: el interruptor GLOBAL cambió
      // La verdad de «¿está el agente parado?» la tiene el servidor (nucleo/runstate.py), y este evento es cómo se
      // enteran TODAS las pestañas: dos ventanas abiertas ya no pueden discrepar sobre si hay alguien al otro lado.
      // Solo se refleja el estado; NO se vuelve a llamar al endpoint (el ⏻ es quien ordena, esto solo obedece).
      // Solo se refleja el ESTADO; de tumbar/levantar la sesión de voz se encarga el efecto de main.js que
      // observa `powerOff` (aquí no se importa `session`: sse.js lo importa session.js, y el ciclo sería mutuo).
      //
      // V2-092 addenda (2026-08-15): "pausing"/"resumed" are a THIRD pair of labels, not a start/stop variant —
      // a deferred stop (turn in flight) leaves the agent genuinely RUNNING underneath, so treating it as "not
      // stop → must be start" would paint ⏻ as if nothing were happening. Resolved BEFORE touching `powerOff`,
      // which that pair doesn't even touch.
      const label = String(d.label || "");
      if (label === "pausing") {
        store.setPausing(true);
      } else if (label === "resumed") {
        store.setPausing(false);
      } else {
        store.setPausing(false);
        const off = label === "stop";
        if (off !== store.powerOff()) store.setPowerOff(off);
      }
    } else if (d.kind === "notify") {                                             // proactive push (a native cron fired)
      // NO floating toast. When a voice session is live, zaelar SPEAKS it → the live caption comes from the
      // audio-synced transcription (session-lk.js), same as any turn. Here we just keep it in the chat wall as
      // history; pushAgentChat dedupes against the spoken transcript so it lands exactly once.
      store.pushAgentChat("🔔 " + d.text);
    } else if (d.kind === "cluster") {                                            // MeshKore channel
      // El muro de chat es SOLO el canal operador ↔ zaelar (regla del operador, 2026-07-25): el tráfico de
      // cluster NO se vuelca aquí. V2-086: tampoco se guarda en ningún sitio del frontend — los clusters tienen
      // su PROPIO monitor, así que la pestaña «Clusters» solo administra la conexión (estado, peers, contadores).
      // Cualquier evento de red refresca esa lista; nada de conversación.
      if (store.chatOpen() && store.chatTab() === "clusters") store.fetchClusters();
    }
  };
}

// El stream vive lo que vive la APLICACIÓN (lo abre main.js en el arranque), no lo que vive la sesión de voz: por
// él llegan los eventos de widget, que deben seguir pintándose con la voz parada o sin micrófono. Se deja como
// escotilla explícita para quien de verdad quiera cortarlo; `session.stop()` ya NO la usa (cerraba la pantalla en
// vivo del operador cada vez que paraba la voz o el navegador denegaba el micro).
export function closeSSE() { if (es) { try { es.close(); } catch (_) {} es = null; } }

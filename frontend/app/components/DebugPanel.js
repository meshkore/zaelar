// ============================================================================
// DebugPanel — a RESIZABLE right-side observability column (VoiceLab-style).
// Toggled by the ◷ button in the TopBar (store.debugOpen). When open it SHRINKS
// the canvas horizontally (body.dbg-open + the --dbg-w CSS var offset the fixed
// layout) so it never overlaps zaelar's stage. Drag the left edge to resize.
//
// It renders the WHOLE event firehose from services/debugbus.js (a dedicated SSE
// subscriber): every transcript (user/bot), widget show/close/create/modify/delete,
// brain prompt/reply + [[deep]] escalation to Hermes, LLM/STT/TTS metric (the local
// qwen fast layer, Whisper, Kokoro), and connector dispatch (cluster/cron/architect/
// whatsapp), each stamped h:m:s.mmm. A filter box narrows by kind/label/text. Rows
// are appended imperatively (a live log of ~800 rows shouldn't re-render wholesale).
// ============================================================================
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { startDebugBus, onDebug, debugBuffer, clearDebugBuffer } from "../services/debugbus.js?v=2";
import { LIST_ICON, LINK_ICON, VOLUME_X_ICON, TRASH_ICON, CLOSE_ICON, BUG_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

const MAX_ROWS = 800;             // cap the DOM so a long session can't grow it without bound

const p2 = (n, l = 2) => String(n).padStart(l, "0");
function stamp(ms) {
  const t = new Date(ms || Date.now());
  return `${p2(t.getHours())}:${p2(t.getMinutes())}:${p2(t.getSeconds())}.${p2(t.getMilliseconds(), 3)}`;
}

// Compress one raw observer event into {label, meta, text} for the row.
function parts(d) {
  const meta = [];
  if (d.role) meta.push(d.role);                         // transcript: user | bot
  if (d.id) meta.push(d.id);                             // widget id
  if (d.dir) meta.push(d.dir);                           // cluster in/out/note
  if (d.module) meta.push(d.module);                     // V2-037: PIEZA donde sucede (memory/nav/voz…)
  if (d.func) meta.push(d.func);                         // V2-037: FUNCIÓN/rutina
  const chan = [d.cluster, d.peer || d.to].filter(Boolean).join("·");
  if (chan) meta.push(chan);
  const text = (d.text != null ? d.text : (d.title != null ? d.title : "")).toString();
  return { label: (d.label || "").toString(), meta: meta.join(" · "), text };
}

// Las FAMILIAS = las piezas reales del sistema. Aquí solo fijan el ORDEN de las filas de la tabla de filtros y
// su rótulo; qué kind pertenece a cuál lo dice el backend (`observer.py::_CAT`, servido en
// `/api/observability/catalog`) — el frontend no duplica ese mapa, lo pide.
const CATS = [
  { key: "flash", label: "FlashBrain" },       // el turno: transcripts, decisión, búsqueda, Susurro
  { key: "worker", label: "Brain Workers" },   // trabajo async + el Chromium interno que abren para navegar
  { key: "memory", label: "Memory" },
  { key: "widget", label: "Widgets" },         // TODA orden contra el canvas (show/close/move/data-op/tap)
  { key: "system", label: "System/Code" },
  // Pulse (V2-043): el LATIDO del loop orquestador (~1 Hz, «PULSE·tick»). OFF por defecto — ensucia el log muy
  // rápido y no lleva datos; actívalo solo para ver el ritmo del loop. Las llamadas REALES de memoria in/out van
  // en «Memoria», nunca aquí (la proyección de estado sin cambios ya no se emite — dispatch.sync_state).
  { key: "pulse", label: "Pulse" },
];
// Tipos que arrancan ENCENDIDOS aunque su familia venga apagada por defecto: un error invisible es el peor modo
// de fallo posible. El operador puede apagarlos, pero tiene que ser una decisión suya, no una omisión.
const ALWAYS_KINDS = new Set(["error", "alert"]);

// V2-089: cada categoría del filtro mapea a su clave i18n (la `key` sigue siendo el valor comparado en código).
const CAT_LABEL_KEY = {
  worker: "debug.cat_worker", memory: "debug.cat_memory", flash: "debug.cat_flash",
  widget: "debug.cat_widget", system: "debug.cat_system", pulse: "debug.cat_pulse",
};

// Cabecera FIJA de columnas (2026-08-09, petición del operador: «no se ve claro qué es cada columna»). Mismo
// grid EXACTO que `.dbg-row` en CSS — mismos anchos, mismo gap, mismo padding — para que cada rótulo caiga
// justo encima de su columna sin tocar el ancho actual de nada. Si el rótulo no cabe se recorta con «…» y el
// `title` (hover) dice qué es. Bajo 560px de panel las filas se colapsan a flujo libre (container query) y la
// cabecera se oculta: ahí ya no hay columnas que rotular.
// El ORDEN cuenta una historia de izquierda a derecha: CUÁNDO · de qué FLUJO · de qué PIEZA · QUÉ tipo ·
// cuánto tardó · con qué modelo · cuántos tokens · y qué pasó. Las dos primeras después de la hora son las que
// permiten leer el log como PROCESOS y no como líneas sueltas.
const COLS = [
  { cls: "dbg-t", key: "debug.col_time", tip: "debug.col_time_t" },
  { cls: "dbg-corr", key: "debug.col_corr", tip: "debug.col_corr_t" },
  { cls: "dbg-cat", key: "debug.col_family", tip: "debug.col_family_t" },
  { cls: "dbg-k", key: "debug.col_kind", tip: "debug.col_kind_t" },
  { cls: "dbg-lat", key: "debug.col_lat", tip: "debug.col_lat_t" },
  { cls: "dbg-eng", key: "debug.col_engine", tip: "debug.col_engine_t" },
  { cls: "dbg-sz", key: "debug.col_size", tip: "debug.col_size_t" },
  { cls: "dbg-msg", key: "debug.col_event", tip: "debug.col_event_t" },
];

// Which layer of the «Colmena» brain resolved this turn: the FlashBrain stamps its fast-model provider
// ("aimlapi"/"ollama"/…), the SlowBrain escalation path stamps "slowbrain". Stamped by the provider itself
// (voice/engine/llm/providers/nucleo.py) via emit(..., extra={"engine":..., "model":...}) — read straight off
// the event, never guessed from the label text.
// Column 2 (kind badge): for "brain" rows, name the layer instead of the generic "BRAIN" pill.
// V2-036: ya NO hay "cerebro" aparte — solo el FlashBrain ORQUESTADOR + procesos (workers) que lanza. Los turnos
// del orquestador se etiquetan "FlashBrain"; un evento de worker (engine "slowbrain", legado) → "Worker".
// Familia en 4 letras: la celda es estrecha y el nombre completo ya está en el chip del filtro y en el hover.
const CAT_SHORT = { flash: "FLSH", worker: "WRKR", memory: "MEM", widget: "WDGT", system: "SYS", pulse: "PULS" };
function catShort(cat) { return CAT_SHORT[cat] || (cat || "?").slice(0, 4).toUpperCase(); }

function brainName(engine) {
  if (engine === "slowbrain") return "Worker";
  return "FlashBrain";
}

// Column 3: the actual model serving this turn (e.g. "qwen2.5:14b-instruct", "x-ai/grok-4-fast-non-reasoning") —
// a flat dark chip, deliberately NOT styled like the kind pill, colored by locality (local Ollama vs cloud API).
function modelChip(d) {
  if (!d.model) return null;
  return { text: d.model, cls: (d.engine === "ollama" || d.engine === "local") ? "eng-local" : "eng-api" };
}

// Column 4 for MEMORY rows (V2-014 Task 2): which layer the op hit — state / short / long / slow. A flat chip,
// so the log reads "memory · <layer> · <request> → <result>". Falls back to the model chip for non-memory rows.
function layerChip(d) {
  if (!d.layer) return null;
  return { text: d.layer, cls: "eng-mem" };
}

// Column 2 (right after the timestamp): how long THIS operation actually took, for every request-shaped event
// in the system — an LLM/brain turn, a TTS synth, an STT transcription, a widget generation job, a connector
// dispatch (architect/cluster/messaging triage). Every such call site stamps its own *_ms duration field (see
// voice/engine/llm/providers/{duo,hermes}.py, voice/engine/speech/{tts,stt}/*.py, widgets/server_api.py,
// connectors/{architect,meshkore,messaging}/*.py) — this just picks the right one per row. Preference order:
// a TOTAL-duration field (brain_ms/fast_ms/deep_ms/tts_ms/stt_ms/gen_ms/architect_ms/cluster_ms/triage_ms) over
// a partial one (ttft_ms = first-token only), since "how long did this take" beats "how long to start."
const LAT_FIELDS = ["brain_ms", "fast_ms", "deep_ms", "tts_ms", "stt_ms", "gen_ms",
                     "architect_ms", "cluster_ms", "triage_ms", "mem_ms", "ttft_ms"];
function latencyInfo(d) {
  for (const f of LAT_FIELDS) {
    const v = d[f];
    if (typeof v === "number") {
      const cls = v < 500 ? "lat-good" : v < 1000 ? "lat-warn" : "lat-bad";
      return { text: v < 1000 ? v + "ms" : (v / 1000).toFixed(1) + "s", cls, field: f, ms: v };
    }
  }
  return null;
}

// TOTALIZADORES DE TAMAÑO (FASE 0, premisa del operador): in→out en tokens (reales del proveedor si vinieron, si
// no estimados por chars/4) + nº de tools + marca de FRÍO. Sirve para distinguir «lento por el modelo» de «lento
// por prompt gigante» o «cold-start». Solo cuando el evento trae métricas de LLM.
function fmtTok(n) { if (n == null) return "?"; return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n); }
function sizeInfo(d) {
  const pin = d.prompt_tokens != null ? d.prompt_tokens : null;
  const pout = d.completion_tokens != null ? d.completion_tokens : null;
  if (pin == null && d.prompt_chars == null) return null;
  const parts = [];
  parts.push(`${fmtTok(pin)}→${fmtTok(pout)} tok`);
  if (d.n_tools) parts.push(`+${d.n_tools}t`);
  if (d.cold_estimate === true) parts.push("❄️");
  const cls = (pin != null && pin > 6000) ? "sz-big" : "sz-ok";   // prompt gordo ⇒ ámbar
  return { text: parts.join(" "), cls, title: `in≈${pin} tok / ${d.prompt_chars} ch · out≈${pout} tok · ${d.usage_source || ""}` };
}

// "noise" = high-frequency, low-signal events (5-state machine churn, routine widget data-refresh). Hidden by
// default so the real story (transcripts, brain, show/close, escalations, errors) stays legible; toggle to see all.
function isNoise(kind, label) { return kind === "state" || (kind === "widget" && label === "data"); }

// ── TRAZABILIDAD (V2-044) ────────────────────────────────────────────────────────────────────────────────────
// Cada estímulo (frase del operador, cron, probe, tap de UI, peer de cluster) nace con un `trace` id en el
// backend (voice/trace.py) y TODO lo que deriva de él (tools, tags, rails, workers, navegador, memoria) llega
// sellado con ese id. Aquí: (a) chip clicable por fila en el log cronológico (click → filtra la cadena) y
// (b) la vista «Trazas»: un árbol por trace — la FRASE raíz y debajo, agrupado por actor (span), todo lo que generó.
function traceHue(tid) {                       // color determinista por trace (mismo id = mismo tono, siempre)
  let hs = 0; for (let i = 0; i < tid.length; i++) hs = (hs * 31 + tid.charCodeAt(i)) >>> 0;
  return hs % 360;
}
function traceChip(tid, onClick) {
  const c = document.createElement("span");
  c.className = "dbg-tr";
  c.textContent = tid.split("·")[0];           // "T12" — corto; el id completo va en el title
  c.title = tid + " — click: filtrar esta cadena";
  const hue = traceHue(tid);
  c.style.background = `hsla(${hue},60%,50%,.18)`;
  c.style.borderColor = `hsla(${hue},60%,55%,.55)`;
  c.style.color = `hsl(${hue},70%,70%)`;
  if (onClick) c.addEventListener("click", (e) => { e.stopPropagation(); onClick(tid); });
  return c;
}
const ORIGIN_ICON = { turno: "🗣", kickoff: "👋", probe: "🧪", cron: "⏰", proactivo: "✨", ui: "🖱", cluster: "🌐" };

export function DebugPanel() {
  let listEl, countEl, filterEl, lastRow = null, lastSig = "";
  let tracesEl;                                  // V2-044: contenedor de la vista Trazas (árbol por trace)
  let hdrEl;                                     // cabecera fija de columnas (solo tiene sentido en la vista log)
  let mode = localStorage.getItem("hb_dbg_mode") === "traces" ? "traces" : "log";
  let filter = "";
  let noiseHidden = true;
  let count = 0;
  // ── UN SOLO EJE DE FILTRO: EL TIPO ──────────────────────────────────────────────────────────────────────────
  // Rediseño 2026-08-09 (petición del operador): «vamos a exponer el MAPA COMPLETO de todo lo que podemos
  // filtrar, ya inicializado con unos valores por defecto». Se retira la barra de familias: era un SEGUNDO eje
  // que se solapaba con el de tipos y obligaba a razonar dos veces («esta fila no sale… ¿por la familia o por el
  // tipo?»). La familia sigue existiendo, pero como FILA de la tabla: su rótulo enciende o apaga todos sus tipos
  // de una vez, que es para lo que servía el chip.
  //
  // El mapa NO se construye con lo que va apareciendo: se pide entero al backend (`/api/observability/catalog`,
  // que lo saca de `observer.py::_CAT`, la misma fuente que sella la familia de cada evento). Así el operador ve
  // de una lo que puede encender y apagar, incluso lo que hoy no ha ocurrido todavía.
  //
  // Se persisten los APAGADOS, no los encendidos: un kind NUEVO (el que estrene una capacidad futura) nace
  // VISIBLE en vez de desaparecer por una lista vieja del localStorage. Shift+click = solo ese tipo.
  const DEFAULT_ON_CATS = new Set(["flash", "worker", "memory", "widget"]);
  const hiddenKinds = new Set((() => {
    try { const s = JSON.parse(localStorage.getItem("hb_dbg_kinds_off_v2") || "null"); if (Array.isArray(s)) return s; } catch {}
    return null;   // null = aún sin decidir: los valores por defecto se aplican al llegar el catálogo
  })() || []);
  let defaultsApplied = localStorage.getItem("hb_dbg_kinds_off_v2") != null;
  const catalog = new Map();                     // kind -> familia (el mapa COMPLETO, del backend)
  const kindChips = new Map();                   // kind -> {btn, nEl, n, cat}
  const kindGroups = new Map();                  // familia -> {box, body, head, cat} — la FILA de esa familia
  let kindsEl, filtersEl, filtersBtn, filtersLabel;
  // PANEL DE FILTROS PLEGABLE (2026-08-09, petición del operador: «hay tantos datos que configurar en los
  // filtros que no los podemos tener a la vista porque perdemos la pantalla»). CERRADO por defecto: lo normal
  // es mirar eventos, no reconfigurar el filtro. Cerrado no queda NADA de filtros en pantalla — solo la
  // cabecera de columnas y la lista.
  let filtersOpen = localStorage.getItem("hb_dbg_filters_open") === "1";

  // ── stick-to-tail: seguir SIEMPRE el último evento, pero soltar si el operador sube el scroll ──
  // (V2 obs) El fondo se fija DESPUÉS del layout (rAF), así una fila recién añadida —que ahora puede
  // ocupar dos líneas en columna estrecha— nunca queda a medio cortar en el borde inferior. Cuando el
  // operador sube a mirar algo, `stick` pasa a false y no le arrastramos; al volver abajo, se reengancha.
  let stick = true;
  let pinPending = false;
  function activeList() { return mode === "traces" ? tracesEl : listEl; }   // V2-044: contenedor visible
  function onListScroll() {
    const el = activeList();
    if (!el) return;
    stick = el.scrollHeight - el.scrollTop - el.clientHeight < 24;   // 24px de tolerancia = "está abajo"
  }
  function pinTail() {
    if (!stick || pinPending || !activeList()) return;
    pinPending = true;
    requestAnimationFrame(() => {                 // esperar a que el navegador mida la fila (2 líneas) antes de fijar
      pinPending = false;
      const el = activeList();
      if (stick && el) el.scrollTop = el.scrollHeight;
    });
  }

  function visible(row) {
    // UN SOLO EJE: el tipo. La familia ya no filtra por su cuenta (su rótulo enciende/apaga sus tipos), así que
    // «esta fila no sale» tiene siempre UNA respuesta y no dos que se pisan.
    if (hiddenKinds.has(row.dataset.kind || "log")) return false;
    if (noiseHidden && row.dataset.noise === "1") return false;
    return !filter || (row.dataset.s || "").includes(filter);
  }

  // El MAPA COMPLETO desde el backend: `observer.py::_CAT`, la misma fuente que sella la familia de cada evento.
  // Se pide una vez al abrir el panel; si falla, el visor sigue funcionando y la tabla se irá poblando con lo que
  // vaya llegando (degradación, no pantalla en blanco).
  async function loadCatalog() {
    if (catalog.size) return;
    try {
      const r = await fetch("/api/observability/catalog", { cache: "no-cache" });
      const d = await r.json();
      for (const [kind, cat] of Object.entries(d.kinds || {})) catalog.set(kind, cat);
    } catch (_) { /* sin catálogo se degrada a lo observado */ }
    applyDefaults();
    for (const [kind, cat] of catalog) ensureChip(kind, cat);
    syncGroups();
  }

  // Valores POR DEFECTO, aplicados una sola vez (la primera apertura de una instalación): visibles las familias
  // de trabajo, apagadas las de plomería… salvo error/alert, que arrancan encendidos aunque su familia esté
  // apagada — un error invisible es el peor modo de fallo posible. A partir de ahí manda el operador.
  function applyDefaults() {
    if (defaultsApplied) return;
    defaultsApplied = true;
    for (const [kind, cat] of catalog) {
      if (!DEFAULT_ON_CATS.has(cat) && !ALWAYS_KINDS.has(kind)) hiddenKinds.add(kind);
    }
    persistKinds();
  }

  // Los tipos van AGRUPADOS BAJO SU FAMILIA (2026-08-09, petición del operador: «si cojo la familia de memoria,
  // que salga debajo una línea con los kinds que puedo filtrar»). Antes era una lista plana de ~35 chips donde no
  // se veía a qué pieza pertenecía cada uno; ahora cada familia ACTIVA aporta su línea, y apagar la familia se
  // lleva su línea con ella. La familia de cada kind NO se duplica aquí: viene sellada en el propio evento
  // (`cat`, de `observer.py::_CAT`), así que el frontend la aprende mirando lo que pasa y no puede desalinearse.
  function groupFor(cat) {
    let g = kindGroups.get(cat);
    if (!g && kindsEl) {
      const box = document.createElement("div");
      box.className = "dbg-kgroup c-" + cat;
      // El rótulo de la familia ES el mando de la familia: enciende o apaga todos sus tipos de golpe. Sustituye
      // al chip de la barra que se retiró, sin volver a introducir un segundo eje de filtrado.
      const head = document.createElement("button");
      head.className = "dbg-kgh";
      head.addEventListener("click", () => toggleFamily(cat));
      const body = document.createElement("span"); body.className = "dbg-kgb";
      box.append(head, body);
      // Orden ESTABLE por el catálogo (CATS + lo no clasificado al final), no por orden de aparición: la tabla
      // no puede bailar mientras el operador la mira.
      const order = CATS.map((c) => c.key);
      const at = order.indexOf(cat);
      let before = null;
      for (const [k, other] of kindGroups) {
        const oi = order.indexOf(k);
        if ((at === -1 ? Infinity : at) < (oi === -1 ? Infinity : oi)) { before = other.box; break; }
      }
      kindsEl.insertBefore(box, before);
      g = { box, body, head, cat };
      kindGroups.set(cat, g);
      labelGroup(g);
    }
    return g;
  }

  // Toda la familia de una vez. Si ya estaba entera encendida, se apaga; si no, se enciende (incluye recuperar
  // los tipos que el operador hubiera apagado sueltos dentro de ella).
  function toggleFamily(cat) {
    const kinds = [...catalog].filter(([, c]) => c === cat).map(([k]) => k);
    for (const [k, c] of kindChips) if (c.cat === cat && !kinds.includes(k)) kinds.push(k);
    const allOn = kinds.every((k) => !hiddenKinds.has(k));
    for (const k of kinds) { if (allOn) hiddenKinds.add(k); else hiddenKinds.delete(k); }
    for (const [k, c] of kindChips) c.btn.classList.toggle("on", !hiddenKinds.has(k));
    persistKinds();
    syncGroups();
    reflow();
  }

  // El rótulo de una familia se pinta de forma IMPERATIVA (el chip vive fuera del árbol reactivo de dom.js), así
  // que hay que re-rotularlo a mano cuando cambia el idioma o cuando llega el bundle bueno. Sin esto salían
  // rótulos MEZCLADOS —«FAMILY» en una fila y «FAMILIA» en la siguiente— según si el grupo se creó antes o
  // después de que el fetch del bundle reconciliara. Una familia sin nombre conocido se rotula como tal, en vez
  // de caer al genérico «Familia», que no decía nada.
  function labelGroup(g) {
    g.head.textContent = CAT_LABEL_KEY[g.cat] ? t(CAT_LABEL_KEY[g.cat]) : t("debug.cat_other");
    g.head.title = g.head.textContent;   // el rótulo se recorta en columna estrecha; el hover lo dice entero
  }

  // La tabla enseña SIEMPRE el mapa entero (esa es la gracia); lo que cambia es el aspecto del rótulo de cada
  // familia según tenga todos, algunos o ningún tipo encendido.
  function syncGroups() {
    for (const [cat, g] of kindGroups) {
      const kinds = [...kindChips].filter(([, c]) => c.cat === cat).map(([k]) => k);
      const on = kinds.filter((k) => !hiddenKinds.has(k)).length;
      g.head.classList.toggle("on", on > 0);
      g.head.classList.toggle("partial", on > 0 && on < kinds.length);
    }
    updateFiltersLabel();
  }

  // «Filtros (N)» — N = tipos MARCADOS entre los visibles ahora mismo. Es el número que responde «¿estoy viendo
  // todo o me falta algo?» sin abrir el panel.
  function updateFiltersLabel() {
    if (!filtersLabel) return;
    let n = 0;
    for (const kind of kindChips.keys()) if (!hiddenKinds.has(kind)) n++;
    filtersLabel.textContent = t("debug.filters", { n });
  }

  function toggleFilters() {
    filtersOpen = !filtersOpen;
    localStorage.setItem("hb_dbg_filters_open", filtersOpen ? "1" : "0");
    if (filtersEl) filtersEl.hidden = !filtersOpen;
    if (filtersBtn) filtersBtn.classList.toggle("on", filtersOpen);
    pinTail();      // el panel cambia el alto de la lista → re-fijar el fondo si estábamos siguiendo
  }

  // Registra (o actualiza) el chip de un kind. Se llama por CADA evento —también por los colapsados en ×N— así el
  // contador dice cuánto pesa realmente cada tipo en el hilo, que es lo que decide qué apagar.
  function noteKind(kind, cat) {
    let c = kindChips.get(kind);
    if (!c) {
      const btn = document.createElement("button");
      btn.className = "dbg-kind" + (hiddenKinds.has(kind) ? "" : " on");
      btn.title = t("debug.kind_hint", { kind });
      const lb = document.createElement("span"); lb.textContent = kind;
      const nEl = document.createElement("i"); nEl.className = "dbg-kn";
      btn.append(lb, nEl);
      btn.addEventListener("click", (e) => toggleKind(kind, e.shiftKey));
      c = { btn, nEl, n: 0, cat };
      kindChips.set(kind, c);
      const g = groupFor(cat);
      if (g) g.body.appendChild(btn);
    }
    c.n++; c.nEl.textContent = String(c.n);
    updateFiltersLabel();
  }

  function persistKinds() {
    try { localStorage.setItem("hb_dbg_kinds_off", JSON.stringify([...hiddenKinds])); } catch {}
    if (filtersBtn) filtersBtn.classList.toggle("muted", hiddenKinds.size > 0);
  }

  function toggleKind(kind, solo) {
    if (solo) {
      // «solo esto»: si YA estaba aislado, el segundo shift+click devuelve todo (interruptor, no callejón sin salida).
      const alreadySolo = !hiddenKinds.has(kind) && hiddenKinds.size === kindChips.size - 1;
      hiddenKinds.clear();
      if (!alreadySolo) for (const k of kindChips.keys()) if (k !== kind) hiddenKinds.add(k);
    } else if (hiddenKinds.has(kind)) hiddenKinds.delete(kind);
    else hiddenKinds.add(kind);
    for (const [k, c] of kindChips) c.btn.classList.toggle("on", !hiddenKinds.has(k));
    persistKinds();
    updateFiltersLabel();
    reflow();
  }



  function addRow(d) {
    if (!listEl) return;
    const { label, meta, text } = parts(d);
    const kind = (d.kind || d.type || "log").toString();
    const bn = kind === "brain" ? brainName(d.engine) : null;
    const chip = modelChip(d) || layerChip(d);
    const lat = latencyInfo(d);
    const sz = sizeInfo(d);
    const searchable = (kind + " " + label + " " + meta + " " + text + " " + (bn || "") + " " + (chip ? chip.text : "")
      + " " + (d.trace || "") + " " + (d.span || "")).toLowerCase();   // V2-044: filtrable por trace/span
    const sig = kind + "|" + label + "|" + meta + "|" + text;

    noteKind(kind, (d.cat || "other").toString());

    // Collapse consecutive identical events into one row with a ×N counter (defends the panel against any burst).
    if (lastRow && sig === lastSig) {
      const n = (parseInt(lastRow.dataset.n || "1", 10) + 1);
      lastRow.dataset.n = String(n);
      let badge = lastRow.querySelector(".dbg-x"); if (!badge) { badge = document.createElement("span"); badge.className = "dbg-x"; lastRow.querySelector(".dbg-msg").appendChild(badge); }
      badge.textContent = " ×" + n;
      lastRow.querySelector(".dbg-t").textContent = stamp(d._rx);
      count++; if (countEl) countEl.textContent = t("debug.events", { n: count });
      pinTail();   // el ×N puede crecer la fila → re-fijar el fondo si estamos siguiendo
      return;
    }

    const row = document.createElement("div");
    row.className = "dbg-row k-" + kind.replace(/[^a-z0-9_]/gi, "");
    row.dataset.s = searchable;
    row.dataset.noise = isNoise(kind, label) ? "1" : "0";
    row.dataset.cat = (d.cat || "main").toString();       // V2-037: categoría para el filtro superior
    row.dataset.kind = kind;                              // desglose por kind (2ª fila de chips)

    const ts = document.createElement("span"); ts.className = "dbg-t"; ts.textContent = stamp(d._rx);
    // CORRELATION ID: el flujo completo al que pertenece esta línea (voice/trace.py). Antes el chip iba dentro
    // del mensaje, donde se perdía entre el texto; en columna propia se leen los flujos de un vistazo — click
    // sigue aislando la cadena entera.
    const cr = document.createElement("span"); cr.className = "dbg-corr";
    if (d.trace) cr.appendChild(traceChip(d.trace, (tid) => { if (filterEl) { filterEl.value = tid; } applyFilter(); }));
    const ct = document.createElement("span"); ct.className = "dbg-cat c-" + (d.cat || "other");
    ct.textContent = catShort(d.cat); ct.title = t(CAT_LABEL_KEY[d.cat] || "debug.col_family");
    const lt = document.createElement("span"); lt.className = "dbg-lat" + (lat ? " " + lat.cls : "");
    if (lat) { lt.textContent = lat.text; lt.title = lat.field; }
    const kd = document.createElement("span"); kd.className = "dbg-k"; kd.textContent = bn || kind;
    if (bn) kd.title = kind;                    // hover the brain name to see the raw event kind
    const eg = document.createElement("span"); eg.className = "dbg-eng" + (chip ? " " + chip.cls : "");
    if (chip) { eg.textContent = chip.text; eg.title = chip.text; }
    const szc = document.createElement("span"); szc.className = "dbg-sz" + (sz ? " " + sz.cls : "");
    if (sz) { szc.textContent = sz.text; szc.title = sz.title; }
    const msg = document.createElement("span"); msg.className = "dbg-msg";
    if (label) { const b = document.createElement("b"); b.textContent = label; msg.appendChild(b); msg.appendChild(document.createTextNode(" ")); }
    if (meta) { const m = document.createElement("i"); m.className = "dbg-meta"; m.textContent = meta; msg.appendChild(m); msg.appendChild(document.createTextNode(" ")); }
    if (text) msg.appendChild(document.createTextNode(text));
    row.append(ts, cr, ct, kd, lt, eg, szc, msg);
    row.hidden = !visible(row);

    listEl.appendChild(row);
    lastRow = row; lastSig = sig;
    while (listEl.childElementCount > MAX_ROWS) { const f = listEl.firstElementChild; if (f === lastRow) break; listEl.removeChild(f); }
    pinTail();   // seguir el tail (tras el layout) salvo que el operador haya subido — ver onListScroll
    count++; if (countEl) countEl.textContent = t("debug.events", { n: count });
  }

  // ── vista TRAZAS (V2-044): árbol  frase-raíz → actor (span) → eventos ──────────────────────────────────────
  // Cada trace = un <details> con la FRASE que lo inició en el summary; debajo, los eventos que generó, agrupados
  // por actor (`span`: worker:N / rail:X / web:tN). Es la vista de EVALUACIÓN: ¿esta frase cayó en el rail
  // correcto y desembocó en el set de eventos que corresponde? Imperativa como el log (sin re-render global).
  const traces = new Map();              // tid -> {det, ic, tx, nEl, body, spans:Map(span->bodyEl), n}
  const MAX_TRACES = 120;                // cap de árboles vivos en el DOM
  const MAX_TR_EVENTS = 250;             // cap de eventos por trace (una navegación larga no crece sin límite)

  function traceEntry(tid) {
    let e = traces.get(tid);
    if (e) return e;
    const det = document.createElement("details");
    det.className = "dbg-trace"; det.open = true;
    const sum = document.createElement("summary");
    const chip = traceChip(tid, null);
    const ic = document.createElement("span"); ic.className = "dbg-tro"; ic.textContent = "•";
    const tx = document.createElement("span"); tx.className = "dbg-trt"; tx.textContent = "…";
    const nEl = document.createElement("span"); nEl.className = "dbg-trn";
    sum.append(chip, ic, tx, nEl);
    const body = document.createElement("div"); body.className = "dbg-trb";
    det.append(sum, body);
    e = { det, ic, tx, nEl, body, spans: new Map(), n: 0 };
    traces.set(tid, e);
    if (tracesEl) {
      tracesEl.appendChild(det);
      while (tracesEl.childElementCount > MAX_TRACES) {
        const f = tracesEl.firstElementChild;
        for (const [k, v] of traces) if (v.det === f) { traces.delete(k); break; }
        tracesEl.removeChild(f);
      }
    }
    return e;
  }

  function traceRow(d) {
    const { label, meta, text } = parts(d);
    const kind = (d.kind || "log").toString();
    const row = document.createElement("div");
    row.className = "dbg-row dbg-trrow k-" + kind.replace(/[^a-z0-9_]/gi, "");
    const ts = document.createElement("span"); ts.className = "dbg-t"; ts.textContent = stamp(d._rx);
    const kd = document.createElement("span"); kd.className = "dbg-k"; kd.textContent = kind === "brain" ? brainName(d.engine) : kind;
    const msg = document.createElement("span"); msg.className = "dbg-msg";
    if (label) { const b = document.createElement("b"); b.textContent = label; msg.appendChild(b); msg.appendChild(document.createTextNode(" ")); }
    if (meta) { const m = document.createElement("i"); m.className = "dbg-meta"; m.textContent = meta; msg.appendChild(m); msg.appendChild(document.createTextNode(" ")); }
    if (text) msg.appendChild(document.createTextNode(text));
    row.append(ts, kd, msg);
    return row;
  }

  function addTrace(d) {
    const tid = d.trace;
    if (!tid || !tracesEl) return;
    const e = traceEntry(tid);
    if (d.kind === "trace" && d.root) {                 // la RAÍZ: la frase/estímulo que inició la cadena
      e.ic.textContent = ORIGIN_ICON[d.origin] || "•";
      e.tx.textContent = (d.text || d.label || "").toString();
      e.tx.title = stamp(d._rx) + " · origen: " + (d.origin || "?");
      return;
    }
    if (e.n >= MAX_TR_EVENTS) return;
    e.n++; e.nEl.textContent = t("debug.events", { n: e.n });
    let parent = e.body;
    if (d.span) {                                        // nivel 2: el ACTOR que trabaja para esta frase
      let sp = e.spans.get(d.span);
      if (!sp) {
        const sd = document.createElement("details"); sd.className = "dbg-span"; sd.open = true;
        const ss = document.createElement("summary"); ss.textContent = "▹ " + d.span; sd.appendChild(ss);
        const sb = document.createElement("div"); sb.className = "dbg-trb"; sd.appendChild(sb);
        e.body.appendChild(sd);
        sp = sb; e.spans.set(d.span, sp);
      }
      parent = sp;
    }
    parent.appendChild(traceRow(d));
    if (mode === "traces") pinTail();
  }

  function setMode(m, btn) {
    mode = m;
    localStorage.setItem("hb_dbg_mode", m);
    if (listEl) listEl.hidden = (m === "traces");
    if (tracesEl) tracesEl.hidden = (m !== "traces");
    if (hdrEl) hdrEl.hidden = (m === "traces");     // el árbol no va en columnas → sin cabecera que rotular
    if (btn) { btn.innerHTML = m === "traces" ? LIST_ICON : LINK_ICON; btn.title = m === "traces" ? t("debug.view_log") : t("debug.view_traces"); }
  }

  function applyFilter() {
    filter = (filterEl ? filterEl.value : "").trim().toLowerCase();
    reflow();
  }
  function reflow() { if (!listEl) return; for (const row of listEl.children) row.hidden = !visible(row); pinTail(); }
  function toggleNoise(btn) { noiseHidden = !noiseHidden; btn.classList.toggle("on", !noiseHidden); reflow(); }
  function clearAll() {
    clearDebugBuffer();
    if (listEl) listEl.replaceChildren();
    if (tracesEl) tracesEl.replaceChildren();   // V2-044: también el árbol
    // Los chips de kind describen lo que HAY en el log → al vaciarlo se vacían con él (y se re-crean solos con el
    // siguiente evento). Lo que NO se toca es qué kinds están apagados: esa es la preferencia del operador.
    if (kindsEl) kindsEl.replaceChildren();
    kindChips.clear();
    kindGroups.clear();
    traces.clear();
    lastRow = null; lastSig = ""; count = 0;
    if (countEl) countEl.textContent = t("debug.events", { n: 0 });
  }

  // ── resize by dragging the left edge ──────────────────────────────────────
  function startResize(e) {
    e.preventDefault();
    const move = (ev) => {
      const w = Math.round(window.innerWidth - ev.clientX);
      const clamped = Math.max(300, Math.min(w, Math.round(window.innerWidth * 0.72)));
      store.setDebugWidth(clamped);
      document.documentElement.style.setProperty("--dbg-w", clamped + "px");
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("dbg-resizing");
      localStorage.setItem("hb_debug_w", String(store.debugWidth()));
    };
    document.body.classList.add("dbg-resizing");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  const panel = h("div", { class: "dbgpanel", style: { width: () => store.debugWidth() + "px" } },
    h("div", { class: "dbg-resize", title: () => t("debug.resize"), onPointerdown: startResize }),
    h("div", { class: "dbg-head" },
      h("span", { class: "dbg-title" }, raw(BUG_ICON), () => t("debug.title")),
      h("input", { class: "dbg-filter", placeholder: () => t("debug.filter_placeholder"), ref: (el) => (filterEl = el), onInput: applyFilter }),
      // FILTROS — un solo botón que despliega TODO el panel (familias + tipos). Lleva el nº de tipos marcados
      // para saber de un vistazo si se está mirando el hilo entero o uno recortado.
      h("button", {
        class: "dbg-fbtn" + (filtersOpen ? " on" : ""), title: () => t("debug.filters_title"),
        ref: (el) => (filtersBtn = el), onClick: toggleFilters,
      },
        h("span", { ref: (el) => { filtersLabel = el; el.textContent = t("debug.filters", { n: 0 }); } }),
        h("span", { class: "dbg-fcar" }, "▾"),
      ),
      h("span", { class: "dbg-count", ref: (el) => (countEl = el) }, () => t("debug.events", { n: 0 })),
      // V2-044: toggle Log cronológico ⇄ árbol de Trazas (frase → acciones → eventos)
      h("button", {
        class: "dbg-btn hb-icbtn", title: () => t("debug.view_traces"),
        ref: (el) => { el.innerHTML = mode === "traces" ? LIST_ICON : LINK_ICON; },
        onClick: (e) => setMode(mode === "traces" ? "log" : "traces", e.currentTarget),
      }),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.noise"), onClick: (e) => toggleNoise(e.currentTarget) }, raw(VOLUME_X_ICON)),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.clear"), onClick: clearAll }, raw(TRASH_ICON)),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.close"), onClick: () => store.setDebugOpen(false) }, raw(CLOSE_ICON)),
    ),
    // PANEL DE FILTROS (plegable). Cerrado no deja NADA en pantalla: debajo de la cabecera van directamente los
    // rótulos de columna y los eventos, que es lo que se viene a mirar.
    // Dentro va LA TABLA y nada más: una fila por familia —su rótulo enciende o apaga la familia entera— con
    // todos sus tipos a la derecha. La barra de chips de familia que había encima se RETIRÓ: era un segundo eje
    // que se solapaba con este y obligaba a razonar dos veces por qué no salía una fila.
    h("div", { class: "dbg-filters", ref: (el) => { filtersEl = el; el.hidden = !filtersOpen; } },
      h("div", { class: "dbg-kinds", ref: (el) => (kindsEl = el) }),
      // Condensar desde DENTRO del panel: al terminar de configurar no hay que volver a subir a la cabecera.
      h("div", { class: "dbg-fbar" },
        h("button", { class: "dbg-fclose", onClick: toggleFilters }, "▴ ", () => t("debug.filters_collapse")),
      ),
    ),
    // CABECERA DE COLUMNAS — fija, fuera del contenedor con scroll (así no scrollea ni la puede podar el
    // recorte de MAX_ROWS) y con el MISMO grid que las filas. El wrapper es su propio query-container para que
    // se oculte sola cuando el panel se estrecha y las filas dejan de estar en columnas.
    h("div", { class: "dbg-hdrwrap", ref: (el) => { hdrEl = el; el.hidden = (mode === "traces"); } },
      h("div", { class: "dbg-hdr" },
        ...COLS.map((c) => h("span", { class: c.cls, title: () => t(c.tip) }, () => t(c.key))),
      ),
    ),
    h("div", { class: "dbg-list", ref: (el) => { listEl = el; el.hidden = (mode === "traces"); el.addEventListener("scroll", onListScroll, { passive: true }); } }),
    // V2-044: la vista Trazas — misma zona, contenedor alterno (toggle ⛓ arriba)
    h("div", { class: "dbg-list dbg-traces", ref: (el) => { tracesEl = el; el.hidden = (mode !== "traces"); el.addEventListener("scroll", onListScroll, { passive: true }); } }),
  );

  // Open ⇒ start the bus, shrink the canvas (body class + --dbg-w), y REPONER lo que falte del buffer.
  // El bus (debugbus.js) sigue vivo y acumulando SIEMPRE, abierto o cerrado el panel — pero mientras está
  // cerrado no pintamos filas (abajo, el suscriptor vivo lo filtra por `store.debugOpen()`), así que al
  // reabrir puede haber eventos reales más recientes que el último que SÍ se pintó. Antes esto se resolvía
  // con un flag de una sola vez (`backfilled`), que solo rellenaba en la PRIMERA apertura de la página — la
  // 2ª+ apertura se quedaba con la última fila pintada antes de cerrar, aunque hubiera eventos más nuevos en
  // el buffer: el scroll SÍ estaba abajo, pero abajo de un DOM incompleto (parecía "no sigue al último
  // evento" sin serlo). Ahora cada evento se marca `_dbgSeen` al pintarse, y CADA apertura repone los que
  // falten — así el operador siempre ve el evento real más reciente, no solo el más reciente que ya viera.
  function catchUp() {
    if (!listEl) return;
    for (const d of debugBuffer()) {
      if (d._dbgSeen) continue;
      d._dbgSeen = true;
      addRow(d); addTrace(d);
    }
  }
  createEffect(() => {
    const open = store.debugOpen();
    document.body.classList.toggle("dbg-open", open);
    document.documentElement.style.setProperty("--dbg-w", (open ? store.debugWidth() : 0) + "px");
    localStorage.setItem("hb_debug_open", open ? "1" : "0");
    if (open) {
      startDebugBus();
      stick = true;   // al abrir el panel, arrancar SIEMPRE enganchado al último evento
      catchUp();
      pinTail();
    }
  });

  // Los rótulos del panel de filtros se pintan IMPERATIVAMENTE (viven fuera del árbol reactivo de dom.js), así
  // que hay que re-rotularlos cuando cambia el idioma o cuando llega el bundle bueno. Leer `t()` aquí dentro es
  // lo que crea la dependencia. Sin esto se veían rótulos MEZCLADOS en dos idiomas a la vez —«FAMILY» en una
  // fila y «FAMILIA» en la siguiente— según si el grupo se creó antes o después de reconciliar el bundle.
  createEffect(() => {
    t("debug.filters", { n: 0 });
    for (const g of kindGroups.values()) labelGroup(g);
    updateFiltersLabel();
  });

  onDebug((d) => { if (store.debugOpen()) { d._dbgSeen = true; addRow(d); addTrace(d); } });   // live append only while visible

  return panel;
}

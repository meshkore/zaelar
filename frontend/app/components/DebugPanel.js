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
// are inserted imperatively (a live log of ~800 rows shouldn't re-render wholesale).
//
// ORDEN: EL ÚLTIMO EVENTO VA ARRIBA (2026-08-10, decisión of the operador). The lista crece hacia ABAJO por
// PREPEND, así that lo recién ocurrido está siempre pegado a the cabecera of columnas — a the vista, without perseguir
// nada. The scroll remains 100% MANUAL: nadie lo mueve by ti. Esto SUSTITUYE al “stick-to-tail” (seguir the fondo,
// soltarse al subir, re-enganchar al bajar, indicador of seguimiento, guarda of rAF, ventana of gesto real):
// ~70 líneas of state that se podía desincronizar of the realidad —y that ya falló dos veces— for resolver un
// problema that the orden inverso simplemente NO TIENE.
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
  if (d.module) meta.push(d.module);                     // V2-037: PIEZA where sucede (memory/nav/voz…)
  if (d.func) meta.push(d.func);                         // V2-037: FUNCIÓN/rutina
  const chan = [d.cluster, d.peer || d.to].filter(Boolean).join("·");
  if (chan) meta.push(chan);
  const text = (d.text != null ? d.text : (d.title != null ? d.title : "")).toString();
  return { label: (d.label || "").toString(), meta: meta.join(" · "), text };
}

// The FAMILIAS = the piezas reales of the sistema. Here only fijan the ORDEN of the filas of the tabla of filtros y
// su rótulo; qué kind pertenece a cuál lo dice the backend (`observer.py::_CAT`, servido en
// `/api/observability/catalog`) — the frontend no duplica ese mapa, lo pide.
const CATS = [
  { key: "flash", label: "FlashBrain" },       // the turno: transcripts, decisión, búsqueda, Susurro
  { key: "worker", label: "Brain Workers" },   // trabajo async + the Chromium interno that abren for navegar
  { key: "memory", label: "Memory" },
  { key: "widget", label: "Widgets" },         // TODA orden contra the canvas (show/close/move/data-op/tap)
  { key: "system", label: "System/Code" },
  // Pulse (V2-043): the LATIDO of the loop orquestador (~1 Hz, “PULSE·tick”). OFF by defecto — ensucia the log muy
  // rápido and no lleva datos; actívalo only for ver the ritmo of the loop. The llamadas REALES of memory in/out van
  // en “Memoria”, nunca here (la proyección of state without cambios ya no se emite — dispatch.sync_state).
  { key: "pulse", label: "Pulse" },
];
// Tipos that arrancan ENCENDIDOS aunque su familia venga apagada by defecto: un error invisible es the peor modo
// of fallo posible. The operador puede apagarlos, pero tiene that ser a decisión suya, no a omisión.
const ALWAYS_KINDS = new Set(["error", "alert"]);

// V2-089: each categoría of the filtro mapea a su clave i18n (la `key` sigue siendo the valor comparado en código).
const CAT_LABEL_KEY = {
  worker: "debug.cat_worker", memory: "debug.cat_memory", flash: "debug.cat_flash",
  widget: "debug.cat_widget", system: "debug.cat_system", pulse: "debug.cat_pulse",
};

// Cabecera FIJA of columnas (2026-08-09, operator request: “no se ve claro qué es each columna”). Mismo
// grid EXACTO that `.dbg-row` en CSS — mismos anchos, mismo gap, mismo padding — for that each rótulo caiga
// justo encima of su columna without tocar the ancho actual of nada. Si the rótulo no cabe se recorta with “…” and el
// `title` (hover) dice qué es. Bajo 560px of panel the filas se colapsan a flujo libre (container query) and la
// cabecera se oculta: ahí ya no there is columnas that rotular.
// The ORDEN cuenta a historia of izquierda a derecha: CUÁNDO · of qué FLUJO · of qué PIEZA · QUÉ tipo ·
// cuánto tardó · with qué modelo · cuántos tokens · and qué pasó. The dos primeras después of the hora son the que
// permiten leer the log as PROCESOS and no as líneas sueltas.
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

// Which layer of the “Colmena” brain resolved this turn: the FlashBrain stamps its fast-model provider
// ("aimlapi"/"ollama"/…), the SlowBrain escalation path stamps "slowbrain". Stamped by the provider itself
// (voice/engine/llm/providers/nucleo.py) via emit(..., extra={"engine":..., "model":...}) — read straight off
// the event, never guessed from the label text.
// Column 2 (kind badge): for "brain" rows, name the layer instead of the generic "BRAIN" pill.
// V2-036: ya NO there is "cerebro" aparte — only the FlashBrain ORQUESTADOR + procesos (workers) that lanza. The turnos
// of the orquestador se etiquetan "FlashBrain"; un evento of worker (engine "slowbrain", legado) → "Worker".
// Familia abreviada for the celda estrecha of the columna FAMILIA. Va by i18n as cualquier otro texto of la
// interfaz —un idioma generado puede necesitar otras letras, u otro alfabeto entero— and the nombre completo sigue
// estando en the hover and en the tabla of filtros. Without clave (familia aún without clasificar) → the 4 primeras letras
// of the código técnico, that es lo único that se sabe of ella.
function catShort(cat) {
  const key = CAT_LABEL_KEY[cat] ? "debug.short_" + cat : null;
  return key ? t(key) : (cat || "?").slice(0, 4).toUpperCase();
}

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

// Column 4 for MEMORAnd rows (V2-014 Task 2): which layer the op hit — state / short / long / slow. A flat chip,
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

// TOTALIZADORES DE TAMAÑO (FASE 0, premisa of the operador): in→out en tokens (reales of the proveedor si vinieron, si
// no estimados by chars/4) + nº of tools + marca of FRÍO. Sirve for distinguir “lento by the modelo” of “lento
// by prompt gigante” or “cold-start”. Only when the evento trae métricas of LLM.
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
// Each estímulo (frase of the operador, cron, probe, tap of UI, peer of cluster) nace with un `trace` id en el
// backend (voice/trace.py) and TODO lo that deriva of él (tools, tags, rails, workers, navegador, memoria) llega
// sellado with ese id. Aquí: (a) chip clicable by row en the log cronológico (click → filtra the cadena) y
// (b) the vista “Trazas”: un árbol by trace — the FRASE raíz and debajo, agrupado by actor (span), todo lo that generó.
function traceHue(tid) {                       // color determinista by trace (mismo id = mismo tono, siempre)
  let hs = 0; for (let i = 0; i < tid.length; i++) hs = (hs * 31 + tid.charCodeAt(i)) >>> 0;
  return hs % 360;
}
function traceChip(tid, onClick) {
  const c = document.createElement("span");
  c.className = "dbg-tr";
  c.textContent = tid.split("·")[0];           // "T12" — corto; the id completo va en the title
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
  let tracesEl;                                  // V2-044: contenedor of the vista Trazas (árbol by trace)
  let hdrEl;                                     // cabecera fija of columnas (solo tiene sentido en the vista log)
  let mode = localStorage.getItem("hb_dbg_mode") === "traces" ? "traces" : "log";
  let filter = "";
  let noiseHidden = true;
  let count = 0;
  // ── UN SOLO EJE DE FILTRO: EL TIPO ──────────────────────────────────────────────────────────────────────────
  // Rediseño 2026-08-09 (petición of the operador): “vamos a exponer the MAPA COMPLETO of todo lo that podemos
  // filtrar, ya inicializado with unos valores by defecto”. Se retira the barra of familias: era un SEGUNDO eje
  // that se solapaba with the of tipos and obligaba a razonar dos veces (“esta row no sale… por the familia or by el
  // tipo?”). The familia sigue existiendo, pero as FILA of the tabla: su rótulo enciende or apaga todos sus tipos
  // of a vez, that es for lo that servía the chip.
  //
  // The mapa NO se construye with lo that va apareciendo: se pide entero al backend (`/api/observability/catalog`,
  // that lo saca of `observer.py::_CAT`, the misma fuente that sella the familia of each evento). Así the operador ve
  // of a lo that puede encender and apagar, incluso lo that hoy no ha ocurrido todavía.
  //
  // Se persisten the APAGADOS, no the encendidos: un kind NUEVO (el that estrene a capacidad futura) nace
  // VISIBLE en vez of desaparecer by a lista old of the localStorage. Shift+click = only ese tipo.
  const DEFAULT_ON_CATS = new Set(["flash", "worker", "memory", "widget"]);
  const hiddenKinds = new Set((() => {
    try { const s = JSON.parse(localStorage.getItem("hb_dbg_kinds_off_v2") || "null"); if (Array.isArray(s)) return s; } catch {}
    return null;   // null = aún without decidir: the valores by defecto se aplican al llegar the catálogo
  })() || []);
  let defaultsApplied = localStorage.getItem("hb_dbg_kinds_off_v2") != null;
  const catalog = new Map();                     // kind -> familia (el mapa COMPLETO, of the backend)
  const kindChips = new Map();                   // kind -> {btn, nEl, n, cat}
  const kindGroups = new Map();                  // familia -> {box, body, head, cat} — the FILA of esa familia
  let kindsEl, filtersEl, filtersBtn, filtersLabel;
  // PANEL DE FILTROS PLEGABLE (2026-08-09, operator request: “hay tantos data that configurar en los
  // filtros that no the podemos tener a the vista porque perdemos the pantalla”). CLOSED by defecto: lo normal
  // es mirar eventos, no reconfigurar the filtro. Cerrado no remains NADA of filtros en pantalla — only la
  // cabecera of columnas and the lista.
  let filtersOpen = localStorage.getItem("hb_dbg_filters_open") === "1";

  // ── LO NUEVO ENTRA POR ARRIBA — and the scroll es of the operador (2026-08-10) ────────────────────────────────────
  // Toda the maquinaria of “seguir the fondo” desaparece: no there is state of seguimiento, ni gestos that vigilar, ni
  // rAF, ni indicador that mantener sincronizado. Only dos casos, and ninguno guarda nada:
  //
  //   · the operador está ARRIBA (scrollTop 0) → the row entra justo bajo the cabecera and empuja al resto hacia
  //     abajo. Es lo that quiere ver, and sale without tocar the scroll.
  //   · the operador está LEYENDO more abajo → se compensa the alto that acaba of aparecer ENCIMA, así lo that tiene
  //     bajo the ojos no se mueve ni un píxel. Without esto, each evento le desplazaría the texto hacia abajo.
  //
  // The compensación the hacemos NOSOTROS and no the navegador (`overflow-anchor:none` en `.dbg-list`): the anclaje
  // automático only existe en Chrome/Firefox and su ajuste se sumaría al nuestro. Un only dueño, mismo
  // comportamiento en todos the navegadores.
  // `bulk` = relleno masivo al abrir the panel (hasta 1.000 filas of the anillo of golpe). Ahí no there is nada que
  // compensar —el scroll se coloca arriba al terminar— and the corto-circuito evita leer the scroll row a fila, que
  // fuerza un relayout en each una. No es state that sobreviva a nada: se pone and se quita en the mismo pase.
  let bulk = false;
  function prepend(el, node) {
    if (!el) return;
    if (bulk || el.scrollTop <= 0) { el.insertBefore(node, el.firstChild); return; }
    const h0 = el.scrollHeight;
    el.insertBefore(node, el.firstChild);
    el.scrollTop += el.scrollHeight - h0;
  }

  function visible(row) {
    // UN SOLO EJE: the tipo. The familia ya no filtra by su cuenta (su rótulo enciende/apaga sus tipos), así que
    // “esta row no sale” tiene siempre UNA respuesta and no dos that se pisan.
    if (hiddenKinds.has(row.dataset.kind || "log")) return false;
    if (noiseHidden && row.dataset.noise === "1") return false;
    return !filter || (row.dataset.s || "").includes(filter);
  }

  // The MAPA COMPLETO from the backend: `observer.py::_CAT`, the misma fuente that sella the familia of each evento.
  // Se pide a vez al abrir the panel; si falla, the visor sigue funcionando and the tabla se irá poblando with lo que
  // vaya llegando (degradación, no pantalla en blanco).
  async function loadCatalog() {
    if (catalog.size) return;
    try {
      const r = await fetch("/api/observability/catalog", { cache: "no-cache" });
      const d = await r.json();
      for (const [kind, cat] of Object.entries(d.kinds || {})) catalog.set(kind, cat);
    } catch (_) { /* sin catálogo se degrada a lo observado */ }
    // SIN catálogo NO se tocan the valores by defecto ni se persiste nada, and se reintenta en the siguiente
    // apertura. Failure real 2026-08-09: with un backend that aún no servía the endpoint, `applyDefaults()` corría
    // sobre un mapa VACÍO, se marcaba as aplicado and guardaba a lista of apagados vacía — así that the día que
    // the catálogo llegara, “ya estaba configurado” and the familias of plomería habrían salido ENCENDIDAS. Los
    // valores by defecto only tienen sentido when se sabe sobre qué se aplican.
    if (!catalog.size) return;
    applyDefaults();
    for (const [kind, cat] of catalog) ensureChip(kind, cat);
    syncGroups();
  }

  // Valores POR DEFECTO, aplicados a sola vez (la first apertura of a instalación): visibles the familias
  // of trabajo, apagadas the of plomería… salvo error/alert, that arrancan encendidos aunque su familia esté
  // apagada — un error invisible es the peor modo of fallo posible. A partir of ahí manda the operador.
  function applyDefaults() {
    if (defaultsApplied) return;
    defaultsApplied = true;
    for (const [kind, cat] of catalog) {
      if (!DEFAULT_ON_CATS.has(cat) && !ALWAYS_KINDS.has(kind)) hiddenKinds.add(kind);
    }
    persistKinds();
  }

  // The tipos van AGRUPADOS BAJO SU FAMILIA (2026-08-09, operator request: “si cojo the familia of memoria,
  // that salga debajo a línea with the kinds that puedo filtrar”). Antes era a lista plana of ~35 chips where no
  // se veía a qué pieza pertenecía each uno; now each familia ACTIVA aporta su línea, and apagar the familia se
  // lleva su línea with ella. The familia of each kind NO se duplica aquí: viene sellada en the propio evento
  // (`cat`, of `observer.py::_CAT`), así that the frontend the aprende mirando lo that pasa and no puede desalinearse.
  function groupFor(cat) {
    let g = kindGroups.get(cat);
    if (!g && kindsEl) {
      const box = document.createElement("div");
      box.className = "dbg-kgroup c-" + cat;
      // The rótulo of the familia ES the mando of the familia: enciende or apaga todos sus tipos of golpe. Sustituye
      // al chip of the barra that se retiró, without volver a introducir un segundo eje of filtrado.
      const head = document.createElement("button");
      head.className = "dbg-kgh";
      head.addEventListener("click", () => toggleFamily(cat));
      const body = document.createElement("span"); body.className = "dbg-kgb";
      box.append(head, body);
      // Orden ESTABLE by the catálogo (CATS + lo no clasificado al final), no by orden of aparición: the tabla
      // no puede bailar mientras the operador the mira.
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

  // Toda the familia of a vez. Si ya estaba entera encendida, se apaga; si no, se enciende (incluye recuperar
  // the tipos that the operador hubiera apagado sueltos inside of ella).
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

  // The rótulo of a familia se pinta of forma IMPERATIVA (el chip vive outside of the árbol reactivo of dom.js), así
  // that there is that re-rotularlo a mano when cambia the idioma or when llega the bundle bueno. Without esto salían
  // rótulos MEZCLADOS —“FAMILY” en a row and “FAMILIA” en the siguiente— según si the grupo se creó antes o
  // después of that the fetch of the bundle reconciliara. A familia without nombre conocido se rotula as tal, en vez
  // of caer al genérico “Familia”, that no decía nada.
  function labelGroup(g) {
    g.head.textContent = CAT_LABEL_KEY[g.cat] ? t(CAT_LABEL_KEY[g.cat]) : t("debug.cat_other");
    g.head.title = g.head.textContent;   // the rótulo se recorta en columna estrecha; the hover lo dice entero
  }

  // The tabla enseña SIEMPRE the mapa entero (esa es the gracia); lo that cambia es the aspecto of the rótulo of cada
  // familia según tenga todos, algunos or ningún tipo encendido.
  function syncGroups() {
    for (const [cat, g] of kindGroups) {
      const kinds = [...kindChips].filter(([, c]) => c.cat === cat).map(([k]) => k);
      const on = kinds.filter((k) => !hiddenKinds.has(k)).length;
      g.head.classList.toggle("on", on > 0);
      g.head.classList.toggle("partial", on > 0 && on < kinds.length);
    }
    updateFiltersLabel();
  }

  // “Filtros (N)” — N = tipos MARCADOS entre the visibles now mismo. Es the número that responde “estoy viendo
  // todo or me falta algo?” without abrir the panel.
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
  }

  // Registra (o actualiza) the chip of un kind. Se llama by CADA evento —también by the colapsados en ×N— así el
  // contador dice cuánto pesa realmente each tipo en the hilo, that es lo that decide qué apagar.
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
    // MISMA clave that se LEE arriba (`hb_dbg_kinds_off_v2`). Escribía en the old without `_v2`: the configuration de
    // filtros of the operador no sobrevivía a un recargado —y the valores by defecto se re-aplicaban each vez—
    // porque nadie leía nunca lo that se guardaba.
    try { localStorage.setItem("hb_dbg_kinds_off_v2", JSON.stringify([...hiddenKinds])); } catch {}
    if (filtersBtn) filtersBtn.classList.toggle("muted", hiddenKinds.size > 0);
  }

  function toggleKind(kind, solo) {
    if (solo) {
      // “solo esto”: si YA estaba aislado, the segundo shift+click devuelve todo (interruptor, no callejón without salida).
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
      + " " + (d.trace || "") + " " + (d.span || "")).toLowerCase();   // V2-044: filtrable by trace/span
    const sig = kind + "|" + label + "|" + meta + "|" + text;

    noteKind(kind, (d.cat || "other").toString());

    // Collapse consecutive identical events into one row with a ×N counter (defends the panel against any burst).
    // `lastRow` es the row of ARRIBA (la more reciente), that es justo where the operador está mirando.
    if (lastRow && sig === lastSig) {
      const n = (parseInt(lastRow.dataset.n || "1", 10) + 1);
      lastRow.dataset.n = String(n);
      let badge = lastRow.querySelector(".dbg-x"); if (!badge) { badge = document.createElement("span"); badge.className = "dbg-x"; lastRow.querySelector(".dbg-msg").appendChild(badge); }
      badge.textContent = " ×" + n;
      lastRow.querySelector(".dbg-t").textContent = stamp(d._rx);
      count++; if (countEl) countEl.textContent = t("debug.events", { n: count });
      return;
    }

    const row = document.createElement("div");
    row.className = "dbg-row k-" + kind.replace(/[^a-z0-9_]/gi, "");
    row.dataset.s = searchable;
    row.dataset.noise = isNoise(kind, label) ? "1" : "0";
    row.dataset.cat = (d.cat || "main").toString();       // V2-037: categoría for the filtro superior
    row.dataset.kind = kind;                              // desglose by kind (2ª row of chips)

    const ts = document.createElement("span"); ts.className = "dbg-t"; ts.textContent = stamp(d._rx);
    // CORRELATION ID: the flujo completo al that pertenece this línea (voice/trace.py). Antes the chip iba dentro
    // of the mensaje, where se perdía entre the texto; en columna propia se leen the flujos of un vistazo — click
    // sigue aislando the cadena entera.
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

    prepend(listEl, row);
    lastRow = row; lastSig = sig;
    // The recorte se lleva the filas MÁS VIEJAS, that now son the of the final.
    while (listEl.childElementCount > MAX_ROWS) { const f = listEl.lastElementChild; if (f === lastRow) break; listEl.removeChild(f); }
    count++; if (countEl) countEl.textContent = t("debug.events", { n: count });
  }

  // ── vista TRAZAS (V2-044): árbol  frase-raíz → actor (span) → eventos ──────────────────────────────────────
  // Each trace = un <details> with the FRASE that lo inició en the summary; debajo, the eventos that generó, agrupados
  // by actor (`span`: worker:N / rail:X / web:tN). Es the vista of EVALUACIÓN: esta frase cayó en the rail
  // correcto and desembocó en the set of eventos that corresponde? Imperativa as the log (without re-render global).
  const traces = new Map();              // tid -> {det, ic, tx, nEl, body, spans:Map(span->bodyEl), n}
  const MAX_TRACES = 120;                // cap of árboles vivos en the DOM
  const MAX_TR_EVENTS = 250;             // cap of eventos by trace (una navegación larga no crece without límite)

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
    // The flujo more RECIENTE arriba, igual that the log. DENTRO of each árbol the eventos siguen en orden
    // cronológico: un flujo se lee of principio a fin, es lo that permite ver dónde se torció.
    if (tracesEl) {
      prepend(tracesEl, det);
      while (tracesEl.childElementCount > MAX_TRACES) {
        const f = tracesEl.lastElementChild;
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
    if (d.kind === "trace" && d.root) {                 // the RAÍZ: the frase/estímulo that inició the cadena
      e.ic.textContent = ORIGIN_ICON[d.origin] || "•";
      e.tx.textContent = (d.text || d.label || "").toString();
      e.tx.title = stamp(d._rx) + " · origen: " + (d.origin || "?");
      return;
    }
    if (e.n >= MAX_TR_EVENTS) return;
    e.n++; e.nEl.textContent = t("debug.events", { n: e.n });
    let parent = e.body;
    if (d.span) {                                        // nivel 2: the ACTOR that trabaja for this frase
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
  }

  function setMode(m, btn) {
    mode = m;
    localStorage.setItem("hb_dbg_mode", m);
    if (listEl) listEl.hidden = (m === "traces");
    if (tracesEl) tracesEl.hidden = (m !== "traces");
    if (hdrEl) hdrEl.hidden = (m === "traces");     // the árbol no va en columnas → without cabecera that rotular
    if (btn) { btn.innerHTML = m === "traces" ? LIST_ICON : LINK_ICON; btn.title = m === "traces" ? t("debug.view_log") : t("debug.view_traces"); }
  }

  function applyFilter() {
    filter = (filterEl ? filterEl.value : "").trim().toLowerCase();
    reflow();
  }
  function reflow() { if (!listEl) return; for (const row of listEl.children) row.hidden = !visible(row); }
  function toggleNoise(btn) { noiseHidden = !noiseHidden; btn.classList.toggle("on", !noiseHidden); reflow(); }
  function clearAll() {
    clearDebugBuffer();
    if (listEl) listEl.replaceChildren();
    if (tracesEl) tracesEl.replaceChildren();   // V2-044: also the árbol
    // The chips of kind describen lo that HAAnd en the log → al vaciarlo se vacían with él (y se re-crean solos with el
    // siguiente evento). Lo that NO se toca es qué kinds están apagados: esa es the preferencia of the operador.
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
      // FILTROS — un only button that despliega TODO the panel (familias + tipos). Lleva the nº of tipos marcados
      // for saber of un vistazo si se está mirando the hilo entero or uno recortado.
      h("button", {
        class: "dbg-fbtn" + (filtersOpen ? " on" : ""), title: () => t("debug.filters_title"),
        ref: (el) => (filtersBtn = el), onClick: toggleFilters,
      },
        h("span", { ref: (el) => { filtersLabel = el; el.textContent = t("debug.filters", { n: 0 }); } }),
        h("span", { class: "dbg-fcar" }, "▾"),
      ),
      h("span", { class: "dbg-count", ref: (el) => (countEl = el) }, () => t("debug.events", { n: 0 })),
      // V2-044: toggle Log cronológico ⇄ árbol of Trazas (frase → acciones → eventos)
      h("button", {
        class: "dbg-btn hb-icbtn", title: () => t("debug.view_traces"),
        ref: (el) => { el.innerHTML = mode === "traces" ? LIST_ICON : LINK_ICON; },
        onClick: (e) => setMode(mode === "traces" ? "log" : "traces", e.currentTarget),
      }),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.noise"), onClick: (e) => toggleNoise(e.currentTarget) }, raw(VOLUME_X_ICON)),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.clear"), onClick: clearAll }, raw(TRASH_ICON)),
      h("button", { class: "dbg-btn hb-icbtn", title: () => t("debug.close"), onClick: () => store.setDebugOpen(false) }, raw(CLOSE_ICON)),
    ),
    // PANEL DE FILTROS (plegable). Cerrado no deja NADA en pantalla: debajo of the cabecera van directamente los
    // rótulos of columna and the eventos, that es lo that se viene a mirar.
    // Inside va LA TABLA and nada más: a row by familia —su rótulo enciende or apaga the familia entera— con
    // todos sus tipos a the derecha. The barra of chips of familia that había encima se RETIRÓ: era un segundo eje
    // that se solapaba with this and obligaba a razonar dos veces by qué no salía a fila.
    h("div", { class: "dbg-filters", ref: (el) => { filtersEl = el; el.hidden = !filtersOpen; } },
      h("div", { class: "dbg-kinds", ref: (el) => (kindsEl = el) }),
      // Condensar from DENTRO of the panel: al terminar of configurar no there is that volver a subir a the cabecera.
      h("div", { class: "dbg-fbar" },
        h("button", { class: "dbg-fclose", onClick: toggleFilters }, "▴ ", () => t("debug.filters_collapse")),
      ),
    ),
    // CABECERA DE COLUMNAS — fija, outside of the contenedor with scroll (así no scrollea ni the puede podar el
    // recorte of MAX_ROWS) and with the MISMO grid that the filas. The wrapper es su propio query-container for que
    // se oculte sola when the panel se estrecha and the filas dejan of estar en columnas.
    h("div", { class: "dbg-hdrwrap", ref: (el) => { hdrEl = el; el.hidden = (mode === "traces"); } },
      h("div", { class: "dbg-hdr" },
        ...COLS.map((c) => h("span", { class: c.cls, title: () => t(c.tip) }, () => t(c.key))),
      ),
    ),
    h("div", { class: "dbg-list", ref: (el) => { listEl = el; el.hidden = (mode === "traces"); } }),
    // V2-044: the vista Trazas — misma zona, contenedor alterno (toggle ⛓ arriba)
    h("div", { class: "dbg-list dbg-traces", ref: (el) => { tracesEl = el; el.hidden = (mode !== "traces"); } }),
  );

  // Open ⇒ start the bus, shrink the canvas (body class + --dbg-w), and REPONER lo that falte of the buffer.
  // The bus (debugbus.js) sigue vivo and acumulando SIEMPRE, open or closed the panel — pero mientras está
  // closed no pintamos filas (abajo, the suscriptor vivo lo filtra by `store.debugOpen()`), así that al
  // reabrir puede haber eventos reales more recientes that the último that SÍ se pintó. Antes esto se resolvía
  // with un flag of a sola vez (`backfilled`), that only rellenaba en the PRIMERA apertura of the página — la
  // 2ª+ apertura seremainsba with the última row pintada antes of cerrar, aunque hubiera eventos more nuevos en
  // the buffer: the scroll SÍ estaba abajo, pero abajo of un DOM incompleto (parecía "no sigue al último
  // evento" without serlo). Now each evento se marca `_dbgSeen` al pintarse, and CADA apertura repone the que
  // falten — así the operador siempre ve the evento real more reciente, no only the more reciente that ya viera.
  function catchUp() {
    if (!listEl) return;
    bulk = true;
    try {
      // From the more VIEJO al more nuevo: as each uno entra by arriba, the último of the anillo acaba arriba of the todo.
      for (const d of debugBuffer()) {
        if (d._dbgSeen) continue;
        d._dbgSeen = true;
        addRow(d); addTrace(d);
      }
    } finally { bulk = false; }
  }
  createEffect(() => {
    const open = store.debugOpen();
    document.body.classList.toggle("dbg-open", open);
    document.documentElement.style.setProperty("--dbg-w", (open ? store.debugWidth() : 0) + "px");
    localStorage.setItem("hb_debug_open", open ? "1" : "0");
    if (open) {
      startDebugBus();
      catchUp();
      // Abrir the panel es “a ver qué está pasando” → arriba, where está lo último. Es the ÚNICA vez that movemos
      // the scroll nosotros; a partir of here es todo of the operador.
      if (listEl) listEl.scrollTop = 0;
      if (tracesEl) tracesEl.scrollTop = 0;
    }
  });

  // The rótulos of the panel of filtros se pintan IMPERATIVAMENTE (viven outside of the árbol reactivo of dom.js), así
  // that there is that re-rotularlos when cambia the idioma or when llega the bundle bueno. Leer `t()` here inside es
  // lo that crea the dependencia. Without esto se veían rótulos MEZCLADOS en dos idiomas a the vez —“FAMILY” en una
  // row and “FAMILIA” en the siguiente— según si the grupo se creó antes or después of reconciliar the bundle.
  createEffect(() => {
    t("debug.filters", { n: 0 });
    for (const g of kindGroups.values()) labelGroup(g);
    updateFiltersLabel();
    // The celda FAMILIA of each row ya pintada also es texto of interfaz: se re-rotula, no se remains with el
    // idioma that hubiera when llegó the evento.
    if (listEl) for (const row of listEl.children) {
      const c = row.querySelector(".dbg-cat");
      if (c) c.textContent = catShort(row.dataset.cat || "");
    }
  });

  // SESIÓN NUEVA (2026-08-10) → the columna se vacía. Un Reset deliberado abre otra sesión of trabajo en the backend
  // (id nuevo, observabilidad a cero); si here siguieran the filas of the anterior, the operador estaría leyendo el
  // historial of a sesión that ya no existe creyendo that es the of ahora. Es the MISMO vaciado that the button 🗑, con
  // a diferencia deliberada: the kinds that the operador tenía apagados NO se re-encienden — eso es su preferencia
  // of trabajo, no contenido of the sesión. `store.sessionEpoch` empieza en 0, así that the primer pase (montaje) no
  // borra nada.
  let _lastEpoch = store.sessionEpoch();
  createEffect(() => {
    const e = store.sessionEpoch();
    if (e === _lastEpoch) return;
    _lastEpoch = e;
    clearAll();
  });

  onDebug((d) => { if (store.debugOpen()) { d._dbgSeen = true; addRow(d); addTrace(d); } });   // live append only while visible

  return panel;
}

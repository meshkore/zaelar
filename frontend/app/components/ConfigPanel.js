// ConfigPanel — ⚙ área of CONFIGURACIÓN a pantalla completa (V2-043).
// Elige QUÉ API/modelo usa CADA pieza (FlashBrain, CodeAgent, memoria, voz, búsqueda web, música, conectores)
// and shows the RESUMEN of APIs with SALDO. Todo from the UI (invariante of producto). Patrón: menú lateral
// (una sección visible a the vez, estilo Chrome/macOS Ajustes) + panel of formulario a the derecha with filas
// agrupadas and su button of guardar, leído by id (como SettingsModal), guardado by sección contra /api/config/*.
// The API keys by pieza se guardan en the ENV of the proveedor (coherente with the resolución by endpoint of the FlashBrain).
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import * as session from "../services/session.js?v=3";
import { GEAR_ICON, BRAIN_ICON, CPU_ICON, DATABASE_ICON, MIC_ICON, SEARCH_ICON, MUSIC_ICON, SERVER_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const opt = (list, sel) => (list || []).map(o => `<option value="${esc(o.value != null ? o.value : o)}"${(o.value != null ? o.value : o) === sel ? " selected" : ""}>${esc(o.label != null ? o.label : o)}</option>`).join("");
const badge = st => `<span class="cf-badge cf-${esc(st || "off")}">${({ ok: t("config.badge.ok"), warn: t("config.badge.warn"), error: t("config.badge.error"), off: t("config.badge.off"), unknown: "—" }[st] || st || "—")}</span>`;

// a row of ajuste: etiqueta a the izquierda, control (+ pista opcional) a the derecha — patrón Ajustes/Chrome.
const row = (label, ctl, hint) =>
  `<div class="cf-row2"><label class="cf-row2-label">${esc(label)}</label><div class="cf-row2-ctl">${ctl}${hint ? `<span class="cf-hint">${hint}</span>` : ""}</div></div>`;

// a sección = título + subtítulo + un grupo of filas (tarjeta with separadores, as un grupo of Ajustes).
const panel = (id, title, sub, inner) =>
  `<section class="cf-panel-sec" id="cf_${id}"><header class="cf-panel-head"><h4>${esc(title)}</h4>${sub ? `<p>${esc(sub)}</p>` : ""}</header><div class="cf-group">${inner}</div></section>`;

const SECTIONS = [
  { id: "fast", icon: BRAIN_ICON },
  { id: "code", icon: CPU_ICON },
  { id: "memory", icon: DATABASE_ICON },
  { id: "voice", icon: MIC_ICON },
  { id: "search", icon: SEARCH_ICON },
  { id: "music", icon: MUSIC_ICON },
  { id: "apis", icon: SERVER_ICON },
];

// Sections that PICK a provider/model — centrally managed in the cloud profile, hidden there (V2-043 area
// stays intact for self-host; see INI-019 addenda "Cambio B", 2026-08-05 and server/config_api.py's
// matching _CLOUD_LOCKED_V2_SECTIONS backend gate). `apis` (balance/status) stays visible either way —
// it's read-only information, not a choice.
const CLOUD_LOCKED_NAV_SECTIONS = new Set(["fast", "code", "memory"]);
// voice_api's STT/TTS provider knobs specifically (the rest of `voice` — language, VAD, etc. — stays editable).
const CLOUD_LOCKED_VOICE_KEYS = new Set(["stt_provider", "tts_provider"]);

// V2-083: tres pestañas principales. "settings" = todo lo of antes (menú lateral + secciones); "conectores" y
// "widgets" son nuevas. Patrón of pastilla segmentada (como the pestañas of the ChatWall).
const TABS = [
  { id: "settings" },
  { id: "conectores" },
  { id: "widgets" },
];

export function ConfigPanel() {
  let cfg = null, bodyEl, msgEl, ovl;
  let activeSec = SECTIONS[0].id;
  let activeTab = "settings";

  const msg = t => { if (msgEl) msgEl.textContent = t || ""; };

  // ---- render ----
  function render() {
    const cat = cfg.catalog || {};
    const cloudProfile = !!cfg.cloud_profile;
    const visibleSections = cloudProfile ? SECTIONS.filter(s => !CLOUD_LOCKED_NAV_SECTIONS.has(s.id)) : SECTIONS;
    const builders = {
      fast: () => sec_fast(cat.fast || {}),
      code: () => sec_code(cat.code_agent || {}),
      memory: () => sec_memory(cat),
      voice: () => sec_voice(cloudProfile),
      search: () => sec_search(),
      music: () => sec_music(),
      apis: () => sec_apis(),
    };
    if (!builders[activeSec] || (cloudProfile && CLOUD_LOCKED_NAV_SECTIONS.has(activeSec))) activeSec = visibleSections[0].id;
    const tabsBar = TABS.map(tab => `<button type="button" class="cf-tab${tab.id === activeTab ? " on" : ""}" data-tab="${tab.id}">${esc(t("config.tab." + tab.id))}</button>`).join("");
    let pane;
    if (activeTab === "conectores") {
      pane = `<div class="cf-tabpane"><div class="cf-scroll"><div class="cf-panel">${sec_connectors()}</div></div></div>`;
    } else if (activeTab === "widgets") {
      pane = `<div class="cf-tabpane"><div class="cf-scroll"><div class="cf-panel">${sec_widgets()}</div></div></div>`;
    } else {
      const nav = visibleSections.map(s => `<button type="button" class="cf-nav-item${s.id === activeSec ? " active" : ""}" data-sec="${s.id}">${s.icon}<span>${esc(t("config.sec." + s.id))}</span></button>`).join("");
      pane = `<div class="cf-tabpane"><nav class="cf-nav">${nav}</nav><div class="cf-scroll"><div class="cf-panel">${builders[activeSec]()}</div></div></div>`;
    }
    bodyEl.innerHTML = `<div class="cf-tabs">${tabsBar}</div>${pane}`;
    wire();
  }

  const providerKeyRow = (prov) => {
    // row of API key for the proveedor seleccionado (si es cloud and tiene key_env). Redactada: only presencia.
    if (!prov || !prov.cloud || !prov.key_env) return "";
    const setNow = (cfg.credentials || []).some(c => (c.env || []).includes(prov.key_env) && c.set);
    return row(t("config.apikey.label", { env: prov.key_env }),
      `<input id="cf_key_${esc(prov.key_env)}" type="password" placeholder="${setNow ? t("config.key.ph_saved_keep") : t("config.key.ph_paste")}" autocomplete="off"/>`,
      setNow ? t("config.key.configured") : t("config.key.not_configured"));
  };

  // Desplegable CLOSED of modelos: only lo that ese proveedor sirve. `blank` = a first opción vacía with su
  // texto (heredar / by defecto of the proveedor). Un modelo that the proveedor no sirve ya no es tecleable — el
  // backend además lo rechaza al guardar (config_api._model_mismatch), porque the síntoma of un modelo imposible
  // aparecía minutos después inside of a tarea muerta, no al guardar.
  const modelSelect = (id, models, sel, blank) =>
    `<select id="${id}">${blank != null ? `<option value=""${sel ? "" : " selected"}>${esc(blank)}</option>` : ""}${opt(models || [], sel)}</select>`;

  function sec_fast(c) {
    const f = (cfg.v2 && cfg.v2.fast) || {};
    const provs = c.providers || [];
    const cur = provs.find(p => p.id === f.provider) || provs[0] || {};
    // Ni URL base ni modelo a mano (norma of the operador 2026-08-12): the proveedor determina the endpoint and the lista
    // of modelos son the that the benchmark avala. Lo único that se teclea here es the API key.
    return panel("fast", t("config.fast.title"), (c.note || "") + t("config.fast.sub_suffix"),
      row(t("config.row.provider"), `<select id="cf_fast_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), f.provider)}</select>`) +
      row(t("config.row.model"), `<span id="cf_fast_modelbox">${modelSelect("cf_fast_model", cur.models, f.model)}</span>`) +
      `<div id="cf_fast_keyrow">${providerKeyRow(cur)}</div>` +
      `<div class="cf-foot"><button class="cf-save" data-sec="fast">${t("config.fast.save")}</button></div>` +
      `<div class="cf-foot cf-foot-info"><button type="button" class="cf-benchmarks-btn">${t("config.fast.benchmarks")}</button></div>`);
  }

  // Está the CLI of ese proveedor instalado en ESTA máquina? Lo dice the backend (`detected`/`version`). Antes the UI
  // ofrecía the dos by igual and elegir the that no estaba se descubría inside of a tarea muerta.
  const cliState = (p) => {
    if (p.detected === undefined) return "";
    if (!p.detected) return `<span class="cf-hint cf-warn">⚠ ${esc(t("config.code.cli_missing"))}</span>`;
    let s = `<span class="cf-hint">✓ ${esc(t("config.code.cli_found", { version: p.version || "?" }))}</span>`;
    // Su propio config of the CLI pide un modelo that the API no sirve: se DICE, no se descarta callando.
    if (p.stale_default) s += `<span class="cf-hint cf-warn">⚠ ${esc(t("config.code.stale_default", { model: p.stale_default }))}</span>`;
    return s;
  };

  const codeModelRows = (p, a) => {
    const ms = p.models || [];
    // The default of the propio CLI (leído of su config) manda as pista: si the operador ya decidió cuál usa su
    // Codex, the UI arranca of ahí en vez of proponer otro.
    const dflt = p.default_model && ms.includes(p.default_model) ? p.default_model : "";
    const g = t("config.ph.provider_default") + (dflt ? ` (${dflt})` : "");
    return row(t("config.code.model_global"), modelSelect("cf_code_model", ms, a.model, g)) +
      row(t("config.code.model_memory"), modelSelect("cf_code_model_memory", ms, a.model_memory, t("config.ph.inherits"))) +
      row(t("config.code.model_web"), modelSelect("cf_code_model_web", ms, a.model_web, t("config.ph.inherits"))) +
      row(t("config.code.model_code"), modelSelect("cf_code_model_code", ms, a.model_code, t("config.ph.inherits")));
  };

  // Un preset mueve CLI + endpoint + modelo A LA VEZ. Elegir the tres piezas by separado es where salían los
  // desajustes (glm-5.2 sobre Codex, gpt-5.5 sobre Z.AI). Se marca the that NO puede funcionar and POR QUÉ — verlo
  // antes of elegir, no inside of a tarea muerta media hora después.
  const presetCard = (p, activeId) => {
    const on = p.id === activeId;
    const money = p.billing === "subscription" ? "◆" : (p.billing === "licence" ? "◇" : "$");
    const state = p.ready ? "" : `<span class="cf-hint cf-warn">⚠ ${esc(p.blocked_by === "cli"
      ? t("config.preset.no_cli") : t("config.preset.no_key", { env: p.key_env || "" }))}</span>`;
    return `<button type="button" class="cf-preset${on ? " on" : ""}${p.ready ? "" : " off"}" data-preset="${esc(p.id)}">
      <span class="cf-preset-h">${money} ${esc(p.label)}${on ? " ✓" : ""}</span>
      <span class="cf-hint">${esc(p.cost || "")}</span>${state}</button>`;
  };

  // Cuál of the presets es the that está puesto ahora? Se compara the TERNA completa: dos presets pueden compartir
  // CLI and distinguirse only by the endpoint.
  const activePreset = (presets, a) => (presets.find(p =>
    p.provider === (a.provider || "") && (p.base_url || "") === (a.base_url || "") &&
    (p.model || "") === (a.model || "")) || {}).id || "";

  function sec_code(c) {
    const a = (cfg.v2 && cfg.v2.code_agent) || {};
    const provs = c.providers || [];
    const cur = provs.find(p => p.id === a.provider) || provs[0] || {};
    const presets = c.presets || [];
    const act = activePreset(presets, a);
    const presetBox = presets.length
      ? row(t("config.code.preset"), `<div class="cf-presets" id="cf_code_presets">${presets.map(p => presetCard(p, act)).join("")}</div>`,
        t("config.code.preset_hint"))
      : "";
    return panel("code", t("config.code.title"), t("config.code.sub"),
      presetBox +
      row(t("config.row.provider"), `<select id="cf_code_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), a.provider)}</select>`,
        `<span id="cf_code_clistate">${cliState(cur)}</span>`) +
      `<div id="cf_code_models">${codeModelRows(cur, a)}</div>` +
      `<div id="cf_code_provnote" class="cf-hint">${esc(cur.note || c.note || "")}</div>` +
      row(t("config.code.max_parallel"), `<input id="cf_code_max_parallel" type="number" min="1" max="8" value="${esc(a.max_parallel)}"/>`) +
      `<div class="cf-foot"><button class="cf-save" data-sec="code_agent">${t("config.code.save")}</button></div>`);
  }

  function sec_memory(cat) {
    const m = (cfg.v2 && cfg.v2.memory) || {};
    const emb = (cat.memory_embed && cat.memory_embed.providers) || [];
    const rer = (cat.memory_rerank && cat.memory_rerank.providers) || [];
    return panel("memory", t("config.memory.title"), t("config.memory.sub"),
      row(t("config.memory.embedding"), `<select id="cf_mem_embed_provider">${opt(emb.map(p => ({ value: p.id, label: p.label })), m.embed_provider)}</select>`, t("config.memory.embed_warn")) +
      row(t("config.memory.embed_model"), `<input id="cf_mem_embed_model" value="${esc(m.embed_model)}"/>`) +
      row(t("config.memory.reranker"), `<select id="cf_mem_rerank_provider">${opt(rer.map(p => ({ value: p.id, label: p.label })), m.rerank_provider)}</select>`) +
      row(t("config.memory.rerank_model"), `<input id="cf_mem_rerank_model" value="${esc(m.rerank_model)}" placeholder="${t("config.ph.provider_default")}"/>`) +
      row(t("config.memory.top_n"), `<input id="cf_mem_rerank_top_n" type="number" min="1" max="100" value="${esc(m.rerank_top_n)}"/>`) +
      row(t("config.memory.blend"), `<input id="cf_mem_rerank_blend" type="number" step="0.05" min="0" max="1" value="${esc(m.rerank_blend)}"/>`) +
      row(t("config.memory.write_processor"), `<input id="cf_mem_mem_processor_model" value="${esc(m.mem_processor_model)}"/>`) +
      `<div class="cf-foot"><button class="cf-save" data-sec="memory">${t("config.memory.save")}</button></div>`);
  }

  function sec_voice(cloudProfile) {
    const v = cfg.voice || {};
    const allKnobs = v.knobs || [];
    const knobs = cloudProfile ? allKnobs.filter(k => !CLOUD_LOCKED_VOICE_KEYS.has(k.key)) : allKnobs;
    const free = new Set(v.free_text || []);
    const rows = knobs.map(k => {
      const hint = k.note ? esc(k.note) : "";
      const ctl = free.has(k.key)
        ? `<input id="cfv_${k.key}" list="dlv_${k.key}" value="${esc(k.value)}"/><datalist id="dlv_${k.key}">${opt(k.options)}</datalist>`
        : `<select id="cfv_${k.key}">${opt(k.options, k.value)}</select>`;
      return row(k.label, ctl, hint);
    }).join("");
    const cloudNote = cloudProfile
      ? `<p class="cf-hint">${esc(t("config.voice.cloud_locked"))}</p>`
      : "";
    // THIS BROWSER's capture, which the rest of this panel is not: everything above is server configuration
    // saved with the button below, while these two are the device the mic opens on and how the OS cleans it —
    // per-browser, held in localStorage, applied by reconnecting. They arrived here when the bottom-left
    // connection line was deleted (V2-542): a device choice belongs in Settings, and hiding it in a diagnostic
    // strip is why it sat on the desktop for months looking like clutter. The ids stay `micsel`/`micmode`
    // because the session's own helpers drive them by id; `wire()` asks the session to fill them, and empties
    // the block when it cannot (the legacy Pipecat engine has no such helper) rather than showing two dead
    // selects.
    // Its OWN card, BELOW the save button, and that placement is the point: everything above is server
    // configuration that «Guardar voz» writes, while these two are already applied the moment they change.
    // Sitting them inside that card would put a Save button under two controls it does not save.
    const device = panel("voice_device", t("config.voice.device_title"), t("config.voice.device_sub"),
      row(t("config.voice.device"), `<select id="micsel"></select>`, esc(t("config.voice.device_hint"))) +
      row(t("config.voice.capture"), `<select id="micmode"></select>`, esc(t("config.voice.capture_hint"))));
    return panel("voice", t("config.voice.title"), t("config.voice.sub"),
      cloudNote + rows + `<div class="cf-foot"><button class="cf-save-voice">${t("config.voice.save")}</button></div>`)
      + device;
  }

  function sec_search() {
    // The búsqueda web elige proveedor AUTO by calidad según the key disponible (Perplexity→Tavily→Brave→Google
    // gratis→DDG). No there is store propio: se gobierna with the KEYS. Se editan here as credenciales.
    const creds = cfg.credentials || [];
    const keyRow = (prov, env, label) => {
      const setNow = creds.some(c => c.key === prov && c.set);
      return row(`${label} · ${env}`,
        `<input id="cf_key_${esc(env)}" type="password" placeholder="${setNow ? t("config.key.ph_saved") : t("config.key.ph_paste_optional")}" autocomplete="off"/>`,
        setNow ? t("config.key.active") : "—");
    };
    return panel("search", t("config.search.title"), t("config.search.sub"),
      keyRow("perplexity", "PERPLEXITY_API_KEY", t("config.search.perplexity")) +
      keyRow("tavily", "TAVILY_API_KEY", t("config.search.tavily")) +
      keyRow("brave", "BRAVE_SEARCH_KEY", t("config.search.brave")) +
      `<div class="cf-foot"><button class="cf-save-keys" data-envs="PERPLEXITY_API_KEY,TAVILY_API_KEY,BRAVE_SEARCH_KEY">${t("config.search.save")}</button></div>`);
  }

  function sec_music() {
    const sp = cfg.spotify || {};
    const st = sp.logged_in ? t("config.music.connected") : (sp.can_connect ? t("config.music.ready") : t("config.music.missing_client"));
    return panel("music", t("config.music.title"), t("config.music.sub"),
      row(t("config.row.status"), `<span class="cf-status">${esc(st)}${sp.logged_in ? "" : (sp.default_available ? t("config.music.oneclick") : "")}</span>`) +
      `<div class="cf-foot">${sp.logged_in
        ? `<button class="cf-spotify-dis">${t("config.music.disconnect")}</button>`
        : `<button class="cf-spotify" ${sp.can_connect ? "" : "disabled"}>${t("config.music.connect")}</button>`}</div>`);
  }

  function apisRows() {
    const apis = cfg.apis || [];
    return apis.map(a => `<tr class="cf-api cf-api-${esc(a.state)}">
        <td class="cf-api-name">${esc(a.key)}<span>${esc(a.enables || "")}</span></td>
        <td>${badge(a.state)}</td>
        <td class="cf-api-detail">${esc(a.detail || "")}${a.balance && a.balance.limit ? ` · ${bar(a.balance)}` : ""}</td>
      </tr>`).join("") || '<tr><td colspan="3">—</td></tr>';
  }
  function sec_apis() {
    return panel("apis", t("config.apis.title"), t("config.apis.sub"),
      `<table class="cf-apis"><tbody id="cf_apis_tbody">${apisRows()}</tbody></table>
       <div class="cf-foot"><button class="cf-refresh-apis">${t("config.apis.refresh")}</button></div>`);
  }

  const bar = (b) => {
    const pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
    return `<span class="cf-bar"><i style="width:${pct}%"></i></span> ${pct}%`;
  };

  // ---- wiring ----
  function wire() {
    // V2-083: pestañas principales (settings/conectores/widgets)
    bodyEl.querySelectorAll(".cf-tab").forEach(b => b.onclick = () => { if (b.dataset.tab !== activeTab) { activeTab = b.dataset.tab; render(); } });
    // controles of the pestaña Conectores
    bodyEl.querySelectorAll(".cf-cx-act").forEach(b => b.onclick = () => cxAct(b.dataset.act, b.dataset.id, b));
    const cxr = bodyEl.querySelector(".cf-cx-refresh"); if (cxr) cxr.onclick = () => reloadConnectors();
    bodyEl.querySelectorAll(".cf-nav-item").forEach(b => b.onclick = () => { if (b.dataset.sec !== activeSec) { activeSec = b.dataset.sec; render(); } });

    // proveedor of the FlashBrain → repuebla SUS modelos and su row of key
    const fp = document.getElementById("cf_fast_provider");
    if (fp) fp.onchange = () => {
      const provs = (cfg.catalog.fast && cfg.catalog.fast.providers) || [];
      const p = provs.find(x => x.id === fp.value) || {};
      const mb = document.getElementById("cf_fast_modelbox");
      if (mb) mb.innerHTML = modelSelect("cf_fast_model", p.models, (p.models || [])[0]);
      const kr = document.getElementById("cf_fast_keyrow"); if (kr) kr.innerHTML = providerKeyRow(p);
    };

    // preset of Brain Workers → guarda the TERNA of golpe (proveedor + endpoint + modelo) and recarga
    bodyEl.querySelectorAll(".cf-preset").forEach(b => b.onclick = () => {
      const presets = (cfg.catalog.code_agent && cfg.catalog.code_agent.presets) || [];
      const p = presets.find(x => x.id === b.dataset.preset);
      if (p) savePreset(p, b);
    });

    // proveedor of the Brain Workers → repuebla SUS modelos (el bug that traía al operador aquí: cambiaba a Codex
    // and the cinco campos seguían with the `glm-5.2` of the proveedor anterior, that Codex no sirve), su nota de
    // seguridad and the state of the CLI. The modelos NO se conservan al cambiar: son of otro proveedor.
    const cp = document.getElementById("cf_code_provider");
    if (cp) cp.onchange = () => {
      const provs = (cfg.catalog.code_agent && cfg.catalog.code_agent.providers) || [];
      const p = provs.find(x => x.id === cp.value) || {};
      const box = document.getElementById("cf_code_models");
      if (box) box.innerHTML = codeModelRows(p, { model: p.default_model || "", model_memory: "", model_web: "", model_code: "" });
      const st = document.getElementById("cf_code_clistate"); if (st) st.innerHTML = cliState(p);
      const nt = document.getElementById("cf_code_provnote");
      if (nt) nt.textContent = p.note || (cfg.catalog.code_agent && cfg.catalog.code_agent.note) || "";
    };
    bodyEl.querySelectorAll(".cf-save").forEach(b => b.onclick = () => saveV2(b.dataset.sec, b));
    const bv = bodyEl.querySelector(".cf-save-voice"); if (bv) bv.onclick = () => saveVoice(bv);
    // The capture block is filled by the session engine, which owns the device list and the reconnect. If this
    // engine has no such helper, REMOVE the block: two empty selects that do nothing are worse than no block.
    const dev = bodyEl.querySelector("#cf_voice_device");   // the browser-capture card (sec_voice)
    if (dev) {
      // Filling is ASYNC (the device list comes from `enumerateDevices`), so the pruning has to wait for it.
      // A select nobody filled is a control that does nothing — drop its row instead of showing it empty. That
      // is also what keeps this honest across the two engines: the legacy one has no capture-MODE picker, so
      // its row disappears on its own without this panel having to know which engine it is talking to.
      const filled = session.mountMicPickers ? session.mountMicPickers() : Promise.resolve();
      Promise.resolve(filled).catch(() => {}).then(() => {
        dev.querySelectorAll("select").forEach(sel => {
          if (!sel.options.length) { const r = sel.closest(".cf-row2"); if (r) r.remove(); }
        });
        if (!dev.querySelector("select")) dev.remove();
      });
    }
    bodyEl.querySelectorAll(".cf-save-keys").forEach(b => b.onclick = () => saveKeys(b.dataset.envs.split(","), b));
    const rf = bodyEl.querySelector(".cf-refresh-apis"); if (rf) rf.onclick = () => refreshApis(rf);
    const bb = bodyEl.querySelector(".cf-benchmarks-btn"); if (bb) bb.onclick = () => store.setBenchmarksOpen(true);
    const sc = bodyEl.querySelector(".cf-spotify"); if (sc) sc.onclick = () => connectSpotify(sc);
    const sd = bodyEl.querySelector(".cf-spotify-dis"); if (sd) sd.onclick = () => disconnectSpotify(sd);
  }

  const val = id => { const el = document.getElementById(id); return el ? el.value : undefined; };

  async function saveKey(env) {
    const v = val("cf_key_" + env);
    if (v && v.trim()) { await api.saveConfigCredential(env, v.trim()); return true; }
    return false;
  }

  async function saveV2(section, btn) {
    btn.disabled = true; msg(t("config.msg.saving"));
    try {
      let patch = {};
      if (section === "fast") {
        const provs = (cfg.catalog.fast && cfg.catalog.fast.providers) || [];
        const p = provs.find(x => x.id === val("cf_fast_provider")) || {};
        // The endpoint SALE of the proveedor, ya no there is campo of URL: elegir proveedor and dejar a base_url vieja
        // apuntando a otro sitio era a forma silenciosa of romper the FlashBrain.
        patch = { provider: val("cf_fast_provider"), model: val("cf_fast_model"), base_url: p.base_url || "" };
        // the key of the proveedor seleccionado (si se tecleó) → credencial en su env
        if (p.key_env) await saveKey(p.key_env);
      } else if (section === "code_agent") {
        patch = { provider: val("cf_code_provider"), model: val("cf_code_model"), model_memory: val("cf_code_model_memory"),
          model_web: val("cf_code_model_web"), model_code: val("cf_code_model_code"), max_parallel: Number(val("cf_code_max_parallel")) || 3 };
      } else if (section === "memory") {
        patch = { embed_provider: val("cf_mem_embed_provider"), embed_model: val("cf_mem_embed_model"),
          rerank_provider: val("cf_mem_rerank_provider"), rerank_model: val("cf_mem_rerank_model"),
          rerank_top_n: Number(val("cf_mem_rerank_top_n")) || 20, rerank_blend: Number(val("cf_mem_rerank_blend")) || 0.85,
          mem_processor_model: val("cf_mem_mem_processor_model") };
      }
      const r = await api.saveConfigV2(section, patch);
      msg(r.ok ? t("config.msg.saved_next_turn") : ("✗ " + (r.error || t("config.msg.error"))));
      api.uiEvent("config.save", { section });
    } catch (e) { msg(t("config.msg.error_saving")); } finally { btn.disabled = false; }
  }

  async function savePreset(p, btn) {
    btn.disabled = true; msg(t("config.msg.saving"));
    try {
      // The `model_<kind>` se LIMPIAN a propósito: son of otro proveedor and arrastrarlos es exactamente the desajuste
      // that the preset viene a evitar.
      const r = await api.saveConfigV2("code_agent", {
        provider: p.provider, base_url: p.base_url || "", model: p.model || "",
        model_memory: "", model_web: "", model_code: "",
      });
      msg(r.ok ? "✓ " + p.label : ("✗ " + (r.error || t("config.msg.error"))));
      api.uiEvent("config.save", { section: "code_agent", preset: p.id });
      if (r.ok) await load();
    } catch (e) { msg(t("config.msg.error_saving")); } finally { btn.disabled = false; }
  }

  async function saveVoice(btn) {
    btn.disabled = true; msg(t("config.msg.saving_voice"));
    try {
      const payload = {};
      (cfg.voice.knobs || []).forEach(k => { const el = document.getElementById("cfv_" + k.key); if (el) payload[k.key] = el.value; });
      const r = await api.saveSettings(payload);
      if (r.ok && r.needs_reconnect) {
        try { await session.loadVoices(); } catch (_) {}
        if (session.isActive()) { msg(t("config.msg.applying_reconnect")); await session.reconnect(); msg(t("config.msg.applied")); }
        else msg(t("config.msg.saved_on_connect"));
      } else msg(r.ok ? ("✓ " + (r.note || t("config.msg.saved"))) : t("config.msg.no_changes"));
    } catch (e) { msg(t("config.msg.error_saving_voice")); } finally { btn.disabled = false; }
  }

  async function saveKeys(envs, btn) {
    btn.disabled = true; msg(t("config.msg.saving_keys"));
    try { let n = 0; for (const e of envs) { if (await saveKey(e)) n++; } msg(n ? t("config.msg.keys_saved", { n }) : t("config.msg.no_changes")); }
    catch (e) { msg(t("config.msg.error_generic")); } finally { btn.disabled = false; await reloadApis(); }
  }

  async function refreshApis(btn) {
    btn.disabled = true; msg(t("config.msg.querying_balances"));
    try { await reloadApis(true); msg(t("config.msg.balances_updated")); } catch (_) { msg(t("config.msg.couldnt_query")); } finally { btn.disabled = false; }
  }

  async function reloadApis(refresh) {
    const r = await api.getApiSummary(refresh);
    cfg.apis = r.apis || [];
    store.setApiSummary(r.apis || []); store.setApiAlerts(r.alerts || []);
    const tb = document.getElementById("cf_apis_tbody");
    if (tb) tb.innerHTML = apisRows();
  }

  async function connectSpotify(btn) {
    btn.disabled = true; msg(t("config.msg.opening_spotify"));
    try {
      const r = await fetch("/api/spotify/connect", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(x => x.json());
      if (r.url) { window.open(r.url, "_blank", "width=520,height=680"); msg(t("config.msg.spotify_authorize")); }
      else msg("✗ " + (r.error || t("config.msg.couldnt_start")));
    } catch (_) { msg(t("config.msg.error_generic")); } finally { btn.disabled = false; }
  }
  async function disconnectSpotify(btn) {
    btn.disabled = true;
    try { await fetch("/api/spotify/disconnect", { method: "POST" }); msg(t("config.msg.spotify_disconnected")); await load(); } catch (_) {} finally { btn.disabled = false; }
  }

  // ═══ PESTAÑA CONECTORES (V2-083) ═══════════════════════════════════════════════════════════════════════
  // Etiqueta traducida directa (without depender of the texto renderizado by badge): connected/error/off.
  const cxBadge = c => {
    const st = c.connected ? "ok" : (c.status === "error" ? "error" : "off");
    const label = c.connected ? t("config.cx.connected")
      : (c.status === "error" ? t("config.badge.error") : t("config.cx.disconnected"));
    return `<span class="cf-badge cf-${esc(st)}">${label}</span>`;
  };

  function connectorCard(c) {
    const id = esc(c.id), fam = esc(c.family || "");
    let box = "";
    if (c.connected) {
      // ya conectado → button of desconectar/revocar
      const revoke = c.family === "infra" ? t("config.cx.revoke") : t("config.cx.disconnect_btn");
      box = `<button class="cf-btn cf-cx-act" data-act="disconnect" data-id="${id}">${revoke}</button>`;
    } else if (id === "whatsapp") {
      box = `<button class="cf-btn cf-cx-act" data-act="connect" data-id="whatsapp">${t("config.cx.connect_qr")}</button>`;
    } else if (id === "telegram") {
      box = `${row("api_id", `<input id="cx_tg_api_id" type="text" placeholder="${t("config.cx.tg_placeholder")}"/>`)}
        ${row("api_hash", `<input id="cx_tg_api_hash" type="password" placeholder="${t("config.cx.tg_placeholder")}"/>`)}
        <button class="cf-btn cf-cx-act" data-act="connect" data-id="telegram">${t("config.cx.connect_qr")}</button>`;
    } else if (id === "email") {
      box = `${row(t("config.row.provider"), `<select id="cx_em_provider">${opt(["gmail", "outlook", "other"], "gmail")}</select>`)}
        ${row(t("config.cx.email_label"), `<input id="cx_em_address" type="email" placeholder="${t("config.cx.email_placeholder")}"/>`)}
        ${row(t("config.cx.app_password"), `<input id="cx_em_pass" type="password" placeholder="${t("config.cx.app_password_ph")}"/>`)}
        <button class="cf-btn cf-cx-act" data-act="connect" data-id="email">${t("config.cx.connect")}</button>`;
    } else if (id === "spotify") {
      box = `<button class="cf-btn cf-cx-act" data-act="connect" data-id="spotify">${t("config.cx.connect_spotify")}</button>`;
    } else if (id === "architect") {
      const set = (c.config || {}).token_set;
      box = `${row(t("config.cx.daemon_token"), `<input id="cx_arch_token" type="password" placeholder="${set ? t("config.key.ph_saved") : t("config.cx.paste_token")}"/>`)}
        ${row(t("config.cx.url_optional"), `<input id="cx_arch_url" type="text" placeholder="https://127.0.0.1:5573"/>`)}
        <button class="cf-btn cf-cx-act" data-act="architect-save" data-id="architect">${t("config.cx.save_token")}</button>`;
    } else if (id === "meshkore") {
      const clusters = (c.clusters || []).map(cl =>
        `<div class="cf-cx-cluster"><span>${esc(cl.name)} ${cl.connected ? t("config.cx.cluster_connected") : ""}</span>
          <button class="cf-btn cf-cx-act" data-act="mesh-remove" data-id="meshkore" data-name="${esc(cl.name)}">${t("config.cx.revoke")}</button></div>`).join("");
      box = `${clusters}${row(t("config.cx.mk_name"), `<input id="cx_mk_name" type="text" placeholder="${t("config.cx.mk_name_ph")}"/>`)}
        ${row("cluster_id", `<input id="cx_mk_cid" type="text"/>`)}
        ${row("token", `<input id="cx_mk_token" type="password"/>`)}
        ${row(t("config.cx.mk_handle"), `<input id="cx_mk_handle" type="text" placeholder="zaelar"/>`)}
        <button class="cf-btn cf-cx-act" data-act="mesh-add" data-id="meshkore">${t("config.cx.add_cluster")}</button>`;
    }
    return `<section class="cf-panel-sec"><header class="cf-panel-head"><h4>${esc(c.label)} ${cxBadge(c)}</h4>
      <p>${esc(c.detail || "")}</p></header><div class="cf-group">${box}</div></section>`;
  }

  function sec_connectors() {
    const cs = cfg.connectors || [];
    if (!cs.length) return `<p class="cf-loading">${t("config.cx.load_error")}</p>`;
    const fams = [["mensajeria", t("config.cx.fam_messaging")], ["musica", t("config.cx.fam_music")], ["infra", t("config.cx.fam_infra")]];
    return fams.map(([f, title]) => {
      const items = cs.filter(c => c.family === f);
      if (!items.length) return "";
      return `<h3 class="cf-fam">${esc(title)}</h3>${items.map(connectorCard).join("")}`;
    }).join("") + `<div class="cf-foot"><button class="cf-btn cf-cx-refresh">${t("config.cx.refresh_status")}</button></div>`;
  }

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function reloadConnectors() {
    try { cfg.connectors = (await api.getConnectors()).connectors || []; } catch (_) {}
    if (activeTab === "conectores") render();
  }
  async function pollConnectors() {   // tras conectar mensajería, the QR/estado tardan un momento en aparecer
    for (let i = 0; i < 6; i++) { await sleep(1500); await reloadConnectors(); }
  }

  async function cxAct(act, id, btn) {
    btn.disabled = true;
    try {
      if (act === "disconnect") {
        if (id === "spotify") { await disconnectSpotify(btn); }
        else if (id === "architect") { await api.architectDisconnect(); msg(t("config.msg.architect_revoked")); }
        else { await api.disconnectMessaging(id, {}); msg(t("config.msg.disconnected", { id })); }
        await reloadConnectors();
      } else if (act === "connect") {
        if (id === "spotify") { await connectSpotify(btn); return; }
        let payload = {};
        if (id === "telegram") payload = { api_id: val("cx_tg_api_id"), api_hash: val("cx_tg_api_hash") };
        if (id === "email") payload = { email_address: val("cx_em_address"), email_password: val("cx_em_pass"), provider: val("cx_em_provider") };
        const r = await api.connectMessaging(id, payload);
        msg(r.ok ? t("config.msg.connecting", { id }) : ("✗ " + (r.error || t("config.msg.error"))));
        pollConnectors();
      } else if (act === "architect-save") {
        const token = val("cx_arch_token"), url = val("cx_arch_url");
        const r = await api.architectConnect({ token, url });
        msg(r.ok ? t("config.msg.token_saved") : ("✗ " + (r.error || t("config.msg.error")))); await reloadConnectors();
      } else if (act === "mesh-add") {
        const r = await api.meshkoreAdd({ name: val("cx_mk_name"), cluster_id: val("cx_mk_cid"), token: val("cx_mk_token"), handle: val("cx_mk_handle") });
        msg(r.ok ? t("config.msg.cluster_added") : ("✗ " + (r.error || t("config.msg.error")))); await reloadConnectors();
      } else if (act === "mesh-remove") {
        await api.meshkoreRemove(btn.dataset.name); msg(t("config.msg.cluster_revoked")); await reloadConnectors();
      }
    } catch (e) { msg(t("config.msg.error_generic")); } finally { btn.disabled = false; }
  }

  // ═══ PESTAÑA WIDGETS (V2-083) — a sola lista alfabética with badge de-serie/tuyo ═══════════════════════
  function sec_widgets() {
    const ws = (cfg.widgets || []).filter(w => w.surface === "user")
      .sort((a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id), "es"));
    if (!ws.length) return `<p class="cf-loading">${t("config.widgets.load_error")}</p>`;
    const rows = ws.map(w => {
      const kind = w.origin === "builtin"
        ? `<span class="cf-wbadge builtin">${t("config.widgets.builtin_badge")}</span>`
        : `<span class="cf-wbadge user">${t("config.widgets.yours_badge")}</span>`;
      const al = (w.aliases || []).filter(a => a.toLowerCase() !== String(w.name || "").toLowerCase()).slice(0, 6).join(" · ");
      return `<div class="cf-wrow"><div class="cf-wname">${esc(w.name || w.id)} ${kind}</div>
        <div class="cf-waliases">${esc(al)}</div></div>`;
    }).join("");
    return panel("widgets", t("config.widgets.title"), t("config.widgets.sub"), rows);
  }

  async function load() {
    msg(""); bodyEl.innerHTML = `<p class="cf-loading">${t("config.loading")}</p>`;
    try {
      cfg = await api.getConfig();
      // V2-083: conectores + widgets for sus pestañas (best-effort, en paralelo).
      try {
        const [cx, wr] = await Promise.all([api.getConnectors(), api.getWidgetsRegistry()]);
        cfg.connectors = (cx && cx.connectors) || [];
        cfg.widgets = (wr && wr.registry) || [];
      } catch (_) { cfg.connectors = cfg.connectors || []; cfg.widgets = cfg.widgets || []; }
      render();
      store.setApiSummary(cfg.apis || []);
      store.setApiAlerts((cfg.apis || []).filter(a => a.state === "warn" || a.state === "error"));
    } catch (e) { bodyEl.innerHTML = `<p class="cf-loading">${t("config.load_config_error")}</p>`; }
  }
  const close = () => store.setConfigOpen(false);
  const onKey = e => { if (e.key === "Escape" && store.configOpen()) close(); };
  window.addEventListener("keydown", onKey);

  ovl = h("div", { class: () => "cfgfull" + (store.configOpen() ? " open" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cf-shell" },
      h("div", { class: "cf-head" },
        h("h3", {}, raw(GEAR_ICON), () => t("config.tab.settings")),
        h("span", { class: "cf-msg", ref: el => (msgEl = el) }),
        h("button", { class: "cf-x", onClick: close }, () => t("config.close")),
      ),
      h("div", { class: "cf-body", ref: el => (bodyEl = el) }, h("p", { class: "cf-loading" }, () => t("config.loading_short"))),
    ),
  );

  let wasOpen = false;
  createEffect(() => { const o = store.configOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return ovl;
}

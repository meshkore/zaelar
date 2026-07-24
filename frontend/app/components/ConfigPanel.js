// ConfigPanel — ⚙ área de CONFIGURACIÓN a pantalla completa (V2-043).
// Elige QUÉ API/modelo usa CADA pieza (FlashBrain, CodeAgent, memoria, voz, búsqueda web, música, conectores)
// y muestra el RESUMEN de APIs con SALDO. Todo desde la UI (invariante de producto). Patrón: menú lateral
// (una sección visible a la vez, estilo Chrome/macOS Ajustes) + panel de formulario a la derecha con filas
// agrupadas y su botón de guardar, leído por id (como SettingsModal), guardado por sección contra /api/config/*.
// Las API keys por pieza se guardan en la ENV del proveedor (coherente con la resolución por endpoint del FlashBrain).
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import * as session from "../services/session.js?v=2";
import { GEAR_ICON, BRAIN_ICON, CPU_ICON, DATABASE_ICON, MIC_ICON, SEARCH_ICON, MUSIC_ICON, SERVER_ICON } from "../lib/icons.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const opt = (list, sel) => (list || []).map(o => `<option value="${esc(o.value != null ? o.value : o)}"${(o.value != null ? o.value : o) === sel ? " selected" : ""}>${esc(o.label != null ? o.label : o)}</option>`).join("");
const badge = st => `<span class="cf-badge cf-${esc(st || "off")}">${({ ok: "OK", warn: "aviso", error: "problema", off: "sin key", unknown: "—" }[st] || st || "—")}</span>`;

// una fila de ajuste: etiqueta a la izquierda, control (+ pista opcional) a la derecha — patrón Ajustes/Chrome.
const row = (label, ctl, hint) =>
  `<div class="cf-row2"><label class="cf-row2-label">${esc(label)}</label><div class="cf-row2-ctl">${ctl}${hint ? `<span class="cf-hint">${hint}</span>` : ""}</div></div>`;

// una sección = título + subtítulo + un grupo de filas (tarjeta con separadores, como un grupo de Ajustes).
const panel = (id, title, sub, inner) =>
  `<section class="cf-panel-sec" id="cf_${id}"><header class="cf-panel-head"><h4>${esc(title)}</h4>${sub ? `<p>${esc(sub)}</p>` : ""}</header><div class="cf-group">${inner}</div></section>`;

const SECTIONS = [
  { id: "fast", label: "Cerebro rápido", icon: BRAIN_ICON },
  { id: "code", label: "Agente de código", icon: CPU_ICON },
  { id: "memory", label: "Memoria", icon: DATABASE_ICON },
  { id: "voice", label: "Voz", icon: MIC_ICON },
  { id: "search", label: "Búsqueda web", icon: SEARCH_ICON },
  { id: "music", label: "Música", icon: MUSIC_ICON },
  { id: "apis", label: "APIs y saldo", icon: SERVER_ICON },
];

export function ConfigPanel() {
  let cfg = null, bodyEl, msgEl, ovl;
  let activeSec = SECTIONS[0].id;

  const msg = t => { if (msgEl) msgEl.textContent = t || ""; };

  // ---- render ----
  function render() {
    const cat = cfg.catalog || {};
    const builders = {
      fast: () => sec_fast(cat.fast || {}),
      code: () => sec_code(cat.code_agent || {}),
      memory: () => sec_memory(cat),
      voice: () => sec_voice(),
      search: () => sec_search(),
      music: () => sec_music(),
      apis: () => sec_apis(),
    };
    if (!builders[activeSec]) activeSec = SECTIONS[0].id;
    const nav = SECTIONS.map(s => `<button type="button" class="cf-nav-item${s.id === activeSec ? " active" : ""}" data-sec="${s.id}">${s.icon}<span>${esc(s.label)}</span></button>`).join("");
    bodyEl.innerHTML = `<nav class="cf-nav">${nav}</nav><div class="cf-scroll"><div class="cf-panel">${builders[activeSec]()}</div></div>`;
    wire();
  }

  const providerKeyRow = (prov) => {
    // fila de API key para el proveedor seleccionado (si es cloud y tiene key_env). Redactada: solo presencia.
    if (!prov || !prov.cloud || !prov.key_env) return "";
    const setNow = (cfg.credentials || []).some(c => (c.env || []).includes(prov.key_env) && c.set);
    return row(`API key · ${prov.key_env}`,
      `<input id="cf_key_${esc(prov.key_env)}" type="password" placeholder="${setNow ? "•••••• (guardada — deja vacío para mantener)" : "pega la key"}" autocomplete="off"/>`,
      setNow ? "✓ configurada" : "no configurada");
  };

  function sec_fast(c) {
    const f = (cfg.v2 && cfg.v2.fast) || {};
    const provs = c.providers || [];
    const cur = provs.find(p => p.id === f.provider) || provs[0] || {};
    const models = cur.models || [];
    return panel("fast", "Cerebro rápido · FlashBrain", (c.note || "") + " — el que responde en cada turno de voz.",
      row("Proveedor", `<select id="cf_fast_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), f.provider)}</select>`) +
      row("Modelo", `<input id="cf_fast_model" list="dl_fast_model" value="${esc(f.model)}"/><datalist id="dl_fast_model">${opt(models)}</datalist>`) +
      row("Base URL", `<input id="cf_fast_base_url" value="${esc(f.base_url)}" placeholder="${esc(cur.base_url || "")}"/>`) +
      `<div id="cf_fast_keyrow">${providerKeyRow(cur)}</div>` +
      `<div class="cf-foot"><button class="cf-save" data-sec="fast">Guardar cerebro rápido</button></div>`);
  }

  function sec_code(c) {
    const a = (cfg.v2 && cfg.v2.code_agent) || {};
    const provs = c.providers || [];
    return panel("code", "Agente de código · workers", (c.note || ""),
      row("Proveedor", `<select id="cf_code_provider">${opt(provs.map(p => ({ value: p.id, label: p.label })), a.provider)}</select>`) +
      row("Modelo (global)", `<input id="cf_code_model" value="${esc(a.model)}" placeholder="default del proveedor"/>`) +
      row("· memoria", `<input id="cf_code_model_memory" value="${esc(a.model_memory)}" placeholder="hereda"/>`) +
      row("· web", `<input id="cf_code_model_web" value="${esc(a.model_web)}" placeholder="hereda"/>`) +
      row("· código", `<input id="cf_code_model_code" value="${esc(a.model_code)}" placeholder="hereda"/>`) +
      row("Máx. en paralelo", `<input id="cf_code_max_parallel" type="number" min="1" max="8" value="${esc(a.max_parallel)}"/>`) +
      `<div class="cf-foot"><button class="cf-save" data-sec="code_agent">Guardar agente de código</button></div>`);
  }

  function sec_memory(cat) {
    const m = (cfg.v2 && cfg.v2.memory) || {};
    const emb = (cat.memory_embed && cat.memory_embed.providers) || [];
    const rer = (cat.memory_rerank && cat.memory_rerank.providers) || [];
    return panel("memory", "Memoria · recuperación y escritura", "Embedding + reranker + procesador de escritura. Local por defecto.",
      row("Embedding", `<select id="cf_mem_embed_provider">${opt(emb.map(p => ({ value: p.id, label: p.label })), m.embed_provider)}</select>`, "⚠️ cambiarlo exige re-embed") +
      row("Modelo embedding", `<input id="cf_mem_embed_model" value="${esc(m.embed_model)}"/>`) +
      row("Reranker", `<select id="cf_mem_rerank_provider">${opt(rer.map(p => ({ value: p.id, label: p.label })), m.rerank_provider)}</select>`) +
      row("Modelo reranker", `<input id="cf_mem_rerank_model" value="${esc(m.rerank_model)}" placeholder="default del proveedor"/>`) +
      row("top-N", `<input id="cf_mem_rerank_top_n" type="number" min="1" max="100" value="${esc(m.rerank_top_n)}"/>`) +
      row("blend", `<input id="cf_mem_rerank_blend" type="number" step="0.05" min="0" max="1" value="${esc(m.rerank_blend)}"/>`) +
      row("Procesador de escritura (el CORAZÓN)", `<input id="cf_mem_mem_processor_model" value="${esc(m.mem_processor_model)}"/>`) +
      `<div class="cf-foot"><button class="cf-save" data-sec="memory">Guardar memoria</button></div>`);
  }

  function sec_voice() {
    const v = cfg.voice || {};
    const knobs = v.knobs || [];
    const free = new Set(v.free_text || []);
    const rows = knobs.map(k => {
      const hint = k.note ? esc(k.note) : "";
      const ctl = free.has(k.key)
        ? `<input id="cfv_${k.key}" list="dlv_${k.key}" value="${esc(k.value)}"/><datalist id="dlv_${k.key}">${opt(k.options)}</datalist>`
        : `<select id="cfv_${k.key}">${opt(k.options, k.value)}</select>`;
      return row(k.label, ctl, hint);
    }).join("");
    return panel("voice", "Voz · STT · TTS · idioma · atención", "La VOZ concreta se cambia tocando el orbe. Guardar puede reconectar.",
      rows + `<div class="cf-foot"><button class="cf-save-voice">Guardar voz</button></div>`);
  }

  function sec_search() {
    // La búsqueda web elige proveedor AUTO por calidad según la key disponible (Perplexity→Tavily→Brave→Google
    // gratis→DDG). No hay store propio: se gobierna con las KEYS. Se editan aquí como credenciales.
    const creds = cfg.credentials || [];
    const keyRow = (prov, env, label) => {
      const setNow = creds.some(c => c.key === prov && c.set);
      return row(`${label} · ${env}`,
        `<input id="cf_key_${esc(env)}" type="password" placeholder="${setNow ? "•••••• (guardada)" : "pega la key (opcional)"}" autocomplete="off"/>`,
        setNow ? "✓ activa" : "—");
    };
    return panel("search", "Búsqueda web", "Proveedor AUTO por calidad según la key: Perplexity → Tavily → Brave → Google (gratis) → DuckDuckGo. Sin ninguna key funciona gratis con Google.",
      keyRow("perplexity", "PERPLEXITY_API_KEY", "Perplexity (síntesis, mejor)") +
      keyRow("tavily", "TAVILY_API_KEY", "Tavily") +
      keyRow("brave", "BRAVE_SEARCH_KEY", "Brave (snippets)") +
      `<div class="cf-foot"><button class="cf-save-keys" data-envs="PERPLEXITY_API_KEY,TAVILY_API_KEY,BRAVE_SEARCH_KEY">Guardar keys de búsqueda</button></div>`);
  }

  function sec_music() {
    const sp = cfg.spotify || {};
    const st = sp.logged_in ? "conectado" : (sp.can_connect ? "listo para conectar" : "falta client_id");
    return panel("music", "Música · Spotify", "Reproduce por voz. Sin Spotify, cae al audio gratis de YouTube dentro del widget de música.",
      row("Estado", `<span class="cf-status">${esc(st)}${sp.logged_in ? "" : (sp.default_available ? " · app de un clic disponible" : "")}</span>`) +
      `<div class="cf-foot">${sp.logged_in
        ? `<button class="cf-spotify-dis">Desconectar Spotify</button>`
        : `<button class="cf-spotify" ${sp.can_connect ? "" : "disabled"}>Conectar Spotify</button>`}</div>`);
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
    return panel("apis", "APIs y servicios · saldo", "Resumen de las APIs externas. El saldo se muestra donde el proveedor lo expone; el resto avisa por el último error.",
      `<table class="cf-apis"><tbody id="cf_apis_tbody">${apisRows()}</tbody></table>
       <div class="cf-foot"><button class="cf-refresh-apis">Actualizar saldos</button></div>`);
  }

  const bar = (b) => {
    const pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
    return `<span class="cf-bar"><i style="width:${pct}%"></i></span> ${pct}%`;
  };

  // ---- wiring ----
  function wire() {
    bodyEl.querySelectorAll(".cf-nav-item").forEach(b => b.onclick = () => { if (b.dataset.sec !== activeSec) { activeSec = b.dataset.sec; render(); } });

    // proveedor del FlashBrain → repuebla modelos, placeholder de base_url y fila de key
    const fp = document.getElementById("cf_fast_provider");
    if (fp) fp.onchange = () => {
      const provs = (cfg.catalog.fast && cfg.catalog.fast.providers) || [];
      const p = provs.find(x => x.id === fp.value) || {};
      const dl = document.getElementById("dl_fast_model"); if (dl) dl.innerHTML = opt(p.models || []);
      const bu = document.getElementById("cf_fast_base_url"); if (bu) { bu.placeholder = p.base_url || ""; }
      const kr = document.getElementById("cf_fast_keyrow"); if (kr) kr.innerHTML = providerKeyRow(p);
    };
    bodyEl.querySelectorAll(".cf-save").forEach(b => b.onclick = () => saveV2(b.dataset.sec, b));
    const bv = bodyEl.querySelector(".cf-save-voice"); if (bv) bv.onclick = () => saveVoice(bv);
    bodyEl.querySelectorAll(".cf-save-keys").forEach(b => b.onclick = () => saveKeys(b.dataset.envs.split(","), b));
    const rf = bodyEl.querySelector(".cf-refresh-apis"); if (rf) rf.onclick = () => refreshApis(rf);
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
    btn.disabled = true; msg("Guardando…");
    try {
      let patch = {};
      if (section === "fast") {
        patch = { provider: val("cf_fast_provider"), model: val("cf_fast_model"), base_url: val("cf_fast_base_url") };
        // la key del proveedor seleccionado (si se tecleó) → credencial en su env
        const provs = (cfg.catalog.fast && cfg.catalog.fast.providers) || [];
        const p = provs.find(x => x.id === patch.provider) || {};
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
      msg(r.ok ? "✓ guardado (aplica en el próximo turno, sin reconectar)" : ("✗ " + (r.error || "error")));
      api.uiEvent("config.save", { section });
    } catch (e) { msg("✗ error al guardar"); } finally { btn.disabled = false; }
  }

  async function saveVoice(btn) {
    btn.disabled = true; msg("Guardando voz…");
    try {
      const payload = {};
      (cfg.voice.knobs || []).forEach(k => { const el = document.getElementById("cfv_" + k.key); if (el) payload[k.key] = el.value; });
      const r = await api.saveSettings(payload);
      if (r.ok && r.needs_reconnect) {
        try { await session.loadVoices(); } catch (_) {}
        if (session.isActive()) { msg("✓ aplicando… reconectando"); await session.reconnect(); msg("✓ aplicado"); }
        else msg("✓ guardado · se aplica al conectar");
      } else msg(r.ok ? ("✓ " + (r.note || "guardado")) : "sin cambios");
    } catch (e) { msg("✗ error al guardar la voz"); } finally { btn.disabled = false; }
  }

  async function saveKeys(envs, btn) {
    btn.disabled = true; msg("Guardando keys…");
    try { let n = 0; for (const e of envs) { if (await saveKey(e)) n++; } msg(n ? `✓ ${n} key(s) guardada(s)` : "sin cambios"); }
    catch (e) { msg("✗ error"); } finally { btn.disabled = false; await reloadApis(); }
  }

  async function refreshApis(btn) {
    btn.disabled = true; msg("Consultando saldos…");
    try { await reloadApis(true); msg("✓ saldos actualizados"); } catch (_) { msg("✗ no pude consultar"); } finally { btn.disabled = false; }
  }

  async function reloadApis(refresh) {
    const r = await api.getApiSummary(refresh);
    cfg.apis = r.apis || [];
    store.setApiSummary(r.apis || []); store.setApiAlerts(r.alerts || []);
    const tb = document.getElementById("cf_apis_tbody");
    if (tb) tb.innerHTML = apisRows();
  }

  async function connectSpotify(btn) {
    btn.disabled = true; msg("Abriendo Spotify…");
    try {
      const r = await fetch("/api/spotify/connect", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then(x => x.json());
      if (r.url) { window.open(r.url, "_blank", "width=520,height=680"); msg("Autoriza en la ventana de Spotify y vuelve."); }
      else msg("✗ " + (r.error || "no pude iniciar"));
    } catch (_) { msg("✗ error"); } finally { btn.disabled = false; }
  }
  async function disconnectSpotify(btn) {
    btn.disabled = true;
    try { await fetch("/api/spotify/disconnect", { method: "POST" }); msg("Spotify desconectado."); await load(); } catch (_) {} finally { btn.disabled = false; }
  }

  async function load() {
    msg(""); bodyEl.innerHTML = '<p class="cf-loading">Cargando configuración…</p>';
    try {
      cfg = await api.getConfig();
      render();
      store.setApiSummary(cfg.apis || []);
      store.setApiAlerts((cfg.apis || []).filter(a => a.state === "warn" || a.state === "error"));
    } catch (e) { bodyEl.innerHTML = '<p class="cf-loading">No pude cargar /api/config</p>'; }
  }
  const close = () => store.setConfigOpen(false);
  const onKey = e => { if (e.key === "Escape" && store.configOpen()) close(); };
  window.addEventListener("keydown", onKey);

  ovl = h("div", { class: () => "cfgfull" + (store.configOpen() ? " open" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cf-shell" },
      h("div", { class: "cf-head" },
        h("h3", {}, raw(GEAR_ICON), "Configuración"),
        h("span", { class: "cf-msg", ref: el => (msgEl = el) }),
        h("button", { class: "cf-x", onClick: close }, "cerrar"),
      ),
      h("div", { class: "cf-body", ref: el => (bodyEl = el) }, h("p", { class: "cf-loading" }, "Cargando…")),
    ),
  );

  let wasOpen = false;
  createEffect(() => { const o = store.configOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return ovl;
}

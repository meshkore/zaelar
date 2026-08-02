// WizardModal — asistente de primer arranque (V2-040): elige perfil LOCAL/CLOUD (con el detector recomendando),
// resuelve los HUECOS (instala con un clic lo del proyecto, o da el comando para lo de sistema) y valida las
// CREDENCIALES. Se auto-abre cuando la config no está validada (first_run) y es reabrible desde el TopBar (🧭).
// Estilo con las variables --hb-* (tema dark/light). Render por innerHTML + wiring por id, como SettingsModal.
import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { CHEVRON_LEFT_ICON, CHEVRON_RIGHT_ICON, REFRESH_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const ok = b => b ? "✓" : "✗";

export function WizardModal() {
  let S = null;          // estado cacheado del server (/api/wizard/state)
  let chosen = "";       // perfil elegido
  let step = "perfil";   // perfil | huecos | credenciales
  let bodyEl, titleEl, ovl;
  const jobs = {};       // id-instalador → job en curso (poll)

  const close = () => store.setWizardOpen(false);

  async function load() {
    bodyEl.innerHTML = '<p class="wiz-hint">' + t("wizard.analyzing") + '</p>';
    try {
      S = await api.wizardState();
      chosen = S.active_profile || (S.report && S.report.recommend && S.report.recommend.profile) || "local";
      step = "perfil";
      render();
    } catch (e) {
      bodyEl.innerHTML = '<p class="wiz-hint">' + t("wizard.loadError") + '</p>';
    }
  }

  async function reanalyze(btn) {
    if (btn) { btn.disabled = true; btn.textContent = t("wizard.analyzingShort"); }
    try { S.report = await api.wizardReport(true); } catch (_) {}
    render();
  }

  function render() {
    titleEl.textContent = { perfil: t("wizard.stepPerfilTitle"), huecos: t("wizard.stepHuecosTitle"), credenciales: t("wizard.stepCredencialesTitle") }[step] || t("wizard.title");
    if (step === "perfil") return renderPerfil();
    if (step === "huecos") return renderHuecos();
    if (step === "credenciales") return renderCreds();
  }

  // ── ① PERFIL ──────────────────────────────────────────────────────────────────────────────────────────
  function renderPerfil() {
    const rec = (S.report && S.report.recommend) || {};
    const hw = (S.report && S.report.hardware) || {};
    const cards = (S.profiles || []).map(p => {
      const isRec = rec.profile === p.name;
      const v = p.voice || {}, f = p.fast || {};
      return `<div class="wiz-card${isRec ? " rec" : ""}" data-profile="${esc(p.name)}">
        <div class="wiz-card-h"><b>${esc(p.label)}</b>${isRec ? '<span class="wiz-badge">' + t("wizard.recommended") + '</span>' : ""}</div>
        <div class="wiz-sub">${esc(p.summary)}</div>
        <div class="wiz-fix">${t("wizard.providerLine", { stt: esc(v.stt_provider || "?"), tts: esc(v.tts_provider || "?"), brain: esc(f.provider || "?") })}</div>
        <button class="wiz-btn pick" data-profile="${esc(p.name)}">${t("wizard.choose")}</button>
      </div>`;
    }).join("");
    bodyEl.innerHTML = `
      <p class="wiz-hint">${t("wizard.machineLine", { platform: esc(hw.platform || "?"), arch: esc(hw.arch || "?"), apple: hw.apple_silicon ? " · " + t("wizard.appleSilicon") : "", metal: ok(hw.metal), ollama: ok(S.report && S.report.ollama && S.report.ollama.reachable) })}
      ${rec.why ? t("wizard.suggestion", { profile: esc(rec.profile), why: esc(rec.why) }) : ""}</p>
      <div class="wiz-cards">${cards}</div>
      <div class="wiz-foot"><button class="wiz-btn ghost" id="wizReanalyze">${REFRESH_ICON}${t("wizard.reanalyze")}</button><span class="wiz-msg" id="wizMsg"></span></div>`;
    bodyEl.querySelectorAll(".pick").forEach(b => b.onclick = async () => {
      chosen = b.dataset.profile;
      b.disabled = true; b.textContent = t("wizard.applying");
      try { await api.wizardProfile(chosen); } catch (_) {}
      step = "huecos"; render();
    });
    const rb = bodyEl.querySelector("#wizReanalyze");
    if (rb) rb.onclick = () => reanalyze(rb);
  }

  // ── ② HUECOS ──────────────────────────────────────────────────────────────────────────────────────────
  function gaps() {
    const r = S.report || {}, t2 = r.tooling || {}, oll = r.ollama || {}, hw = r.hardware || {};
    const prof = (S.profiles || []).find(p => p.name === chosen) || {};
    const needOllama = (prof.fast && prof.fast.provider === "ollama") || (prof.memory && prof.memory.embed_provider === "ollama");
    const out = [];
    if (needOllama && !oll.reachable) out.push({ id: "ollama", label: t("wizard.gapOllamaDown"), runnable: false });
    if (needOllama && oll.reachable) {
      const models = oll.models || [];
      const want = [];
      if (prof.fast && prof.fast.provider === "ollama" && prof.fast.model) want.push(prof.fast.model);
      if (prof.memory && prof.memory.embed_provider === "ollama" && prof.memory.embed_model) want.push(prof.memory.embed_model);
      if (prof.memory && prof.memory.mem_processor_model) want.push(prof.memory.mem_processor_model);
      [...new Set(want)].forEach(m => {
        const has = models.some(x => (x || "").toLowerCase().split(":")[0] === (m || "").toLowerCase().split(":")[0]);
        if (!has) out.push({ id: "ollama_model", model: m, label: t("wizard.gapOllamaModel", { model: m }), runnable: true });
      });
    }
    if (!t2.claude_cli) out.push({ id: "claude_cli", label: t("wizard.gapClaudeCli"), runnable: false });
    if (!t2.playwright_chromium) out.push({ id: "playwright", label: t("wizard.gapPlaywright"), runnable: true });
    if (!t2.livekit_server) out.push({ id: "livekit", label: t("wizard.gapLivekit"), runnable: false });
    if (chosen === "local" && !hw.metal && !hw.cuda) out.push({ id: "_accel", label: t("wizard.gapNoAccel"), runnable: false, note: true });
    return out;
  }

  function renderHuecos() {
    const g = gaps();
    const insts = {}; (S.installers || []).forEach(i => insts[i.id] = i);
    const rows = g.length ? g.map((x, i) => {
      const inst = insts[x.id] || {};
      if (x.note) return `<div class="wiz-row note"><span>${esc(x.label)}</span></div>`;
      const right = x.runnable
        ? `<button class="wiz-btn run" data-i="${i}">${t("wizard.install")}</button>`
        : `<button class="wiz-btn ghost copy" data-cmd="${esc(inst.cmd || "")}">${t("wizard.copyCommand")}</button>`;
      const cmd = x.runnable ? "" : `<code class="wiz-cmd">${esc(inst.cmd || "")}</code>`;
      return `<div class="wiz-row" data-row="${i}"><div class="wiz-row-l"><span>${esc(x.label)}</span>${cmd}</div><div class="wiz-row-r" id="wizr${i}">${right}</div></div>`;
    }).join("") : '<p class="wiz-hint">' + t("wizard.allSet") + '</p>';
    bodyEl.innerHTML = `
      <p class="wiz-hint">${t("wizard.huecosIntro", { profile: esc(chosen) })}</p>
      <div class="wiz-rows">${rows}</div>
      <div class="wiz-foot"><button class="wiz-btn ghost" id="wizBack">${CHEVRON_LEFT_ICON}${t("wizard.backToProfile")}</button><button class="wiz-btn ghost" id="wizReanalyze">${REFRESH_ICON}${t("wizard.reanalyze")}</button><button class="wiz-btn" id="wizNext">${CHEVRON_RIGHT_ICON}${t("wizard.continue")}</button></div>`;
    bodyEl.querySelector("#wizBack").onclick = () => { step = "perfil"; render(); };
    bodyEl.querySelector("#wizReanalyze").onclick = (e) => reanalyze(e.target);
    bodyEl.querySelector("#wizNext").onclick = () => { step = "credenciales"; render(); };
    bodyEl.querySelectorAll(".copy").forEach(b => b.onclick = () => { navigator.clipboard && navigator.clipboard.writeText(b.dataset.cmd); b.textContent = t("wizard.copied"); });
    bodyEl.querySelectorAll(".run").forEach(b => b.onclick = () => launchInstall(g[+b.dataset.i], +b.dataset.i));
  }

  async function launchInstall(gap, i) {
    const cell = bodyEl.querySelector("#wizr" + i);
    if (cell) cell.innerHTML = '<span class="wiz-msg">' + t("wizard.installing") + '</span>';
    try {
      const res = await api.wizardInstall({ id: gap.id, model: gap.model || "" });
      if (!res.ok) { if (cell) cell.innerHTML = '<span class="wiz-msg err">' + esc(res.error || t("wizard.error")) + "</span>"; return; }
      if (!res.runnable) { if (cell) cell.innerHTML = '<code class="wiz-cmd">' + esc(res.command) + "</code>"; return; }
      pollInstall(res.job, i);
    } catch (e) { if (cell) cell.innerHTML = '<span class="wiz-msg err">' + t("wizard.error") + '</span>'; }
  }

  async function pollInstall(job, i) {
    const cell = bodyEl.querySelector("#wizr" + i);
    try {
      const st = await api.wizardInstallStatus(job);
      if (cell) cell.innerHTML = '<span class="wiz-msg">' + esc(st.status || "…") + "</span>";
      if (st.status === "done") { if (cell) cell.innerHTML = '<span class="wiz-msg okk">' + t("wizard.installDone") + '</span>'; return; }
      if (st.status === "failed") { if (cell) cell.innerHTML = '<span class="wiz-msg err">' + t("wizard.installFailed") + '</span>'; return; }
    } catch (_) {}
    setTimeout(() => pollInstall(job, i), 2000);   // sin Date.now: intervalo fijo
  }

  // ── ③ CREDENCIALES ─────────────────────────────────────────────────────────────────────────────────────
  function renderCreds() {
    const creds = ((S.report && S.report.credentials) || []).filter(c => (c.profiles || []).includes(chosen));
    const rows = creds.length ? creds.map(c => `
      <div class="wiz-row">
        <div class="wiz-row-l"><span>${esc(c.key)} ${c.set ? '<span class="wiz-badge ok">' + t("wizard.set") + '</span>' : ""}</span><span class="wiz-sub">${esc(c.enables)}</span></div>
        <div class="wiz-row-r"><input class="wiz-inp" type="password" placeholder="${c.set ? t("wizard.credChange") : t("wizard.credPaste")}" id="cred_${esc(c.key)}"/><button class="wiz-btn save" data-key="${esc(c.key)}">${t("wizard.save")}</button></div>
      </div>`).join("") : '<p class="wiz-hint">' + t("wizard.noKeys") + '</p>';
    bodyEl.innerHTML = `
      <p class="wiz-hint">${t("wizard.credsIntro", { profile: esc(chosen) })}</p>
      <div class="wiz-rows">${rows}</div>
      <div class="wiz-foot"><button class="wiz-btn ghost" id="wizBack">${CHEVRON_LEFT_ICON}${t("wizard.back")}</button><button class="wiz-btn done" id="wizDone">${t("wizard.enterZaelar")}</button><span class="wiz-msg" id="wizMsg"></span></div>`;
    bodyEl.querySelector("#wizBack").onclick = () => { step = "huecos"; render(); };
    bodyEl.querySelector("#wizDone").onclick = finish;
    bodyEl.querySelectorAll(".save").forEach(b => b.onclick = async () => {
      const key = b.dataset.key, inp = bodyEl.querySelector("#cred_" + key);
      const provider = key;   // el catálogo usa el id de proveedor; el server lo resuelve a su env
      b.disabled = true; b.textContent = "…";
      try {
        const r = await api.wizardCredential({ provider, value: inp ? inp.value : "" });
        b.textContent = r.ok ? t("wizard.saved") : t("wizard.error");
      } catch (_) { b.textContent = t("wizard.error"); }
    });
  }

  async function finish(e) {
    const msg = bodyEl.querySelector("#wizMsg");
    if (msg) msg.textContent = t("wizard.saving");
    try { await api.wizardComplete(true); } catch (_) {}
    close();
  }

  ovl = h("div", { class: () => "ovl wiz" + (store.wizardOpen() ? " on" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cfgm wizm" },
      h("div", { class: "mh" }, h("h3", { ref: el => (titleEl = el) }, () => t("wizard.title")), h("button", { class: "x", onClick: close }, () => t("wizard.close"))),
      h("div", { class: "wiz-body", ref: el => (bodyEl = el) }, h("p", { class: "wiz-hint" }, "…")),
    ),
  );

  let was = false;
  createEffect(() => { const o = store.wizardOpen(); if (o && !was) load(); was = o; });
  return ovl;
}

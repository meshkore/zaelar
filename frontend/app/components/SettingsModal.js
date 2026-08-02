// SettingsModal — ⚙ panel: voice provider · language · STT/TTS.
// The VOICE itself is changed by tapping the orb. Saving may trigger a reconnect.
// The dynamic knob form keeps its innerHTML approach (read back by id on save).
import { h, raw } from "../core/dom.js?v=2";
import { createSignal, createEffect } from "../core/reactive.js?v=2";
import * as api from "../services/api.js?v=2";
import * as session from "../services/session.js?v=3";
import { GEAR_ICON, PLAY_ICON } from "../lib/icons.js?v=1";

const [isOpen, setOpen] = createSignal(false);
export const openSettings = () => setOpen(true);

const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const optsHTML = (list, sel) => (list || []).map(o => `<option value="${esc(o.value)}"${o.value === sel ? " selected" : ""}>${esc(o.label)}</option>`).join("");

export function SettingsModal() {
  let cfg = null, bodyEl, msgEl, ovl;

  function render() {
    const free = new Set(cfg.free_text || []);
    bodyEl.innerHTML = cfg.knobs.map(k => {
      const note = k.note ? `<div class="note">${esc(k.note)}</div>` : "";
      // Voice: a normal <select> PLUS a ▶ test button, and its option list is repopulated when the TTS provider
      // changes (wireVoice, below). Selecting + saving applies the voice on reconnect, same as tapping the orb.
      if (k.key === "assistant_voice") {
        return `<div class="knob"><label>${esc(k.label)}</label><div class="voicerow"><select id="cfg_assistant_voice">${optsHTML(k.options, k.value)}</select><button type="button" id="cfg_voicetest" class="voicetest">${PLAY_ICON}<span>test</span></button></div>${note}</div>`;
      }
      if (free.has(k.key)) {
        const dl = "cfg_" + k.key;
        const opts = k.options.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
        return `<div class="knob"><label>${esc(k.label)}</label><input id="cfg_${k.key}" list="${dl}" value="${esc(k.value)}"/><datalist id="${dl}">${opts}</datalist>${note}</div>`;
      }
      return `<div class="knob"><label>${esc(k.label)}</label><select id="cfg_${k.key}">${optsHTML(k.options, k.value)}</select>${note}</div>`;
    }).join("");
    wireVoice();
  }

  // Wire the voice picker after (re)rendering: repopulate voices when the provider changes, and preview on ▶ test.
  function wireVoice() {
    const prov = document.getElementById("cfg_tts_provider");
    const vsel = document.getElementById("cfg_assistant_voice");
    const btn = document.getElementById("cfg_voicetest");
    if (!vsel) return;
    const vbp = (cfg && cfg.voices_by_provider) || {};
    if (prov) prov.onchange = () => {
      const list = vbp[prov.value] || [];
      vsel.innerHTML = optsHTML(list, list[0] && list[0].value);
    };
    if (btn) btn.onclick = async () => {
      const provider = prov ? prov.value : "";
      const voice = vsel.value;
      if (!voice) return;
      const label = btn.innerHTML; btn.disabled = true; btn.innerHTML = PLAY_ICON + "<span>…</span>"; msgEl.textContent = "";
      try {
        const blob = await api.testVoice(provider, voice);
        const url = URL.createObjectURL(blob);
        const a = new Audio(url); a.onended = () => URL.revokeObjectURL(url);
        await a.play();
      } catch (e) {
        msgEl.textContent = "✗ couldn't play the voice (" + (e && e.message ? e.message : "error") + ")";
      } finally { btn.disabled = false; btn.innerHTML = label; }
    };
  }

  async function open() {
    msgEl.textContent = ""; bodyEl.innerHTML = '<p class="hint">Loading…</p>';
    try { cfg = await api.getSettings(); render(); } catch (e) { bodyEl.innerHTML = '<p class="hint">Couldn\'t load /api/settings</p>'; }
  }
  const close = () => setOpen(false);

  async function save() {
    const payload = {}; cfg.knobs.forEach(k => { const el = document.getElementById("cfg_" + k.key); if (el) payload[k.key] = el.value; });
    msgEl.textContent = "Saving…";
    try {
      const r = await api.saveSettings(payload);
      msgEl.textContent = r.ok ? ("✓ " + r.note) : "no changes";
      if (r.ok && r.needs_reconnect) {
        // Sync the voice picker with the index the server just chose (single source of truth) BEFORE reconnecting,
        // so start() re-applies the NEW voice instead of clobbering it with the stale orb index.
        try { await session.loadVoices(); } catch (_) {}
        if (session.isActive()) { msgEl.textContent = "✓ applying… reconnecting"; await session.reconnect(); msgEl.textContent = "✓ applied"; }
        else { msgEl.textContent = "✓ saved · applied on connect"; }
      }
    } catch (e) { msgEl.textContent = "✗ error saving"; }
  }

  ovl = h("div", { id: "cfgOvl", class: () => "ovl" + (isOpen() ? " on" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cfgm" },
      h("div", { class: "mh" }, h("h3", {}, raw(GEAR_ICON), "Settings"), h("button", { class: "x", onClick: close }, "close")),
      h("p", { class: "hint", html: 'Voice provider, language, STT/TTS. The <b>voice</b> is changed by tapping the orb. Changes → reconnect.' }),
      h("div", { id: "cfgBody", ref: el => (bodyEl = el) }, h("p", { class: "hint" }, "Loading…")),
      h("div", { class: "mfoot" }, h("button", { id: "cfgSave", onClick: save }, "Save"), h("span", { class: "msg", ref: el => (msgEl = el) })),
    ),
  );

  let wasOpen = false;
  createEffect(() => { const o = isOpen(); if (o && !wasOpen) open(); wasOpen = o; });   // fetch settings on each open
  return ovl;
}

// ConnectorWizard.js — the ⚙ «Conectores» tab: a LIST, and ONE connector at a time behind a breadcrumb.
//
// Before this, the tab rendered every connector's form at once (WhatsApp, Telegram, Email, … all open), so the
// operator who clicked «Conectar» on ONE row of the chat column's connector catalog landed in a wall of forms
// and had to find his own. Now the catalog names the connector it was clicked on (`store.configConnector`), the
// tab opens on that connector alone, and the setup is a guide: the steps that happen OUTSIDE (a Google Cloud
// project, an app password, an api_id) one at a time, then the form, then the live state (the WhatsApp QR the
// tab used to never draw). The forms themselves are still ConfigPanel's (`connectorForm`), so every write
// keeps going through the endpoints it always used.
//
// The guides are DATA (`guideSteps`) — the same steps a widget's own connector screen can import instead of
// writing its own copy (the agenda's Google Calendar wizard is the first candidate).

/** The callback each OAuth connector serves — what the operator registers as the redirect URI. Mirrors the
 * `CALLBACK_PATH` of each `connectors/<family>/oauth.py`. */
export const CALLBACKS = {
  gdrive: "/api/cloudfiles/callback", onedrive: "/api/cloudfiles/callback",
  "google-photos": "/api/photos/callback", youtube: "/api/video/callback",
  google: "/api/calendar/callback", "google-contacts": "/api/contacts/callback",
};

// The Google API each Google-backed connector needs switched on (product names, never translated).
const GOOGLE_API = {
  gdrive: "Google Drive API", "google-photos": "Photos Picker API", youtube: "YouTube Data API v3",
  google: "Google Calendar API", "google-contacts": "People API",
};

/** Google is ONE connector: one OAuth app, one account, several services (each with its OWN consent, because
 * each runs its own flow and token store — linking the calendar grants nothing to Drive). The section shows a
 * single «Google» entry; any of these ids — from a card's plug, the catalog or the voice — opens it with that
 * service picked out. Email is not here on purpose: Gmail is IMAP with an app password, its own connector. */
export const GOOGLE_SERVICES = ["google", "google-contacts", "gdrive", "google-photos", "youtube"];
export const GOOGLE = "google-account";
/** The id the section focuses for a requested one, and the service to pick out inside it. */
export const focusOf = id => GOOGLE_SERVICES.includes(id) ? { focus: GOOGLE, service: id } : { focus: id || null, service: "" };

/** The connector list with the Google services folded into the account: one row, `services` inside. */
export function groupGoogle(cs) {
  const acct = cs.find(c => c.id === GOOGLE);
  const services = GOOGLE_SERVICES.map(id => cs.find(c => c.id === id)).filter(Boolean);
  if (!acct && !services.length) return cs;
  const base = acct || { id: GOOGLE, config: {} };
  const group = { ...base, label: "Google", family: "google", services,
                  connected: services.some(s => s.connected), app: !!(base.config || {}).app_configured };
  return [group, ...cs.filter(c => c.id !== GOOGLE && !GOOGLE_SERVICES.includes(c.id))];
}

const LINKS = {
  telegram: "https://my.telegram.org/apps",
  email: "https://myaccount.google.com/apppasswords",
  spotify: "https://www.spotify.com/account/",
  gcloud_lib: "https://console.cloud.google.com/apis/library",
  gcloud_cred: "https://console.cloud.google.com/apis/credentials",
  entra: "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
};

/** The steps BEFORE the form, for one connector: [{key, link?, code?, params?}]. Empty = the form is step one.
 * The Google account whose app is already registered skips the Cloud Console half: only the consents are left. */
export function guideSteps(c) {
  const id = String((c && c.id) || ""), cc = (c && c.config) || {};
  const uri = CALLBACKS[id] ? (location.origin + CALLBACKS[id]) : "";
  if (id === "whatsapp") return [{ key: "whatsapp.1" }];
  // The messaging card's own three steps (sign in → create the app with these exact values → paste), moved here.
  // With Zaelar's own Telegram app on this install, Telegram is WhatsApp's flow: the form step is the QR.
  if (id === "telegram") return cc.app_shipped ? [] : [{ key: "telegram.1", link: LINKS.telegram }, { key: "telegram.2", link: LINKS.telegram }];
  if (id === "email") return [{ key: "email.1", link: LINKS.email }];
  if (id === "spotify") return [{ key: "spotify.1", link: LINKS.spotify }];
  if (id === "onedrive") return cc.app_configured ? [] : [{ key: "onedrive.1", link: LINKS.entra, code: uri }, { key: "onedrive.2" }];
  if (id === GOOGLE) {
    // The shipped (or already registered) app leaves only the consents: the services step is the first.
    if (c.app || cc.app_configured) return [];
    const apis = [...new Set((c.services || []).map(x => GOOGLE_API[x.id]).filter(Boolean))].join(", ");
    return [{ key: "google.1", link: LINKS.gcloud_lib, params: { api: apis } },
            { key: "google.2", link: LINKS.gcloud_cred, code: (cc.redirect_uris || []).join("\n") }];
  }
  if (id === "architect") return [{ key: "architect.1" }];
  if (id === "meshkore") return [{ key: "meshkore.1" }];
  return [];
}

/** The first letter of the service as its mark. The catalog ships no logos (and third-party marks carry their
 * own usage terms), so the tile is ours: one letter, the accent at low alpha, the same shape in the list and
 * on the connector's page — what makes a row and its page read as the same thing. */
const avatar = (label, esc, small) =>
  `<span class="cf-cx-avatar${small ? " cf-cx-avatar--sm" : ""}" aria-hidden="true">${esc(String(label || "?").trim().charAt(0).toUpperCase())}</span>`;

/** The tab with nothing chosen: per family, a heading and a ROW of cards — one card per connector (mark, name,
 * state, action), left-aligned and wrapping. Nothing is open yet. The operator (2026-10-23): «ordenados por filas:
 * Google este; Mensajería y los tres iconos por separado en cajitas; Música, dos iconos… todo pegado a la
 * izquierda». It was one full-width stacked list per family, centred in the panel. */
export function connectorList(cs, fams, { t, esc, badge }) {
  const rows = fams.map(([f, title]) => {
    const items = cs.filter(c => c.family === f);
    if (!items.length) return "";
    return `<h3 class="cf-fam">${esc(title)}</h3><div class="cf-cx-grid">${items.map(c =>
      `<button type="button" class="cf-cx-card" data-cx="${esc(c.id)}"><span class="cf-cx-card-top">${avatar(c.label, esc, true)}` +
      `<span class="cf-cx-name">${esc(c.label)}</span></span><span class="cf-cx-card-state">${badge(c)}</span>` +
      `<span class="cf-cx-go">${esc(c.connected ? t("config.cxw.manage") : t("config.cxw.configure"))} ›</span></button>`).join("")}</div>`;
  }).join("");
  // Titled like every other page of the panel (2026-10-25: the list read as «suelta» without one).
  return `<header class="cf-panel-head cf-cx-head"><h4>${esc(t("config.tab.conectores"))}</h4><p>${esc(t("config.cxw.choose"))}</p></header>${rows}`;
}

// ── The building blocks every connector page is made of (2026-10-25 pass) ──────────────────────────────────
// Operator: «necesita un diseño estructurado, alineado, con subsecciones, minimalista… alineado a la izquierda».
// So every connector, whatever it asks for, is laid out from the SAME four pieces, all on the left edge:
// a FIELD (label above its control, one reading width), a ROW OF ACTIONS (primary first), a SUBSECTION
// (small heading + its content) and the page FOOT (Volver · Cerrar). A form never right-floats its button,
// and nothing is centred — the QR included.
const field = (esc, label, ctl, hint) =>
  `<label class="cf-field"><span class="cf-field-l">${esc(label)}</span>${ctl}${hint ? `<span class="cf-field-h">${hint}</span>` : ""}</label>`;
const acts = (...btns) => `<div class="cf-acts">${btns.filter(Boolean).join("")}</div>`;
const sub = (esc, title, inner) => `<div class="cf-sub">${title ? `<h5 class="cf-sub-h">${esc(title)}</h5>` : ""}${inner}</div>`;
const opt = (esc, list, sel) => list.map(o => `<option value="${esc(o.value)}"${o.value === sel ? " selected" : ""}>${esc(o.label)}</option>`).join("");
const tierSelect = (esc, cc, idAttr) => (cc.tiers || []).length > 1
  ? `<select id="${idAttr}">${cc.tiers.map(x => `<option value="${esc(x.id)}"${x.id === cc.default_tier ? " selected" : ""}>${esc(x.label)}</option>`).join("")}</select>` : "";

// ONE Google account, one consent per service: each row says which card it feeds and connects on its own.
const G_ACT = { google: "calendar-connect", "google-contacts": "contacts-connect", gdrive: "cloudfiles-connect",
                "google-photos": "photos-connect", youtube: "video-connect" };

function googleForm(c, famTitle, { t, esc, badge, service }) {
  const app = c.app ? "" : sub(esc, t("config.cxw.google_app"), `<div class="cf-fields">` +
    field(esc, "client_id", `<input id="cx_g_id" type="text" autocomplete="off" placeholder="${esc(t("config.cx.paste_client_id"))}"/>`) +
    field(esc, "client_secret", `<input id="cx_g_sec" type="password" autocomplete="off" placeholder="${esc(t("config.cx.only_if_asked"))}"/>`) + `</div>`);
  const rows = (c.services || []).map(sv => {
    const id = esc(sv.id), cc = sv.config || {};
    const tiers = !sv.connected && sv.id === "gdrive" ? tierSelect(esc, cc, `cx_cf_tier_${id}`) : "";
    const btn = sv.connected
      ? `<button type="button" class="cf-btn cf-btn-ghost cf-cx-act" data-act="disconnect" data-id="${id}" data-fam="${esc(sv.family || "")}">${esc(t("config.cx.disconnect_btn"))}</button>`
      : `<button type="button" class="cf-btn cf-cx-act" data-act="${G_ACT[sv.id]}" data-id="${id}">${esc(t("config.cx.connect"))}</button>`;
    return `<div class="cf-gsvc${sv.id === service ? " on" : ""}"><span class="cf-gsvc-name">${esc(sv.label)}` +
      `<small>${esc(famTitle(sv.family))}</small></span><span class="cf-gsvc-act">${badge(sv)}${tiers}${btn}</span></div>`;
  }).join("");
  return app + `<div class="cf-gsvcs">${rows}</div>`;
}

/** The blocked consent, offered where the operator is looking: under the connector (or Google service) he pressed. */
function consentLink(c, { t, esc, consent }) {
  if (!consent || !(consent.id === c.id || (c.services || []).some(x => x.id === consent.id))) return "";
  return `<div class="cf-wiz-blocked" role="status"><p class="cf-wiz-text">${esc(t("config.cx.popup_blocked"))}</p>` +
    `<a class="cf-btn cf-consent-link" href="${esc(consent.url)}" target="_blank" rel="noopener">${esc(t("config.cx.open_consent"))} ↗</a></div>`;
}

/** The connector's own controls — the last step of its guide. Moved out of ConfigPanel (2026-10-25) so the whole
 * page is one module that can be rendered and looked at without the app; ConfigPanel still owns every WRITE
 * (`.cf-cx-act` → `cxAct`, the same element ids it always read). `ui`: {t, esc, badge, service, consent}. */
export function connectorForm(c, famTitle, ui) {
  const { t, esc } = ui;
  const id = esc(c.id), fam = esc(c.family || ""), cc = c.config || {};
  const L = k => esc(t(k));
  let box = "";
  if (c.id === GOOGLE) {
    box = googleForm(c, famTitle, ui);
  } else if (c.connected) {
    const revoke = c.family === "infra" ? t("config.cx.revoke") : t("config.cx.disconnect_btn");
    box = `<button type="button" class="cf-btn cf-btn-ghost cf-cx-act" data-act="disconnect" data-id="${id}" data-fam="${fam}">${esc(revoke)}</button>`;
  } else if (c.id === "whatsapp" || c.id === "telegram") {
    // A code on screen IS the form now: the button that asked for it and the sentence that explained it step
    // aside, and the QR block (liveState) carries the how-to beside the code — said once, not twice.
    if (qrOf(c)) return consentLink(c, ui);
    const own = c.id === "telegram" && !cc.app_shipped;
    const intro = c.id === "telegram" ? (own ? t("config.cxw.telegram.form_tip") : t("config.cxw.telegram.shipped")) : t("config.cxw.whatsapp.form");
    box = `<p class="cf-wiz-text">${esc(intro)}</p>` +
      (own ? `<div class="cf-fields">` +
        field(esc, "api_id", `<input id="cx_tg_api_id" type="text" inputmode="numeric" autocomplete="off" placeholder="12345678"/>`) +
        field(esc, "api_hash", `<input id="cx_tg_api_hash" type="text" autocomplete="off" placeholder="${L("config.cx.tg_placeholder")}"/>`) + `</div>` : "") +
      acts(`<button type="button" class="cf-btn cf-cx-act" data-act="connect" data-id="${id}">${L("config.cx.connect_qr")}</button>`);
  } else if (c.id === "email") {
    // WHERE to get the app password follows the provider picked; the servers appear only for «other».
    const P = { gmail: "https://myaccount.google.com/apppasswords", outlook: "https://account.live.com/proofs/AppPassword",
                icloud: "https://appleid.apple.com/account/manage" };
    const links = Object.entries(P).map(([k, u]) =>
      `<a class="cf-em-link" data-em="${k}" href="${u}" target="_blank" rel="noopener"${k === "gmail" ? "" : " hidden"}>${L("config.cx.em_link_" + k)} ↗</a>`).join("");
    const provs = [{ value: "gmail", label: "Gmail" }, { value: "outlook", label: "Outlook" }, { value: "icloud", label: "iCloud" },
                   { value: "other", label: t("config.cx.em_other") }];
    box = `<div class="cf-fields">` +
      field(esc, t("config.row.provider"), `<select id="cx_em_provider">${opt(esc, provs, "gmail")}</select>`, links) +
      field(esc, t("config.cx.email_label"), `<input id="cx_em_address" type="email" autocomplete="off" placeholder="${L("config.cx.email_placeholder")}"/>`) +
      field(esc, t("config.cx.app_password"), `<input id="cx_em_pass" type="password" autocomplete="off" placeholder="${L("config.cx.app_password_ph")}"/>`) +
      `<div class="cf-fields cf-em-other" hidden>` +
      field(esc, "IMAP", `<input id="cx_em_imap" type="text" autocomplete="off" placeholder="imap.tudominio.com"/>`) +
      field(esc, "SMTP", `<input id="cx_em_smtp" type="text" autocomplete="off" placeholder="smtp.tudominio.com"/>`) + `</div></div>` +
      acts(`<button type="button" class="cf-btn cf-cx-act" data-act="connect" data-id="email">${L("config.cx.connect")}</button>`);
  } else if (c.id === "spotify") {
    // Your own app's Client ID is optional and ADVANCED: folded away unless the shipped one is missing.
    const own = `<details class="cf-adv"${cc.can_connect ? "" : " open"}><summary>${L("config.cx.sp_own")}</summary><div class="cf-adv-body">` +
      `<p class="cf-wiz-text">${L("config.cx.sp_own_steps")}</p>` +
      `<div class="cf-wiz-code"><code>${esc(cc.redirect_uri || (location.origin + "/api/spotify/callback"))}</code></div>` +
      field(esc, "Client ID", `<input id="cx_sp_cid" type="text" autocomplete="off" placeholder="${cc.own_client_id_set ? L("config.key.ph_saved") : L("config.cx.sp_id_ph")}"/>`) +
      `</div></details>`;
    box = acts(`<button type="button" class="cf-btn cf-cx-act" data-act="connect" data-id="spotify">${L("config.cx.connect_spotify")}</button>`) + own;
  } else if (c.id === "onedrive") {
    const tiers = tierSelect(esc, cc, `cx_cf_tier_${id}`);
    box = `<div class="cf-fields">` +
      field(esc, "client_id", `<input id="cx_cf_id_${id}" type="text" autocomplete="off" placeholder="${cc.app_configured ? L("config.key.ph_saved") : L("config.cx.paste_client_id")}"/>`) +
      field(esc, "client_secret", `<input id="cx_cf_sec_${id}" type="password" autocomplete="off" placeholder="${L("config.cx.only_if_asked")}"/>`) +
      (tiers ? field(esc, t("config.cx.permission"), tiers) : "") + `</div>` +
      acts(`<button type="button" class="cf-btn cf-cx-act" data-act="cloudfiles-connect" data-id="${id}">${L("config.cx.connect")}</button>`);
  } else if (c.id === "architect") {
    box = `<div class="cf-fields">` +
      field(esc, t("config.cx.daemon_token"), `<input id="cx_arch_token" type="password" autocomplete="off" placeholder="${cc.token_set ? L("config.key.ph_saved") : L("config.cx.paste_token")}"/>`) +
      field(esc, t("config.cx.url_optional"), `<input id="cx_arch_url" type="text" autocomplete="off" placeholder="https://127.0.0.1:5573"/>`) + `</div>` +
      acts(`<button type="button" class="cf-btn cf-cx-act" data-act="architect-save" data-id="architect">${L("config.cx.save_token")}</button>`);
  } else if (c.id === "meshkore") {
    const clusters = (c.clusters || []).map(cl =>
      `<div class="cf-gsvc"><span class="cf-gsvc-name">${esc(cl.name)}</span><span class="cf-gsvc-act">${cl.connected ? `<span class="cf-badge cf-ok">${L("config.cx.connected")}</span>` : ""}` +
      `<button type="button" class="cf-btn cf-btn-ghost cf-cx-act" data-act="mesh-remove" data-id="meshkore" data-name="${esc(cl.name)}">${L("config.cx.revoke")}</button></span></div>`).join("");
    box = (clusters ? `<div class="cf-gsvcs">${clusters}</div>` : "") + sub(esc, t("config.cx.add_cluster"), `<div class="cf-fields">` +
      field(esc, t("config.cx.mk_name"), `<input id="cx_mk_name" type="text" autocomplete="off" placeholder="${L("config.cx.mk_name_ph")}"/>`) +
      field(esc, "cluster_id", `<input id="cx_mk_cid" type="text" autocomplete="off"/>`) +
      field(esc, "token", `<input id="cx_mk_token" type="password" autocomplete="off"/>`) +
      field(esc, t("config.cx.mk_handle"), `<input id="cx_mk_handle" type="text" autocomplete="off" placeholder="zaelar"/>`) + `</div>` +
      acts(`<button type="button" class="cf-btn cf-cx-act" data-act="mesh-add" data-id="meshkore">${L("config.cx.add_cluster")}</button>`));
  }
  return box + consentLink(c, ui);
}

/** ONE connector: breadcrumb, a hero (mark, name, state, one line), then the guide as a VERTICAL stepper whose
 * open step carries its text, its resources (a link, a value to copy), its form and its Next/Back — and under it
 * all, the page foot: «Volver» (to whoever opened it, `returnTo`, named when known) and «Cerrar», on EVERY step,
 * so leaving ⚙ never depends on spotting the ✕ at the top of the screen. A connector with nothing to guide is the
 * same page without the stepper: one subsection under its title. Every hook the panel wires is kept:
 * data-cx-back, data-cx-step, data-cx-done, data-cx-close, data-copy, .cf-cx-act. */
export function connectorWizard(c, step, form, famTitle, { t, esc, badge, returnTo = null }) {
  // Google's last step is its SERVICES, so its guide is shown whenever the app is missing, connected or not.
  const guide = c.connected && c.id !== GOOGLE ? [] : guideSteps(c);
  const total = guide.length + 1;
  const at = Math.max(0, Math.min(step | 0, total - 1));
  // «Google › Google» said nothing twice: the family crumb is shown only when it adds a word.
  const fam = famTitle && famTitle !== c.label ? `<span class="cf-crumb-sep">›</span><span>${esc(famTitle)}</span>` : "";
  const crumb = `<nav class="cf-crumb" aria-label="breadcrumb"><button type="button" class="cf-crumb-back" data-cx-back="1">← ${esc(t("config.cxw.back"))}</button>` +
    `${fam}<span class="cf-crumb-sep">›</span><b>${esc(c.label)}</b></nav>`;
  const line = c.warning ? t(`config.cx.warn.${c.warning}_detail`) : c.detail && c.status !== "error" ? c.detail : (c.id === GOOGLE ? t("config.cxw.google_services") : "");
  const head = `<header class="cf-cx-hero">${avatar(c.label, esc, false)}<div class="cf-cx-hero-text"><h4>${esc(c.label)} ${badge(c)}</h4>` +
    `${line ? `<p>${esc(line)}</p>` : ""}</div></header>`;
  const titles = guide.map(g => t(`config.cxw.${g.key}.title`, g.params))
    .concat([c.id === GOOGLE ? t("config.cxw.services_title")
              : c.connected ? t("config.cxw.connected_title") : t("config.cxw.final_title")]);
  let body;
  if (at < guide.length) {
    const g = guide[at];
    body = `<p class="cf-wiz-text">${esc(t(`config.cxw.${g.key}.body`, g.params))}</p>` +
      (g.code ? `<div class="cf-wiz-code"><code>${esc(g.code)}</code><button type="button" class="cf-btn cf-btn-ghost cf-wiz-copy" data-copy="${esc(g.code)}">${esc(t("config.cxw.copy"))}</button></div>` : "") +
      (g.link ? acts(`<a class="cf-btn cf-btn-ghost cf-wiz-link" href="${esc(g.link)}" target="_blank" rel="noopener">${esc(t("config.cxw.open_link", { site: new URL(g.link).host }))} ↗</a>`) : "");
  } else {
    // Connected (and not Google): ONE status card that carries its own action (Disconnect) inside it — the
    // operator: «los botones de disconnect van dentro de los box de estado».
    body = c.connected && c.id !== GOOGLE
      ? `<div class="cf-wiz-done" role="status"><span class="cf-wiz-done-mark" aria-hidden="true">✓</span><div class="cf-wiz-done-text"><b>${esc(t("config.cxw.connected_title"))}</b>` +
        `<p>${esc(t("config.cxw.connected_body", { label: c.label }))}</p></div><div class="cf-wiz-done-act">${form}</div></div>`
      : `<div class="cf-wiz-form">${form}</div>` + liveState(c, { t, esc });
  }
  // Next first (the left edge is where the eye starts), Back beside it, the count after them. The LAST step has
  // its own action (Connect, Disconnect…) and no nav: a lone «Atrás» under «Conectar» read as a second form
  // button, and every earlier step is one click away on the rail, ticked.
  const nav = total > 1 && at < total - 1 ? `<div class="cf-acts cf-wiz-nav">` +
    `<button type="button" class="cf-btn" data-cx-step="${at + 1}">${esc(t("config.cxw.next"))}</button>` +
    (at > 0 ? `<button type="button" class="cf-btn cf-btn-ghost" data-cx-step="${at - 1}">${esc(t("config.cxw.prev"))}</button>` : "") +
    `<span class="cf-wiz-count">${esc(t("config.cxw.step", { n: at + 1, total }))}</span></div>` : "";
  // The vertical stepper: every title is a step; the open one carries the body and the nav underneath it.
  const steps = total > 1 ? `<ol class="cf-wiz-steps">${titles.map((ti, i) =>
    `<li class="cf-wiz-step${i === at ? " on" : ""}${i < at ? " done" : ""}"><button type="button" class="cf-wiz-step-h" data-cx-step="${i}">` +
    `<span class="cf-wiz-n">${i < at ? "✓" : i + 1}</span><span class="cf-wiz-t">${esc(ti)}</span></button>` +
    (i === at ? `<div class="cf-wiz-body">${body}${nav}</div>` : "") + `</li>`).join("")}</ol>`
    : `<div class="cf-wiz-body cf-wiz-body--solo">${body}</div>`;
  const backLabel = returnTo && returnTo.from ? t("config.cxw.back_to", { name: returnTo.from }) : t("config.cxw.done_back");
  const foot = `<footer class="cf-acts cf-wiz-foot"><button type="button" class="cf-btn cf-btn-ghost" data-cx-done="1">${esc(backLabel)}</button>` +
    `<button type="button" class="cf-btn cf-btn-ghost" data-cx-close="1">${esc(t("config.cxw.close"))}</button></footer>`;
  return `${crumb}<section class="cf-wiz">${head}${steps}${foot}</section>`;
}

const qrOf = c => !c.connected && typeof c.qr === "string" && c.qr.startsWith("data:image/") ? c.qr : "";

/** What is happening NOW on the last step: the QR to scan (WhatsApp/Telegram), a wait, or the error. The code sits
 * on the LEFT with its how-to beside it (under it on a phone) — never centred in a void. */
function liveState(c, { t, esc }) {
  if (c.connected) return "";
  const qr = qrOf(c);
  if (qr) {
    const cap = c.id === "telegram" ? "config.cxw.qr_scan_telegram" : "config.cxw.qr_scan_whatsapp";
    return `<div class="cf-wiz-qr"><img alt="QR" src="${esc(qr)}"/><div class="cf-wiz-qr-text"><p class="cf-wiz-text">${esc(t(cap))}</p>` +
      `<p class="cf-wiz-note">${esc(t("config.cxw.qr_rotates"))}</p></div></div>`;
  }
  if (c.status === "connecting" || c.status === "starting") return `<p class="cf-wiz-wait">${esc(t("config.cxw.qr_wait"))}</p>`;
  // A failure says WHY, in the card the person is looking at: a wait that never ends is what an unexplained
  // failure looked like before (the bridge could not start, the card kept «Preparando…»).
  if (c.status === "error") return `<p class="cf-wiz-err">${esc(t("config.cxw.failed"))}${c.detail ? ` — ${esc(c.detail)}` : ""}</p>`;
  return "";
}

/** Does this connector's state still move on its own (a QR to appear, a scan to land)? Then the tab polls. */
export const isSettling = c => !!c && !c.connected && (c.status === "connecting" || c.status === "starting");

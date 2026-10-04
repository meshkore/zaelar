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
  if (id === "telegram") return [{ key: "telegram.1", link: LINKS.telegram }];
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

/** The tab with nothing chosen: one compact row per connector, grouped by family. Nothing is open yet. */
export function connectorList(cs, fams, { t, esc, badge }) {
  const rows = fams.map(([f, title]) => {
    const items = cs.filter(c => c.family === f);
    if (!items.length) return "";
    return `<h3 class="cf-fam">${esc(title)}</h3><div class="cf-cx-list">${items.map(c =>
      `<button type="button" class="cf-cx-row" data-cx="${esc(c.id)}">${avatar(c.label, esc, true)}<span class="cf-cx-name">${esc(c.label)}</span>${badge(c)}` +
      `<span class="cf-cx-go">${esc(c.connected ? t("config.cxw.manage") : t("config.cxw.configure"))} ›</span></button>`).join("")}</div>`;
  }).join("");
  return `<p class="cf-cx-intro">${esc(t("config.cxw.choose"))}</p>${rows}`;
}

/** ONE connector: breadcrumb, a hero (mark, name, state, one line), then the guide as a VERTICAL stepper whose
 * current step carries its own text, link, code and Back/Next — the shape of a first-rate setup page (one column,
 * one thing at a time, no box inside a box). `form` is the connector's own form (ConfigPanel's), shown flat on the
 * last step; `step` past the guide clamps to it. The 2026-10-04 redesign (operator: «el marco exterior, la
 * ubicación del botón…») kept every hook the panel wires: data-cx-back, data-cx-step, data-copy, .cf-cx-act. */
export function connectorWizard(c, step, form, famTitle, { t, esc, badge }) {
  // Google's last step is its SERVICES, so its guide is shown whenever the app is missing, connected or not.
  const guide = c.connected && c.id !== GOOGLE ? [] : guideSteps(c);
  const total = guide.length + 1;
  const at = Math.max(0, Math.min(step | 0, total - 1));
  // «Google › Google» said nothing twice: the family crumb is shown only when it adds a word.
  const fam = famTitle && famTitle !== c.label ? `<span class="cf-crumb-sep">›</span><span>${esc(famTitle)}</span>` : "";
  const crumb = `<nav class="cf-crumb" aria-label="breadcrumb"><button type="button" class="cf-crumb-back" data-cx-back="1">← ${esc(t("config.cxw.back"))}</button>` +
    `${fam}<span class="cf-crumb-sep">›</span><b>${esc(c.label)}</b></nav>`;
  const line = c.detail || (c.id === GOOGLE ? t("config.cxw.google_services") : "");
  const head = `<header class="cf-panel-head cf-cx-hero">${avatar(c.label, esc, false)}<div class="cf-cx-hero-text"><h4>${esc(c.label)} ${badge(c)}</h4>` +
    `${line ? `<p>${esc(line)}</p>` : ""}</div></header>`;
  const titles = guide.map(g => t(`config.cxw.${g.key}.title`, g.params))
    .concat([c.id === GOOGLE ? t("config.cxw.services_title")
              : c.connected ? t("config.cxw.connected_title") : t("config.cxw.final_title")]);
  let body;
  if (at < guide.length) {
    const g = guide[at];
    body = `<p class="cf-wiz-text">${esc(t(`config.cxw.${g.key}.body`, g.params))}</p>` +
      (g.code ? `<div class="cf-wiz-code"><code>${esc(g.code)}</code><button type="button" class="cf-btn cf-btn-ghost cf-wiz-copy" data-copy="${esc(g.code)}">${esc(t("config.cxw.copy"))}</button></div>` : "") +
      (g.link ? `<p class="cf-wiz-go"><a class="cf-btn cf-btn-ghost cf-wiz-link" href="${esc(g.link)}" target="_blank" rel="noopener">${esc(t("config.cxw.open_link", { site: new URL(g.link).host }))} ↗</a></p>` : "");
  } else {
    // Connected (and not Google): say so in one card, then the form — which is the quiet way out (Disconnect).
    const done = c.connected && c.id !== GOOGLE
      ? `<div class="cf-wiz-done" role="status"><span class="cf-wiz-done-mark" aria-hidden="true">✓</span><div><b>${esc(t("config.cxw.connected_title"))}</b>` +
        `<p>${esc(t("config.cxw.connected_body", { label: c.label }))}</p></div></div>` : "";
    body = done + `<div class="cf-wiz-form${c.connected && c.id !== GOOGLE ? " cf-wiz-form--quiet" : ""}">${form}</div>` + liveState(c, { t, esc });
  }
  const nav = total > 1 ? `<div class="cf-wiz-nav">${at > 0 ? `<button type="button" class="cf-btn cf-btn-ghost" data-cx-step="${at - 1}">${esc(t("config.cxw.prev"))}</button>` : "<span></span>"}` +
    (at < total - 1 ? `<span class="cf-wiz-count">${esc(t("config.cxw.step", { n: at + 1, total }))}</span><button type="button" class="cf-btn" data-cx-step="${at + 1}">${esc(t("config.cxw.next"))}</button>` : "") + `</div>` : "";
  // The vertical stepper: every title is a step; the current one carries the body and the nav underneath it.
  const steps = total > 1 ? `<ol class="cf-wiz-steps">${titles.map((ti, i) =>
    `<li class="cf-wiz-step${i === at ? " on" : ""}${i < at ? " done" : ""}"><button type="button" class="cf-wiz-step-h" data-cx-step="${i}">` +
    `<span class="cf-wiz-n">${i < at ? "✓" : i + 1}</span><span class="cf-wiz-t">${esc(ti)}</span></button>` +
    (i === at ? `<div class="cf-wiz-body">${body}${nav}</div>` : "") + `</li>`).join("")}</ol>`
    : `<div class="cf-wiz-body">${body}</div>`;
  return `${crumb}<section class="cf-panel-sec cf-wiz">${head}${steps}</section>`;
}

/** What is happening NOW on the last step: the QR to scan (WhatsApp/Telegram), a wait, or the error. */
function liveState(c, { t, esc }) {
  if (c.connected) return "";
  const qr = typeof c.qr === "string" && c.qr.startsWith("data:image/") ? c.qr : "";
  if (qr) {
    const cap = c.id === "telegram" ? "config.cxw.qr_scan_telegram" : "config.cxw.qr_scan_whatsapp";
    return `<div class="cf-wiz-qr"><img alt="QR" src="${esc(qr)}"/><p>${esc(t(cap))}</p></div>`;
  }
  if (c.status === "connecting" || c.status === "starting") return `<p class="cf-wiz-wait">${esc(t("config.cxw.qr_wait"))}</p>`;
  return "";
}

/** Does this connector's state still move on its own (a QR to appear, a scan to land)? Then the tab polls. */
export const isSettling = c => !!c && !c.connected && (c.status === "connecting" || c.status === "starting");

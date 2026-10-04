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

const LINKS = {
  telegram: "https://my.telegram.org/apps",
  email: "https://myaccount.google.com/apppasswords",
  spotify: "https://www.spotify.com/account/",
  gcloud_lib: "https://console.cloud.google.com/apis/library",
  gcloud_cred: "https://console.cloud.google.com/apis/credentials",
  entra: "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
};

/** The steps BEFORE the form, for one connector: [{key, link?, code?, params?}]. Empty = the form is step one.
 * A Google connector whose app is already registered skips the Cloud Console half: only consent is left. */
export function guideSteps(c) {
  const id = String((c && c.id) || ""), cc = (c && c.config) || {};
  const uri = CALLBACKS[id] ? (location.origin + CALLBACKS[id]) : "";
  if (id === "whatsapp") return [{ key: "whatsapp.1" }];
  if (id === "telegram") return [{ key: "telegram.1", link: LINKS.telegram }];
  if (id === "email") return [{ key: "email.1", link: LINKS.email }];
  if (id === "spotify") return [{ key: "spotify.1", link: LINKS.spotify }];
  if (GOOGLE_API[id]) {
    if (cc.app_configured) return [];
    return [{ key: "google.1", link: LINKS.gcloud_lib, params: { api: GOOGLE_API[id] } },
            { key: "google.2", link: LINKS.gcloud_cred, code: uri }];
  }
  if (id === "onedrive") return cc.app_configured ? [] : [{ key: "onedrive.1", link: LINKS.entra, code: uri }, { key: "onedrive.2" }];
  if (id === "google-account") return [{ key: "google_account.1", link: LINKS.gcloud_cred }];
  if (id === "architect") return [{ key: "architect.1" }];
  if (id === "meshkore") return [{ key: "meshkore.1" }];
  return [];
}

/** The tab with nothing chosen: one compact row per connector, grouped by family. Nothing is open yet. */
export function connectorList(cs, fams, { t, esc, badge }) {
  const rows = fams.map(([f, title]) => {
    const items = cs.filter(c => c.family === f);
    if (!items.length) return "";
    return `<h3 class="cf-fam">${esc(title)}</h3><div class="cf-cx-list">${items.map(c =>
      `<button type="button" class="cf-cx-row" data-cx="${esc(c.id)}"><span class="cf-cx-name">${esc(c.label)}</span>${badge(c)}` +
      `<span class="cf-cx-go">${esc(c.connected ? t("config.cxw.manage") : t("config.cxw.configure"))} ›</span></button>`).join("")}</div>`;
  }).join("");
  return `<p class="cf-cx-intro">${esc(t("config.cxw.choose"))}</p>${rows}`;
}

/** ONE connector: breadcrumb, stepper, the current step, and a way back at every step. `form` is the
 * connector's own form (ConfigPanel's), shown on the last step; `step` past the guide clamps to it. */
export function connectorWizard(c, step, form, famTitle, { t, esc, badge }) {
  const guide = c.connected ? [] : guideSteps(c);
  const total = guide.length + 1;
  const at = Math.max(0, Math.min(step | 0, total - 1));
  const crumb = `<nav class="cf-crumb" aria-label="breadcrumb"><button type="button" class="cf-crumb-back" data-cx-back="1">← ${esc(t("config.cxw.back"))}</button>` +
    `<span class="cf-crumb-sep">›</span><span>${esc(famTitle)}</span><span class="cf-crumb-sep">›</span><b>${esc(c.label)}</b></nav>`;
  const head = `<header class="cf-panel-head"><h4>${esc(c.label)} ${badge(c)}</h4>${c.detail ? `<p>${esc(c.detail)}</p>` : ""}</header>`;
  const titles = guide.map(g => t(`config.cxw.${g.key}.title`, g.params))
    .concat([c.connected ? t("config.cxw.connected_title") : t("config.cxw.final_title")]);
  const stepper = total > 1 ? `<ol class="cf-wiz-steps">${titles.map((ti, i) =>
    `<li class="cf-wiz-step${i === at ? " on" : ""}${i < at ? " done" : ""}"><button type="button" data-cx-step="${i}">` +
    `<span class="cf-wiz-n">${i < at ? "✓" : i + 1}</span>${esc(ti)}</button></li>`).join("")}</ol>` : "";
  let body;
  if (at < guide.length) {
    const g = guide[at];
    body = `<p class="cf-wiz-text">${esc(t(`config.cxw.${g.key}.body`, g.params))}</p>` +
      (g.code ? `<div class="cf-wiz-code"><code>${esc(g.code)}</code><button type="button" class="cf-btn cf-wiz-copy" data-copy="${esc(g.code)}">${esc(t("config.cxw.copy"))}</button></div>` : "") +
      (g.link ? `<p><a class="cf-wiz-link" href="${esc(g.link)}" target="_blank" rel="noopener">${esc(t("config.cxw.open_link", { site: new URL(g.link).host }))} ↗</a></p>` : "");
  } else {
    const cc = c.config || {};
    const ready = !c.connected && GOOGLE_API[c.id] && cc.app_configured ? `<p class="cf-wiz-text">${esc(t("config.cxw.app_ready"))}</p>` : "";
    body = ready + `<div class="cf-group">${form}</div>` + liveState(c, { t, esc });
  }
  const nav = `<div class="cf-wiz-nav">${at > 0 ? `<button type="button" class="cf-btn cf-btn-ghost" data-cx-step="${at - 1}">${esc(t("config.cxw.prev"))}</button>` : "<span></span>"}` +
    (at < total - 1 ? `<span class="cf-wiz-count">${esc(t("config.cxw.step", { n: at + 1, total }))}</span><button type="button" class="cf-btn" data-cx-step="${at + 1}">${esc(t("config.cxw.next"))}</button>` : "") + `</div>`;
  return `${crumb}<section class="cf-panel-sec cf-wiz">${head}${stepper}<div class="cf-wiz-body">${body}</div>${nav}</section>`;
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

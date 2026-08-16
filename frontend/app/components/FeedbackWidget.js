// FeedbackWidget — floating "send feedback to the developers" launcher + panel (V2-100, 2026-08-16).
//
// One native surface, two visual states: a small draggable button (default bottom-right, like a
// typical support-chat launcher) that opens a panel with two tabs — "Sent" (a static, read-only list
// of what was submitted and its status: received/in progress/done, with our reply if there is one) and
// "New" (a form: textarea + mic dictation + send). Deliberately NOT chat-shaped — no bubbles going back
// and forth, one message goes out, a "thanks" state shows, and it joins the Sent list.
//
// Kept fully self-contained (own components/services files, only two registration points touched —
// system-surfaces.js and store.js) per the explicit "keep this modular, don't entangle it with
// anything" requirement: it can be deleted by removing those two lines and this file's own imports,
// with nothing elsewhere left dangling.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { makeDraggable } from "../lib/draggable.js?v=2";
import { CLOSE_ICON, MIC_ICON, MESSAGE_SQUARE_ICON, SEND_ICON } from "../lib/icons.js?v=1";
import * as feedbackApi from "../services/feedback-api.js?v=1";
import * as dictation from "../services/feedback-dictation.js?v=1";

function _fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(store.lang() || undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch (_) {
    return iso;
  }
}

function _excerpt(text, max = 180) {
  const s = (text || "").trim();
  return s.length > max ? s.slice(0, max).trimEnd() + "…" : s;
}

export function FeedbackWidget() {
  let wrapEl, btnEl, textareaEl, emailEl, evidenceEl;
  let recHandle = null, base = "", finalSoFar = "", pollTimer = null;
  const [listening, setListening] = createSignal(false);
  const [justSent, setJustSent] = createSignal(false);

  const refresh = async () => {
    const res = await feedbackApi.listFeedback();
    store.setFeedbackItems(Array.isArray(res.items) ? res.items : []);
  };

  const renderDictated = (interim) => {
    if (!textareaEl) return;
    textareaEl.value = [base, finalSoFar, interim].filter(Boolean).join(" ");
  };

  const toggleMic = () => {
    if (listening()) { dictation.stop(recHandle); recHandle = null; setListening(false); return; }
    if (!dictation.isSupported()) return;
    base = textareaEl ? textareaEl.value.trim() : "";
    finalSoFar = "";
    recHandle = dictation.start({
      lang: store.lang(),
      onInterim: renderDictated,
      onFinal: (chunk) => { finalSoFar = [finalSoFar, chunk].filter(Boolean).join(" "); renderDictated(""); },
      onEnd: () => setListening(false),
    });
    setListening(true);
  };

  const send = async () => {
    const message = (textareaEl?.value || "").trim();
    if (!message || store.feedbackSending()) return;
    if (listening()) toggleMic();
    store.setFeedbackSending(true);
    const res = await feedbackApi.sendFeedback({
      message, email: emailEl?.value || "", includeSessionEvidence: !!evidenceEl?.checked,
    });
    store.setFeedbackSending(false);
    if (res && res.ok) {
      if (textareaEl) textareaEl.value = "";
      if (emailEl) emailEl.value = "";
      if (evidenceEl) evidenceEl.checked = false;
      setJustSent(true);
      setTimeout(() => setJustSent(false), 4000);
      store.setFeedbackTab("sent");
      refresh();
    }
  };

  const statusBadge = (item) => h("span", { class: "fw-badge fw-badge-" + item.status },
    () => t("feedback.status." + item.status));

  const sentItem = (item) => h("div", { class: "fw-item" },
    h("div", { class: "fw-item-msg" }, _excerpt(item.message)),
    h("div", { class: "fw-item-meta" }, _fmtDate(item.created_at), " · ", statusBadge(item)),
    item.reply_text
      ? h("div", { class: "fw-reply" }, h("div", { class: "fw-reply-label" }, () => t("feedback.replyLabel")), item.reply_text)
      : null,
  );

  const wrap = h("div", { class: "fw-wrap", ref: el => (wrapEl = el) },
    h("button", {
      class: "fw-launcher", ref: el => (btnEl = el), title: () => t("feedback.launcherLabel"),
      onClick: () => store.setFeedbackOpen(!store.feedbackOpen()),
    }, raw(MESSAGE_SQUARE_ICON)),
    h("div", { class: () => "fw-panel tab-" + store.feedbackTab() + (store.feedbackOpen() ? " open" : "") },
      h("div", { class: "fw-head" },
        h("div", { class: "fw-title" }, () => t("feedback.title")),
        h("button", { class: "fw-x", title: () => t("feedback.title"), onClick: () => store.setFeedbackOpen(false) }, raw(CLOSE_ICON)),
      ),
      h("div", { class: "fw-tabs" },
        h("button", { class: () => "fw-tab" + (store.feedbackTab() === "new" ? " on" : ""), onClick: () => store.setFeedbackTab("new") }, () => t("feedback.tabNew")),
        h("button", { class: () => "fw-tab" + (store.feedbackTab() === "sent" ? " on" : ""), onClick: () => store.setFeedbackTab("sent") }, () => t("feedback.tabSent")),
      ),
      h("div", { class: "fw-new" },
        justSent()
          ? h("div", { class: "fw-thanks" }, () => t("feedback.thanks"))
          : null,
        h("textarea", { class: "fw-textarea", ref: el => (textareaEl = el), rows: 4, placeholder: () => t("feedback.placeholder") }),
        h("div", { class: "fw-row" },
          h("label", { class: "fw-check" },
            h("input", { type: "checkbox", ref: el => (evidenceEl = el) }),
            () => t("feedback.evidenceLabel"),
          ),
        ),
        h("div", { class: "fw-hint" }, () => t("feedback.evidenceExplainer")),
        h("div", { class: "fw-field" },
          h("input", { type: "email", class: "fw-email", placeholder: () => t("feedback.emailPlaceholder"), ref: el => (emailEl = el) }),
          h("div", { class: "fw-hint" }, () => t("feedback.emailNudge")),
        ),
        h("div", { class: "fw-actions" },
          h("button", {
            class: () => "fw-mic" + (listening() ? " on" : "") + (dictation.isSupported() ? "" : " hidden"),
            title: () => (listening() ? t("feedback.dictating") : t("feedback.dictate")),
            onClick: toggleMic,
          }, raw(MIC_ICON)),
          h("button", {
            class: "fw-send", title: () => t("feedback.send"), onClick: send,
            disabled: () => store.feedbackSending(),
          }, raw(SEND_ICON)),
        ),
      ),
      h("div", { class: "fw-sent" },
        () => (store.feedbackItems().length
          ? store.feedbackItems().map(sentItem)
          : h("div", { class: "fw-empty" }, () => t("feedback.emptyState"))),
      ),
    ),
  );

  // Draggable but anchored: same call shape as the Orb (mode "bl" — bottom/left math, default screen
  // position comes from CSS bottom-right; a drag persists a new spot, same as every other draggable
  // chrome piece in this app). No bespoke "snap to corner" logic needed.
  makeDraggable(wrapEl, btnEl, "zaelar_feedback_pos", "bl");

  createEffect(() => {
    if (store.feedbackOpen()) {
      refresh();
      clearInterval(pollTimer);
      pollTimer = setInterval(refresh, 30000);
    } else {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  });

  return wrap;
}

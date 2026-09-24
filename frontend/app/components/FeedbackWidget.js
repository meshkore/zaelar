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
import { CLOSE_ICON, MIC_ICON, MESSAGE_SQUARE_ICON, PAPERCLIP_ICON, SEND_ICON, THUMBS_DOWN_ICON } from "../lib/icons.js?v=2";
import * as feedbackApi from "../services/feedback-api.js?v=1";
import { sendOutcome, listOutcome, lineFor } from "../services/feedback-state.js?v=1";
import * as dictation from "../services/feedback-dictation.js?v=1";
import * as shotsvc from "../services/feedback-images.js?v=1";

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

// ── THE HEIGHT IS HIS (V2-695) ──────────────────────────────────────────────────────────────────────
// The panel used to be 585px, a literal picked in V2-681 so the box would stop shrinking and springing
// back between tabs. That fixed the jump and left the operator with a size he never chose; asked what he
// wanted, he said «que lo pueda redimensionar yo». So the number becomes a default and the grip decides.
//
// Calqued from `lib/draggable.js` and for its reasons, not by imitation: the move/up listeners live on
// the WINDOW and are added per drag, because handle-bound listeners stop firing the moment the pointer
// leaves the handle — a drag faster than a 10px grip simply dies (the V2-608 F6 measurement, 0px applied
// for a 120px drag). It stays here rather than in `lib/` on purpose: this surface's contract is that
// deleting two lines in `system-surfaces.js` removes it whole, with nothing left dangling elsewhere.
const FW_MIN_H = 380;
const fwMaxH = () => Math.min(Math.round(window.innerHeight * 0.9), 900);

function makeResizable(panel, grip, key) {
  if (!panel || !grip) return;
  const clamp = v => Math.max(FW_MIN_H, Math.min(Math.round(v), fwMaxH()));
  try {
    const saved = Number(localStorage.getItem(key)) || 0;
    if (saved) panel.style.height = clamp(saved) + "px";
  } catch (_) {}
  let startY = 0, startH = 0, pid = null, on = false;
  grip.style.touchAction = "none";
  const move = e => {
    if (!on || e.pointerId !== pid) return;
    // Anchored at the BOTTOM, so pulling the TOP edge up (a negative delta) is what makes it taller.
    panel.style.height = clamp(startH + (startY - e.clientY)) + "px";
  };
  const end = e => {
    if (!on || (e && e.pointerId !== pid)) return;
    on = false;
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", end);
    removeEventListener("pointercancel", end);
    try { localStorage.setItem(key, String(Math.round(panel.getBoundingClientRect().height))); } catch (_) {}
  };
  grip.addEventListener("pointerdown", e => {
    on = true; pid = e.pointerId; startY = e.clientY;
    startH = panel.getBoundingClientRect().height || FW_MIN_H;
    e.preventDefault();
    addEventListener("pointermove", move);
    addEventListener("pointerup", end);
    addEventListener("pointercancel", end);
  });
}

export function FeedbackWidget() {
  let wrapEl, btnEl, textareaEl, emailEl, panelEl, fileEl, gripEl;
  let recHandle = null, base = "", finalSoFar = "", pollTimer = null;
  const [listening, setListening] = createSignal(false);
  const [justSent, setJustSent] = createSignal(false);
  // The two states this panel used to keep to itself. `sendLine` is whatever the last submit
  // ACTUALLY answered; `listReachable` separates "you have sent nothing" from "we cannot look".
  const [sendLine, setSendLine] = createSignal("");
  const [listReachable, setListReachable] = createSignal(true);
  // The KEY comes from the shared reading, not from a second `if` here. Re-deriving it locally is
  // how the rule ended up living in two places to begin with.
  const [emptyKey, setEmptyKey] = createSignal("feedback.emptyState");
  // V2-695 — WHAT KIND of report this is. The operator's ask, in his words: «I want people communicate
  // errors or desires… whether something they tried failed, or maybe they have an idea». One box could
  // never tell those apart, so whoever reads the inbox could not either. Two options, one always picked,
  // and the placeholder follows it: the cheap half of «tell us what you need».
  const [kind, setKind] = createSignal("issue");
  // V2-760 — THE THUMBS-DOWN. The operator: «cada vez que la gente detecte un fallo, les pediré que clique en
  // este pulgar hacia abajo… así el usuario no tiene que estar rellenando un mail o un texto… y cuando se clique
  // saldrá un mensaje hacia la izquierda… dura dos o tres segundos, el tiempo que sea necesario para leerlo, y
  // desaparece en un fundido. Y el icono vuelve al color original también». One click, no form; the report is
  // the session, composed server-side. `thumb` is idle | sending | done | failed; the toast text is kept through
  // the fade and only cleared once it is invisible, so the words never vanish before the fade does.
  const THUMB_SHOW_MS = 3000, THUMB_FADE_MS = 600;
  const [thumb, setThumb] = createSignal("idle");
  const [thumbText, setThumbText] = createSignal("");
  const [thumbShown, setThumbShown] = createSignal(false);
  let thumbTimers = [];
  const sendThumb = async () => {
    if (thumb() !== "idle") return;                        // one mark per click, never a burst of duplicates
    setThumb("sending");
    const res = await feedbackApi.sendThumbsDown();
    const ok = !!(res && res.ok);
    setThumb(ok ? "done" : "failed");
    setThumbText(t(ok ? "feedback.thumbsDownThanks" : "feedback.thumbsDownFailed"));
    setThumbShown(true);
    thumbTimers.forEach(clearTimeout);
    thumbTimers = [
      setTimeout(() => setThumbShown(false), THUMB_SHOW_MS),                      // starts the fade
      setTimeout(() => { setThumbText(""); setThumb("idle"); }, THUMB_SHOW_MS + THUMB_FADE_MS),
    ];
  };
  // The pictures attached to THIS report, and the sentence that says why one was refused. A picture
  // dropped in silence is a picture the person believes they sent.
  const [shots, setShots] = createSignal([]);
  const [shotLine, setShotLine] = createSignal("");

  const refresh = async () => {
    const out = listOutcome(await feedbackApi.listFeedback());
    setListReachable(out.reachable);
    setEmptyKey(out.emptyKey);
    store.setFeedbackItems(out.items);
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

  // ── PICTURES ────────────────────────────────────────────────────────────────────────────────────
  // Three ways in, because people reach for all three: paste a screenshot, drop a file, or press the
  // clip. They all land here, where the budget is checked ONCE.
  const addFiles = async (files) => {
    setShotLine("");
    for (const f of Array.from(files || [])) {
      if (!shotsvc.isImage(f)) { setShotLine(t("feedback.imagesOnly")); continue; }
      const shot = await shotsvc.prepare(f);
      if (!shot) { setShotLine(t("feedback.shotUnreadable")); continue; }
      const why = shotsvc.refusal(shots(), shot.bytes);
      if (why) { setShotLine(t(why)); continue; }
      setShots([...shots(), shot]);
    }
  };
  const dropShot = (i) => setShots(shots().filter((_, n) => n !== i));

  // ⚠️ `stopPropagation`, and it is the whole reason this works. `main.js` installs a WINDOW-level paste
  // handler that grabs any image on the clipboard, calls preventDefault() and uploads it to the episodic
  // memory inbox — and its own comment says it does that even while focus is in an input. Without this
  // line, pasting a screenshot into the feedback box files it somewhere nobody asked for and the report
  // goes out with nothing attached.
  const onPaste = (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    const files = [];
    for (const it of items) if (it.kind === "file" && /^image\//i.test(it.type)) {
      const f = it.getAsFile(); if (f) files.push(f);
    }
    if (!files.length) return;                       // plain text paste: leave it alone
    e.preventDefault(); e.stopPropagation();
    addFiles(files);
  };
  const onDrop = (e) => {
    const files = (e.dataTransfer && e.dataTransfer.files) || [];
    if (!files.length) return;
    e.preventDefault(); e.stopPropagation();
    addFiles(files);
  };

  const send = async () => {
    const message = (textareaEl?.value || "").trim();
    if (!message || store.feedbackSending()) return;
    if (listening()) toggleMic();
    store.setFeedbackSending(true);
    const res = await feedbackApi.sendFeedback({
      // V2-681 T-2 — the checkbox is gone, so the evidence rides ALWAYS. That is what the box existed to
      // avoid: feedback with no context is a sentence nobody can act on. ⚠️ It is also a privacy DEFAULT
      // for every self-hoster, not only for the operator — reversing it is this one literal.
      message, email: emailEl?.value || "", includeSessionEvidence: true,
      // V2-695 — WHAT it is, and what it looks like. Both travel in the same JSON body the
      // retry rule below already knows how to shed piece by piece.
      kind: kind(), shots: shots(),
    });
    store.setFeedbackSending(false);
    const out = sendOutcome(res);
    // The failure branch is the whole point of V2-256: the message stays in the box (so a retry costs
    // nothing) and the panel SAYS what happened. It used to end here with no `else` at all.
    if (!out.ok) { setSendLine(lineFor(out, t)); return; }
    setSendLine("");
    if (textareaEl) textareaEl.value = "";
    if (emailEl) emailEl.value = "";
    setShots([]); setShotLine("");
    setJustSent(true);
    setTimeout(() => setJustSent(false), 4000);
    store.setFeedbackTab("sent");
    refresh();
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
    // V2-760 — the thumb sits ABOVE the launcher and its message to its left; it hides while the panel is
    // open (the panel opens over that spot) and on phones (CSS).
    h("div", { class: "fw-quick" },
      h("div", { class: () => "fw-thumb-toast" + (thumbShown() ? " show" : "") + (thumb() === "failed" ? " failed" : ""),
                 role: "status", "aria-live": "polite" }, () => thumbText()),
      h("button", {
        class: () => "fw-thumb fw-thumb-" + thumb(),
        title: () => t("feedback.thumbsDownLabel"), "aria-label": () => t("feedback.thumbsDownLabel"),
        onClick: sendThumb,
      }, raw(THUMBS_DOWN_ICON)),
    ),
    h("button", {
      class: "fw-launcher", ref: el => (btnEl = el), title: () => t("feedback.launcherLabel"),
      onClick: () => store.setFeedbackOpen(!store.feedbackOpen()),
    }, raw(MESSAGE_SQUARE_ICON)),
    h("div", {
      class: () => "fw-panel tab-" + store.feedbackTab() + (store.feedbackOpen() ? " open" : ""),
      ref: el => (panelEl = el), onPaste, onDrop, onDragOver: e => e.preventDefault(),
    },
      // V2-695 — the grip the operator asked for: «que lo pueda redimensionar yo». It sits on the TOP
      // edge because the panel is anchored bottom-right, so pulling up is what makes it taller and the
      // gesture can never push the box off the screen.
      h("div", { class: "fw-grip", ref: el => (gripEl = el), title: () => t("feedback.resize") }),
      // V2-619, the operator's layout: ONE header band — title, then the two tabs as real full-row
      // tabulators right beside it, the × at the far end. No second row.
      h("div", { class: "fw-head" },
        h("div", { class: "fw-title" }, () => t("feedback.title")),
        h("div", { class: "fw-tabs" },
          h("button", { class: () => "fw-tab" + (store.feedbackTab() === "new" ? " on" : ""), onClick: () => store.setFeedbackTab("new") }, () => t("feedback.tabNew")),
          h("button", { class: () => "fw-tab" + (store.feedbackTab() === "sent" ? " on" : ""), onClick: () => store.setFeedbackTab("sent") }, () => t("feedback.tabSent")),
        ),
        h("button", { class: "fw-x", title: () => t("feedback.title"), onClick: () => store.setFeedbackOpen(false) }, raw(CLOSE_ICON)),
      ),
      // THE STATUS STRIP — outside both tab panes on purpose (V2-256). The thank-you used to live
      // inside `.fw-new`, and a successful send switches to the Sent tab, which sets `.fw-panel` to
      // `tab-sent` and puts `display:none` on `.fw-new`: the confirmation was hidden by layout at the
      // exact moment it was meant to appear. That was the SECOND independent reason nothing showed —
      // the first is the bare ternary below, which read the signal once while the tree was being
      // built and appended nothing, no error anywhere (V2-124's detached-canvas lesson again).
      h("div", { class: "fw-status" },
        () => (justSent()
          ? h("div", { class: "fw-thanks" }, () => t("feedback.thanks"))
          : null),
        () => (sendLine() ? h("div", { class: "fw-error" }, sendLine()) : null),
      ),
      // V2-619, the operator's order and his exact words: email on TOP, then a BIG clearly-boxed textarea
      // («Escribe aquí tu feedback») and a big send button that SAYS send. (The evidence checkbox that
      // used to sit between them was deleted in V2-681 T-2 — see the note on the row below.)
      // V2-681 T-2, the operator: the "include what happened in this session" checkbox is DELETED, not
      // hidden — «bórralo, que nadie vea el rastro, porque se verá una intención fea». A hidden control is
      // still in the DOM and still reads as an intention to anyone who looks. And the mic moves down into
      // the send row: «el icono del micrófono lo puedes poner en la fila del botón de send my feedback».
      h("div", { class: "fw-new" },
        // V2-695 — TWO OPTIONS, one always picked. Not a dropdown and not free text: the whole value is
        // that whoever reads the inbox can tell a broken thing from a wish without reading first.
        h("div", { class: "fw-kind" },
          h("button", {
            class: () => "fw-kind-btn" + (kind() === "issue" ? " on" : ""),
            onClick: () => setKind("issue"),
          }, () => t("feedback.kindIssue")),
          h("button", {
            class: () => "fw-kind-btn" + (kind() === "idea" ? " on" : ""),
            onClick: () => setKind("idea"),
          }, () => t("feedback.kindIdea")),
        ),
        h("input", { type: "email", class: "fw-email", placeholder: () => t("feedback.emailPlaceholder"), ref: el => (emailEl = el) }),
        // The placeholder follows the option. Asking «what were you trying to do?» gets the one fact a
        // bug report needs and a wish never has.
        h("textarea", {
          class: "fw-textarea", ref: el => (textareaEl = el),
          placeholder: () => t(kind() === "idea" ? "feedback.placeholderIdea" : "feedback.placeholderIssue"),
        }),
        () => (shots().length
          ? h("div", { class: "fw-shots" }, ...shots().map((sh, i) =>
              h("div", { class: "fw-shot" },
                h("img", { class: "fw-shot-img", src: shotsvc.dataUrl(sh), loading: "lazy",
                           decoding: "async", alt: () => t("feedback.shotAlt") }),
                h("button", { class: "fw-shot-x", title: () => t("feedback.shotRemove"),
                              onClick: () => dropShot(i) }, raw(CLOSE_ICON)))))
          : null),
        () => (shotLine() ? h("div", { class: "fw-shot-note" }, shotLine()) : null),
        h("input", { type: "file", class: "fw-file", accept: "image/*", multiple: true,
                     ref: el => (fileEl = el),
                     onChange: () => { addFiles(fileEl.files); fileEl.value = ""; } }),
        h("div", { class: "fw-row" },
          h("button", {
            class: () => "fw-mic" + (listening() ? " on" : "") + (dictation.isSupported() ? "" : " hidden"),
            title: () => (listening() ? t("feedback.dictating") : t("feedback.dictate")),
            onClick: toggleMic,
          }, raw(MIC_ICON)),
          h("button", { class: "fw-clip", title: () => t("feedback.attach"), onClick: () => fileEl && fileEl.click() },
            raw(PAPERCLIP_ICON)),
          h("button", {
            class: "fw-send", onClick: send,
            disabled: () => store.feedbackSending(),
          }, raw(SEND_ICON), h("span", {}, () => t("feedback.send"))),
        ),
      ),
      h("div", { class: "fw-sent" },
        () => (store.feedbackItems().length
          ? store.feedbackItems().map(sentItem)
          : h("div", { class: () => (listReachable() ? "fw-empty" : "fw-empty fw-empty-unreachable") },
              () => t(emptyKey()))),
      ),
    ),
  );

  // Draggable but anchored: same call shape as the Orb (mode "bl" — bottom/left math, default screen
  // position comes from CSS bottom-right; a drag persists a new spot, same as every other draggable
  // chrome piece in this app). No bespoke "snap to corner" logic needed.
  makeDraggable(wrapEl, btnEl, "zaelar_feedback_pos", "bl");
  makeResizable(panelEl, gripEl, "zaelar_feedback_h");

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

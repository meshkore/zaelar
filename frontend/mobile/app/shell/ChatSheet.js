// ============================================================================
// ChatSheet.js — the chat, as a bottom sheet.  Mobile counterpart of components/ChatWall.js (23 KB: a floating,
// draggable, resizable, edge-dockable panel with four tabs). None of those affordances mean anything on a phone,
// so the SHELL is new — but the CONTENT is not forked:
//
//   · the messages are store.chatMsgs()      — the same signal the desktop wall renders
//   · sending goes through submitChat(text)  — imported from ChatWall.js, NOT reimplemented
//
// That import is deliberate even though submitChat is three lines. It is the ONE path from a typed sentence to the
// agent (session.sendText + store.pushChat, in that order). A local copy would be a second path, and a second path
// is how one shell starts recording messages the other never sees. ChatWall.js has no top-level side effects, so
// importing it does not mount any desktop UI.
//
// FOUR TABS BECOME ONE. The desktop panel carries Chat / Processes / Crons / Clusters. On a phone the sheet is Chat
// only; Processes and Crons are read-only monitoring that belongs in the menu, and Clusters is infrastructure setup
// nobody does with a thumb. `store.chatTab` is left completely alone — a mobile user who never touches it does not
// change what the desktop shows on the same account.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import { createEffect } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { submitChat } from "../../../app/components/ChatWall.js?v=5";
import { renderMarkdownLite } from "../../../app/lib/markdown-lite.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";

const SEND = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>`;

export function ChatSheet() {
  let listEl = null, inputEl = null;

  const send = () => {
    const v = (inputEl && inputEl.value) || "";
    if (!v.trim()) return;
    submitChat(v);
    inputEl.value = "";
    // Keep the keyboard up: on a phone, dismissing it after every line turns a conversation into a chore.
    inputEl.focus();
  };

  const sheet = h("section", {
    class: () => "zm-sheet zm-chat" + (store.chatOpen() ? " open" : ""),
    "aria-hidden": () => (store.chatOpen() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("div", { class: "zm-sheet-grab" }),
      h("h2", null, () => t("chat.title")),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"), onClick: () => store.setChatOpen(false) }, "×"),
    ),
    h("div", { class: "zm-msgs", ref: (el) => (listEl = el) },
      () => store.chatMsgs().map((m) => {
        const row = h("div", { class: "zm-msg " + (m.role || "sys") });
        // The agent speaks markdown (lists, bold, code); the person does not. Same renderer as the desktop wall.
        if (m.role === "agent") row.innerHTML = renderMarkdownLite(m.text || "");
        else row.textContent = m.text || "";
        return row;
      }),
    ),
    h("form", { class: "zm-compose", onSubmit: (e) => { e.preventDefault(); send(); } },
      h("input", {
        ref: (el) => (inputEl = el),
        type: "text", autocomplete: "off", autocapitalize: "sentences", enterkeyhint: "send",
        placeholder: () => t("chat.placeholder"),
      }),
      h("button", { type: "submit", class: "zm-send", "aria-label": () => t("chat.send") }, raw(SEND)),
    ),
  );

  // Stick to the bottom as messages land. Not "scroll to bottom always": if the operator has scrolled UP to read
  // something, a new message must not yank them back down — the same rule the widget host applies to ctx.top().
  createEffect(() => {
    store.chatMsgs();
    if (!listEl) return;
    const nearBottom = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 120;
    if (nearBottom) requestAnimationFrame(() => { listEl.scrollTop = listEl.scrollHeight; });
  });

  return sheet;
}

// Alert — top error banner. Services raise it via store.showAlert(msg, onClick);
// clicking runs the callback and clears it. (Most paths stay clean and use the orb
// 🚫 ring instead — this is the rare hard-failure banner.)
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";

export function Alert() {
  return h("div", {
    id: "alert",
    class: () => "alert" + (store.alert() ? " show" : ""),
    onClick: () => { const a = store.alert(); store.hideAlert(); a && a.onClick && a.onClick(); },
  }, () => (store.alert() ? store.alert().msg : ""));
}

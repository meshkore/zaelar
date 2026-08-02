// ConnStatus — bottom-left diagnostics: connection state · reply latency · mic.
// connv/latv/micbar bind to the store; micv/micsel/micmode/micbarwrap keep their ids so the
// session's diagnostic helpers (diagMic / populateMicPicker) can drive them directly.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";

export function ConnStatus() {
  return h("div", { class: "conn" },
    "conn ",
    h("b", { id: "connv", style: { color: () => (store.conn().ok ? "#16B8A6" : "#9aa7b8") } }, () => store.conn().label),
    " · reply ",
    h("b", { id: "latv" }, () => store.latency()),
    " · mic ",
    h("b", { id: "micv", style: { display: "none" } }, "—"),                              // legacy name (hidden): diagnostic only
    h("select", { id: "micsel", title: "Microphone", style: { display: "none", maxWidth: "200px", fontSize: "11px", verticalAlign: "middle" } }),
    h("select", { id: "micmode", title: "Capture mode (noise cleanup)", style: { display: "none", marginLeft: "6px", fontSize: "11px", verticalAlign: "middle" } }),
    h("span", { id: "micbarwrap", style: { display: "none", verticalAlign: "middle", marginLeft: "8px", width: "64px", overflow: "hidden" } },
      h("span", {
        id: "micbar",
        style: {
          display: "inline-block", height: "7px", borderRadius: "4px", transition: "width .08s",
          width: () => Math.min(60, Math.round(store.micLevel() * 400)) + "px",
          background: () => (store.micLevel() > 0.02 ? "#16B8A6" : "#d64545"),
        },
      })
    ),
  );
}

// ============================================================================
// FaultModal.js — THE AGENT CANNOT WORK, SAID IN FULL (V2-676).
//
// The operator's own session (`af4429e0`, 2026-09-11): halfway through a
// conversation held entirely in English, DeepSeek answered `402 Insufficient
// Balance`. What he got was one spoken sentence — in SPANISH, because it was a
// string literal in the engine — telling him to put something in
// `fast.providers`. He kept talking. Nothing on screen said the agent was
// unable to answer, the microphone stayed open, and his report was «no entiendo
// nada».
//
// His ruling: «la voz hay que pararla y hay que bloquear a la gente. Si el
// FlashBrain no tiene dinero, hay que marcar el estado en rojo y que salga la
// alerta en grande… en el idioma del usuario, obviamente… recarga por favor o
// cámbialo en la configuración, y ponemos un botón que abra la configuración.»
//
// WHY EVERY WORD HERE IS AN i18n KEY, and none of it comes from the engine.
// A dry model chain is the one moment when the thing that translates — a model
// — is exactly what we do not have. So the engine sends FACTS (`{code, model,
// provider, suppressed, config_key}`) and this file renders them against the
// bundle, which is generated for whatever language the agent was initialised
// in. That is the operator's own requirement: «el texto debe funcionar en el
// idioma del usuario… en algún archivo que se traduzca también cuando el
// usuario se inicializa en otro idioma».
//
// It BLOCKS on purpose (no click-outside to close). A banner is what this was
// before, and he walked past it for two minutes. The two ways out are both
// deliberate: open the settings, or accept working without voice.
// ============================================================================
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as api from "../services/api.js?v=2";

export function FaultModal() {
  const f = () => store.fault() || {};

  const openConfig = () => {
    api.uiEvent("fault:open_config", { code: f().code || "" });
    store.clearFault();
    store.setConfigOpen(true);
  };

  // «Ya está arreglado»: he topped the account up in another tab and wants the agent back. The page reload is
  // deliberate and is the honest path — the engine caches a per-provider cooldown, the voice session is down,
  // and a half-rebuilt client is how this codebase has twice produced a state that only a reload could fix.
  const retry = () => {
    api.uiEvent("fault:retry", { code: f().code || "" });
    location.reload();
  };

  const dismiss = () => { api.uiEvent("fault:dismiss", { code: f().code || "" }); store.clearFault(); };

  const body = () => {
    const model = String(f().model || "").trim();
    // The model's NAME is a fact, not prose — it interpolates into the translated sentence. Without it the
    // operator has to guess which of his providers ran dry.
    return model ? t("fault.no_model.body", { model }) : t("fault.no_model.body_generic");
  };

  const suppressed = () => {
    const names = (f().suppressed || []).filter(Boolean);
    if (!names.length) return null;
    // V2-244's rule, moved from his EARS to his EYES: a credentialed rung we are silencing is named, with the
    // key that turns it on — here, beside the button that opens the place to type it.
    return h("p", { class: "fault-note" },
      () => t("fault.no_model.suppressed", { names: names.join(", "), key: f().config_key || "fast.providers" }));
  };

  return h("div", { class: () => "ovl fault-ovl" + (store.fault() ? " on" : "") },
    h("div", { class: "fault-box", role: "alertdialog", "aria-live": "assertive" },
      h("div", { class: "fault-mark", "aria-hidden": "true" }, "⚠"),
      h("h3", { class: "fault-title" }, () => t("fault.no_model.title")),
      h("p", { class: "fault-body" }, body),
      suppressed,
      h("p", { class: "fault-fix" }, () => t("fault.no_model.fix")),
      h("div", { class: "fault-actions" },
        h("button", { class: "fault-btn primary", onClick: openConfig }, () => t("fault.no_model.open_config")),
        h("button", { class: "fault-btn", onClick: retry }, () => t("fault.no_model.retry")),
        h("button", { class: "fault-btn ghost", onClick: dismiss }, () => t("fault.no_model.dismiss")),
      ),
    ),
  );
}

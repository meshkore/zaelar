// ============================================================================
// VaultModal — el modal NATIVO de la BÓVEDA de secretos (V2-060). NO es un widget:
// es parte del frontend y del motor de memoria. Cubre crear la bóveda, desbloquear
// (por PASSPHRASE o por PASSKEY biométrica — Touch ID/Windows Hello), mostrar un
// secreto y gestionar dispositivos.
//
// Se abre solo cuando hace falta: el cerebro emite eventos SSE kind "secret"
// (locked → pide desbloqueo; no_vault → propone crear; reveal → muestra el valor),
// o el operador lo abre desde la gestión. El VALOR del secreto se pide a
// /api/vault/reveal (loopback), nunca llega por el bus de eventos ni por el LLM.
// Tema vía --hb-* únicamente.
// ============================================================================
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as vault from "../services/vault.js?v=1";
import { KEY_ICON, LOCK_ICON, CLOSE_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

async function refreshStatus() {
  try { store.setVaultStatus(await vault.status()); } catch (_) {}
}

export function VaultModal() {
  let p1, p2, np1, np2, op1;   // inputs

  // al abrir: refresca estado y, si no hay bóveda, fuerza el modo "create"
  createEffect(() => {
    if (!store.vaultOpen()) return;
    refreshStatus().then(() => {
      const st = store.vaultStatus();
      if (!st.exists && store.vaultMode() !== "create") store.setVaultMode("create");
    });
  });

  const msg = (t) => store.setVaultMsg(t || "");

  // tras desbloquear: si había un secreto pendiente, lo revela y pasa a "reveal"
  async function afterUnlock() {
    await refreshStatus();
    const mid = store.vaultPendingMid();
    if (mid == null) { store.setVaultMode("manage"); msg(t("vault.unlocked")); return; }
    const r = await vault.reveal(mid);
    if (r.value != null) {
      let label = "";
      try { label = ((await vault.secrets()).secrets.find(s => s.memory_id === mid) || {}).label || ""; } catch (_) {}
      store.setVaultRevealed({ label, value: r.value });
      store.setVaultMode("reveal");
    } else {
      msg(r.error || t("vault.revealError"));
      store.setVaultMode("manage");
    }
  }

  const doCreate = async () => {
    const a = (p1.value || "").trim(), b = (p2.value || "").trim();
    if (a.length < 4) return msg(t("vault.pwTooShort"));
    if (a !== b) return msg(t("vault.pwMismatch"));
    const r = await vault.create(a).catch(() => ({}));
    if (r && r.exists) { p1.value = p2.value = ""; msg(t("vault.created")); afterUnlockOrManage(); }
    else msg((r && r.detail) || t("vault.createError"));
  };
  // tras crear, la bóveda queda SIN desbloquear (no hay clave en RAM) → desbloquea con la misma passphrase
  const afterUnlockOrManage = async () => { await refreshStatus(); store.setVaultMode(store.vaultPendingMid() != null ? "unlock" : "manage"); };

  const doUnlock = async () => {
    const a = (p1.value || "").trim();
    if (!a) return msg(t("vault.enterPw"));
    const r = await vault.unlock(a).catch(() => ({}));
    p1.value = "";
    if (r && r.ok) { msg(""); afterUnlock(); } else msg(t("vault.wrongPw"));
  };

  const doUnlockPasskey = async () => {
    msg(t("vault.usePasskey"));
    const r = await vault.unlockPasskey();
    if (r.ok) { msg(""); afterUnlock(); } else msg(r.error || t("vault.passkeyUnlockError"));
  };

  const doEnrollPasskey = async () => {
    msg(t("vault.registeringDevice"));
    const r = await vault.enrollPasskey();
    await refreshStatus();
    msg(r.ok ? t("vault.deviceRegistered") : (r.error || t("vault.registerError")));
  };

  const doChange = async () => {
    const o = (op1.value || "").trim(), a = (np1.value || "").trim(), b = (np2.value || "").trim();
    if (a.length < 4 || a !== b) return msg(t("vault.newPwInvalid"));
    const r = await vault.change(o, a);
    op1.value = np1.value = np2.value = "";
    msg(r.ok ? t("vault.pwChanged") : t("vault.wrongCurrentPw"));
    if (r.ok) refreshStatus();
  };

  const copyValue = async () => {
    const v = store.vaultRevealed(); if (!v) return;
    try { await navigator.clipboard.writeText(v.value); msg(t("vault.copied")); } catch (_) { msg(t("vault.copyError")); }
  };

  const field = (setRef, ph, opts = {}) =>
    h("input", { ref: setRef, class: "vault-in", type: "password", placeholder: ph, autocomplete: "off",
      onKeydown: (e) => { if (e.key === "Enter" && opts.onEnter) opts.onEnter(); } });

  const passkeyBtns = (mode) => {
    if (!vault.passkeySupported()) return null;
    const st = store.vaultStatus();
    if (mode === "unlock" && (st.methods || []).includes("passkey"))
      return h("button", { class: "vault-b ghost", onClick: doUnlockPasskey }, raw(KEY_ICON), () => t("vault.usePasskeyBtn"));
    return null;
  };

  const body = () => {
    const mode = store.vaultMode();
    if (mode === "create") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, () => t("vault.createLead")),
      field(el => (p1 = el), () => t("vault.masterPwPlaceholder"), { onEnter: doCreate }),
      field(el => (p2 = el), () => t("vault.repeatPwPlaceholder"), { onEnter: doCreate }),
      h("button", { class: "vault-b", onClick: doCreate }, () => t("vault.createBtn")),
    );
    if (mode === "unlock") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, () => t("vault.unlockLead")),
      field(el => (p1 = el), () => t("vault.vaultPwPlaceholder"), { onEnter: doUnlock }),
      h("button", { class: "vault-b", onClick: doUnlock }, () => t("vault.unlockBtn")),
      passkeyBtns("unlock"),
    );
    if (mode === "reveal") {
      const v = store.vaultRevealed() || {};
      return h("div", { class: "vault-body" },
        h("p", { class: "vault-lead" }, () => v.label || t("vault.secret")),
        h("div", { class: "vault-secret" }, v.value || ""),
        h("div", { class: "vault-row" },
          h("button", { class: "vault-b", onClick: copyValue }, () => t("vault.copyBtn")),
          h("button", { class: "vault-b ghost", onClick: store.closeVault }, () => t("vault.hideBtn")),
        ),
      );
    }
    // manage
    const st = store.vaultStatus();
    return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, () => t("vault.manageStatus", { state: st.unlocked ? t("vault.stateUnlocked") : t("vault.stateLocked"), count: st.secret_count || 0 })),
      st.unlocked ? null : h("button", { class: "vault-b", onClick: () => store.setVaultMode("unlock") }, () => t("vault.unlockBtn")),
      (st.unlocked && vault.passkeySupported())
        ? h("button", { class: "vault-b ghost", onClick: doEnrollPasskey }, raw(KEY_ICON), () => t("vault.registerDeviceBtn"))
        : null,
      h("div", { class: "vault-sep" }, () => t("vault.changePwSep")),
      field(el => (op1 = el), () => t("vault.currentPwPlaceholder")),
      field(el => (np1 = el), () => t("vault.newPwPlaceholder")),
      field(el => (np2 = el), () => t("vault.repeatNewPwPlaceholder"), { onEnter: doChange }),
      h("button", { class: "vault-b ghost", onClick: doChange }, () => t("vault.changePwBtn")),
    );
  };

  return h("div", { class: () => "vault-modal" + (store.vaultOpen() ? " open" : "") },
    h("div", { class: "vault-card" },
      h("div", { class: "vault-head" },
        h("span", { class: "vault-title" }, raw(LOCK_ICON), () => t("vault.headerTitle")),
        h("button", { class: "vault-x", title: () => t("vault.closeTitle"), onClick: store.closeVault }, raw(CLOSE_ICON)),
      ),
      () => body(),
      h("div", { class: () => "vault-msg" + (store.vaultMsg() ? " show" : "") }, () => store.vaultMsg()),
    ),
  );
}

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
    if (mid == null) { store.setVaultMode("manage"); msg("Vault unlocked."); return; }
    const r = await vault.reveal(mid);
    if (r.value != null) {
      let label = "";
      try { label = ((await vault.secrets()).secrets.find(s => s.memory_id === mid) || {}).label || ""; } catch (_) {}
      store.setVaultRevealed({ label, value: r.value });
      store.setVaultMode("reveal");
    } else {
      msg(r.error || "Couldn't show the secret.");
      store.setVaultMode("manage");
    }
  }

  const doCreate = async () => {
    const a = (p1.value || "").trim(), b = (p2.value || "").trim();
    if (a.length < 4) return msg("The password must be at least 4 characters.");
    if (a !== b) return msg("The two passwords don't match.");
    const r = await vault.create(a).catch(() => ({}));
    if (r && r.exists) { p1.value = p2.value = ""; msg("Vault created. You can now store secrets."); afterUnlockOrManage(); }
    else msg((r && r.detail) || "Couldn't create the vault.");
  };
  // tras crear, la bóveda queda SIN desbloquear (no hay clave en RAM) → desbloquea con la misma passphrase
  const afterUnlockOrManage = async () => { await refreshStatus(); store.setVaultMode(store.vaultPendingMid() != null ? "unlock" : "manage"); };

  const doUnlock = async () => {
    const a = (p1.value || "").trim();
    if (!a) return msg("Enter your password.");
    const r = await vault.unlock(a).catch(() => ({}));
    p1.value = "";
    if (r && r.ok) { msg(""); afterUnlock(); } else msg("Wrong password.");
  };

  const doUnlockPasskey = async () => {
    msg("Use your fingerprint / Face ID…");
    const r = await vault.unlockPasskey();
    if (r.ok) { msg(""); afterUnlock(); } else msg(r.error || "Couldn't unlock with the passkey.");
  };

  const doEnrollPasskey = async () => {
    msg("Registering this device…");
    const r = await vault.enrollPasskey();
    await refreshStatus();
    msg(r.ok ? "Device registered. You can now unlock with your fingerprint." : (r.error || "Couldn't register."));
  };

  const doChange = async () => {
    const o = (op1.value || "").trim(), a = (np1.value || "").trim(), b = (np2.value || "").trim();
    if (a.length < 4 || a !== b) return msg("The new password is invalid or doesn't match.");
    const r = await vault.change(o, a);
    op1.value = np1.value = np2.value = "";
    msg(r.ok ? "Password changed." : "The current password is incorrect.");
    if (r.ok) refreshStatus();
  };

  const copyValue = async () => {
    const v = store.vaultRevealed(); if (!v) return;
    try { await navigator.clipboard.writeText(v.value); msg("Copied to clipboard."); } catch (_) { msg("Couldn't copy."); }
  };

  const field = (setRef, ph, opts = {}) =>
    h("input", { ref: setRef, class: "vault-in", type: "password", placeholder: ph, autocomplete: "off",
      onKeydown: (e) => { if (e.key === "Enter" && opts.onEnter) opts.onEnter(); } });

  const passkeyBtns = (mode) => {
    if (!vault.passkeySupported()) return null;
    const st = store.vaultStatus();
    if (mode === "unlock" && (st.methods || []).includes("passkey"))
      return h("button", { class: "vault-b ghost", onClick: doUnlockPasskey }, raw(KEY_ICON), "Use fingerprint / Face ID");
    return null;
  };

  const body = () => {
    const mode = store.vaultMode();
    if (mode === "create") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, "Create a master password to store your encrypted secrets (passwords, IBAN, keys). Only you know it; without it they can't be read."),
      field(el => (p1 = el), "master password", { onEnter: doCreate }),
      field(el => (p2 = el), "repeat the password", { onEnter: doCreate }),
      h("button", { class: "vault-b", onClick: doCreate }, "Create vault"),
    );
    if (mode === "unlock") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, "Unlock your vault to access your secrets."),
      field(el => (p1 = el), "vault password", { onEnter: doUnlock }),
      h("button", { class: "vault-b", onClick: doUnlock }, "Unlock"),
      passkeyBtns("unlock"),
    );
    if (mode === "reveal") {
      const v = store.vaultRevealed() || {};
      return h("div", { class: "vault-body" },
        h("p", { class: "vault-lead" }, v.label || "Secret"),
        h("div", { class: "vault-secret" }, v.value || ""),
        h("div", { class: "vault-row" },
          h("button", { class: "vault-b", onClick: copyValue }, "Copy"),
          h("button", { class: "vault-b ghost", onClick: store.closeVault }, "Hide"),
        ),
      );
    }
    // manage
    const st = store.vaultStatus();
    return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, `Vault ${st.unlocked ? "unlocked" : "locked"} · ${st.secret_count || 0} secrets stored.`),
      st.unlocked ? null : h("button", { class: "vault-b", onClick: () => store.setVaultMode("unlock") }, "Unlock"),
      (st.unlocked && vault.passkeySupported())
        ? h("button", { class: "vault-b ghost", onClick: doEnrollPasskey }, raw(KEY_ICON), "Register this device (fingerprint)")
        : null,
      h("div", { class: "vault-sep" }, "Change master password"),
      field(el => (op1 = el), "current password"),
      field(el => (np1 = el), "new password"),
      field(el => (np2 = el), "repeat the new one", { onEnter: doChange }),
      h("button", { class: "vault-b ghost", onClick: doChange }, "Change password"),
    );
  };

  return h("div", { class: () => "vault-modal" + (store.vaultOpen() ? " open" : "") },
    h("div", { class: "vault-card" },
      h("div", { class: "vault-head" },
        h("span", { class: "vault-title" }, raw(LOCK_ICON), "Secrets vault"),
        h("button", { class: "vault-x", title: "Close", onClick: store.closeVault }, raw(CLOSE_ICON)),
      ),
      () => body(),
      h("div", { class: () => "vault-msg" + (store.vaultMsg() ? " show" : "") }, () => store.vaultMsg()),
    ),
  );
}

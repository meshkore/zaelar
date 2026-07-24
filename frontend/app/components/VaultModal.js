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
    if (mid == null) { store.setVaultMode("manage"); msg("Bóveda desbloqueada."); return; }
    const r = await vault.reveal(mid);
    if (r.value != null) {
      let label = "";
      try { label = ((await vault.secrets()).secrets.find(s => s.memory_id === mid) || {}).label || ""; } catch (_) {}
      store.setVaultRevealed({ label, value: r.value });
      store.setVaultMode("reveal");
    } else {
      msg(r.error || "No se pudo mostrar el secreto.");
      store.setVaultMode("manage");
    }
  }

  const doCreate = async () => {
    const a = (p1.value || "").trim(), b = (p2.value || "").trim();
    if (a.length < 4) return msg("La contraseña debe tener al menos 4 caracteres.");
    if (a !== b) return msg("Las dos contraseñas no coinciden.");
    const r = await vault.create(a).catch(() => ({}));
    if (r && r.exists) { p1.value = p2.value = ""; msg("Bóveda creada. Ya puedes guardar secretos."); afterUnlockOrManage(); }
    else msg((r && r.detail) || "No se pudo crear la bóveda.");
  };
  // tras crear, la bóveda queda SIN desbloquear (no hay clave en RAM) → desbloquea con la misma passphrase
  const afterUnlockOrManage = async () => { await refreshStatus(); store.setVaultMode(store.vaultPendingMid() != null ? "unlock" : "manage"); };

  const doUnlock = async () => {
    const a = (p1.value || "").trim();
    if (!a) return msg("Escribe tu contraseña.");
    const r = await vault.unlock(a).catch(() => ({}));
    p1.value = "";
    if (r && r.ok) { msg(""); afterUnlock(); } else msg("Contraseña incorrecta.");
  };

  const doUnlockPasskey = async () => {
    msg("Pon tu huella / Face ID…");
    const r = await vault.unlockPasskey();
    if (r.ok) { msg(""); afterUnlock(); } else msg(r.error || "No se pudo desbloquear con la passkey.");
  };

  const doEnrollPasskey = async () => {
    msg("Registrando este dispositivo…");
    const r = await vault.enrollPasskey();
    await refreshStatus();
    msg(r.ok ? "Dispositivo registrado. Ya puedes desbloquear con la huella." : (r.error || "No se pudo registrar."));
  };

  const doChange = async () => {
    const o = (op1.value || "").trim(), a = (np1.value || "").trim(), b = (np2.value || "").trim();
    if (a.length < 4 || a !== b) return msg("La nueva contraseña no es válida o no coincide.");
    const r = await vault.change(o, a);
    op1.value = np1.value = np2.value = "";
    msg(r.ok ? "Contraseña cambiada." : "La contraseña actual no es correcta.");
    if (r.ok) refreshStatus();
  };

  const copyValue = async () => {
    const v = store.vaultRevealed(); if (!v) return;
    try { await navigator.clipboard.writeText(v.value); msg("Copiado al portapapeles."); } catch (_) { msg("No se pudo copiar."); }
  };

  const field = (setRef, ph, opts = {}) =>
    h("input", { ref: setRef, class: "vault-in", type: "password", placeholder: ph, autocomplete: "off",
      onKeydown: (e) => { if (e.key === "Enter" && opts.onEnter) opts.onEnter(); } });

  const passkeyBtns = (mode) => {
    if (!vault.passkeySupported()) return null;
    const st = store.vaultStatus();
    if (mode === "unlock" && (st.methods || []).includes("passkey"))
      return h("button", { class: "vault-b ghost", onClick: doUnlockPasskey }, raw(KEY_ICON), "Usar huella / Face ID");
    return null;
  };

  const body = () => {
    const mode = store.vaultMode();
    if (mode === "create") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, "Crea una contraseña maestra para guardar tus secretos cifrados (contraseñas, IBAN, claves). Solo tú la conoces; sin ella no se pueden leer."),
      field(el => (p1 = el), "contraseña maestra", { onEnter: doCreate }),
      field(el => (p2 = el), "repite la contraseña", { onEnter: doCreate }),
      h("button", { class: "vault-b", onClick: doCreate }, "Crear bóveda"),
    );
    if (mode === "unlock") return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, "Desbloquea tu bóveda para acceder a tus secretos."),
      field(el => (p1 = el), "contraseña de la bóveda", { onEnter: doUnlock }),
      h("button", { class: "vault-b", onClick: doUnlock }, "Desbloquear"),
      passkeyBtns("unlock"),
    );
    if (mode === "reveal") {
      const v = store.vaultRevealed() || {};
      return h("div", { class: "vault-body" },
        h("p", { class: "vault-lead" }, v.label || "Secreto"),
        h("div", { class: "vault-secret" }, v.value || ""),
        h("div", { class: "vault-row" },
          h("button", { class: "vault-b", onClick: copyValue }, "Copiar"),
          h("button", { class: "vault-b ghost", onClick: store.closeVault }, "Ocultar"),
        ),
      );
    }
    // manage
    const st = store.vaultStatus();
    return h("div", { class: "vault-body" },
      h("p", { class: "vault-lead" }, `Bóveda ${st.unlocked ? "desbloqueada" : "bloqueada"} · ${st.secret_count || 0} secretos guardados.`),
      st.unlocked ? null : h("button", { class: "vault-b", onClick: () => store.setVaultMode("unlock") }, "Desbloquear"),
      (st.unlocked && vault.passkeySupported())
        ? h("button", { class: "vault-b ghost", onClick: doEnrollPasskey }, raw(KEY_ICON), "Registrar este dispositivo (huella)")
        : null,
      h("div", { class: "vault-sep" }, "Cambiar contraseña maestra"),
      field(el => (op1 = el), "contraseña actual"),
      field(el => (np1 = el), "nueva contraseña"),
      field(el => (np2 = el), "repite la nueva", { onEnter: doChange }),
      h("button", { class: "vault-b ghost", onClick: doChange }, "Cambiar contraseña"),
    );
  };

  return h("div", { class: () => "vault-modal" + (store.vaultOpen() ? " open" : "") },
    h("div", { class: "vault-card" },
      h("div", { class: "vault-head" },
        h("span", { class: "vault-title" }, raw(LOCK_ICON), "Bóveda de secretos"),
        h("button", { class: "vault-x", title: "Cerrar", onClick: store.closeVault }, raw(CLOSE_ICON)),
      ),
      () => body(),
      h("div", { class: () => "vault-msg" + (store.vaultMsg() ? " show" : "") }, () => store.vaultMsg()),
    ),
  );
}

// ============================================================================
// vault.js — client for the secret VAULT (V2-060). Talks to /api/vault/* and
// manages PASSKEYS (WebAuthn `prf` extension, Touch ID / Windows Hello).
//
// Model (details in zaelar-security.md): the passphrase or the passkey PRF
// unlock the SAME private key on the SERVER (convenience mode — the default). The
// secret value is served through /api/vault/reveal (loopback), NEVER through the
// event bus or the LLM. Biometrics belong to the BROWSER; if unavailable, use the passphrase.
// ============================================================================
import { t } from "../core/i18n.js?v=1";

const json = (r) => r.json();
const postJSON = (url, body) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

// ---- REST ----
export const status   = () => fetch("/api/vault/status", { cache: "no-store" }).then(json).catch(() => ({ exists: false }));
export const create   = (passphrase) => postJSON("/api/vault/create", { passphrase }).then(json);
export const unlock   = (passphrase, hold = true) => postJSON("/api/vault/unlock", { passphrase, hold }).then(json);
export const lock     = () => postJSON("/api/vault/lock", {}).then(json);
export const change   = (oldP, newP) => postJSON("/api/vault/change", { old: oldP, new: newP });
export const secrets  = () => fetch("/api/vault/secrets", { cache: "no-store" }).then(json).catch(() => ({ secrets: [] }));
// reveal → 200 {value} · 423 locked (open modal) · 403 wrong passphrase · 404 does not exist
export async function reveal(memory_id, passphrase) {
  const r = await postJSON("/api/vault/reveal", passphrase != null ? { memory_id, passphrase } : { memory_id });
  if (r.status === 423) return { locked: true };
  if (!r.ok) return { error: (await r.json().catch(() => ({}))).detail || ("HTTP " + r.status) };
  return r.json();
}

// ---- WebAuthn / passkeys (PRF extension) ----
export const passkeySupported = () =>
  !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);

const _b64ToBytes = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const _bytesToB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const _b64url = (buf) => _bytesToB64(buf).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function _challenge() { return fetch("/api/vault/passkey/challenge", { cache: "no-store" }).then(json); }

// ENROLL this device: create a platform passkey, derive the PRF with the vault salt, and send it to the server
// (which wraps the private key under that PRF). Requires the vault to be UNLOCKED. Returns {ok} or {error}.
export async function enrollPasskey() {
  try {
    const ch = await _challenge();
    if (!ch.prf_salt) return { error: t("vaultsvc.no_vault_yet") };
    const salt = _b64ToBytes(ch.prf_salt);
    const userId = crypto.getRandomValues(new Uint8Array(16));
    const cred = await navigator.credentials.create({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rp: { name: "Zaelar", id: location.hostname },
        user: { id: userId, name: "zaelar-vault", displayName: "Zaelar vault" },
        pubKeyCredParams: [{ type: "public-key", alg: -7 }, { type: "public-key", alg: -257 }],
        authenticatorSelection: { residentKey: "preferred", userVerification: "required" },
        extensions: { prf: { eval: { first: salt } } },
        timeout: 60000,
      },
    });
    if (!cred) return { error: t("vaultsvc.cancelled") };
    // the PRF may come from creation; otherwise obtain it with an immediate get() (robust cross-browser pattern)
    let prf = cred.getClientExtensionResults?.()?.prf?.results?.first;
    if (!prf) {
      const asrt = await navigator.credentials.get({
        publicKey: {
          challenge: crypto.getRandomValues(new Uint8Array(32)),
          rpId: location.hostname,
          allowCredentials: [{ type: "public-key", id: new Uint8Array(cred.rawId) }],
          userVerification: "required",
          extensions: { prf: { eval: { first: salt } } },
          timeout: 60000,
        },
      });
      prf = asrt?.getClientExtensionResults?.()?.prf?.results?.first;
    }
    if (!prf) return { error: t("vaultsvc.no_prf") };
    const r = await postJSON("/api/vault/passkey/enroll",
      { cred_id: _b64url(cred.rawId), prf_secret: _bytesToB64(prf) });
    if (r.status === 423) return { error: t("vaultsvc.unlock_first") };
    if (!r.ok) return { error: (await r.json().catch(() => ({}))).detail || t("vaultsvc.couldnt_register") };
    return { ok: true };
  } catch (e) { return { error: (e && e.message) || t("vaultsvc.passkey_cancelled") }; }
}

// UNLOCK with a registered passkey (biometrics). Returns {ok} or {error}.
export async function unlockPasskey(hold = true) {
  try {
    const ch = await _challenge();
    if (!ch.prf_salt || !ch.cred_ids || !ch.cred_ids.length) return { error: t("vaultsvc.no_passkeys") };
    const salt = _b64ToBytes(ch.prf_salt);
    const allow = ch.cred_ids.map(id => ({
      type: "public-key",
      id: _b64ToBytes(id.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((id.length + 3) % 4)),
    }));
    const asrt = await navigator.credentials.get({
      publicKey: {
        challenge: crypto.getRandomValues(new Uint8Array(32)),
        rpId: location.hostname,
        allowCredentials: allow,
        userVerification: "required",
        extensions: { prf: { eval: { first: salt } } },
        timeout: 60000,
      },
    });
    const prf = asrt?.getClientExtensionResults?.()?.prf?.results?.first;
    if (!prf) return { error: t("vaultsvc.couldnt_read_fp") };
    const r = await postJSON("/api/vault/passkey/unlock", { prf_secret: _bytesToB64(prf), hold }).then(json);
    return r.ok ? { ok: true } : { error: t("vaultsvc.passkey_didnt_open") };
  } catch (e) { return { error: (e && e.message) || t("vaultsvc.passkey_cancelled") }; }
}

// ============================================================================
// vault.js — cliente de la BÓVEDA de secretos (V2-060). Habla con /api/vault/* y
// gestiona los PASSKEYS (WebAuthn extensión `prf`, Touch ID / Windows Hello).
//
// Modelo (detalle en zaelar-security.md): la passphrase o el PRF de la passkey
// desbloquean la MISMA clave privada en el SERVER (modo cómodo — el default). El
// valor del secreto se sirve por /api/vault/reveal (loopback), NUNCA por el bus de
// eventos ni por el LLM. La biometría es del NAVEGADOR; si no hay, se usa passphrase.
// ============================================================================
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
// reveal → 200 {value} · 423 bloqueada (abrir modal) · 403 passphrase mala · 404 no existe
export async function reveal(memory_id, passphrase) {
  const r = await postJSON("/api/vault/reveal", passphrase != null ? { memory_id, passphrase } : { memory_id });
  if (r.status === 423) return { locked: true };
  if (!r.ok) return { error: (await r.json().catch(() => ({}))).detail || ("HTTP " + r.status) };
  return r.json();
}

// ---- WebAuthn / passkeys (extensión PRF) ----
export const passkeySupported = () =>
  !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);

const _b64ToBytes = (b64) => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
const _bytesToB64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const _b64url = (buf) => _bytesToB64(buf).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function _challenge() { return fetch("/api/vault/passkey/challenge", { cache: "no-store" }).then(json); }

// ENROLA este aparato: crea una passkey de plataforma, deriva el PRF con el salt de la bóveda y lo manda al server
// (que envuelve la clave privada bajo ese PRF). Requiere la bóveda DESBLOQUEADA. Devuelve {ok} o {error}.
export async function enrollPasskey() {
  try {
    const ch = await _challenge();
    if (!ch.prf_salt) return { error: "no hay bóveda" };
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
    if (!cred) return { error: "cancelado" };
    // el PRF puede venir en la creación; si no, se obtiene con un get() inmediato (patrón robusto multi-navegador)
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
    if (!prf) return { error: "este dispositivo no soporta PRF (usa la contraseña)" };
    const r = await postJSON("/api/vault/passkey/enroll",
      { cred_id: _b64url(cred.rawId), prf_secret: _bytesToB64(prf) });
    if (r.status === 423) return { error: "desbloquea la bóveda primero" };
    if (!r.ok) return { error: (await r.json().catch(() => ({}))).detail || "no se pudo registrar" };
    return { ok: true };
  } catch (e) { return { error: (e && e.message) || "passkey cancelada" }; }
}

// DESBLOQUEA con una passkey registrada (biometría). Devuelve {ok} o {error}.
export async function unlockPasskey(hold = true) {
  try {
    const ch = await _challenge();
    if (!ch.prf_salt || !ch.cred_ids || !ch.cred_ids.length) return { error: "no hay passkeys registradas" };
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
    if (!prf) return { error: "no se pudo leer la huella" };
    const r = await postJSON("/api/vault/passkey/unlock", { prf_secret: _bytesToB64(prf), hold }).then(json);
    return r.ok ? { ok: true } : { error: "la passkey no abrió la bóveda" };
  } catch (e) { return { error: (e && e.message) || "passkey cancelada" }; }
}

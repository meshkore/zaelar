"""memory/vault_api.py — API HTTP de la BÓVEDA de secretos (V2-060).

Es lo que POSTEA el **modal nativo del frontend** (crear passphrase / desbloquear) y lo que conduce el **tester**
en el dominio de prueba «seguridad de datos» (que no puede usar biometría → usa la passphrase). Endpoints:

  GET  /api/vault/status              → estado redactado (exists/unlocked/methods/secret_count)
  POST /api/vault/create   {passphrase}        → crea la bóveda
  POST /api/vault/unlock   {passphrase, hold?} → desbloquea (hold=True cómodo, RAM; False estricto/transitorio)
  POST /api/vault/lock                 → bloquea (borra la clave de RAM)
  POST /api/vault/change   {old,new}   → rota la passphrase
  GET  /api/vault/secrets              → lista de ETIQUETAS (nunca valores)
  POST /api/vault/reveal   {memory_id, passphrase?}  → descifra y devuelve el VALOR

**Seguridad**: los endpoints que manejan passphrase o devuelven un secreto en claro son **loopback-only** (mismo
patrón que el plano de control de meshkore) — un origen remoto no puede exfiltrar. El descifrado en el NAVEGADOR
(modo estricto, zero-knowledge) es F3; hoy `reveal` descifra en el servidor (modo cómodo, para servir por voz).
La autenticación remota/cloud queda para la fase cloud (F4).
"""
from __future__ import annotations

from base64 import b64decode

from fastapi import APIRouter, Body, HTTPException, Request

from . import vault as _vault

router = APIRouter()

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _guard(request: Request) -> None:
    host = (request.client.host if request.client else "") or ""
    if host not in _LOOPBACK:
        raise HTTPException(status_code=403, detail="vault API is loopback-only")


@router.get("/api/vault/status")
async def vault_status():
    return _vault.status()


@router.post("/api/vault/create")
async def vault_create(request: Request, passphrase: str = Body(..., embed=True)):
    _guard(request)
    try:
        _vault.create(passphrase)
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _vault.status()


@router.post("/api/vault/unlock")
async def vault_unlock(request: Request, passphrase: str = Body(..., embed=True),
                       hold: bool = Body(True, embed=True)):
    _guard(request)
    try:
        ok = _vault.unlock(passphrase, hold=hold)
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": ok, **_vault.status()}


@router.post("/api/vault/lock")
async def vault_lock():
    _vault.lock()
    return _vault.status()


@router.post("/api/vault/change")
async def vault_change(request: Request, old: str = Body(..., embed=True), new: str = Body(..., embed=True)):
    _guard(request)
    try:
        _vault.change_passphrase(old, new)
    except _vault.WrongPassphrase:
        raise HTTPException(status_code=403, detail="passphrase actual incorrecta")
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **_vault.status()}


@router.get("/api/vault/secrets")
async def vault_secrets():
    return {"secrets": _vault.list_secrets()}


@router.get("/api/vault/passkey/challenge")
async def vault_passkey_challenge():
    """Datos NO secretos para el reto de WebAuthn del navegador (salt del PRF + credenciales registradas)."""
    return _vault.passkey_meta()


@router.post("/api/vault/passkey/enroll")
async def vault_passkey_enroll(request: Request, cred_id: str = Body(..., embed=True),
                               prf_secret: str = Body(..., embed=True)):
    """Registra este aparato (requiere la bóveda DESBLOQUEADA). `prf_secret` = 32 bytes en base64."""
    _guard(request)
    try:
        _vault.add_passkey(b64decode(prf_secret), cred_id)
    except _vault.VaultLocked:
        raise HTTPException(status_code=423, detail="locked")
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **_vault.status()}


@router.post("/api/vault/passkey/unlock")
async def vault_passkey_unlock(request: Request, prf_secret: str = Body(..., embed=True),
                               hold: bool = Body(True, embed=True)):
    """Desbloquea con el secreto PRF de una passkey. `prf_secret` = 32 bytes en base64."""
    _guard(request)
    try:
        ok = _vault.unlock_with_prf(b64decode(prf_secret), hold=hold)
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": ok, **_vault.status()}


@router.post("/api/vault/passkey/remove")
async def vault_passkey_remove(request: Request, cred_id: str = Body(..., embed=True)):
    _guard(request)
    try:
        _vault.remove_passkey(cred_id)
    except _vault.VaultError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **_vault.status()}


@router.post("/api/vault/reveal")
async def vault_reveal(request: Request, memory_id: int = Body(..., embed=True),
                       passphrase: str | None = Body(None, embed=True)):
    _guard(request)
    try:
        value = _vault.open_secret(memory_id, passphrase=passphrase)
    except _vault.VaultLocked:
        # señal para el frontend: abre el modal de passphrase
        raise HTTPException(status_code=423, detail="locked")   # 423 Locked
    except _vault.WrongPassphrase:
        raise HTTPException(status_code=403, detail="passphrase incorrecta")
    except _vault.VaultError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"memory_id": memory_id, "value": value}

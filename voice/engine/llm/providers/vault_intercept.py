"""voice/engine/llm/providers/vault_intercept.py — deterministic vault/secrets pre-flight checks (split out of
nucleo.py's `_run_inner`, 2026-08-17 modularization pass, extraction step 1 of the plan in the audit that led to
this: the smallest, most self-contained slice of the ~1600-line closure-heavy body, done first to prove the
"extract a slice of `_run_inner` into a callable with explicit params" pattern on this specific file before
touching anything riskier).

Two intercepts, both V2-060 (bóveda de secretos): a security-config voice command ("no me digas los secretos
por voz") and a spoken secret ("mi contraseña de Netflix es X") — both must be handled DETERMINISTA, before the
model ever sees the text, so a secret value never reaches the LLM and a config command never gets rephrased by
a non-reasoning model that might refuse it ("no puedo guardar contraseñas").

`try_vault_intercept()` returns True if it fully handled the turn (the caller must `return` immediately,
exactly like the inline `return` this replaces) or False if neither intercept applies (continue normal turn
processing). `send`/`emit` are passed in explicitly rather than imported fresh: `send` is `_run_inner`'s local
closure over turn state (spoken/first_ms/brain._last_spoken/_last_reply — see nucleo.py), and `emit` may have
been locally overridden to a no-op in some error paths — passing the exact live callables preserves behavior
identically to the inline version."""
from __future__ import annotations

import asyncio

from loguru import logger

from voice import speech


async def try_vault_intercept(text: str, first_turn: bool, send, emit) -> bool:
    # COMANDO DE CONFIG DE SEGURIDAD (V2-060 F2): «no me digas los secretos por voz» / «modo máxima seguridad» /
    # «puedes leérmelos por voz» = USER RULE DURA — se aplica DETERMINISTA (persiste en state.security) y se
    # confirma, sin pasar por el modelo (el FlashBrain sigue no-razonador). Short-circuit como el degradado.
    if not first_turn:
        try:
            from nucleo.flash import vault_rules as _vrules
            _cfg_cmd = _vrules.detect(text)
        except Exception:
            _cfg_cmd = None
        if _cfg_cmd is not None:
            _cfg_line = _vrules.apply(_cfg_cmd)
            emit("secret", "config", role="system", extra={"key": _cfg_cmd[0], "value": _cfg_cmd[1]})
            send(speech.sanitize(_cfg_line, drop_metadata=False))
            return True

    # GUARDAR UN SECRETO (V2-060, fix 2026-07-21): si el operador DICE un secreto (contraseña/IBAN/…), el valor
    # NO puede pasar por el modelo → se intercepta DETERMINISTA aquí (como el comando de config): se CIFRA en la
    # bóveda y se confirma EN el turno, sin que el no-razonador rehúse («no puedo guardar contraseñas»). El
    # auto-vaulting de la ingesta es la red de fondo; esto es la RESPUESTA hablada. El valor jamás llega al LLM.
    if not first_turn:
        try:
            from memory import secrets as _secrets0
            _sec_found = _secrets0.detect(text)
        except Exception:
            _sec_found = []
        if _sec_found:
            from voice.engine.core import langs as _lg0
            _L0 = _lg0.current_language()
            try:
                from memory import vault as _vault0
                _has_vault = _vault0.exists()
            except Exception:
                _vault0, _has_vault = None, False
            if _has_vault:
                _saved = 0
                for _d in _sec_found:
                    try:
                        await asyncio.to_thread(_vault0.store_secret, _d.label, _d.value,
                                                slot=_d.slot, sensitivity=_d.sensitivity)
                        _saved += 1
                    except Exception as _e:  # noqa: BLE001
                        logger.warning(f"guardar secreto {_d.label!r} falló: {_e}")
                emit("secret", "saved", role="system",
                     extra={"n": _saved, "labels": [d.label for d in _sec_found]})
                send(speech.sanitize(_L0.secret_saved, drop_metadata=False))
            else:
                emit("secret", "no_vault", role="system")   # el frontend abre el modal de crear bóveda
                send(speech.sanitize(_L0.secret_need_vault, drop_metadata=False))
            return True

    return False

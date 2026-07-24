"""nucleo/flash/vault_flow.py — flujo de LECTURA de secretos del FlashBrain (V2-060 F1b).

Cuando el operador pide un secreto guardado («dame la contraseña de Netflix»), el FlashBrain llama a la tool
`reveal_secret(label)`. Este módulo resuelve la ETIQUETA a un secreto de la bóveda y decide el desenlace, SIN que
el valor pase JAMÁS por el modelo:

  - `no_vault`   → no hay bóveda: el FlashBrain propone crearla.
  - `empty`      → hay bóveda pero ningún secreto guardado.
  - `not_found`  → no casa ninguna etiqueta: el FlashBrain lo dice (y sugiere las que hay).
  - `locked`     → la bóveda está bloqueada: el FlashBrain pide la passphrase (el provider abre el modal nativo).
  - `ok`         → desbloqueada: devuelve el VALOR para que el provider lo entregue **OUT-OF-BAND** (voz/pantalla
                   según las reglas), nunca metiéndolo en un prompt.

`reveal()` devuelve un dict; SOLO el caso `ok` incluye `value`. La resolución de etiqueta es difusa (stdlib
`difflib` + solape de tokens, acento-insensible) y CONSERVADORA: si es ambiguo o no llega al umbral → `not_found`
con candidatos, nunca sirve el secreto equivocado. Depende solo de `memory.vault` (no del provider) → testeable.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from memory import vault as _vault


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9\s]+", " ", s).strip()


_STOP = {"la", "el", "de", "del", "mi", "mis", "una", "un", "dame", "dime", "cual", "cuál", "es", "para",
         "contrasena", "contraseña", "clave", "password", "pin", "codigo", "código", "secreto", "acceso",
         "usuario", "y", "cuenta", "numero", "número", "necesito", "quiero", "ensename", "enséñame", "muestrame",
         "dime", "recuerdame", "recuérdame", "que", "tengo"}


def _tokens(s: str) -> set[str]:
    return {t for t in _norm(s).split() if t and t not in _STOP and len(t) > 1}


def resolve_label(query: str, secrets: list[dict]) -> dict | None:
    """Devuelve el secreto ({memory_id,label,slot,sensitivity}) que mejor casa la query, o None si ambiguo/lejano.

    Prioriza el solape de tokens SIGNIFICATIVOS (el nombre del servicio: 'netflix', 'wifi'); desempata con la
    similitud difusa del texto completo. Umbral conservador: sin señal clara → None (mejor preguntar que servir
    el secreto equivocado)."""
    if not secrets:
        return None
    qt = _tokens(query)
    scored = []
    for s in secrets:
        lt = _tokens(s["label"])
        overlap = len(qt & lt)
        ratio = difflib.SequenceMatcher(None, _norm(query), _norm(s["label"])).ratio()
        scored.append((overlap, ratio, s))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best = scored[0]
    # gana por token significativo compartido, o por alta similitud difusa
    if best[0] >= 1 or best[1] >= 0.6:
        # ambigüedad: dos candidatos empatados en el mejor solape de tokens → no adivinar
        if len(scored) > 1 and scored[1][0] == best[0] and best[0] >= 1 and \
                abs(scored[1][1] - best[1]) < 0.08:
            return None
        return best[2]
    return None


def reveal(query: str) -> dict:
    """Resuelve una petición de secreto. SOLO el caso 'ok' trae `value` (para entrega out-of-band por el provider)."""
    try:
        if not _vault.exists():
            return {"status": "no_vault"}
        secrets = _vault.list_secrets()
        if not secrets:
            return {"status": "empty"}
        hit = resolve_label(query, secrets)
        if hit is None:
            return {"status": "not_found", "candidates": [s["label"] for s in secrets][:6]}
        mid, label = hit["memory_id"], hit["label"]
        if not _vault.is_unlocked():
            return {"status": "locked", "memory_id": mid, "label": label,
                    "sensitivity": hit.get("sensitivity", "high")}
        value = _vault.open_secret(mid)
        return {"status": "ok", "memory_id": mid, "label": label, "value": value,
                "sensitivity": hit.get("sensitivity", "high")}
    except _vault.VaultLocked:
        return {"status": "locked"}
    except Exception:  # noqa: BLE001 — fail-safe: nunca revienta el turno de voz
        return {"status": "error"}

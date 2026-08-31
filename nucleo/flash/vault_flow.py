"""nucleo/flash/vault_flow.py — FlashBrain secret READ flow (V2-060 F1b).

When the operator requests a stored secret (“give me the Netflix password”), FlashBrain calls the
`reveal_secret(label)` tool. This module resolves the LABEL to a vault secret and decides the outcome, WITHOUT the
value EVER passing through the model:

  - `no_vault`   → no vault exists: FlashBrain proposes creating one.
  - `empty`      → a vault exists but no secrets are stored.
  - `not_found`  → no label matches: FlashBrain says so (and suggests the available ones).
  - `locked`     → the vault is locked: FlashBrain requests the passphrase (the provider opens the native modal).
  - `ok`         → unlocked: returns the VALUE for the provider to deliver **OUT-OF-BAND** (voice/screen
                   according to the rules), never putting it into a prompt.

`reveal()` returns a dict; ONLY the `ok` case includes `value`. Label resolution is fuzzy (stdlib
`difflib` + token overlap, accent-insensitive) and CONSERVATIVE: if it is ambiguous or does not reach the threshold
→ `not_found` with candidates; it never serves the wrong secret. It depends only on `memory.vault` (not the provider)
→ testable.
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
    """Return the secret ({memory_id,label,slot,sensitivity}) that best matches the query, or None if ambiguous/remote.

    Prioritize the overlap of SIGNIFICANT tokens (the service name: 'netflix', 'wifi'); break ties with the
    fuzzy similarity of the full text. Conservative threshold: without a clear signal → None (better to ask than
    serve the wrong secret)."""
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
    # wins by a shared significant token, or by high fuzzy similarity
    if best[0] >= 1 or best[1] >= 0.6:
        # ambiguity: two candidates tied for the best token overlap → do not guess
        if len(scored) > 1 and scored[1][0] == best[0] and best[0] >= 1 and \
                abs(scored[1][1] - best[1]) < 0.08:
            return None
        return best[2]
    return None


def reveal(query: str) -> dict:
    """Resolve a secret request. ONLY the 'ok' case contains `value` (for out-of-band delivery by the provider)."""
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
    except Exception:  # noqa: BLE001 — fail-safe: never crashes the voice turn
        return {"status": "error"}

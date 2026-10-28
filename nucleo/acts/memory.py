"""The memory door's vault half (V2-060; refactor2710-06 T-04): what a spoken secret leaves of the turn, which stored
secret a request names, and the hard rule of whether secrets are read aloud. `nucleo/turn/vault_gate` is the one
caller; a secret's VALUE never reaches a model on any of these paths.

  · `secret_is_the_whole_turn` — V2-141: the intercept consumes the turn only when the secret IS the turn. A carrier
    phrase is short by nature («my X is»), a request carrying an IBAN is not (measured 3-5 content words against
    18-24); the threshold sits in that gap, on the side that keeps the request.
  · `reveal` — the label resolved CONSERVATIVELY (shared significant token, else high fuzzy similarity; a tie is
    `not_found` with candidates): it never serves the wrong secret. Only `ok` carries `value`, for out-of-band delivery.
  · `rule_of` / `apply_rule` — «don't say my secrets aloud» is a HARD rule in `state.security`, applied in code.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from loguru import logger

from memory import vault as _vault

#: Middle of the measured gap (6 → 18): any value from ~8 to ~15 separates the two classes, so it is not load-bearing.
CARRIER_MAX_WORDS = 10


def _note(what: str) -> None:
    logger.debug(f"acts.memory: {what}")


def leftover_words(text: str, detected) -> int:
    """Content words left once every detected secret VALUE and the redaction marker are taken out."""
    rest = text or ""
    for d in detected or []:
        if getattr(d, "value", ""):
            rest = rest.replace(d.value, " ")
    return sum(any(c.isalnum() for c in w) for w in rest.replace("«secreto guardado»", " ").split())


def secret_is_the_whole_turn(text: str, detected) -> bool:
    """True when the turn carries nothing but the secret and its carrier phrase; False when a request is left in it
    and the turn goes on (on the REDACTED text)."""
    return bool(detected) and leftover_words(text, detected) <= CARRIER_MAX_WORDS


# ── reveal ───────────────────────────────────────────────────────────────────────────────────────────────────

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
    """The secret (`{memory_id, label, slot, sensitivity}`) the query names, or None when it is ambiguous or remote:
    the service name's overlap first, the whole text's fuzzy similarity to break ties."""
    if not secrets:
        return None
    qt = _tokens(query)
    scored = sorted(((len(qt & _tokens(s["label"])), difflib.SequenceMatcher(None, _norm(query), _norm(s["label"])).ratio(), s)
                     for s in secrets), key=lambda x: (x[0], x[1]), reverse=True)
    best = scored[0]
    if best[0] < 1 and best[1] < 0.6:
        return None
    if len(scored) > 1 and scored[1][0] == best[0] and best[0] >= 1 and abs(scored[1][1] - best[1]) < 0.08:
        return None                                     # two candidates tied on the service name: do not guess
    return best[2]


def reveal(query: str) -> dict:
    """`{status}` — no_vault · empty · not_found (+candidates) · locked · ok (+value) · error. Never raises."""
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
            return {"status": "locked", "memory_id": mid, "label": label, "sensitivity": hit.get("sensitivity", "high")}
        return {"status": "ok", "memory_id": mid, "label": label, "value": _vault.open_secret(mid),
                "sensitivity": hit.get("sensitivity", "high")}
    except _vault.VaultLocked:
        return {"status": "locked"}
    except Exception as e:  # noqa: BLE001 — fail-safe: a broken reveal never takes the voice turn down
        _note(f"reveal failed ({e!r})")
        return {"status": "error"}


# ── the hard rule: are secrets read aloud? ─────────────────────────────────────────────────────────────────

_SECRET_WORD = r"(?:secretos?|secrets?|contrase[nñ]as?|claves?|datos? (?:privados?|protegidos?)|passwords?)"
_BY_VOICE = r"(?:en voz alta|por voz|hablando|en alto|out loud|aloud|by voice)"
_NEG = r"(?:no|nunca|don'?t|do not|never)"
_NO_VOICE_RE = re.compile(
    rf"\b{_NEG}\b[^.]*\b(?:digas|leas|menciones|reproduzcas|say|read|tell)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b{_SECRET_WORD}\b[^.]*\bsolo (?:en|por) pantalla\b"
    rf"|\bmodo (?:de )?maxima seguridad\b",
)
_YES_VOICE_RE = re.compile(
    rf"\b(?:si|puedes|vale|ok)\b[^.]*\b(?:decir|leer|say|read)\w*\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\b(?:dime|leeme|read me|read)\b[^.]*{_SECRET_WORD}[^.]*{_BY_VOICE}"
    rf"|\bmodo (?:de )?comod\w*\b[^.]*{_SECRET_WORD}",
)


def rule_of(text: str) -> tuple[str, object] | None:
    """`("secrets_voice", bool)` when the turn sets the vault's voice rule; None otherwise. NO wins (safer)."""
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    if not t:
        return None
    if _NO_VOICE_RE.search(t):
        return ("secrets_voice", False)
    if _YES_VOICE_RE.search(t):
        return ("secrets_voice", True)
    return None


def apply_rule(cmd: tuple[str, object]) -> str:
    """Persist the rule in `state.security` and return the confirmation in his language."""
    key, value = cmd
    try:
        from memory import state as _state
        _state.set_security_flag(key, value)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.memory: the vault rule was not stored ({e!r})")
    try:
        from i18n import langs as _lg
        es = _lg.current_language().code == "es"
    except Exception as e:  # noqa: BLE001
        _note(f"no language ({e!r})")
        es = True
    if key == "secrets_voice":
        if value:
            return "Vale, te leeré los secretos en voz alta cuando me los pidas." if es \
                else "Alright, I'll read secrets aloud when you ask."
        return "Hecho: no diré tus secretos en voz alta, solo te los mostraré en pantalla." if es \
            else "Done: I won't say your secrets aloud, I'll only show them on screen."
    return "Hecho." if es else "Done."

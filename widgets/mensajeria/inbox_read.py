"""inbox_read.py — what the INBOX tells the brain: a summary that rides the prompt, and an answer to a question.

Two seams, both optional contracts the reader already looks for, and this widget published NEITHER. Measured
2026-09-15 with ten real messages sitting in the store: `refs.prompt_digest("mensajeria")` returned 0 characters
and so did `nucleo/flash/widget_read.read`. So «¿me ha escrito alguien?», «¿qué quería Marta?», «¿tengo algo
urgente?» reached the model with an EMPTY block — and an empty block answers "no", confidently, about messages
that are on screen. The agenda and the directory had a poor answer; this one had none at all, which is the same
failure with the volume turned up.

  · `prompt_digest()` — the always-on summary, for the turns where the card is open. Bounded and shallow: who
    wrote, on which platform, one line of what they said. It rides EVERY turn, so it carries no addresses and no
    identifiers, the same rule `contactos` follows.
  · `read_query(question)` — the messages the question is ABOUT, searched across the whole inbox. Fuller,
    because it was asked for.

Written as its own module because `data.py` is a hundred lines under the architecture ratchet's ceiling for an
unlisted file, and a seam is not a reason to spend that margin.
"""
from __future__ import annotations

import re
import time
import unicodedata as _ud

_MAX_DIGEST_ROWS = 10        # the summary is a glance: who is waiting, not the inbox
_MAX_ANSWER_ROWS = 8
_MAX_BODY_DIGEST = 90
_MAX_BODY_ANSWER = 300

#: Scaffolding, not subject. A question is mostly this, and matching on it returns the whole inbox — which is
#: what the summary already is, and the reason this door exists.
_STOP = {
    "que", "qué", "quien", "quién", "cual", "cuál", "cuando", "cuándo", "donde", "dónde", "como", "cómo",
    "mensaje", "mensajes", "correo", "correos", "email", "emails", "chat", "chats", "bandeja", "escrito",
    "escribio", "escribió", "dijo", "dice", "dicho", "hay", "tengo", "tienes", "algo", "alguien", "algun",
    "algún", "alguna", "nuevo", "nueva", "nuevos", "nuevas", "sin", "leer", "leido", "leído", "ultimo",
    "último", "ultima", "última", "del", "de", "la", "el", "los", "las", "un", "una", "y", "o", "con", "para",
    "por", "en", "a", "al", "mi", "me", "se", "lo", "su", "sobre", "acerca", "dime", "dame", "muestra",
    "message", "messages", "mail", "inbox", "unread", "new", "any", "anyone", "anybody", "something",
    "what", "who", "whom", "when", "where", "which", "how", "the", "a", "an", "is", "are", "was", "were",
    "do", "does", "did", "have", "has", "had", "i", "my", "of", "on", "at", "in", "for", "with", "and", "or",
    "about", "tell", "show", "give", "said", "says", "say", "from", "there", "read", "latest", "last",
}


def _norm(s) -> str:
    s = _ud.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not _ud.combining(c))


def _terms(question: str) -> list[str]:
    words = [w for w in re.split(r"[^\wÁÉÍÓÚÜÑáéíóúüñ@.]+", _norm(question)) if len(w) > 2]
    return [w for w in dict.fromkeys(words) if w not in _STOP][:8]


def _items() -> list[dict]:
    """The same list the card shows — muted channels already dropped, `highlight` already computed. Asking
    `data` for it rather than reading the store is what keeps what the brain says and what the screen shows
    from being two different inboxes."""
    try:
        from . import data as _data
        return list(_data._visible_items(_data.load_db()) or [])
    except Exception:                                    # noqa: BLE001 — a broken inbox tells nothing
        return []


def _who(it: dict) -> str:
    who = str(it.get("from") or it.get("senderName") or it.get("senderId") or "alguien")
    if it.get("isGroup") and it.get("group"):
        who += f" (grupo «{str(it['group'])[:40]}»)"
    return who


def _when(it: dict) -> str:
    try:
        ts = float(it.get("ts") or 0)
    except (TypeError, ValueError):
        return ""
    if not ts:
        return ""
    mins = max(0, int((time.time() - ts) / 60))
    if mins < 60:
        return f"hace {mins} min"
    if mins < 60 * 36:
        return f"hace {mins // 60} h"
    return time.strftime("%d/%m", time.localtime(ts))


def _row(it: dict, body_cap: int) -> str:
    bits = [str(it.get("platform") or "?"), _who(it)]
    when = _when(it)
    if when:
        bits.append(when)
    if str(it.get("urgencia") or "") in ("alta", "urgente"):
        bits.append("URGENTE")
    if it.get("mediaType"):
        bits.append(str(it["mediaType"]))
    head = " · ".join(bits)
    body = re.sub(r"\s+", " ", str(it.get("body") or "")).strip()[:body_cap]
    return f"· {head}: «{body}»" if body else f"· {head}"


def prompt_digest() -> str:
    """Who is waiting, in one glance. "" when the inbox is empty — an empty inbox has nothing to say, and
    saying «no tienes mensajes» from here would be this module asserting something the reader should infer."""
    items = _items()
    if not items:
        return ""
    plats: dict = {}
    for it in items:
        plats[str(it.get("platform") or "?")] = plats.get(str(it.get("platform") or "?"), 0) + 1
    head = (f"BANDEJA: {len(items)} mensaje{'s' if len(items) != 1 else ''} sin atender ("
            + ", ".join(f"{n} de {p}" for p, n in sorted(plats.items(), key=lambda t: -t[1])) + "). "
            "Es un RESUMEN de los más recientes: si preguntan por uno que no esté aquí, búscalo, no lo niegues.")
    rows = [_row(it, _MAX_BODY_DIGEST) for it in items[:_MAX_DIGEST_ROWS]]
    if len(items) > _MAX_DIGEST_ROWS:
        rows.append(f"· … y {len(items) - _MAX_DIGEST_ROWS} más (la tarjeta los enseña todos).")
    return "\n".join([head] + rows)


def read_query(question: str) -> str:
    """The messages this question is about. "" when it names nothing findable — which falls through to the
    digest, and `compose_system` then says out loud that a summary is not a record."""
    terms = _terms(question)
    if not terms:
        return ""
    items = _items()
    if not items:
        return ""
    scored = []
    for it in items:
        hay = _norm(" ".join(str(it.get(k) or "") for k in
                             ("from", "senderName", "group", "body", "platform", "motivo")))
        hits = sum(1 for t in terms if t in hay)
        if hits:
            scored.append((hits, -float(it.get("ts") or 0), it))
    if not scored:
        return ""
    scored.sort(key=lambda t: (-t[0], t[1]))
    rows = [_row(t[2], _MAX_BODY_ANSWER) for t in scored[:_MAX_ANSWER_ROWS]]
    head = ("El mensaje por el que se pregunta (esto SÍ es el registro):" if len(scored) == 1 else
            f"{len(scored)} mensajes de la bandeja encajan con lo que se pregunta"
            + (f" — los {len(rows)} más recientes:" if len(scored) > len(rows) else ":"))
    return "\n".join([head] + rows)

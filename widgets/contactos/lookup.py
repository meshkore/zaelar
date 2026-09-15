"""lookup.py — the directory ANSWERING A QUESTION about somebody, instead of handing over its first page.

`data.prompt_digest()` is the always-on summary: it rides EVERY turn's prompt while the card is open, so it is
fifteen rows of however many thousand there are, and it publishes PLATFORMS without handles — a handle is
personal data and has no business in every prompt (V2-683). Both decisions are right for what it is, and both
are fatal the moment that same block is handed to somebody who asked a question.

Measured 2026-09-15 (session 76270f41). «Contact Kryptonite… you've got my Telegram contact for them.» The
brain read this widget four times, got that digest four times, and answered «it's saved with Telegram as the
preferred channel, but there's no Telegram handle stored». The row held `@cryptonite_fund`, and
`directory.resolve("Kryptonite")` — misspelt exactly as he said it — returned it on the first try. Nothing was
hallucinated: the block was built never to contain the answer, and its own first line orders the reader to
treat an absence in it as authoritative.

So the summary stays exactly as it is, and a QUESTION gets its own door — through the resolver the SENDING side
already trusts, so what the brain says about who somebody is and what the message door does with that person
can never again be two different answers. The seam is `data.read_query(question)`, declared generically in
`nucleo/flash/widget_read.py`; the agenda and the inbox joined through the same one.
"""
from __future__ import annotations

import re

# ── ANSWERING A QUESTION ABOUT ONE PERSON (V2-704) ───────────────────────────────────────────────────────
# `prompt_digest` above is the always-on summary: it rides EVERY turn while the card is open, so it is a first
# page (fifteen rows) and it publishes platforms WITHOUT handles — a handle is personal data and has no business
# in every prompt. Both decisions are right for what it is, and both are fatal when the same block is handed to
# somebody who asked a question. Measured 2026-09-15: asked four times for Cryptonite's Telegram, the brain got
# the digest four times and answered «there's no Telegram handle stored», while the row held `@cryptonite_fund`
# and `directory.resolve("Kryptonite")` — misspelt as he said it — returned that row on the first try.
# So: the summary stays exactly as it is, and a QUESTION gets its own door, through the resolver the sending
# side already trusts. One directory, one judgement about who somebody is.

#: Words that are never a person here and would otherwise drag half a 2 686-row directory into an answer: the
#: scaffolding a model wraps a question in. Kept SHORT on purpose — the real guard is `_MAX_HITS` below, which
#: throws away any span that matches too many people, whatever the word happens to be.
_ASK_STOP = {
    "que", "qué", "cual", "cuál", "quien", "quién", "como", "cómo", "donde", "dónde", "cuando", "cuándo",
    "the", "what", "which", "who", "whom", "whose", "where", "when", "how", "is", "are", "was", "were", "do",
    "does", "did", "for", "from", "with", "and", "or", "of", "in", "on", "at", "to", "a", "an", "my", "his",
    "her", "their", "our", "your", "mi", "su", "tu", "el", "la", "los", "las", "un", "una", "de", "del", "y",
    "o", "con", "para", "por", "en", "se", "me", "te", "le", "lo", "hay", "tengo", "tiene", "tienes",
    "contact", "contacto", "contacts", "contactos", "info", "information", "details", "detalles", "datos",
    "dato", "name", "nombre", "phone", "telefono", "teléfono", "number", "numero", "número", "email", "mail",
    "correo", "channel", "channels", "canal", "canales", "preferred", "preferido", "handle", "usuario",
    "username", "address", "direccion", "dirección", "stored", "guardado", "guardada", "saved", "there",
    "any", "all", "about", "tell", "give", "show", "dime", "dame", "busca", "buscar", "find", "look", "get",
    "have", "has", "we", "i", "you", "it", "they", "sobre", "acerca", "ficha", "agenda", "telegram",
    "whatsapp", "signal", "sms", "meet", "google", "zoom",
}

#: A span that resolves to more than this is not a name, it is a common word that happens to appear inside
#: several names («maria» in a directory of 2 686). Answering with twenty rows is not answering.
_MAX_HITS = 4
#: And at most this many people in one answer — past it the honest reply is «which one».
_MAX_ANSWERED = 3


def _spans(question: str) -> list[str]:
    """The pieces of a question that could be somebody's NAME, most specific first.

    Quoted spans and capitalised runs first (a model writes `"Kryptonite"` or `Kryptonite`), then the remaining
    words on their own — because speech arrives lowercased and a capitalised run is a luxury, not a guarantee.
    """
    q = str(question or "")
    out: list[str] = []
    out += [m.strip() for m in re.findall(r"[\"'«]([^\"'»]{2,60})[\"'»]", q)]
    # A capitalised run, and a run may end in DIGITS — «Relleno Número 7», «Calle 5», a company with a year in
    # it. Stopping the run at the first number split exactly the names that need their number to be unique.
    out += [m.strip() for m in re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'-]+(?:\s+(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÜÑáéíóúüñ'-]+|\d+))*)", q)]
    words = [w for w in re.split(r"[^\wÁÉÍÓÚÜÑáéíóúüñ'@.+-]+", q) if len(w) > 2]
    out += [w for w in words if w.lower() not in _ASK_STOP]
    seen, keep = set(), []
    for s in out:
        s = s.strip(" .,;:¿?¡!")
        k = s.lower()
        if not s or k in seen or k in _ASK_STOP:
            continue
        seen.add(k)
        keep.append(s)
    return keep[:12]


def _full_row(c: dict) -> str:
    """ONE contact, whole. This is the record, not the summary — so the handles ARE here: the operator asked."""
    bits = [f"«{c.get('name') or c.get('id')}»"]
    if c.get("kind") and c["kind"] != "person":
        bits.append(str(c["kind"]))
    if c.get("favorite"):
        bits.append("favorito ⭐")
    for label, key in (("tel", "phone"), ("email", "email"), ("ciudad", "city"), ("dirección", "address")):
        if c.get(key):
            bits.append(f"{label} {c[key]}")
    if c.get("groups"):
        bits.append("grupos: " + ", ".join(str(g) for g in c["groups"]))
    pref = str(c.get("preferred") or "")
    # `_reach` lives next door and is imported HERE, not at module load, because `data.py` imports this module:
    # one definition of «which channels this person is reachable by», asked at call time.
    from .data import _reach
    for ch in _reach(c):
        plat = str(ch.get("platform") or "")
        ident = str(ch.get("handle") or ch.get("address") or ch.get("email") or ch.get("phone") or "")
        cid = str(ch.get("chatId") or "")
        piece = plat + (f" {ident}" if ident else "") + (f" (chatId {cid})" if cid and not ident else "")
        bits.append(piece + (" ← CANAL PREFERIDO" if plat == pref else ""))
    if c.get("agent"):                       # the contact's own agent address, for cluster-to-cluster contact
        bits.append(f"agente {c['agent']}")
    if c.get("notes"):
        bits.append("notas: " + str(c["notes"])[:200])
    return "· " + " · ".join(b for b in bits if b)


def read_query(question: str) -> str:
    """The rows this question is ABOUT, in full. "" when it names nobody we hold (`nucleo/flash/widget_read`).

    Resolution goes through `widgets/directory.resolve`, which is the same door the sending side uses and
    already survives the operator's spelling (`Kryptonite` → `Cryptonite`, V2-698). Asking it here rather than
    matching names locally is the whole point: what the brain SAYS about who somebody is and what the message
    door DOES with that person can never again be two different answers.
    """
    spans = _spans(question)
    if not spans:
        return ""
    try:
        from .. import directory
    except Exception:                                    # noqa: BLE001
        return ""
    hits: list[dict] = []
    seen: set = set()
    for s in spans:
        try:
            found = directory.resolve(s) or []
        except Exception:                                # noqa: BLE001
            continue
        if not found or len(found) > _MAX_HITS:          # a common word, not a name
            continue
        for c in found:
            cid = str(c.get("id") or "")
            if cid and cid not in seen:
                seen.add(cid)
                hits.append(c)
        if len(hits) >= _MAX_ANSWERED:
            break
    if not hits:
        return ""
    head = ("Ficha COMPLETA de quien se pregunta (resuelto contra el directorio; esto SÍ es el registro):"
            if len(hits) == 1 else
            f"{len(hits)} personas del directorio encajan con lo que se pregunta — si hace falta elegir, "
            "PREGÚNTALE cuál:")
    return "\n".join([head] + [_full_row(c) for c in hits[:_MAX_ANSWERED]])

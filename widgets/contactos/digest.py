# Contacts widget — what the BRAIN reads of the directory: the digest that rides the turn prompt while the card is
# open, the rows a sentence names, and the voice reference index (`data.py` re-exports all three).
#
# The store and the row helpers are read back through `data` (`_d.load_db`, `_d.visible`, …), so a test that
# patches `data.load_db` reaches these readers too.
from i18n import langs as _langs   # V2-778 F3-30: hints are read back aloud, in the agent's language
from . import model


def prompt_digest() -> str:
    """What the directory ACTUALLY holds, compact enough to ride every turn prompt while the card is open
    (`refs.prompt_digest` contract; bounded on its own too). It states the authoritative counts and rows and says
    it outranks memory, so speech about this card starts from what is on screen, not stale pills (V2-576)."""
    db = _d.load_db()
    contacts = _d.visible(db)
    favs = sum(1 for c in contacts if c.get("favorite"))
    if not contacts:
        return ("Directorio VACÍO: 0 contactos, 0 favoritos. Si tu memoria dice otra cosa, MANDA este "
                "bloque: no afirmes que hay entradas guardadas.")
    lines = [f"Directorio COMPLETO y real: {len(contacts)} entradas, {favs} favoritas (⭐). Para contar o "
             "listar lo guardado, MANDA este bloque sobre tu memoria y sobre la conversación: lo que no "
             "esté aquí NO está guardado."]
    circles = [c for c in contacts if c.get("kind") == "group"]
    if circles:
        # Real groups are stated so «which groups am I in?» is answered from the card, not memory.
        lines.append("GRUPOS reales (chats y clusters, se les puede escribir): " + " · ".join(
            f"«{g.get('name')}» ({g.get('platform') or g.get('source') or '?'}"
            + (f", {len(g.get('members') or [])} miembros" if g.get("membersKnown", True)
               else ", miembros no enumerables")
            + ")" for g in circles[:8]) + ".")
    sel = ((_d._fresh_view(db) or {}).get("sel")) or {}
    if sel:
        bits = []
        if "favorites" in sel:
            bits.append("solo favoritos" if sel["favorites"] else "solo no-favoritos")
        bits += [f"{k}: {sel[k]}" for k in ("group", "city", "query") if sel.get(k)]
        if bits:
            lines.append("Vista filtrada en pantalla ahora: " + " · ".join(bits) + ".")
    for c in contacts[:15]:
        row = ("⭐ " if c.get("favorite") else "· ") + str(c.get("name") or c.get("id"))
        extra = [str(c.get("kind") or "")] if c.get("kind") not in (None, "", "person") else []
        extra += [str(c.get("city") or "")] if c.get("city") else []
        extra += [", ".join(c.get("groups") or [])] if c.get("groups") else []
        extra += ["flags: " + ", ".join(c["flags"])] if c.get("flags") else []
        # The primary number and HOW MANY more — never all (budget); «+2 más» stops it reading as the only one.
        # The whole list is one `read_query` away.
        tels = model.values(c, "phones") or ([c["phone"]] if c.get("phone") else [])
        if tels:
            extra.append(f"tel {tels[0]}" + (f" (+{len(tels) - 1} más)" if len(tels) > 1 else ""))
        # By WHICH channel he can be written to, and the preferred one. Platforms only, asked through `directory`
        # so the digest and the sending door never disagree about who is reachable (V2-683).
        chans = [str(ch.get("platform")) for ch in _d._reach(c)]
        if chans:
            pref = str(c.get("preferred") or "")
            extra.append("canales: " + ", ".join((p + " (preferido)") if p == pref else p for p in chans))
        if c.get("notes"):
            extra.append(str(c["notes"])[:80])
        if extra:
            row += " (" + "; ".join(x for x in extra if x) + ")"
        lines.append(row)
    if len(contacts) > 15:
        lines.append(f"… y {len(contacts) - 15} entradas más (la tarjeta las enseña todas).")
    return "\n".join(lines)


def people_named(text: str, limit: int = 4) -> list[dict]:
    """The directory rows the operator's sentence NAMES — the compact public row, platforms only.

    The digest only carries the first rows while the card is open, so a person named by first name needs this.
    A whole name in the sentence wins; otherwise a name whose FIRST word is in the sentence (several come back
    together and the model asks which). Names under three letters never match."""
    import re as _re
    low = (text or "").lower()
    words = set(_re.findall(r"[^\W\d_]{3,}", low))
    full, first = [], []
    for c in _d.visible(_d.load_db()):
        if c.get("kind") not in (None, "", "person"):
            continue
        name = str(c.get("name") or "").strip().lower()
        toks = _re.findall(r"[^\W\d_]+", name)
        if not toks:
            continue
        # The whole name inside his sentence — also for scripts written without spaces between words.
        if len(name) >= 2 and (len(toks) > 1 or not name.isascii()) and name in low:
            full.append(c)
        elif len(toks) > 1 and all(t in words for t in toks):
            full.append(c)
        elif len(toks[0]) >= 3 and toks[0] in words:
            first.append(c)
    return [_d._public(c) for c in (full or first)[:limit]]


def ref_index() -> list[dict]:
    """Items the brain can reference by voice (V2-026): every contact, by name (+city to disambiguate two
    «Juan»s). `field` is the payload key every action uses, so refs resolve without the model guessing ids."""
    out = []
    for c in _d.visible(_d.load_db()):            # hidden rows stay MAPPED and stop being referenceable
        label = str(c.get("name") or c.get("id"))
        if c.get("city"):
            label += f" ({c['city']})"
        if c.get("kind") == "group":
            # …and a group says so, plus where it lives: the chat «Familia» is not the label «Familia».
            n = len(c.get("members") or [])
            hint = " · ".join(x for x in (str(c.get("platform") or ""),
                                          (_langs.words("hints.members", default="{n}").format(n=n) if n else "")) if x) \
                or _langs.words("hints.group", default="")
        else:
            hint = ", ".join(c.get("groups") or []) or str(c.get("kind") or "")
        out.append({"id": c["id"], "label": label, "field": "contactId", "hint": hint})
    return out


from . import data as _d  # noqa: E402 — read back at call time (see the header)

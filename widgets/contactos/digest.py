# Contacts widget — what the BRAIN reads of the directory: the digest that rides the turn prompt while the card is
# open, the rows a sentence names, and the voice reference index (refactor2710-12 T-03: moved out of `data.py`,
# which re-exports all three because the runtime and the turn read them there).
#
# The store and the row helpers are read back through `data` (`_d.load_db`, `_d.visible`, …) on purpose: that
# module owns them, and a test that patches `data.load_db` has to reach these readers too.
from i18n import langs as _langs   # V2-778 F3-30: hints are read back aloud, in the agent's language
from . import model


def prompt_digest() -> str:
    """What the directory ACTUALLY holds, compact enough to ride every turn prompt while the card is open
    (`refs.prompt_digest` contract; capped there, so this stays bounded on its own too).

    Why (V2-576, session 0a93de06 of 2026-09-04): asked «¿cuántos restaurantes favoritos tenemos?», the
    brain answered from stale memory pills («one») while the open card showed four — and when the operator
    pointed at the screen, it CONFABULATED a view explanation («la vista actual no lo muestra») for a
    mismatch it could not check. `ref_index` publishes labels without meaning: nothing said «these ARE all
    the favourites, four in total». The digest states the authoritative counts and rows, and says out loud
    that it outranks memory, so speech about this card starts from what the operator is looking at."""
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
        # The brain has to be able to answer «¿en qué grupos estoy?» and «escribe al grupo de la familia»
        # from the card rather than from memory — the same reason the counts above are stated out loud.
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
        # The primary number, and HOW MANY more there are — never all of them: this block rides every turn
        # while the card is open, and a company with six lines would spend the budget on one row. «+2 más»
        # is what stops «tel 900111222» reading as «that is the only number we hold» (the whole list is one
        # `read_query` away, which is the door a question about somebody goes through).
        tels = model.values(c, "phones") or ([c["phone"]] if c.get("phone") else [])
        if tels:
            extra.append(f"tel {tels[0]}" + (f" (+{len(tels) - 1} más)" if len(tels) > 1 else ""))
        # V2-683 — by WHICH channel he can be written to, and which one is his. Platforms only (a handle is
        # personal data and the sending door reads it from the store, not from here). Asked through
        # `directory` rather than read raw, so a stored address counts as the email channel it is — the
        # digest and the door that sends must never disagree about who is reachable.
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

    Demo pass 2026-09-28 (full14 E3): «send the invoice to quinn…» was answered «I don't see an Quinn in your
    contacts» with Quinn saved. The directory reaches the prompt only as the card's digest (first rows of
    ~2,700, and only while the card is open), so a person he names by first name was invisible to the turn that
    had to write to him. A whole name in the sentence wins; otherwise a name whose FIRST word is a word of the
    sentence (several «Quinn» come back together, and the model asks which). Names under three letters never
    match — they are words, not people."""
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
        # The whole name inside his sentence — which also works for scripts written without spaces between
        # words, where a name is a run of characters rather than a separate word.
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
            # …and a group says so, plus where it lives: «Familia» the WhatsApp chat and «Familia» the
            # label he types are two different things, and the menu has to be able to tell them apart.
            n = len(c.get("members") or [])
            hint = " · ".join(x for x in (str(c.get("platform") or ""),
                                          (_langs.words("hints.members", default="{n}").format(n=n) if n else "")) if x) \
                or _langs.words("hints.group", default="")
        else:
            hint = ", ".join(c.get("groups") or []) or str(c.get("kind") or "")
        out.append({"id": c["id"], "label": label, "field": "contactId", "hint": hint})
    return out


from . import data as _d  # noqa: E402 — read back at call time (see the header)

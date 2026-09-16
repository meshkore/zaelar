"""voice/engine/llm/providers/confirm_gate.py — «is this the same question I already asked?», how to ask it,
and whether there is anything to ask at all.

Extracted from the voice provider (2026-09-02, architecture ratchet: 3551 lines over a 3493 ceiling, and the
ratchet's instruction is to EXTRACT, never to raise the number). These were the natural first cut because
they are the only pair in that file that needs NOTHING from it — verified before moving, not assumed: no
module global, no helper, no `_spawn`. The dependency runs one way, so the provider imports them back and
nothing else changed.

WHAT IS HERE. `_similar_pending` answers whether a confirmation now being raised is really the one already
waiting — the check that stops the agent asking the same irreversible question twice with slightly different
words. `_human_confirm_question` turns the raw action into the sentence a person actually hears. `decide`
is the whole gate's verdict for one data-op, and it is the piece V2-707 F6 added.

## V2-707 F6 — A NUMBER THAT CONTRADICTS THE ORDER IS NOT A CONFIRMATION

Measured in session `080b96a7` (2026-09-16, i=10753→10794). He had just described three all-day items on
the 17th and said «Can you clean the three?». The gate answered «Voy a borrar 5 citas del 2026-09-17. Es
permanente. ¿Las borro?», he said «Yes.», and five rows went.

The number in that sentence is not an accident — V2-693 put it there on purpose, because «a confirmation
that does not count what it takes away is a confirmation you say yes to without looking». What it never
did is COMPARE. Three and five are not a question and its answer; they are two different claims about the
same act, and a «yes» to a contradiction authorises nothing. So the gate now measures both halves —
`nucleo/asked_count.named` reads the count the ORDER put on it, `radius` reads the count the DATA gives —
and when they disagree it refuses, names both and lists the rows. Nothing is registered, so a later «yes»
has nothing to execute.

Same subtraction one step over: a range with NOTHING in it used to be registered as a confirmation whose
«question» was the statement «No hay ninguna cita que borrar en ese tramo.» (heard at i=10600). A
confirmation with no question in it can only be answered by accident, and `rows.plan` already decided this
correctly for the generic door — nothing matched is a misunderstanding, never a yes/no.

## V2-707 F6 — AND EVERY SENTENCE HERE COMES FROM THE LANGUAGE TABLE

V2-682 moved the two `danger.py` gates into `i18n/langs.py` and left this module composing its own prose,
so thirty seconds after «Do not speak Spanish» the operator heard both sentences above in Castilian
(i=10600, i=10765), plus `clear_all`'s own `confirm_q` from the manifest (i=10427). None of the three is a
`notify`/`say` call or an assignment to a spoken field — they are RETURN values, the one shape V2-682's
prose ratchet cannot see, which is why the leak was invisible until he heard it.

A widget's `confirm_q` stays in its manifest — that is where a widget's rails belong — and is now looked
up in the i18n bundle first (`widgets.<id>.confirm.<action>`), exactly as V2-694 did for widget names, so
the shipped Castilian is the DEFAULT rather than the only thing there is.
"""
from __future__ import annotations


def _similar_pending(req: str, pendings: list[dict]) -> bool:
    """True si `req` se parece mucho a una escalada YA en vuelo (Jaccard de palabras de contenido ≥0.5) — el
    operador insiste/refina la MISMA petición mientras el SlowBrain trabaja (V2-029). Evita tareas y entregas
    duplicadas. Dos peticiones distintas (moto vs piso) NO se funden."""
    import re as _re
    import unicodedata as _ud

    def _w(s: str) -> set:
        n = "".join(c for c in _ud.normalize("NFKD", s or "") if not _ud.combining(c)).lower()
        return {t for t in _re.findall(r"\w+", n) if len(t) >= 4}

    g = _w(req)
    if not g:
        return False
    for p in (pendings or []):
        o = _w(p.get("request", ""))
        union = len(g | o)
        if union and len(g & o) / union >= 0.5:
            return True
    return False
def _out_label(platform) -> str:
    """The app's name as the operator says it — he hears «por Telegram», never «por telegram»."""
    return {"whatsapp": "WhatsApp", "telegram": "Telegram", "email": "correo"}.get(
        str(platform or "").strip().lower(), "")


def _say():
    """The operator's language table. Every sentence this module hands him comes from here (V2-707 F6)."""
    from i18n import langs as _lg
    return _lg.current_language()


def _confirm_q(wid: str, action: str, spec: dict) -> str:
    """The widget's own confirmation question, in the operator's language.

    The manifest keeps writing it — a widget's declared shape IS its rails, and a widget the operator wrote
    himself has nothing else. The bundle key is consulted FIRST so the sentences the repo ships travel to
    every language the way widget names do since V2-694, instead of reaching an English session in
    Castilian (measured i=10427: «¿Vacío la agenda entera? Es permanente.»)."""
    raw = str((spec or {}).get("confirm_q") or "").strip()
    try:
        from i18n import runtime as _rt
        return _rt.text(f"widgets.{wid}.confirm.{action}", raw).strip() or raw
    except Exception:  # noqa: BLE001
        return raw


# ── THE RADIUS: how many rows this call would touch, and which ──────────────────────────────────────────

def radius(wid: str, action: str, payload: dict) -> dict | None:
    """`{"n", "names", "kept", "span"}` for a call whose scope is COUNTABLE, else None.

    None is not a failure: most actions name one item and the count adds nothing. What this answers is the
    question the door needs before it can tell a confirmation from a contradiction — «how many rows is
    this, really». It reads the window and the keepers from the SAME module the action itself uses
    (`agenda/sweep.py`), never re-derived here: a question that counts differently from the deletion it
    gates is worse than no question."""
    wid, action = (wid or "").strip().lower(), (action or "").strip()
    if wid == "agenda" and action in ("clear_range", "clear_all"):
        try:
            from widgets.agenda import data as _ag, sweep as _sweep
            rows = [m for m in (_ag.load_db().get("meetings") or []) if isinstance(m, dict)]
            if action == "clear_all":
                return {"n": len(rows), "names": [str(m.get("title") or "?") for m in rows],
                        "kept": [], "span": ""}
            lo, hi = _sweep.window(payload or {})
            keep = _sweep.keep_list(payload or {})
            inside = [m for m in rows if lo <= str(m.get("date") or "") <= hi]
            doomed = [m for m in inside if not _sweep.kept(m, keep)]
            sp = _say()
            span = (sp.sweep_span_one.format(since=lo) if hi == lo
                    else sp.sweep_span_range.format(since=lo, until=hi))
            return {"n": len(doomed), "names": [str(m.get("title") or "?") for m in doomed],
                    "kept": [m for m in inside if _sweep.kept(m, keep)], "span": span}
        except Exception:  # noqa: BLE001
            return None
    if action.startswith("rows."):
        try:
            from widgets import rows as _rows
            p = _rows.plan(wid, action.split(".", 1)[1], payload or {})
            if p.get("ok"):
                return {"n": int(p.get("n") or 0), "names": list(p.get("names") or []),
                        "kept": [], "span": ""}
            if p.get("error") == _rows.NOTHING_MATCHED:
                return {"n": 0, "names": [], "kept": [], "span": ""}
        except Exception:  # noqa: BLE001
            return None
    return None


def scope_mismatch(wid: str, action: str, payload: dict, order: str) -> dict:
    """The order named a count and the radius resolved to a different one → `{"asked", "n", "names",
    "sentence"}`; `{}` when the two agree, when he named no number, or when this call cannot be counted.

    This is the whole of F6's first half and it is a rail on CONSEQUENCE: it neither reads intent nor
    decides what he meant. Two measurements of the same act disagree, so the door does not act."""
    asked = None
    try:
        from nucleo import asked_count as _ac
        asked = _ac.named(order)
    except Exception:  # noqa: BLE001
        return {}
    if asked is None:
        return {}
    r = radius(wid, action, payload)
    if not r or not r.get("n") or int(r["n"]) == int(asked):
        return {}
    sp = _say()
    names = "; ".join(f"«{t}»" for t in (r.get("names") or [])[:8])
    return {"asked": int(asked), "n": int(r["n"]), "names": list(r.get("names") or []),
            "sentence": sp.scope_mismatch.format(asked=asked, n=r["n"], names=names)}


def _sweep_question(r: dict) -> str:
    """The agenda sweep's own sentence, composed from the table (V2-693's number, F6's language)."""
    sp = _say()
    kept = r.get("kept") or []
    if not r.get("n"):
        return (sp.sweep_nothing_keeping.format(n=len(kept)) if kept else sp.sweep_nothing)
    keeping = ""
    if kept:
        names = ", ".join(f"«{m.get('title')}»" for m in kept[:3])
        keeping = sp.sweep_keeping.format(names=names) + (
            sp.sweep_keeping_more.format(n=len(kept) - 3) if len(kept) > 3 else "")
    tpl = sp.sweep_confirm_one if int(r["n"]) == 1 else sp.sweep_confirm_many
    return tpl.format(n=r["n"], span=(r.get("span") or "").strip(), keeping=keeping)


def _human_confirm_question(wid: str, action: str, payload: dict) -> str:
    """Texto HUMANO de una confirmación de data-op irreversible (overlay + voz). Expone el ALCANCE real leído del
    MANIFEST — qué HACE la acción (`desc`) y sobre QUÉ item (etiqueta resuelta) — para que el operador vea si es
    MÁS de lo que pidió (p.ej. un PROYECTO entero en vez de una tarea). Genérico: sirve a cualquier widget. Fallback
    prudente si no hay manifest/desc."""
    sp = _say()
    # V2-693 — DELETING A RANGE OF THE AGENDA. Same reason as the two messaging branches below: the question
    # has to expose the REAL SCOPE, and here the scope is a NUMBER. Measured 2026-09-14: he asked to clear
    # the week keeping two appointments, the model called `clear_all` (whose scope is EVERYTHING and
    # forever), and the canned question said «¿Vacío la agenda entera?» — true of the action and unrelated
    # to what he had asked for.
    if wid == "agenda" and action == "clear_range":
        r = radius(wid, action, payload)
        return _sweep_question(r) if r else sp.sweep_confirm_bare

    # V2-051: RESPONDER un mensaje → la confirmación LEE el borrador (destinatario + texto), no la jerga de la
    # acción. Así el operador oye exactamente qué se va a enviar antes de decir sí.
    if wid == "mensajeria" and action == "reply":
        body = str((payload or {}).get("text") or "").strip()
        draft = (body[:180] + "…") if len(body) > 180 else body
        who = ""
        try:
            from widgets.mensajeria import data as _md
            v = _md.view_data()
            n = (payload or {}).get("n")
            if v.get("active_chat"):
                hit = next((it for it in v.get("active_items", []) if it.get("n") == n), None)
                who = (hit or {}).get("from") or ""
            else:
                hit = next((c for c in v.get("chats", []) if c.get("n") == n), None)
                who = (hit or {}).get("name") or ""
        except Exception:
            pass
        return sp.reply_confirm.format(dest=sp.reply_confirm_dest.format(who=who) if who else "", draft=draft)

    # V2-683 — WRITING TO A PERSON. Same reason as the branch above, one step further: this send does not
    # answer a conversation, it OPENS one, so the question has to name WHO and by WHICH app before anything
    # leaves — «¿Le escribo a Iván por Telegram: "…"?». And when the order carries an `objective`, this
    # sentence is also the MANDATE: the one yes that authorises the whole exchange that follows, said out
    # loud instead of asked again per message. `confirm_q` cannot do it (it interpolates `{item}` and nothing
    # else), which is exactly why `reply` composes its own here too.
    if wid == "mensajeria" and action == "send_to":
        p = payload or {}
        try:
            from widgets.mensajeria import outbound as _out
            d = _out.describe(p)
        except Exception:  # noqa: BLE001
            d = {}
        body = str(p.get("text") or "").strip()
        draft = (body[:180] + "…") if len(body) > 180 else body
        who = str(d.get("name") or p.get("contact") or p.get("to") or "").strip()
        via = _out_label(d.get("platform") or p.get("channel") or "")
        parts = {"who": sp.send_to_who.format(who=who) if who else "",
                 "via": sp.send_to_via.format(via=via) if via else "", "draft": draft}
        obj = str(p.get("objective") or "").strip()
        return (sp.send_to_confirm_mandate.format(objective=obj, **parts) if obj
                else sp.send_to_confirm.format(**parts))

    desc = ""
    human = ""
    label = ""
    try:
        from widgets import refs, runtime
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(action) or {}
        human = _confirm_q(wid, action, spec)
        desc = str(spec.get("desc") or "").strip().rstrip(".")
        field = refs.id_field_for_action(wid, action)
        if field:
            label = refs.label_for(wid, field, (payload or {}).get(field, ""))
    except Exception:
        pass
    tail = sp.data_confirm_item.format(item=label) if label else ""
    # `confirm_q` MANDA: es la pregunta escrita PARA EL OPERADOR (2026-08-15, sesión 319252e7). El `desc` del
    # manifest es la descripción de la tool, o sea texto escrito PARA EL MODELO — y leerlo en voz alta es un error
    # de categoría que el operador oyó entero: «VACÍA la agenda entera de una vez: descarta todas las tareas…
    # **Úsala cuando el operador pida** dejarla vacía «del todo»/«por completo»…». Le estábamos recitando nuestras
    # instrucciones internas y pidiéndole que dijera «sí» a eso.
    if human:
        # `{item}` deja que el autor del widget coloque el elemento DONDE suena bien al oído, en vez de pegarlo
        # al final: «¿Congelo el proyecto «Reddit» entero?» en vez de «…entero. («Reddit»)». Si no hay item
        # resuelto, la frase se queda sin él antes que decir «el proyecto «»».
        if "{item}" in human:
            q = human.replace(" «{item}»", f" «{label}»" if label else "").replace("{item}", label)
        else:
            q = f"{human}{tail}"
        return q if "?" in q else sp.data_confirm_needs_q.format(q=q)
    if desc:
        # Sin `confirm_q`, se cita SOLO la primera frase del desc: la guía de uso («Úsala cuando…») vive a partir
        # del primer punto y no es asunto del operador. Mejor que la jerga cruda de 2026-07-15 («¿Confirmas
        # drop_project?»), que es lo que esta rama vino a arreglar, y sin arrastrar el resto del prompt.
        primera = desc.split(". ")[0].rstrip(".")
        return sp.data_confirm_from_desc.format(what=primera, item=tail)
    return sp.data_confirm_generic.format(action=action, item=tail)


def decide(wid: str, action: str, payload: dict, order: str = "") -> dict:
    """The gate's whole verdict for ONE irreversible data-op, in the shape the caller acts on:

      · `{"kind": "ask", "question": …}`        — register the confirmation and ask it;
      · `{"kind": "mismatch", "sentence": …}`   — the order's count and the radius disagree: say both,
                                                  register NOTHING (a «yes» must have nothing to execute);
      · `{"kind": "empty", "sentence": …}`      — nothing matches, so there is nothing to confirm.

    It lives here rather than in the provider's closure for the reason the whole module exists: it needs
    nothing from that file, and the provider is at its ceiling.
    """
    wid, action = (wid or "").strip().lower(), (action or "").strip()
    if not wid:
        return {}
    mis = scope_mismatch(wid, action, payload or {}, order or "")
    if mis:
        return {"kind": "mismatch", "sentence": mis["sentence"], "asked": mis["asked"], "n": mis["n"],
                "names": mis["names"], "wid": wid, "action": action}
    r = radius(wid, action, payload or {})
    q = _human_confirm_question(wid, action, payload or {})
    if r is not None and not r.get("n"):
        return {"kind": "empty", "sentence": q, "wid": wid, "action": action}
    return {"kind": "ask", "question": q, "wid": wid, "action": action,
            "op": {"action": action, "payload": payload or {}}}

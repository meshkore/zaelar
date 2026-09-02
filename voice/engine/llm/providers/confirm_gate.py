"""voice/engine/llm/providers/confirm_gate.py — «is this the same question I already asked?», and how to ask it.

Extracted from the voice provider (2026-09-02, architecture ratchet: 3551 lines over a 3493 ceiling, and the
ratchet's instruction is to EXTRACT, never to raise the number). These two are the natural first cut because
they are the only pair in that file that needs NOTHING from it — verified before moving, not assumed: no
module global, no helper, no `_spawn`. The dependency runs one way, so the provider imports them back and
nothing else changed.

WHAT THEY DO. `_similar_pending` answers whether a confirmation now being raised is really the one already
waiting — the check that stops the agent asking the same irreversible question twice with slightly different
words. `_human_confirm_question` turns the raw action into the sentence a person actually hears.

Both moved BYTE FOR BYTE. This module changed no behaviour; it changed where the behaviour lives.
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
def _human_confirm_question(wid: str, action: str, payload: dict) -> str:
    """Texto HUMANO de una confirmación de data-op irreversible (overlay + voz). Expone el ALCANCE real leído del
    MANIFEST — qué HACE la acción (`desc`) y sobre QUÉ item (etiqueta resuelta) — para que el operador vea si es
    MÁS de lo que pidió (p.ej. un PROYECTO entero en vez de una tarea). Genérico: sirve a cualquier widget. Fallback
    prudente si no hay manifest/desc."""
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
        dest = f" a {who}" if who else ""
        return f"Voy a responder{dest}: «{draft}». ¿Lo envío?"

    desc = ""
    human = ""
    label = ""
    try:
        from widgets import refs, runtime
        spec = ((runtime.get(wid) or {}).get("actions") or {}).get(action) or {}
        human = str(spec.get("confirm_q") or "").strip()
        desc = str(spec.get("desc") or "").strip().rstrip(".")
        field = refs.id_field_for_action(wid, action)
        if field:
            label = refs.label_for(wid, field, (payload or {}).get(field, ""))
    except Exception:
        pass
    tail = f" («{label}»)" if label else ""
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
        return q if "?" in q else f"{q} ¿Lo confirmo?"
    if desc:
        # Sin `confirm_q`, se cita SOLO la primera frase del desc: la guía de uso («Úsala cuando…») vive a partir
        # del primer punto y no es asunto del operador. Mejor que la jerga cruda de 2026-07-15 («¿Confirmas
        # drop_project?»), que es lo que esta rama vino a arreglar, y sin arrastrar el resto del prompt.
        primera = desc.split(". ")[0].rstrip(".")
        return f"Ojo, esto es permanente: «{primera}»{tail}. ¿Lo confirmo?"
    return f"Ojo, la acción «{action}»{tail} es permanente. ¿La confirmo?"

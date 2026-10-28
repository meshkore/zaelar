"""The player library's PREFERENCE ops: the keys he may set, how a spoken value reads, applying them (from `library`)."""
from __future__ import annotations

from .. import store
from .library import _ENFORCEABLE, WID, _norm


# Spoken names for the enforceable keys («calidad mínima», not "min_definition"); one-way, the answer names the key.
_KEY_ALIASES = {
    "min_definition": "min_definition", "definition": "min_definition", "quality": "min_definition",
    "calidad": "min_definition", "calidad minima": "min_definition", "resolucion": "min_definition",
    "resolucion minima": "min_definition", "min_quality": "min_definition",
    "captions": "captions", "subtitles": "captions", "subtitulos": "captions",
    "volume": "volume", "volumen": "volume",
}


_TRUE = {"1", "true", "on", "si", "yes", "activar", "activalos", "activados", "activado",
         "ponlos", "siempre", "encender", "encendidos"}


_FALSE = {"0", "false", "off", "no", "quitar", "quitalos", "desactivar", "desactivalos",
          "desactivados", "desactivado", "nunca", "apagar", "apagados"}


def _pref_value(key: str, raw) -> "tuple[object, str]":
    """(value, error). Parses the operator's words into the type the key enforces — «720p», «sí», «al 40».

    The value goes through the SAME `_norm` as the key, accents included. It did not at first, and the very
    first sentence an operator says in Spanish — «pon los subtítulos, sí» — was refused because the table
    held `si` and he said `sí`: a value vocabulary matched more strictly than the key vocabulary rejects
    exactly the words the widget was written to understand."""
    s = _norm(raw if raw is not None else "")
    if key == "min_definition":
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None, "Dime la calidad mínima en píxeles, por ejemplo 720."
        n = int(digits[:5])
        if n not in (144, 240, 360, 480, 720, 1080, 1440, 2160):
            # Not a rejection of his taste — a rejection of a number the player can never report, which
            # would make the rule silently unenforceable (the failure this whole module is built against).
            return None, ("Las calidades que el reproductor sabe medir son 144, 240, 360, 480, 720, 1080, "
                          "1440 y 2160.")
        return n, ""
    if key == "captions":
        if s in _TRUE:
            return True, ""
        if s in _FALSE:
            return False, ""
        return None, "Dime si quiero los subtítulos activados o desactivados."
    if key == "volume":
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None, "Dime un volumen de 0 a 100."
        return max(0, min(100, int(digits[:3]))), ""
    return None, "No sé aplicar esa preferencia."


def _apply_pref(action: str, p: dict, db: dict) -> dict:
    """set_preference / clear_preference — rows of the rules table at `widget:youtube` (`prefs.py`, V2-806)."""
    from . import prefs as _prefs
    raw_key = str(p.get("key") or p.get("name") or p.get("preference") or "").strip()
    key = _KEY_ALIASES.get(_norm(raw_key), "")
    if action == "clear_preference":
        _prefs.overlay(db, _ENFORCEABLE)
        if key and key in db["prefs"]:
            _prefs.clear_value(db, key, _ENFORCEABLE)
            store.save(WID, db)
            return {"ok": True, "key": key, "prefs": dict(db["prefs"])}
        n = _norm(raw_key)
        hit = next((x for x in db["prefs_notes"] if n and n in _norm(x.get("text"))), None)
        if hit is not None:
            _prefs.remove_note(db, hit["id"], _ENFORCEABLE)
            store.save(WID, db)
            return {"ok": True, "note": hit.get("text"), "prefs": dict(db["prefs"])}
        return {"ok": False, "error": "not_set", "key": raw_key, "prefs": dict(db["prefs"]),
                "message": "No tengo esa preferencia guardada."}
    value = p.get("value") if p.get("value") is not None else p.get("level")
    if not key:
        # Not enforceable — and that is said out loud rather than stored as if it were a rule. The brain
        # still receives it (a note row, published as prefs_notes), so it can honour it by judgement.
        text = " ".join(x for x in [raw_key, "" if value is None else str(value)] if x).strip()[:200]
        if not text:
            return {"ok": False, "error": "no_preference",
                    "message": "Dime qué preferencia guardo.", "enforceable": sorted(_ENFORCEABLE)}
        _prefs.add_note(db, text, _ENFORCEABLE)
        store.save(WID, db)
        return {"ok": True, "stored_as": "note", "note": text, "enforceable": sorted(_ENFORCEABLE),
                "message": ("Lo guardo y lo tendré en cuenta, pero no puedo forzarlo automáticamente: "
                            "lo que sí aplico solo es " + ", ".join(sorted(_ENFORCEABLE)) + ".")}
    val, err = _pref_value(key, value)
    if err:
        return {"ok": False, "error": "bad_value", "key": key, "message": err}
    _prefs.set_value(db, key, val, " ".join(x for x in [raw_key, str(value)] if x), _ENFORCEABLE)
    store.save(WID, db)
    return {"ok": True, "stored_as": "rule", "key": key, "value": val,
            "how": _ENFORCEABLE[key], "prefs": dict(db["prefs"])}

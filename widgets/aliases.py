#
# Alias de widget — edición QUIRÚRGICA del manifest (V2-082, D1 keyword≡alias).
#
# "Añade el alias WhatsApp al widget de mensajería" (voz o texto) NO regenera el widget: es una escritura ATÓMICA
# del campo `manifest["aliases"]`, hermana de `widget_data` (que toca datos) pero sobre la IDENTIDAD. Barata,
# determinista, sin agente headless. Con GUARD de colisión: un alias pertenece a UNA sola pieza (widget o superficie
# de sistema) → preserva la certeza del resolver. Migración perezosa: si el widget aún no tiene `aliases`, se siembra
# de `name`+`keywords` en la primera edición (una sola lista de identidad).
#
from __future__ import annotations

import json
import os
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))


def _safe(wid: str) -> str:
    return "".join(c for c in os.path.basename(wid or "") if c.isalnum() or c in "-_")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _manifest_path(wid: str) -> str:
    return os.path.join(HERE, _safe(wid), "manifest.json")


def _load(wid: str):
    p = _manifest_path(wid)
    if not _safe(wid) or not os.path.isfile(p):
        return None, p
    try:
        return json.load(open(p, encoding="utf-8")), p
    except Exception:
        return None, p


def _current_aliases(man: dict) -> list[str]:
    """Alias vigentes del manifest, sembrando de name+keywords si aún no existe el campo (migración perezosa)."""
    from . import registry
    if man.get("aliases"):
        return list(man["aliases"])
    return registry.widget_identity(man)["aliases"]        # name + keywords, dedup, casing preservado


def _owner_of(alias: str, exclude_id: str):
    """(owner_id, surface) de quién posee ya `alias` (widget o superficie), o (None, None). Excluye `exclude_id`."""
    from . import registry
    an = _norm(alias)
    for r in registry.registry():
        if r["id"] == exclude_id:
            continue
        if any(_norm(a) == an for a in r["aliases"]):
            return r["id"], r["surface"]
    return None, None


def _write(man: dict, path: str, aliases: list[str]) -> None:
    """Escribe `aliases` en el manifest de forma ATÓMICA (tmp + os.replace) e invalida las cachés del resolver."""
    man = dict(man)
    man["aliases"] = aliases
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    from . import runtime
    runtime.invalidate()
    try:
        from . import registry
        registry.refresh_state()
    except Exception:
        pass


def add(widget_id: str, alias: str) -> dict:
    """Añade un alias al widget. Rechaza si colisiona con otro widget o una superficie de sistema. Idempotente
    (si ya lo tiene, ok sin cambios). Devuelve {ok, aliases} o {ok:False, error[, owner]}."""
    wid = _safe(widget_id)
    alias = str(alias or "").strip()
    if not alias:
        return {"ok": False, "error": "alias vacío"}
    man, path = _load(wid)
    if man is None:
        return {"ok": False, "error": f"widget '{widget_id}' no existe"}
    cur = _current_aliases(man)
    if any(_norm(a) == _norm(alias) for a in cur):
        return {"ok": True, "aliases": cur, "unchanged": True}
    owner, surface = _owner_of(alias, wid)
    if owner is not None:
        return {"ok": False, "error": f"el alias «{alias}» ya lo usa "
                f"{'la superficie de sistema' if surface == 'system' else 'el widget'} «{owner}»", "owner": owner}
    cur = cur + [alias]
    _write(man, path, cur)
    return {"ok": True, "aliases": cur, "id": wid}


def remove(widget_id: str, alias: str) -> dict:
    """Quita un alias del widget. NO permite quitar el NOMBRE canónico (sin nombre no se abre). Idempotente."""
    wid = _safe(widget_id)
    alias = str(alias or "").strip()
    man, path = _load(wid)
    if man is None:
        return {"ok": False, "error": f"widget '{widget_id}' no existe"}
    name = str(man.get("name") or man.get("title") or wid).strip()
    if _norm(alias) == _norm(name):
        return {"ok": False, "error": f"«{alias}» es el nombre del widget; no se puede quitar (renómbralo)"}
    cur = _current_aliases(man)
    new = [a for a in cur if _norm(a) != _norm(alias)]
    if len(new) == len(cur):
        return {"ok": True, "aliases": cur, "unchanged": True}
    _write(man, path, new)
    return {"ok": True, "aliases": new, "id": wid}


def check_collision(widget_id: str, alias: str) -> str | None:
    """Fachada para el generador: devuelve el id que YA posee `alias` (widget/superficie) o None. Reutilizable
    para rechazar al CREAR un widget con un alias ocupado."""
    owner, _ = _owner_of(alias, _safe(widget_id))
    return owner

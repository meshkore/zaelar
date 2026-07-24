#
# files/store.py — SHIM de compatibilidad (V2-003 · T55). El módulo `files/` se PLIEGA en la memoria central:
# la vieja bandeja plana files/uploads/ y su índice los absorbe la capa EPISÓDICA de `memory/` (bytes en el
# data-dir de la memoria + resumen buscable embebido; el retriever del cerebro los encuentra por su cuenta,
# sin ruta absoluta ni tools de fichero de Hermes — la nota [SISTEMA] de ruta se retiró en este cambio).
#
# Se conserva este shim SOLO para no romper importadores externos; delega en memory.api. La migración de lo ya
# subido (files/uploads/*) la hace `memory.migrate_inbox()` en el arranque (perezosa, idempotente, NO destructiva).
#
from memory import api as _memapi


def save_upload(filename: str, data: bytes) -> str:
    """Compat: guarda en la memoria episódica y devuelve la ruta del binario almacenado."""
    ref = _memapi.write_episode(data, filename=filename)
    return ref["path"]


def list_files() -> list[dict]:
    """Compat: listado plano derivado de los episodios de memoria (name/size/mtime≈created)."""
    return [
        {"name": e["name"], "size": e.get("bytes"), "mtime": e.get("created")}
        for e in _memapi.list_episodes()
    ]

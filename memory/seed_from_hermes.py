"""memory/seed_from_hermes.py — One-shot seeding of central memory from Hermes (V2-003 · T56).

**Best-effort, idempotent, READ-ONLY** importer for what Hermes already knew about the operator:
`~/.hermes/memories/USER.md` (perfil + preferencias de trato) y `MEMORY.md` (recuerdos generales). Ambos son
texto libre con secciones separadas por `§`. NO toca `~/.hermes/` (solo lee); si no hay Hermes instalado, no
hace nada y no falla — es una siembra, no una dependencia.

What it does:
  - `state`: extrae del perfil el **nombre del operador** y el **idioma** (heurística simple) → `state.patch`.
  - `memories`: cada sección `§` no vacía entra como recuerdo **pinned** (`kind='pref'` para USER.md,
    `kind='fact'` para MEMORY.md, `level='long'`). Los pinned NUNCA los borra el consolidador.

Idempotencia: antes de insertar comprueba coincidencia EXACTA de texto (`SELECT ... WHERE text=?`) → re-ejecutar
no duplica. Pensado para correr una vez en el arranque (o a mano) mientras migramos de Hermes al cerebro v2.
"""
import os
import re
from pathlib import Path

from . import db as _db
from . import state as _state
from . import writer as _writer

_NAME_RE = re.compile(r"Nombre:\s*([A-Za-zÀ-ÿ']+)", re.IGNORECASE)


def _hermes_dir(override=None) -> Path:
    if override:
        return Path(override)
    env = os.getenv("HERMES_MEMORIES_DIR")
    if env:
        return Path(env)
    return Path.home() / ".hermes" / "memories"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _sections(text: str) -> list[str]:
    return [s.strip() for s in text.split("§") if s.strip()]


def _exists(text: str) -> bool:
    row = _db.get_db().query_one("SELECT id FROM memories WHERE text=? LIMIT 1", (text,))
    return row is not None


def _seed_state(user_text: str) -> dict:
    """Extract the name and language from the profile without overwriting manual seeds."""
    fields: dict = {}
    m = _NAME_RE.search(user_text)
    if m:
        fields["operator_name"] = m.group(1).strip()
    low = user_text.lower()
    if "castellano" in low or "español" in low or "espanol" in low:
        fields["language"] = "es"
    elif "english" in low or "inglés" in low or "ingles" in low:
        fields["language"] = "en"
    if not fields:
        return {}
    cur = _state.read()
    # Do not overwrite an existing name (respect later operator edits).
    if cur.get("operator_name") and "operator_name" in fields:
        fields.pop("operator_name")
    # Do not rewrite when the language already matches and there is nothing else to add.
    if fields.get("language") == cur.get("language"):
        fields.pop("language", None)
    if not fields:
        return {}
    _state.patch(fields)
    return fields


def seed(hermes_dir=None) -> dict:
    """Run seeding. Return {seeded, skipped, state_updated, source_present}."""
    d = _hermes_dir(hermes_dir)
    user_text = _read(d / "USER.md")
    mem_text = _read(d / "MEMORY.md")
    source_present = bool(user_text or mem_text)
    if not source_present:
        return {"seeded": 0, "skipped": 0, "state_updated": False, "source_present": False}

    state_updated = bool(_seed_state(user_text)) if user_text else False

    seeded = skipped = 0
    for text, kind in ((s, "pref") for s in _sections(user_text)):
        if _exists(text):
            skipped += 1
            continue
        _writer.insert_memory(text, level="long", kind=kind, importance=0.85, weight=0.8, pinned=True)
        seeded += 1
    for text in _sections(mem_text):
        if _exists(text):
            skipped += 1
            continue
        _writer.insert_memory(text, level="long", kind="fact", importance=0.8, weight=0.75, pinned=True)
        seeded += 1

    return {"seeded": seeded, "skipped": skipped, "state_updated": bool(state_updated),
            "source_present": True}


if __name__ == "__main__":  # Manual execution: `python -m memory.seed_from_hermes`
    import json
    print(json.dumps(seed(), ensure_ascii=False, indent=2))

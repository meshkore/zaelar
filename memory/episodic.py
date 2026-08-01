"""memory/episodic.py — memoria EPISÓDICA lazy-loaded (V2-002 · T51 · V2-003 · T53).

Ficheros/PDF subidos. Se custodian con un **resumen embebido** que SÍ participa en la búsqueda (una fila en
`memories`, kind='summary', indexada en vec+fts vía el writer); el fichero completo solo se carga bajo orden
("consulta el informe") o si el retriever lo selecciona — **nunca en contexto por defecto**.

- V2-002 (T51): esqueleto — `register()` (crea el resumen buscable + la fila `episodic`), `get()` (metadatos),
  `load_text()`/`load_bytes()` (carga LAZY desde disco).
- V2-003 (T53): la memoria **absorbe `files/uploads/`**. Los bytes viven ahora en el data-dir de la memoria
  (`episodic_dir()`, junto a `zaelar.db`); `write_episode(data, filename, mime)` guarda el binario + genera un
  RESUMEN buscable best-effort (nombre + extracto de texto). La sumarización semántica profunda es del agente de
  memoria (V2-006, hook `summarize_fn`), no de aquí. `migrate_inbox()` = migración PEREZOSA, idempotente y NO
  destructiva de la vieja bandeja `files/uploads/`.
"""
import json
import mimetypes
import os
import time
from pathlib import Path

from . import db as _db
from . import writer as _writer

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEXT_MIMES = ("text/", "application/json", "application/xml", "application/javascript")
_TEXT_EXTS = {".txt", ".md", ".json", ".csv", ".log", ".xml", ".yaml", ".yml", ".py", ".js", ".html", ".css"}


def episodic_dir() -> Path:
    """Directorio de bytes de la memoria episódica. Junto al `zaelar.db` (respeta `ZAELAR_DB` en tests/headless).
    Sustituye a la vieja bandeja plana `files/uploads/` (V2-003)."""
    d = _db.db_path().parent / "episodic"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    """Frontera de confianza para un nombre de fichero del cliente: basename, sin path traversal, sin dotfiles."""
    base = os.path.basename((name or "").strip())
    cleaned = "".join(c for c in base if c.isalnum() or c in "-_.")
    cleaned = cleaned.lstrip(".")
    return cleaned or "archivo"


def _store_bytes(data: bytes, filename: str) -> Path:
    """Escribe bytes en el data-dir episódico resolviendo colisiones (nunca sobreescribe). Escritura atómica
    (tmp+rename → un lector nunca ve medio fichero). Devuelve la ruta absoluta."""
    name = _safe_name(filename)
    stem, ext = os.path.splitext(name)
    d = episodic_dir()
    candidate, n = name, 1
    while (d / candidate).exists():
        candidate = f"{stem}_{n}{ext}"
        n += 1
    path = d / candidate
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def _auto_summary(path: Path, filename: str, mime: str | None, data: bytes | None = None) -> str:
    """Resumen buscable best-effort SIN cerebro: nombre + tipo + (si es texto legible) un extracto. La
    sumarización semántica profunda la hace el agente de memoria (V2-006)."""
    label = filename or path.name
    head = f"Archivo: {label}"
    if mime:
        head += f" ({mime})"
    is_texty = (mime is not None and mime.startswith(_TEXT_MIMES)) or \
               (mime is None and path.suffix.lower() in _TEXT_EXTS)
    if is_texty:
        try:
            raw = data if data is not None else path.read_bytes()
            txt = " ".join(raw.decode("utf-8", errors="replace").split())[:800]
            if txt:
                return f"{head}. {txt}"
        except Exception:
            pass
    return head


def register(path: str, summary: str, *, mime: str | None = None, size: int | None = None,
             importance: float | None = None) -> dict:
    """Registra un episodio: crea el RESUMEN buscable (memories, embebido) + la fila `episodic`.

    Devuelve {episode_id, memory_id}. El resumen es lo único que participa en la búsqueda; el binario es lazy."""
    db = _db.get_db()
    from .clock import now as _clock_now
    now = _clock_now()
    if size is None:
        try:
            size = os.path.getsize(path)
        except OSError:
            size = None
    # el resumen entra como recuerdo 'summary' → embedding + fts vía el writer (único escritor).
    memory_id = _writer.insert_memory(summary, level="long", kind="summary", importance=importance)
    episode_id = db.execute(
        "INSERT INTO episodic (path, summary, memory_id, bytes, mime, created) VALUES (?,?,?,?,?,?)",
        (str(path), summary, memory_id, size, mime, now),
    )
    return {"episode_id": episode_id, "memory_id": memory_id}


def get(episode_id: int) -> dict | None:
    row = _db.get_db().query_one(
        "SELECT id, path, summary, memory_id, bytes, mime, created FROM episodic WHERE id=?",
        (int(episode_id),),
    )
    return dict(row) if row is not None else None


def by_memory(memory_id: int) -> dict | None:
    """Dado el id del recuerdo-resumen, devuelve su episodio (para que el retriever ofrezca la carga lazy)."""
    row = _db.get_db().query_one(
        "SELECT id, path, summary, memory_id, bytes, mime, created FROM episodic WHERE memory_id=?",
        (int(memory_id),),
    )
    return dict(row) if row is not None else None


def load_bytes(episode_id: int) -> bytes | None:
    """Carga LAZY del binario completo desde `path`. None si no existe (aún no persistido / borrado)."""
    ep = get(episode_id)
    if ep is None:
        return None
    p = Path(ep["path"])
    if not p.is_file():
        return None
    return p.read_bytes()


def load_text(episode_id: int, encoding: str = "utf-8") -> str | None:
    """Carga LAZY del contenido como texto. None si no existe o no es decodificable."""
    data = load_bytes(episode_id)
    if data is None:
        return None
    try:
        return data.decode(encoding, errors="replace")
    except Exception:
        return None


def write_episode(data: bytes, *, filename: str, mime: str | None = None,
                  summary: str | None = None, importance: float | None = None) -> dict:
    """Guarda `data` en el data-dir episódico + registra un RESUMEN buscable (V2-003). Reemplaza la vieja
    `files/store.save_upload`: el binario carga LAZY, el resumen participa en la búsqueda desde ya.

    Si no se pasa `summary`, se genera uno best-effort (nombre + extracto de texto). Devuelve
    {episode_id, memory_id, path, name, summary, bytes}."""
    if mime is None and filename:
        mime = mimetypes.guess_type(filename)[0]
    path = _store_bytes(data, filename)
    size = len(data)
    if summary is None:
        summary = _auto_summary(path, filename, mime, data=data)
    ref = register(str(path), summary, mime=mime, size=size, importance=importance)
    ref.update({"path": str(path), "name": path.name, "summary": summary, "bytes": size})
    return ref


def list_episodes(limit: int = 200) -> list[dict]:
    """Listado plano de episodios (nombre/tamaño/mime/resumen), lo más reciente primero. Sustituye a
    `files.store.list_files()` para la verificación y un futuro widget de navegación."""
    rows = _db.get_db().query(
        "SELECT id, path, summary, memory_id, bytes, mime, created "
        "FROM episodic ORDER BY created DESC LIMIT ?",
        (int(limit),),
    )
    out = []
    for r in rows:
        d = dict(r)
        d["name"] = os.path.basename(d.get("path") or "")
        out.append(d)
    return out


def migrate_inbox(src_dir: str | os.PathLike | None = None) -> dict:
    """Migración PEREZOSA one-shot de la vieja bandeja plana `files/uploads/` → memoria episódica.
    Idempotente (marca lo migrado en `episodic/.migrated.json`, no re-importa) y **NO destructiva** (no borra
    el origen hasta que el operador verifique). Best-effort: un fichero ilegible no aborta el resto."""
    src = Path(src_dir) if src_dir else (_REPO_ROOT / "files" / "uploads")
    marker = episodic_dir() / ".migrated.json"
    done: set[str] = set()
    if marker.exists():
        try:
            done = set(json.loads(marker.read_text()))
        except Exception:
            done = set()
    migrated: list[str] = []
    skipped = 0
    if src.is_dir():
        for p in sorted(src.iterdir()):
            if not p.is_file() or p.name.startswith(".") or p.name.endswith(".tmp"):
                continue
            if p.name in done:
                skipped += 1
                continue
            try:
                write_episode(p.read_bytes(), filename=p.name)
                done.add(p.name)
                migrated.append(p.name)
            except Exception:
                continue
    if migrated:
        try:
            marker.write_text(json.dumps(sorted(done)))
        except Exception:
            pass
    return {"migrated": migrated, "skipped": skipped}

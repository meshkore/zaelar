"""Episodic files through the facade (lazy load, register, write/adopt bytes, list, inbox migration), plus the
two off-hot-path doors: the consolidation cycle and the vault's secret detector over a free text."""
from .. import consolidator as _consolidator
from .. import episodic as _episodic
from .events import _emit


def load_episode(episode_id: int, as_text: bool = True):
    """LAZY load of an episode's bytes/text (on demand). Direct."""
    return _episodic.load_text(episode_id) if as_text else _episodic.load_bytes(episode_id)


def register_episode(path: str, summary: str, **kwargs) -> dict:
    """Registers an episodic file (searchable summary + episodic row). Emits memory.updated."""
    ref = _episodic.register(path, summary, **kwargs)
    _emit("memory.updated", {"op": "episode", **ref})
    return ref


def write_episode(data: bytes, *, filename: str, mime: str | None = None,
                  summary: str | None = None, importance: float | None = None) -> dict:
    """Stores bytes in episodic memory (data dir) + a searchable summary (V2-003); written by the upload endpoint.
    Emits memory.updated. Direct (the caller needs the id)."""
    ref = _episodic.write_episode(data, filename=filename, mime=mime, summary=summary, importance=importance)
    _emit("memory.updated", {"op": "episode", "id": ref.get("memory_id"), "name": ref.get("name")})
    return ref


def episode_inbox():
    """The directory an upload is streamed into before `adopt_episode` (V2-809). Direct."""
    return _episodic.inbox_dir()


def adopt_episode(src_path, *, filename: str, mime: str | None = None,
                  summary: str | None = None, importance: float | None = None) -> dict:
    """`write_episode` for a file already streamed to disk: moved, never loaded into memory (V2-809). Emits
    memory.updated. Direct."""
    ref = _episodic.adopt_episode(src_path, filename=filename, mime=mime, summary=summary, importance=importance)
    _emit("memory.updated", {"op": "episode", "id": ref.get("memory_id"), "name": ref.get("name")})
    return ref


def list_episodes(limit: int = 200) -> list[dict]:
    """Flat list of episodes (verification / a future widget). Direct."""
    return _episodic.list_episodes(limit=limit)


def migrate_inbox(src_dir=None) -> dict:
    """Lazy, idempotent, NON-destructive migration of `files/uploads/` → episodic memory (V2-003)."""
    rep = _episodic.migrate_inbox(src_dir)
    if rep.get("migrated"):
        _emit("memory.updated", {"op": "migrate_inbox", "count": len(rep["migrated"])})
    return rep


def redact_secrets(text: str) -> str:
    """The vault's detector over a free text (a password, a card, a code said aloud → «secreto guardado») — the
    facade door for a caller outside memory (V2-778 F4-37, `observability/scrub.py`)."""
    from .. import secrets as _secrets
    return _secrets.redact(text)[0]


# ── periodic job (not hot path) ──────────────────────────────────────────────────────────────────────────
def consolidate(**kwargs) -> dict:
    """One consolidation («sleep») cycle, fired by the orchestrator loop (V2-005). Emits memory.updated."""
    rep = _consolidator.consolidate(**kwargs)
    _emit("memory.updated", {"op": "consolidate", **{k: rep[k] for k in ("deduped", "evicted")}})
    return rep

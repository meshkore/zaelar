"""The worker's METHOD: the playbook's nine checkpoints, in the session's language (V2-851 §6, F3).

Not code: the method given with the brief. Which playbook a task follows is read from facts the engine already has —
the errand's surface, its mandate, the request's SHAPE — never from words of the request (a table of verbs is not a
router, V2-750). The row's `playbook` column records the name, so «how is it going» and the battery read it back.

  · `which(...)` — `document` (its surface is a document), `message` (it runs under a mandate that names channels),
    `lista` (the request is unmistakably a list by shape, `nucleo/batch/detect.unmistakable`), else `errand`;
  · `done_when(name)` — the end state, stated up front;
  · `block(name, done_when)` — the nine checkpoints; a `lista` adds how a list is walked (one worker, one item at a
    time — the list's own rows in `nucleo/batch` stay as they are).

Rules are DATA in the brief (`rules_bridge.brief_block`); the door is their only authoritative reader.
"""
from __future__ import annotations

ERRAND, DOCUMENT, MESSAGE, LISTA = "errand", "document", "message", "lista"
#: The checkpoint loop's bound (§6): a third failure at the same checkpoint → `ask` or end with the reason.
ATTEMPTS = 2


def _note(what: str, e: Exception) -> None:
    from loguru import logger
    logger.debug(f"playbook: {what} unread ({type(e).__name__}: {e})")


def _words(path: str, default=""):
    try:
        from i18n import langs
        return langs.words(f"worker_brief.{path}", default=default)
    except Exception:  # noqa: BLE001 — a missing pack never blocks a worker
        return default


def which(*, surface: str = "", mandate: dict | None = None, request: str = "", declared: str = "") -> str:
    """The playbook a task follows, from what the engine already decided about it. One the escalation already DECLARED
    (an answered send names `message`, V2-851 F2e) wins over every inference below."""
    if declared in (ERRAND, DOCUMENT, MESSAGE, LISTA):
        return declared
    try:
        from nucleo import surfaces as _surfaces
        if _surfaces.opens_doc(surface or ""):
            return DOCUMENT
    except Exception as e:  # noqa: BLE001
        _note("surface", e)
    if (mandate or {}).get("channels"):
        return MESSAGE
    try:
        from nucleo.batch import detect
        if detect.unmistakable(request or ""):
            return LISTA
    except Exception as e:  # noqa: BLE001
        _note("list shape", e)
    return ERRAND


def done_when(name: str) -> str:
    """The end state the worker states at checkpoint 1 (the research brief, when there is one, adds its funnel)."""
    return str(_words(f"done_when.{name}") or _words(f"done_when.{ERRAND}") or "")


def block(name: str, end_state: str) -> str:
    """The method block for a playbook, or '' when the language pack has none."""
    tpl = str(_words("playbook") or "")
    if not tpl:
        return ""
    out = tpl.format(name=name, attempts=ATTEMPTS, done_when=end_state)
    if name == LISTA:
        extra = str(_words("lista") or "")
        if extra:
            out += "\n" + extra
    return out


def record(rec, name: str) -> None:
    """Write the playbook on the task's durable row (the `playbook` column). Never raises."""
    try:
        from nucleo.circuit import ledger
        _ts = ledger.store()                      # the task store through its one importer (memory boundary)
        uid = str(getattr(rec, "uid", "") or "") or ledger.task_uid(getattr(rec, "task_id", ""))
        if uid and _ts.task_get(uid):
            _ts.task_patch(uid, playbook=name)
    except Exception as e:  # noqa: BLE001 — a row without its playbook is the row it was
        _note("record", e)

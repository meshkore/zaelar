"""A blank sheet the agent fills with ONE thing worth READING (V2-549).

## The boundary with `results`

`results` answers «find me the options»: a SET you compare. This one answers «give me the recipe»: ONE piece of
content, already chosen, that you read. A single document in a comparison surface reads as a list of links; a
comparison in here loses its columns.

## Three kinds, and no fourth

`markdown` (plain text is markdown with no marks), `html` (an already-formatted fragment) and `pdf` (a file the
browser displays). Anything else has a better home: photos → `imagenes`, a live page → `navegador`, a set →
`results`.

Nothing here reaches the network: `show` is handed content somebody else produced; `data.py` is stdlib-only.
"""
from __future__ import annotations

import os
import re
import time

from .. import store
from .blocks import _best_block, _blocks, _clean_phases, _process, _sections  # noqa: F401

WIDGET_ID = "documento"
DB_VERSION = 1

# One JSON file, rewritten on every save; past this a report is a corpus, which belongs in a file, not a card.
MAX_CHARS = 60000
_KINDS = ("markdown", "html", "pdf")
# What the operator or a model might call each kind; plain text goes to the markdown renderer.
_KIND_ALIASES = {
    "markdown": "markdown", "md": "markdown", "text": "markdown", "txt": "markdown", "plain": "markdown",
    "texto": "markdown", "nota": "markdown", "receta": "markdown", "informe": "markdown", "report": "markdown",
    "html": "html", "htm": "html", "web": "html", "rich": "html",
    "pdf": "pdf", "documento": "pdf", "document": "pdf", "file": "pdf",
}
# A `src` that is a bare file name is served from this widget's OWN data directory through the generic asset
# route. That is the only path a widget may read from, and the only one the browser can reach.
_ASSET_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_TAG_RE = re.compile(r"<[^>]+>")


def _seed() -> dict:
    return {"kind": "markdown", "title": "", "subtitle": "", "body": "", "src": "", "source": "", "updated": 0,
            # A REPORT errand binds this sheet to its task: `task` the live errand, `task_title` its name, `process`
            # the history persisted once it closed; while alive the narrative is DERIVED per read (V2-644).
            "task": "", "task_title": "", "process": []}


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION)


def _kind(raw, fallback: str = "markdown") -> str:
    k = str(raw or "").strip().lower()
    return _KIND_ALIASES.get(k, k if k in _KINDS else fallback)


def _text(raw, cap: int) -> str:
    return " ".join(str(raw or "").split())[:cap]


def _asset_names() -> list[str]:
    try:
        # `state.json` is this widget's own store, not a document somebody put here to be read.
        return sorted(n for n in os.listdir(store.data_dir(WIDGET_ID))
                      if not n.startswith(".") and n != "state.json")
    except OSError:
        return []


def _resolve_src(raw) -> tuple[str, str]:
    """A `src` the browser can actually open, or ('', reason): an http(s) URL, or the name of a file this widget
    already holds. A path is deliberately NOT accepted — a widget reads inside its own data directory or nowhere."""
    s = str(raw or "").strip()
    if not s:
        return "", "hace falta 'src': la URL del PDF, o el nombre del fichero si ya está guardado aquí"
    if s.startswith(("http://", "https://")):
        return s[:1000], ""
    if s.startswith("/widgets/"):                          # already resolved (a re-show of what we served)
        return s[:400], ""
    name = os.path.basename(s)
    if not _ASSET_RE.match(name):
        return "", "el 'src' tiene que ser una URL http(s) o el nombre de un fichero guardado en este equipo"
    have = _asset_names()
    if name not in have:
        tengo = ", ".join(have[:8]) if have else "ninguno"
        return "", f"aquí no hay ningún fichero llamado «{name}» (guardados: {tengo})"
    return f"/widgets/{WIDGET_ID}/asset/{name}", ""


def view_data(q: str = "") -> dict:
    db = _load()
    body = str(db.get("body") or "")
    src = str(db.get("src") or "")
    return {
        "kind": _kind(db.get("kind")),
        "title": str(db.get("title") or ""),
        "subtitle": str(db.get("subtitle") or ""),
        "body": body,
        "src": src,
        "source": str(db.get("source") or ""),
        "updated": int(db.get("updated") or 0),
        "chars": len(body),
        "empty": not (body or src),
        "process": _process(db),
        "focus": db.get("focus") if isinstance(db.get("focus"), dict) else None,   # V2-773 — set by `goto`
        # V2-776 L2 — the headings as rows: «go to the part about proof of work» has a section to be attested.
        "sections": _sections(body),
    }


# ── the errand binding (V2-644) — called by `nucleo/docsheet.py`, never by a worker action ──────────────────
def begin_task(title: str, task_id: str) -> None:
    """A REPORT errand was commissioned: bind this sheet to it and start blank — the old document under a live
    process view would read as the answer arriving instantly (as results' `begin_task(fresh=True)`)."""
    db = _seed()
    db.update({"task": str(task_id or ""), "task_title": _text(title, 120)})
    store.save(WIDGET_ID, _stamp(db))


def retitle_task(title: str, task_id: str) -> None:
    """The errand's composed name reaches the process header. Only for the errand this sheet is bound to —
    a late title from a dead errand must not rename somebody else's document."""
    db = _load()
    if str(db.get("task") or "") != str(task_id or "") or not str(task_id or ""):
        return
    db["task_title"] = _text(title, 120)
    store.save(WIDGET_ID, _stamp(db))


def finish_task(task_id: str, phases: list) -> None:
    """The bound errand is OVER: keep its narrative so the report retains the account of how it was reached
    (the live record disappears with the errand), and release the binding."""
    db = _load()
    if str(db.get("task") or "") != str(task_id or "") or not str(task_id or ""):
        return
    db["task"] = ""
    db["process"] = _clean_phases(phases)
    store.save(WIDGET_ID, _stamp(db))


def prompt_digest() -> str:
    """What is ON the sheet, so the brain can ANSWER about it instead of re-fetching it (`widgets/refs.py`).
    Only asked for while the card is OPEN. A PDF is never read here, so the digest gives its title and says the
    inside is not ours to quote."""
    db = _load()
    title = str(db.get("title") or "").strip()
    kind = _kind(db.get("kind"))
    head = f"«{title}»" if title else "sin título"
    if kind == "pdf":
        return (f"En la hoja hay un PDF {head}. No puedo leer su interior desde aquí: si te preguntan por su "
                f"contenido, dilo — no lo inventes.")
    body = str(db.get("body") or "")
    if not body.strip():
        # A bound errand still working is not an empty sheet: the operator is watching its process view (V2-644).
        proc = _process(db)
        if proc and proc.get("alive"):
            last = (proc.get("phases") or [""])[-1]
            head_t = str(db.get("task_title") or "").strip()
            return (f"La hoja enseña el PROCESO del informe en curso{f' «{head_t}»' if head_t else ''}: "
                    f"aún no hay documento. Última fase: {last or 'arrancando'}.")
        return "La hoja está ABIERTA y VACÍA: el operador no ve nada dentro."
    if kind == "html":
        body = _TAG_RE.sub(" ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    cut = body[:1400]
    if len(body) > len(cut):
        cut = cut.rsplit("\n", 1)[0] + "\n…"
        # The WHOLE outline rides with the cut: a cut is not an absence, and the headings say what lies past it.
        heads = [h.strip("# ").strip() for h in re.findall(r"(?m)^#{1,4} .+$", body)]
        if heads:
            cut += ("\n(Recortado: el documento sigue. TODAS sus secciones, en orden: " + " · ".join(heads[:30]) + ")")
    return f"En la hoja, {head} ({kind}):\n{cut}"


def _stamp(db: dict) -> dict:
    db["updated"] = int(time.time())
    return db


from .actions import (  # noqa: E402 — the handlers read the helpers above back through this module
    _a_append, _a_clear, _a_goto, _a_save_to_library, _a_show)

# The table is read off the `_a_<action>` names bound here, so no list of action words is written twice.
ACTIONS = {name[3:]: fn for name, fn in list(globals().items()) if name.startswith("_a_")}


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    handler = ACTIONS.get(str(action or "").strip().lower())
    if handler is None:
        return {"ok": False, "error": f"acción desconocida: {action}"}
    return handler(action, p)

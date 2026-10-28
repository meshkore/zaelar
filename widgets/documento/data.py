"""A blank sheet the agent fills with ONE thing worth READING (V2-549).

The operator asked for it in those words: «a widget that is like a blank sheet, a generic one, to show other
things — a PDF, an HTML, a recipe, a report we make — basically the square, and we fill it with the content».

## The boundary that earns it a place next to `results`

`results` answers «find me the options»: a SET of candidates you compare, with cards, sources and criteria.
This one answers «give me the recipe»: ONE piece of content, already chosen, that you sit down and read. The
operator drew the line himself — «I asked for a recipe and the system brought a list of recipes, and I only
ordered one, and I trust its criteria». A single document dropped into a comparison surface reads as a list of
links (the exact complaint that created the photo viewer, V2-457); a comparison dropped in here loses its
columns.

## Three kinds, and the reason there is no fourth

`markdown` (a recipe, a report, notes — plain text is markdown that happens to carry no marks), `html` (a
fragment somebody already formatted) and `pdf` (a file, local or remote, the browser already knows how to
display). A fourth kind would need a fourth renderer inside a widget whose whole point is being small, and
everything one might ask for is already somewhere better: photos are the `imagenes` viewer, a live page being
driven is `navegador`, a set to compare is `results`. Naming those borders costs one line each here and saves
this widget from slowly becoming all of them.

Nothing in here reaches the network. `show` is handed content that somebody else already produced — the fast
turn writing a recipe it knows, or a worker delivering a report through `nucleo.widget_cli` — which is the same
contract every other viewer in this catalog has: `data.py` is stdlib-only and never fetches.
"""
from __future__ import annotations

import os
import re
import time

from .. import store
from .blocks import _best_block, _blocks, _clean_phases, _process, _sections  # noqa: F401

WIDGET_ID = "documento"
DB_VERSION = 1

# One JSON file, rewritten on every save. A report can be long and still be a report; past this it is a corpus,
# and a corpus belongs in a file, not in a card the operator scrolls.
MAX_CHARS = 60000
_KINDS = ("markdown", "html", "pdf")
# What the operator or a model might call each kind. `text`/`txt`/`plain`/`md` all end up in the markdown
# renderer because plain text IS markdown with no marks — refusing it would be refusing the commonest case.
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
            # V2-644 — a REPORT errand (surface `informe`) binds this sheet to its task at commission time:
            # `task` names the live errand, `task_title` its composed name, `process` the persisted history
            # once the errand closed. While the errand is alive the narrative is DERIVED per read, not stored.
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
    """A `src` the browser can actually open, or ('', reason). Two shapes and no third: an http(s) URL, or the
    name of a file this widget already holds. A path is deliberately NOT accepted — a widget reads inside its
    own data directory or nowhere, and quietly accepting `../..` is how that rule stops being a rule."""
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
    """A REPORT errand was commissioned: bind this sheet to it and start blank. Fresh on purpose — the same
    trade the results sheet makes (`begin_task(fresh=True)`): the operator asked for a NEW report, and the
    old document staying on screen under a live process view would read as the answer arriving instantly."""
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

    This is the reason a document widget is worth more than a screenshot: with the recipe up, «how much flour?»
    is a question about something we already have. Only asked for while the card is OPEN, so a closed sheet
    costs nothing per turn. A PDF is the honest exception — we hand the browser a file and never read it, so
    the digest says the title and says plainly that the inside is not ours to quote."""
    db = _load()
    title = str(db.get("title") or "").strip()
    kind = _kind(db.get("kind"))
    head = f"«{title}»" if title else "sin título"
    if kind == "pdf":
        return (f"En la hoja hay un PDF {head}. No puedo leer su interior desde aquí: si te preguntan por su "
                f"contenido, dilo — no lo inventes.")
    body = str(db.get("body") or "")
    if not body.strip():
        # V2-644 — a bound errand still working is a different fact from an empty sheet: the operator is
        # watching the process view, and «no ves nada» would contradict his own screen.
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
        # The WHOLE outline rides with the cut: demo pass 2026-09-28, full11 F2 — «go to the part about the complaints
        # against the king» over a document that HAS «## The grievances against King George III», and the reply said
        # «the grievances aren't written up yet», because the digest stopped at the natural-rights section. A cut is
        # not an absence, and the headings say what lies past it.
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

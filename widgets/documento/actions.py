"""The documento sheet's action handlers — one function per action, dispatched by `data.ACTIONS`.

Split out of `data.py` (it keeps the contract and the table). Shared helpers are read back through the `data`
module, so a test that patches one of them there is honoured here too.
"""
from __future__ import annotations

import os
import re
import time

from .. import store
from . import data as _d
from .blocks import _best_block, _blocks


def _a_show(action: str, p: dict) -> dict:
    db = _d._load()
    kind = _d._kind(p.get("kind"), "")
    body = str(p.get("body") or p.get("content") or p.get("text") or "")[:_d.MAX_CHARS]
    src = p.get("src") or p.get("url") or p.get("file")
    if not kind:                                       # not told → infer from what actually arrived
        kind = "pdf" if (src and not body) else "markdown"
    resolved = ""
    if kind == "pdf":
        resolved, why = _d._resolve_src(src)
        if why:
            return {"ok": False, "error": why}
    elif not body.strip():
        # An empty `show` must NOT blank a sheet the operator is reading (the `imagenes` lesson): they
        # would be left staring at nothing with no way back, and the honest report is that nothing came.
        # A `query` or a topic is not a document: this card does not search, its caller writes the text.
        # The `error` tells the model's correction pass that; `say` is what the operator may hear.
        return {"ok": False, "say": "widgets.documento.refusal_empty",
                "error": "no llegó ningún contenido para la hoja ('body' vacío): esta hoja no busca — "
                         "escribe TÚ el documento entero en 'body' (markdown) y vuelve a llamar a 'show'"}
    db.pop("focus", None)
    if _d._text(p.get("title"), 120) != db.get("title"):
        db.pop("saved_rel", None)                      # another document: it gets its own file
    db.update({"kind": kind, "body": "" if kind == "pdf" else body, "src": resolved,
               "title": _d._text(p.get("title"), 120),
               "subtitle": _d._text(p.get("subtitle") or p.get("summary"), 200),
               "source": _d._text(p.get("source"), 80)})
    store.save(_d.WIDGET_ID, _d._stamp(db))
    return {"ok": True, "kind": kind, "title": db["title"], "chars": len(db["body"])}


def _a_append(action: str, p: dict) -> dict:
    db = _d._load()
    kind = _d._kind(db.get("kind"))
    if kind == "pdf":
        return {"ok": False, "error": "a un PDF no se le puede añadir texto; usa 'show' con el documento entero"}
    add = str(p.get("body") or p.get("content") or p.get("text") or "")
    if not add.strip():
        return {"ok": False, "say": "widgets.documento.refusal_empty", "error": "no llegó nada que añadir ('body' vacío)"}
    old = str(db.get("body") or "")
    body = old + ("\n\n" if old else "") + add
    if len(body) > _d.MAX_CHARS:
        # Refuse WHOLE rather than truncate. A silent cut lands mid-sentence and reads like a finished
        # document that simply stops — the caller has no way to know it was cut, and neither has the
        # operator. Saying it is full is the only honest answer, and it names the way out.
        return {"ok": False, "say": "widgets.documento.refusal_full", "error": f"la hoja ya está llena ({_d.MAX_CHARS} caracteres): no cabe lo que "
                                      f"añades. Usa 'show' para reemplazarla por una versión más corta",
                "chars": len(old)}
    db["body"] = body
    if not db.get("title"):
        db["title"] = _d._text(p.get("title"), 120)
    store.save(_d.WIDGET_ID, _d._stamp(db))
    return {"ok": True, "added": len(body) - len(old), "chars": len(body)}


def _a_goto(action: str, p: dict) -> dict:
    db = _d._load()
    # «Show me the section explaining why the colonies wanted independence» over the Declaration on screen
    # (demo run, 2026-09-26): the reply described the passage and the sheet never moved — no action could.
    # The best-matching heading or passage becomes the FOCUS; the card scrolls to it and marks it.
    body = str(db.get("body") or "")
    if _d._kind(db.get("kind")) == "pdf" or not body.strip():
        return {"ok": False, "error": "no hay texto en la hoja al que ir"}
    hit = _best_block(body, str(p.get("text") or p.get("section") or p.get("query") or p.get("item") or ""))
    if not hit:
        heads = [b.lstrip("# ").strip() for b in _blocks(body) if b.startswith("#")][:12]
        return {"ok": False, "error": "no encuentro ese pasaje — pásame un título o una frase suya",
                "headings": heads}
    # As the reader will SEE it: the card matches this against rendered text, where «**refused**» is
    # «refused» and a wrapped paragraph is one line (V2-773 audit — a passage with emphasis never matched).
    plain = " ".join(re.sub(r"[*_`~>#\[\]]+", "", hit).split())
    db["focus"] = {"text": plain[:160], "at": time.time()}
    store.save(_d.WIDGET_ID, _d._stamp(db))
    return {"ok": True, "found": plain[:200]}


def _a_clear(action: str, p: dict) -> dict:
    store.save(_d.WIDGET_ID, _d._stamp(_d._seed()))
    return {"ok": True, "empty": True}


def _a_save_to_library(action: str, p: dict) -> dict:
    db = _d._load()
    # V2-661 — «guárdalo en mis archivos» with the document ON SCREEN is one data-op, not an errand: the
    # text is already here. It lands on the library's documents shelf (the `archivos` card's truth), never
    # in this widget's own data directory, which no file manager shows. A PDF is a file we never held.
    kind = _d._kind(db.get("kind"))
    body = str(db.get("body") or "")
    if kind == "pdf" or not body.strip():
        return {"ok": False, "error": ("la hoja enseña un PDF que no tengo guardado: ábrelo desde su URL"
                                       if kind == "pdf" else "la hoja está vacía: no hay nada que guardar")}
    from library import index as _lib
    name = _d._text(p.get("name") or p.get("filename") or db.get("title"), 160) or "documento"
    if kind == "html" and not os.path.splitext(name)[1]:
        name += ".html"
    # The sheet OWNS its file: saving again updates it (demo pass 2026-09-28 — each save made «(1)», «(2)»…,
    # and the worker spent minutes renaming and deleting its own duplicates, asking him to authorise it).
    res = _lib.save_text(name, body, kind="documents", replace=str(db.get("saved_rel") or ""))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "no pude guardar el fichero"}
    db["saved_rel"] = res.get("rel") or ""
    store.save(_d.WIDGET_ID, db)
    ent = res.get("entry") or {}
    return {"ok": True, "file": {"name": ent.get("name") or name, "rel": res.get("rel") or ""},
            "path": res.get("path") or "", "where": "documents",
            "message": f"Guardado en tus archivos, en Documentos: «{ent.get('name') or name}»."}

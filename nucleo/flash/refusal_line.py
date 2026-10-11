"""nucleo/flash/refusal_line.py — what a widget's refusal may SAY to the operator, in the session's language.

Measured in `docs-single-recipe-not-a-list__us` (2026-10-10): «Give me the carbonara recipe.» → `documento:show`
with no body, refused with `{"error": "no llegó ningún contenido para la hoja ('body' vacío)"}`, and the text
channel answered «I'll get it on screen for you. I couldn't: no llegó ningún contenido para la hoja ('body'
vacío)» — a debug string, in Spanish, inside an English reply. Two things let it through: the text channel read
`message or error` (the `error` is for the MODEL, V2-652 — the voice rail already kept the two apart), and the
reply door could not tell the sentence was foreign because the English half outweighed it.

The rule, once for every widget and both channels:
  · the sentence comes from the widget's `say` (an i18n bundle key, so it exists in every session language),
    else from its `message` (product copy, written in Spanish by house convention), never from `error`;
  · anything shaped like code (a field name in quotes, a snake_case word, braces, backticks) is cut out;
  · a sentence in the OTHER product language is translated once (async callers), and when that is not possible
    or nothing speakable is left, the operator hears a plain generic line naming the card — the internal reason
    stays in the log.
"""
from __future__ import annotations

import re

_CODEY = re.compile(r"[{}`]|\b[a-z]+_[a-z_]+\b")
_QUOTED_FIELD = re.compile(r"\s*\([^()]*['\"][A-Za-z_]+['\"][^()]*\)")


def _code() -> str:
    try:
        from i18n import langs as _lg
        return str(_lg.current_code() or "es").lower()[:2]
    except Exception:  # noqa: BLE001
        return "es"


def clean(text: str) -> str:
    """`text` without the parts written for the model: «(… 'body' …)» asides and code-shaped sentences."""
    s = _QUOTED_FIELD.sub("", str(text or "")).strip()
    said = [c for c in re.split(r"(?<=[.;])\s+", s) if c.strip() and not _CODEY.search(c)]
    return " ".join(said).rstrip(";").strip()


def speakable(wid: str, res: dict) -> str:
    """The widget's own sentence for the operator, cleaned — `say` (bundle key) first, then `message`. Never `error`."""
    res = res if isinstance(res, dict) else {}
    key = str(res.get("say") or "").strip()
    if key:
        try:
            from i18n import runtime as _rt
            line = _rt.text(key, "", code=_code())
            if line:
                return line
        except Exception as e:  # noqa: BLE001 — the widget's `message` still speaks
            _debug("say", e)
    return clean(str(res.get("message") or ""))


def generic(wid: str) -> str:
    """The plain line when the widget gave nothing speakable: «the Document card didn't take it.»"""
    code = _code()
    try:
        from i18n import runtime as _rt
        card = _rt.text(f"widgets.{str(wid or '').split('::')[0]}.name", "", code=code)
        line = _rt.text("flash.widget_refused_card", "", code=code)
        if card and line:
            return line.replace("{card}", card)
    except Exception as e:  # noqa: BLE001 — the language table's line below
        _debug("generic", e)
    try:
        from i18n import langs as _lg
        return str(_lg.current_language().widget_refused)
    except Exception:  # noqa: BLE001
        return ""


#: Payload fields that carry a whole TEXT a correction may have to write (a recipe, a note's body).
_CONTENT_FIELDS = ("body", "content", "text")


def correction_budget(manifest: dict, action: str) -> int:
    """Tokens for `act_repair.call_for_refusal`. 300 fits a corrected title or index, not a document: in
    `docs-single-recipe-not-a-list__us` the refused `documento:show {query}` could only be corrected by writing
    the recipe, and a 300-token answer is a truncated call — invalid JSON the client skips — so the pass logged
    «no correction» and the operator got the refusal. An action whose payload declares a content field gets room
    to write it; every other correction keeps the small cap."""
    spec = ((manifest or {}).get("actions") or {}).get(action)
    pay = spec.get("payload") if isinstance(spec, dict) and isinstance(spec.get("payload"), dict) else {}
    return 1600 if any(k in pay for k in _CONTENT_FIELDS) else 300


def foreign(text: str) -> bool:
    from nucleo.flash import outgoing_lang as _ol
    return _ol.foreign_to_session(text)


async def said(wid: str, res: dict, *, generic_line: bool = True) -> str:
    """What the operator hears for this refusal, in the session's language — never the `error`. Empty only when
    `generic_line` is False (a caller with its own fallback wording)."""
    line = speakable(wid, res)
    if not (isinstance(res, dict) and (res.get("ok") is False or res.get("error"))):
        return line                                  # not a refusal: nothing to stand in for
    if line and foreign(line):
        try:
            from i18n import langs as _lg
            from nucleo.flash import outgoing_lang as _ol
            t = await _ol._translate(line, _lg.spec(_code()).name)
            line = t if t and not foreign(t) else ""
        except Exception:  # noqa: BLE001
            line = ""
    if not line:
        _note(wid, res)
        line = generic(wid) if generic_line else ""
    return line


def _debug(where: str, e: BaseException) -> None:
    from loguru import logger
    logger.debug(f"refusal_line {where}: {e}")


def _note(wid: str, res: dict) -> None:
    """The internal reason stays on the timeline: it is what tells US why the card refused."""
    try:
        from voice.observer import emit
        emit("brain", "🙊 widget refusal → generic line (internal reason not said)", role="system",
             text=str((res or {}).get("error") or (res or {}).get("message") or "")[:200],
             extra={"cat": "flash", "id": wid, "is_error": True})
    except Exception as e:  # noqa: BLE001
        _debug("note", e)

"""The card his words name as the TARGET of a shared control — never the one they name to exclude (V2-781).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES, 2026-10-11), the Dune trailer on `youtube` and calm music
on `musica`, both declaring `volume_down`:

  · «El de la música, el vídeo déjalo» — answering our own «¿Cuál exactamente?» — was asked the SAME question again:
    `direct_action.named_cards` saw two cards and `player_control` found no single named player.
  · «La música, la de fondo. El YouTube déjalo como está», «No, en YouTube no: bájale a la música, el vídeo no lo
    toques», «…no es YouTube, es la música de fondo…» → `youtube.volume_down`, three turns in a row. `named_cards`
    returns the catalogue's BEST match, and the brand name «YouTube» outscores «la música» — so the card named to
    be left alone became the target.

A sentence that names two cards is not ambiguous when one of them is named inside a clause that EXCLUDES it: a
keep clause («déjalo», «leave the music», `naming.split_kept`), a don't-touch («no lo toques»), or a bare negation
(«no en YouTube», «not the video», «que no es YouTube»). What is left names the target. One reader for every site
that asks «whose order is it» (`frontend.which_card`, `player_control`, `undecided`), so they cannot disagree.

It also keeps the control a turn PARKED when it asked which card: the answer that names one of the asked cards
runs that control on it, even when the model called nothing that turn (`park` / `parked_answer`).
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

#: A negation next to a card's name denies that card («no en YouTube», «not the video», «la música no», «no bajes la
#: música»): the card is never the target. Only the words AROUND the negation count — «¿no puedes bajar la música?»
#: names the music three words after its «no», and that is a request, not a denial.
_NEGATED_RE = re.compile(r"^(?:no|not|nope|never|isn'?t|wasn'?t|ain'?t|tampoco)$", re.I)
_BEFORE, _AFTER = 2, 3

#: How long a parked «which card?» waits for its answer.
_PARK_TTL_S = 180.0
_PARKED: dict = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def _named(text: str, open_ids) -> list[str]:
    try:
        from widgets import instances as _inst
        return _inst.named_in(text, open_ids)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"named_target: names unread — {e}")
        return []


def _clauses(text: str) -> list[str]:
    from widgets import naming as _naming
    return [p for p in _naming._CLAUSE_RE.split(str(text or "")) if p and not _naming._CLAUSE_RE.fullmatch(p)]


def _denied(clause: str, open_ids) -> set[str]:
    """The bases of the cards a negation in `clause` denies — those named within `_BEFORE`/`_AFTER` words of it."""
    tokens = re.findall(r"\w+", clause)
    out: set[str] = set()
    for i, tok in enumerate(tokens):
        if _NEGATED_RE.match(tok):
            window = " ".join(tokens[max(0, i - _BEFORE):i] + tokens[i + 1:i + 1 + _AFTER])
            out.update(_base(c) for c in _named(window, open_ids))
    return out


def split(text: str, open_ids) -> tuple[list[str], list[str]]:
    """`(targets, excluded)` — the open cards named as the target, and the ones named only to be left alone."""
    from widgets import naming as _naming
    rest, kept = _naming.split_kept(text)
    excluded = {_base(c) for c in _named(kept, open_ids)}
    positive: list[str] = []
    for clause in _clauses(rest):
        denied = _denied(clause, open_ids)
        if denied:
            excluded.update(denied)
        else:
            positive.append(clause)
    targets = [c for c in _named(" , ".join(positive), open_ids) if _base(c) not in excluded]
    return targets, sorted(excluded)


def target(text: str, open_ids, action: str = "") -> str:
    """The ONE open card his words make the target of `action` (any action when ""), else "".

    Named outright and not excluded; or the only card left among those that declare the action once the excluded
    ones are out («no en YouTube» with two players open is the music). "" when nothing or several are named."""
    if not str(text or "").strip():
        return ""
    ids = [str(i) for i in (open_ids or []) if str(i or "").strip()]
    if not ids:
        return ""
    try:
        targets, excluded = split(text, ids)
        if action:
            from nucleo.flash import frontend as _fe
            targets = [c for c in targets if action in (_fe.declared_actions(_base(c)) or {})]
        if len({_base(c) for c in targets}) == 1:
            return targets[0]
        if not targets and excluded and action:
            from nucleo.flash import frontend as _fe
            left = [c for c in ids if _base(c) not in excluded and action in (_fe.declared_actions(_base(c)) or {})]
            if len({_base(c) for c in left}) == 1:
                return left[0]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"named_target: skipped — {type(e).__name__}: {e}")
    return ""


def names_it(text: str, widget_id: str, open_ids) -> bool:
    """Whether his words make THIS card the target (never when they name it only to exclude it)."""
    t = target(text, open_ids)
    return bool(t) and _base(t) == _base(widget_id)


# ── the control a turn parked when it asked which card ──────────────────────────────────────────────────────────
def park(action: str, cards) -> None:
    """Remember the control the turn ASKED about: its action and the cards it offered."""
    ids = [str(c) for c in (cards or []) if str(c or "").strip()]
    if action and ids:
        _PARKED.update({"action": str(action), "cards": ids, "at": time.monotonic()})


def parked_answer(text: str) -> tuple[str, str]:
    """`(card, action)` when his words answer the parked question by naming one of its cards; `("", "")` otherwise.
    One shot: the park is cleared whatever he said next."""
    p = dict(_PARKED)
    _PARKED.clear()
    if not p or time.monotonic() - float(p.get("at") or 0) > _PARK_TTL_S:
        return "", ""
    card = target(text, p.get("cards") or [], str(p.get("action") or ""))
    return (card, str(p["action"])) if card else ("", "")


def parked() -> dict:
    return dict(_PARKED)

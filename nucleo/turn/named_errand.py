"""Which of his errands does a sentence NAME? (three-tasks-at-once, 2026-10-10 20:00)

Two doors needed the same answer and had none:

  · the status line (`errands_of_a_turn.status_owed`) answered «but the jump, did you actually make it higher?»
    with every live errand's phase — the report and the monitor, never the game he asked about, three times;
  · the list lane (`nucleo/batch`) took «del coche, ¿qué tal de autonomía real? ¿Y el juego? …» — four
    sentences about three errands already running — for a NEW list, and answered each of four such turns with
    the same canned receipt.

The yardstick is the attribution's own (`dispatch._ref_words` / `dispatch._same_thing`: singular/plural, glued
punctuation), over every errand he can be talking about: the LIVE ones and the ones PARKED on a question to him
(a parked errand left `_SESSIONS`, and his refinements while it waits are part of what it is). No word list: the
same tokenizer in every language, ranked by the length of the words matched.
"""
from __future__ import annotations

from loguru import logger


def known(*, with_finished: bool = False) -> list[dict]:
    """Every errand he can be asking about: {id, label, request, phase, waiting_on, parked}. Never raises.

    The one STARTING (asked, no session yet) is always in; the just-FINISHED ones only `with_finished` — a status
    line must not report a finished errand as under way (`errand_pool`)."""
    from nucleo import dispatch as _d
    out: list[dict] = []
    try:
        for e in _d.pending_summaries() or []:
            rec = _d.get_record(e.get("id"))
            label = str(getattr(rec, "label", "") or "").strip()
            out.append({"id": str(e.get("id") or ""), "label": "" if label.endswith("…") else label,
                        "title": str(getattr(rec, "title", "") or "").strip(),
                        "request": str(e.get("request") or "").strip(), "phase": str(e.get("phase") or ""),
                        "note": str(e.get("note") or ""), "waiting_on": e.get("waiting_on") or "", "parked": False,
                        "sheet": str(e.get("sheet") or ""), "surface": str(e.get("surface") or ""),
                        "secs": int(e.get("secs") or 0), "done": int(e.get("done") or 0), "total": int(e.get("total") or 0)})
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"named_errand: live errands unreadable — {type(e).__name__}: {e}")
    try:
        from nucleo.dispatch import confirm as _dc     # the gate's own store (`pending_confirm` reads this one)
        for tid, p in list((getattr(_dc, "_PENDING_CONFIRM", None) or {}).items()):
            refs = " ".join(str(r) for r in (p.get("refinements") or []))
            out.append({"id": str(tid), "label": "", "request": str(p.get("request") or "").strip(),
                        "extra": refs, "phase": "", "note": "", "waiting_on": "user", "parked": True,
                        "sheet": str(p.get("sheet") or ""), "surface": str((p.get("context") or {}).get("surface") or "")})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"named_errand: parked errands unreadable — {type(e).__name__}: {e}")
    from nucleo.turn import errand_pool as _pool
    out += _pool.starting(out)
    return out + (_pool.finished(out) if with_finished else [])


def _words(text: str) -> set[str]:
    from nucleo import dispatch as _d
    return _d._ref_words(_d._norm(text))


def named(text: str, errands: list[dict] | None = None) -> list[dict]:
    """Every errand `text` names, strongest first; [] when it names none. ALL of them, not the top one: «del coche,
    ¿qué tal de autonomía? ¿Y el juego? Del monitor no te olvides…» asks about three, and a top-1 would answer
    the monitor alone. A short word shared by chance can add an errand he did not mean — one line too many,
    which is the cheaper error than leaving out the one he asked about."""
    from nucleo import dispatch as _d
    from nucleo.turn.errands_of_a_turn import ask_of
    errands = known() if errands is None else errands
    said = _words(text)
    if not said or not errands:
        return []
    scored = []
    for e in errands:
        # his ASK, never our wrapper around it: «Find real marketplace listings» made «autonomía real» name the hunt
        hay = _words(f"{e.get('label', '')} {e.get('title', '')} {ask_of(e.get('request', ''))} {e.get('extra', '')}")
        scored.append((sum(len(w) for w in said if any(_d._same_thing(w, h) for h in hay)), e))
    scored.sort(key=lambda se: -se[0])
    return [e for s, e in scored if s]


def asks_about_all(text: str) -> bool:
    """«¿Cómo va todo?» / «how's everything going?» — the attribution's own «all» reading (`dispatch._ALL_RE`)."""
    from nucleo import dispatch as _d
    return bool(_d._ALL_RE.search(_d._norm(text)))


def strongest(text: str, errands: list[dict] | None = None) -> dict | None:
    """The errand `text` names MOST — the one the sentence is about when it names several. None when it names none."""
    hits = named(text, errands)
    return hits[0] if hits else None


def owns_card(errand: dict, card: str) -> bool:
    """Is `card` (a results or document sheet, base id or instance) this errand's own box?"""
    from nucleo import surfaces as _s
    card = str(card or "")
    family = card.split("::", 1)[0]
    sheet, surface = str(errand.get("sheet") or ""), str(errand.get("surface") or "")
    if family == "results":
        return (sheet == card) if "::" in card else (sheet.startswith("results") or _s.opens_sheet(surface))
    if family == "documento":
        return _s.opens_doc(surface) or sheet.startswith("documento")
    return True


def card_is_another_errands(card: str, text: str) -> bool:
    """Does his sentence belong to an errand that is NOT the one owning this results/document card?

    three-tasks-at-once (ES, 2026-10-11 02:04): «¿Y el informe ese va bien? Lo quiero corto…» was repaired into
    `results:criteria` because the monitor's sheet was the card on screen; «el informe» is the car REPORT, which had
    no card open. The words of his original asks decide, not what is visible. False for any other card, and when
    the sentence names no errand — then the screen is all there is to go by."""
    if str(card or "").split("::", 1)[0] not in ("results", "documento"):
        return False
    top = strongest(text)
    return bool(top) and not owns_card(top, card)


def spoken_name(errand: dict, limit: int = 72) -> str:
    """How an errand is NAMED to him: the name it was given (`errand_title`), its label, or his ask clipped on a word
    — never our listing wrapper and never a mid-word cut. three-tasks-at-once (ES, 2026-10-11 02:58): «Así va todo:
    Crear un widget nuevo para el canvas: un juego de plataformas tipo Sup: esperando…; Find real marketplace
    listings for: monitor de ordenador usado (condit: mirando «results»» was read to him as a status."""
    from nucleo import errand_title as _et
    from nucleo.turn.errands_of_a_turn import ask_of
    for name in (errand.get("title"), errand.get("label")):
        name = str(name or "").strip()
        if name and not name.endswith("…"):
            return _et.provisional(name, limit)
    return _et.provisional(ask_of(str(errand.get("request") or "")), limit)

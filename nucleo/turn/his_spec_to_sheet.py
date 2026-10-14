"""A spec he states about ONE errand reaches that errand's sheet, whatever the reply did with it.

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es). «Y el monitor, que sea de 27 al menos» was answered
«del monitor apunto lo de 27 pulgadas o más; ¿te vale hasta cuánto pagar?» — a question, so no promise backstop
fired, and the turn called nothing. The 27" floor never reached the monitor hunt: its sheet had no `asked`, no
criteria, and nine minutes later its finalists were an LG 24", a BenQ 24" and an Asus 23,8". He pointed it out twice
(«me sacas un LG de 24 y un Asus de 23,8… te pedí mínimo 27») and the rows stayed.

The sheet's door already rejects a row that contradicts his words (`search.category`, `results/category_gate`); it
only needs to HEAR them. So: each sentence of his that names exactly one errand with a results sheet, and states
something the door reads (a size, a minimum size, a price ceiling, 4K), joins that sheet's `asked` — re-said in the
readers' plain form, never as his raw sentence — and re-judges its rows through the same `sheets.recheck_rows` an
injected correction uses. A sentence naming several errands is cut per errand on its own punctuation
(`split_by_errand.parts`); a clause naming several is left alone: «el informe hasta 30.000 y el monitor hasta 150»
must not give the monitor a €30,000 ceiling.
"""
from __future__ import annotations

from loguru import logger

#: (sheet, sentence) already carried this process: the text channel can pass the same words twice in one turn.
_CARRIED: set[tuple[str, str]] = set()


def spec_of(sentence: str, *, exclusions: bool = False) -> str:
    """The sentence's specs, re-said in the readers' own plain form ("" when it states none).

    Never the sentence itself: «me sacas un LG de 24 y un Asus de 23,8… te pedí mínimo 27» names two rows he is
    REJECTING, and the subject reader takes a capitalised name for the thing every row must name — carried whole, it
    emptied the sheet, the Fujitsu he wanted included. Only the floor, the size, the ceiling and 4K travel. Not the
    exclusions unless `exclusions`: read against a sheet that holds none of his words they are noise («nada de CRT ni
    monitores viejos» excludes «monitores»). With his commissioning words on the sheet («busco un monitor…») the door
    keeps a word he asked for (`category._first_clause`), and what he rules out reaches it in HIS words — the model's
    relay of it («DESCARTAR todos los albergues…», hotel-under-15-days ES 2026-10-14) carries no negation the reader
    reads, so «no hostales ni albergues» never reached the door and «Hostel Ikigai» was offered next turn."""
    from search.category import asked_from
    ask = asked_from(sentence)
    parts = [f"at least {ask['size_min']} inches" if ask.get("size_min")
             else (f'{ask["size"]}"' if ask.get("size") else ""),
             f"under {ask['ceiling']:.0f}" if ask.get("ceiling") else "",
             "4K" if ask.get("uhd") else ""]
    parts += [f"no {w}" for w in (ask.get("excluded") or [])[:4]] if exclusions else []
    return " · ".join(p for p in parts if p)


def carry(operator_text: str) -> list[str]:
    """The sheets his words re-judged ([] when none). Never raises."""
    text = str(operator_text or "").replace("...", "…")
    if not text.strip():
        return []
    out: list[str] = []
    try:
        from nucleo import sheets
        from nucleo.turn import named_errand as _ne
        errands = _ne.known(with_finished=True)
        if not any(str(e.get("sheet") or "").startswith("results") for e in errands):
            return []
        from nucleo.turn import split_by_errand as _split
        for part in _split.parts(text, errands):   # over ALL errands, cut per errand: «…the game, and the monitor 27»
            sheet = str(part["errand"].get("sheet") or "")
            spec = (spec_of(part["words"], exclusions=bool(_asked_of(sheet)))   # exclusions need his words there
                    if sheet.startswith("results") else "")
            if not spec or (sheet, spec) in _CARRIED:
                continue
            _CARRIED.add((sheet, spec))
            sheets.recheck_rows(sheet, spec)
            out.append(sheet)
    except Exception as e:  # noqa: BLE001 — the turn goes on; the sheet keeps its rows
        logger.warning(f"his_spec_to_sheet: could not carry his words to the sheet — {type(e).__name__}: {e}")
    if out:
        _emit(out)
    return out


def _asked_of(sheet: str) -> str:
    from widgets.results import category_gate
    return category_gate.asked_of(sheet)


def forget() -> None:
    _CARRIED.clear()


def _emit(sheets_: list[str]) -> None:
    try:
        from voice.observer import emit
        emit("brain", "📋 his spec reached the errand's sheet", role="system", extra={"sheets": sheets_[:4]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"his_spec_to_sheet: emit failed — {e}")

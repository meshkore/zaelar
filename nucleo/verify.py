"""nucleo/verify.py — ONE verifier: did the end state the task promised actually happen? (V2-707 F2)

## What he asked for (2026-09-16)

> «Asegúrate también de que encajas el arnés… que debe manejar, me imagino, el Brainworker, también tiene
> que estar ahí. Es decir, tiene que saber identificar la tarea que ha propuesto el usuario y determinar
> cuál es la manera de medir el éxito. Y así, después de todo el proceso, podemos ver si hemos llegado a ese
> punto. Si no hemos llegado, entiendo que es capaz de iterar hasta que lo consiga. Y si hiciéramos ese
> bucle, probablemente muchas tareas no quedarían huérfanas o a medias.»

He is describing a mechanism the engine had three fragments of and no whole:

  · `nucleo/harness.py` (V2-660) verifies exactly ONE class, `widget_content`, for five minutes, in RAM;
  · `nucleo/errands/verify.py` (V2-683) verifies exactly ONE condition, `meeting_exists`, hand-written;
  · the Brain Worker verifies NOTHING — `session._finish` closes on `rec.ok`, which the worker sets itself,
    and `_METHOD_BLOCK` step 5 asks it in prose to «VERIFICA… ITERA», which is a rail on judgement.

So: one grammar, one checker, three callers. **The model writes the condition; the engine checks it against
the product's own truth.** Closed in OPERATORS (what can be asked), open in CONTENT (what is asked about) —
the same split as the Brain Worker doctrine's resources/reasoning, and the same one `widgets/rows.py` draws
one layer down. It is not a coincidence that they share it: both answer «which rows match», so this reuses
that selector rather than growing a second one that can disagree with it.

## The grammar

    {"all": [clause, …]}          every clause must hold   (also the bare form: a list, or one clause)
    {"any": [clause, …]}          at least one

    clause = {"widget": "agenda", "collection": "meetings",
              "where": {"title~": "Cryptonite", "date": "2026-09-17"},
              "expect": "present" | "absent",          # default: present
              "count": 3 | {"min": 1, "max": 5}}       # optional, exact or bounded

`where` is `widgets/rows.py`'s expression, unchanged: `field` equals, `field~` contains, `field>=` `<=` `>`
`<`, `field!` not-equal, a list value meaning «any of these», clauses AND'd, case and accents folded.

## The three answers, and why the third is not False

`True` met · `False` not met · **`None` = could not be read**, and None is never treated as failure. That is
the V2-660 rule, kept verbatim: a wrong «you did not deliver» over something that WAS delivered is worse
than staying quiet, and an unreadable widget must not turn a finished errand into a retry loop.
"""
from __future__ import annotations

from loguru import logger

#: Operators a clause may use. Anything else is a condition this engine cannot check, and a condition it
#: cannot check must READ as unverifiable (None), never as failure.
EXPECTS = ("present", "absent")


def _clauses(done_when) -> tuple[str, list]:
    """(mode, clauses) from any of the accepted shapes, or ("", []) when there is nothing to check."""
    if isinstance(done_when, dict):
        for mode in ("all", "any"):
            got = done_when.get(mode)
            if isinstance(got, list):
                return mode, [c for c in got if isinstance(c, dict)]
        if done_when.get("widget"):
            return "all", [done_when]
        return "", []
    if isinstance(done_when, list):
        return "all", [c for c in done_when if isinstance(c, dict)]
    return "", []


def _count_ok(n: int, want) -> bool:
    if isinstance(want, dict):
        lo, hi = want.get("min"), want.get("max")
        if lo is not None and n < int(lo):
            return False
        return not (hi is not None and n > int(hi))
    try:
        return n == int(want)
    except Exception:  # noqa: BLE001
        return False


def check_clause(clause: dict, now: float | None = None) -> bool | None:
    """One clause against the product's own truth. None when it cannot be read — never a guess."""
    try:
        wid = str(clause.get("widget") or "").strip().lower()
        if not wid:
            return None
        from widgets import rows
        coll = str(clause.get("collection") or "").strip()
        if not coll:
            declared = rows.declared(wid)
            if len(declared) != 1:
                # Two collections and no name is ambiguous, and guessing which one he meant is exactly the
                # class of error this file exists to stop.
                return None
            coll = next(iter(declared))
        if coll not in rows.declared(wid):
            return None
        matched = rows.select(wid, coll, clause.get("where") if isinstance(clause.get("where"), dict) else {})
        n = len(matched)
        if "count" in clause:
            return _count_ok(n, clause["count"])
        expect = str(clause.get("expect") or "present").strip().lower()
        if expect not in EXPECTS:
            return None
        return (n > 0) if expect == "present" else (n == 0)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"verify: cláusula ilegible ({e!r}) → None, que NO es un fallo")
        return None


def check(done_when, now: float | None = None) -> bool | None:
    """The whole condition. `None` — unreadable, or nothing to check — is never failure."""
    mode, clauses = _clauses(done_when)
    if not clauses:
        return None
    results = [check_clause(c, now) for c in clauses]
    if mode == "any":
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    # all: one False sinks it; otherwise an unreadable clause makes the whole thing unverifiable.
    if any(r is False for r in results):
        return False
    return None if any(r is None for r in results) else True


def missing(done_when, now: float | None = None) -> list[str]:
    """The clauses that are NOT met, said in a line each — what the worker is handed when it is relaunched,
    and what the operator is told when nobody could finish it. «Queda: la cita sigue en la agenda» is the
    difference between a retry that knows what to fix and one that starts again from zero."""
    mode, clauses = _clauses(done_when)
    out: list[str] = []
    for c in clauses:
        if check_clause(c, now) is not False:
            continue
        wid = str(c.get("widget") or "?")
        coll = str(c.get("collection") or "")
        where = c.get("where") if isinstance(c.get("where"), dict) else {}
        said = ", ".join(f"{k}={v}" for k, v in where.items()) or "cualquiera"
        expect = str(c.get("expect") or "present").lower()
        if "count" in c:
            from widgets import rows
            try:
                n = len(rows.select(wid, coll or next(iter(rows.declared(wid))), where))
            except Exception:  # noqa: BLE001
                n = -1
            out.append(f"«{wid}.{coll}» debía tener {c['count']} filas con {said} y tiene {n}")
        elif expect == "absent":
            out.append(f"«{wid}.{coll}» todavía tiene una fila con {said}")
        else:
            out.append(f"«{wid}.{coll}» no tiene ninguna fila con {said}")
    return out


def describe(done_when) -> str:
    """The condition in one readable line, for observability and for the record's own row."""
    mode, clauses = _clauses(done_when)
    if not clauses:
        return ""
    bits = []
    for c in clauses:
        where = c.get("where") if isinstance(c.get("where"), dict) else {}
        said = ", ".join(f"{k}={v}" for k, v in where.items())
        bits.append(f"{c.get('widget', '?')}.{c.get('collection', '')}"
                    f"[{said}]{'' if str(c.get('expect', 'present')).lower() == 'present' else ' AUSENTE'}")
    return (" Y ".join(bits) if mode == "all" else " O ".join(bits))[:200]

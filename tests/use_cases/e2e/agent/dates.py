"""Use-case dates: ALWAYS in the future, ALWAYS relative to today.

Operator rule (2026-08-19): *“dates must always be future dates from today —
that is a variable the tests must have; you cannot hardcode dates.”*

This is not a style preference; it is test correctness. When audited on the same day, the catalog asked for “flights
for the May long weekend” and “the birthday is on March 14” with the clock in AUGUST: those cases were
**impossible by construction**—no one can book a date that has already passed—and the dashboard counted them
as agent failures. An absolute date in a use case expires on its own and silently poisons the measurement.

How it is used: the case text contains a TOKEN (`{FIN_DE_SEMANA}`, `{EN_UNAS_SEMANAS}`…) and `resolve()`
replaces it when constructing the scenario, that is, on every run. Thus the same case asks for “this Saturday” in August and
“this Saturday” in December, without anyone having to remember to edit it.
"""
from __future__ import annotations

import datetime as _dt

_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre")
_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def today() -> _dt.date:
    return _dt.date.today()


def next_weekend(ref: _dt.date | None = None) -> tuple[_dt.date, _dt.date]:
    """The NEXT Saturday and Sunday. If today IS Saturday or Sunday, that same weekend remains valid
    (a “what should I do this weekend?” request made on a Saturday refers to Saturday), and if today is Sunday, today’s
    Sunday is used—never one in the past."""
    d = ref or today()
    if d.weekday() == 5:                      # Saturday
        sat = d
    elif d.weekday() == 6:                    # Sunday: Saturday has already passed; the weekend is today
        sat = d - _dt.timedelta(days=1)
    else:
        sat = d + _dt.timedelta(days=(5 - d.weekday()))
    return sat, sat + _dt.timedelta(days=1)


def days_ahead(n: int, ref: _dt.date | None = None) -> _dt.date:
    return (ref or today()) + _dt.timedelta(days=max(1, n))


def es(d: _dt.date, *, with_weekday: bool = True) -> str:
    wd = f"{_DIAS_ES[d.weekday()]} " if with_weekday else ""
    return f"{wd}{d.day} de {_MESES_ES[d.month - 1]}"


def en(d: _dt.date, *, with_weekday: bool = True) -> str:
    return d.strftime("%A %B %-d") if with_weekday else d.strftime("%B %-d")


def _tokens() -> dict[str, str]:
    sat, sun = next_weekend()
    in3w = days_ahead(21)
    return {
        # Spanish
        "{FIN_DE_SEMANA}": f"este fin de semana ({es(sat)} y {es(sun)})",
        "{SABADO}": es(sat),
        "{DOMINGO}": es(sun),
        "{EN_UNAS_SEMANAS}": f"alrededor del {es(in3w, with_weekday=False)}",
        "{DENTRO_DE_UN_MES}": f"alrededor del {es(days_ahead(30), with_weekday=False)}",
        "{FECHA_FUTURA_CERCANA}": es(days_ahead(10), with_weekday=False),
        # EN
        "{THIS_WEEKEND}": f"this weekend ({en(sat)} and {en(sun)})",
        "{SATURDAY}": en(sat),
        "{SUNDAY}": en(sun),
        "{IN_A_FEW_WEEKS}": f"around {en(in3w, with_weekday=False)}",
        "{IN_A_MONTH}": f"around {en(days_ahead(30), with_weekday=False)}",
        "{NEAR_FUTURE_DATE}": en(days_ahead(10), with_weekday=False),
    }


def resolve(text: str) -> str:
    """Replaces date tokens with actual future dates. Idempotent for text without tokens."""
    if not text or "{" not in text:
        return text
    for k, v in _tokens().items():
        text = text.replace(k, v)
    return text

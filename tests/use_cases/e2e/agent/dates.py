"""Fechas de los casos de uso: SIEMPRE futuras, SIEMPRE relativas a hoy.

Norma del operador (2026-08-19): *«las fechas siempre tienen que ser fechas a futuro desde el día de hoy —
esa es una variable que los tests tienen que tener, no puedes hardcodear las fechas»*.

No es una preferencia de estilo, es corrección del test. Auditado el mismo día, el catálogo pedía «vuelos
para el puente de mayo» y «el cumpleaños es el 14 de marzo» con el reloj en AGOSTO: esos casos eran
**imposibles por construcción** —nadie puede reservar para una fecha que ya pasó— y el tablero los contaba
como fallos del agente. Una fecha absoluta en un caso de uso caduca sola y envenena la medida en silencio.

Cómo se usa: el texto del caso lleva un TOKEN (`{FIN_DE_SEMANA}`, `{EN_UNAS_SEMANAS}`…) y `resolve()` lo
sustituye al construir el escenario, o sea en cada corrida. Así el mismo caso pide «este sábado» en agosto y
«este sábado» en diciembre, sin que nadie tenga que acordarse de editarlo.
"""
from __future__ import annotations

import datetime as _dt

_MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre")
_DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def today() -> _dt.date:
    return _dt.date.today()


def next_weekend(ref: _dt.date | None = None) -> tuple[_dt.date, _dt.date]:
    """El PRÓXIMO sábado y domingo. Si hoy ES sábado o domingo, ese mismo fin de semana sigue siendo válido
    («¿qué hago este fin de semana?» dicho un sábado va del sábado), y si hoy es domingo se toma el domingo de
    hoy — nunca uno pasado."""
    d = ref or today()
    if d.weekday() == 5:                      # sábado
        sat = d
    elif d.weekday() == 6:                    # domingo: el sábado ya pasó, el finde es hoy
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
        # ES
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
    """Sustituye los tokens de fecha por fechas reales futuras. Idempotente sobre texto sin tokens."""
    if not text or "{" not in text:
        return text
    for k, v in _tokens().items():
        text = text.replace(k, v)
    return text

"""Trinquete de FECHAS FUTURAS + contrato de los casos de descubrimiento.

Norma del operador (2026-08-19): las fechas de un caso de uso son SIEMPRE relativas a hoy. Este test existe
porque el defecto no se ve al leer: el catálogo pedía «vuelos para el puente de mayo» y «el cumpleaños es el 14
de marzo» con el reloj en AGOSTO — casos imposibles por construcción que el tablero contaba como fallos del
agente. Una fecha absoluta caduca sola y envenena la medida en silencio, así que la prohibición va en un test.
"""
from __future__ import annotations

import datetime as dt
import re

from tests.use_cases.e2e.agent import dates as DT, discovery as DISC, scenarios as SC

_MESES = ("enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|"
          "january|february|march|april|may|june|july|august|september|october|november|december")
# «14 de marzo», «September 20th», «puente de mayo»: un mes NOMBRADO en el texto FUENTE es el patrón prohibido.
_ABS = re.compile(rf"\b(?:\d{{1,2}}\s+de\s+(?:{_MESES})|(?:{_MESES})\s+\d{{1,2}}|puente de (?:{_MESES}))\b",
                  re.I)


def _sources() -> dict[str, str]:
    """El texto FUENTE, no el resuelto: tras `resolve()` toda fecha es un mes nombrado y legítimo."""
    import inspect

    from tests.use_cases import cases_data
    out = {}
    for mod in (SC, DISC, cases_data):
        out[mod.__name__] = inspect.getsource(mod)
    from tests.use_cases.e2e.agent import derived
    out["derived"] = inspect.getsource(derived)
    return out


def test_ningun_caso_lleva_una_fecha_absoluta_escrita_a_mano():
    bad = []
    for name, src in _sources().items():
        for line in src.splitlines():
            if line.lstrip().startswith("#") or "dates.py" in line:
                continue
            m = _ABS.search(line)
            if m:
                bad.append(f"{name}: …{m.group(0)}… → usa un token de dates.py")
    assert not bad, ("fechas absolutas en casos de uso (caducan solas y vuelven el caso imposible):\n  "
                     + "\n  ".join(bad))


def test_los_tokens_de_fecha_se_resuelven_en_todo_escenario():
    left = []
    for s in SC.all_scenarios():
        for field in (s.opening_line, s.persona_brief, s.success_checks, *(s.memory_seed or [])):
            for tok in re.findall(r"\{[A-Z_]+\}", field or ""):
                left.append(f"{s.id}: {tok}")
    assert not left, f"tokens sin resolver: {left}"


def test_toda_fecha_resuelta_cae_en_el_futuro():
    """El fin de semana propuesto nunca puede ser pasado — ni un sábado, corrido en domingo."""
    for ref, expect_sat in ((dt.date(2026, 8, 19), dt.date(2026, 8, 22)),   # miércoles
                            (dt.date(2026, 8, 22), dt.date(2026, 8, 22)),   # sábado: hoy vale
                            (dt.date(2026, 8, 23), dt.date(2026, 8, 22))):  # domingo: el finde es el de hoy
        sat, sun = DT.next_weekend(ref)
        assert sat == expect_sat and sun == sat + dt.timedelta(days=1), (ref, sat, sun)
        assert sun >= ref, f"el domingo propuesto ({sun}) es anterior a hoy ({ref})"
    assert DT.days_ahead(21) > DT.today()
    assert DT.days_ahead(0) > DT.today(), "days_ahead(0) tiene que empujar al futuro, no devolver hoy"


def test_los_casos_de_descubrimiento_traen_su_contrato_completo():
    """Cada caso de descubrimiento SIEMBRA memoria y declara con qué comprobar que aterrizó.

    Sin `seed_probe_query` la siembra no se puede verificar, y sin verificación el caso mediría el destilador
    de memoria mientras reporta un fallo del agente — el error que estos casos existen para no cometer.
    """
    assert DISC.SCENARIOS, "no hay casos de descubrimiento"
    for s in DISC.SCENARIOS:
        assert s.memory_seed, f"{s.id} no siembra memoria"
        assert s.seed_probe_query, f"{s.id} no dice cómo comprobar la siembra"
        # `worker`/`widget`, NO «Brain Workers»/«Widgets»: lo que se compara contra el informe de mecanismo
        # es el `cat` CRUDO del evento, no la etiqueta que lee el humano en el visor. Estos dos asserts
        # nombraban la etiqueta, así que CONFIRMABAN el bug en vez de cazarlo — test y código escritos a la
        # vez desde la misma creencia equivocada. El trinquete que sí lo caza (`test_segments.py`) lee las
        # familias de `voice.observer._CAT` en vez de repetir lo que yo creía.
        assert "worker" in s.expected_signals, f"{s.id} debería exigir un worker real"
        assert "widget" in s.expected_signals, f"{s.id} debería exigir el widget de resultados"
        low = s.success_checks.lower()
        assert "widget nuevo" in low or "new widget" in low, (
            f"{s.id}: el criterio no dice que crear un widget nuevo es un fallo (V2-115)")
    assert {s.locale for s in DISC.SCENARIOS} == {"es", "us"}, "la familia tiene que cubrir ES y EN"


def test_un_pass_no_puede_tapar_un_mecanismo_roto():
    """Overall alto + mecanismo 1-2 = FAIL, no PASS.

    Caso REAL que lo motivó (2026-08-19, `reorder-prescription__es`): conducta impecable —5 en naturalidad,
    adaptación y resultado— con **mecanismo 1**, y el juez escribiendo «desincronización crítica: reporta
    estado 'working' con cero actividad de fondo». El umbral agregado lo cerró como PASADO y tiró ese hallazgo.
    La regla fundacional del arnés es que el mecanismo manda sobre el texto; esto la aplica al marcador.
    """
    from tests.use_cases.e2e.agent import status as S

    base = {"run": {}, "verdict": {"veredicto": "ok"}}
    roto = {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 5, "resultado": 5, "mecanismo": 1}}}
    sano = {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 5, "resultado": 5, "mecanismo": 4}}}
    assert S._state(4, roto) == "FAIL", "un mecanismo roto no puede salir en verde"
    assert S._state(4, sano) == "PASS"
    assert S._state(5, {**base, "verdict": {"veredicto": "ok", "scores": {"mecanismo": 2}}}) == "FAIL"
    # Sin nota de mecanismo (casos puramente conversacionales) el umbral sigue mandando: la guarda no puede
    # convertir "no medido" en "roto".
    assert S._state(4, {**base, "verdict": {"veredicto": "ok", "scores": {"naturalidad": 4}}}) == "PASS"
    # Y un INFRA sigue siendo INFRA, nunca FAIL — eso ya era la regla y no debe romperse por este cambio.
    assert S._state(None, base) == "INFRA"

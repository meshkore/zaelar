"""Al worker se le dice el mismo HOY que usa el resto del razonamiento con fechas (V2-250).

`_today_block()` es el bloque que le DICE al worker qué día es, y su único trabajo es anclar «el último», «de
hoy», «el de tal día». Leía el reloj de PARED, mientras que todo lo que resuelve un momento en este motor pasa
por `scheduler.time.time()` — `parse_when`, `next_cron`, y por eso `router_guards` lo lee explícitamente y lo
llama «ONE clock».

Con los dos relojes de acuerdo (producción) no se nota nada. Al medir sí, y la forma gemela la midió memoria-dev
el mismo día en el dosier del worker (`75f2a34`): replay a 2026-03-10, una cita a seis días simulados por
delante, y la agenda devolvía **VACÍA** porque `date.today()` contestaba 2026-08-21 y toda fecha futura se leía
como pasada. El dosier planificaba a ciegas, que es el fallo por el que esa función existe.

Aquí es peor en un sentido: no filtra datos, **le dice al modelo la fecha equivocada**, y a partir de ahí todo lo
que razone con «hoy» sale mal sin que nada falle.
"""
import time

import pytest

from nucleo import dispatch_prompts as dp
from nucleo import scheduler

FIJADO = time.mktime((2026, 3, 10, 9, 30, 0, 0, 0, -1))


class _Reloj:
    @staticmethod
    def time():
        return FIJADO


@pytest.fixture
def reloj_fijado(monkeypatch):
    monkeypatch.setattr(scheduler, "time", _Reloj, raising=False)


def test_el_bloque_de_HOY_sigue_al_reloj_del_motor(reloj_fijado):
    out = dp._today_block()
    assert "2026-03-10" in out, "le decíamos al worker la fecha de PARED mientras el resto razonaba con otra"
    assert "09:30" in out


def test_y_llega_asi_al_prompt_que_recibe(reloj_fijado):
    """GUARDA DE CABLEADO (V2-199): el bloque puede estar perfecto y no ir en el prompt del worker."""
    p = dp._build_prompt("busca el último informe", "", True)
    assert "2026-03-10" in p


def test_sin_reloj_fijado_es_el_de_PARED():
    """La otra dirección, que es el caso normal: en producción los dos relojes son el mismo y esto no cambia nada.
    Sin este caso, «seguir al reloj del motor» podría satisfacerse devolviendo cualquier fecha fija."""
    hoy = time.strftime("%Y-%m-%d")
    assert hoy in dp._today_block()


def test_si_el_reloj_del_motor_NO_esta_no_se_cae(monkeypatch):
    """Fail-soft: esto se construye en el camino de cada escalada. Una excepción aquí deja al worker sin prompt."""
    class _Roto:
        @staticmethod
        def time():
            raise RuntimeError("sin reloj")

    monkeypatch.setattr(scheduler, "time", _Roto, raising=False)
    assert "FECHA/HORA REAL DE HOY" in dp._today_block()


def test_es_UN_solo_reloj_y_no_dos_copias():
    """GUARDA DE FUENTE: la avería nace de tener dos fuentes de «ahora». Si alguien vuelve a poner un
    `strftime()` sin argumento aquí, se abre otra vez sin fallar con ruido."""
    import inspect
    src = inspect.getsource(dp._today_block)
    assert "_sched.time.time()" in src
    assert "_t.strftime('%A %d %b %Y')" not in src, "un strftime sin `_ahora` vuelve al reloj de pared"

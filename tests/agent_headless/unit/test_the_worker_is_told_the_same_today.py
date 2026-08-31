"""The worker is told the same TODAY used by the rest of the date reasoning (V2-250).

`_today_block()` is the block that TELLS the worker what day it is, and its only job is to anchor «the latest», «of
today», «the one from such-and-such a day». It read the WALL clock, while everything that resolves a moment in this
engine goes through `scheduler.time.time()` — `parse_when`, `next_cron`, and that is why `router_guards` reads it
explicitly and calls it «ONE clock».

When the two clocks agree (production), nothing is noticeable. It is when measuring that it matters, and memoria-dev
measured the twin form on the same day in the worker dossier (`75f2a34`): replay to 2026-03-10, an appointment six
simulated days ahead, and the agenda returned **EMPTY** because `date.today()` answered 2026-08-21 and every future
date was read as past. The dossier planned blindly, which is the failure this function exists to prevent.

Here it is worse in one sense: it does not filter data, **it tells the model the wrong date**, and from that point on
everything it reasons about with «today» comes out wrong without anything failing.
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
    """WIRING GUARD (V2-199): the block can be perfect and still not make it into the worker prompt."""
    p = dp._build_prompt("busca el último informe", "", True)
    assert "2026-03-10" in p


def test_sin_reloj_fijado_es_el_de_PARED():
    """The other direction, which is the normal case: in production the two clocks are the same and this changes nothing.
    Without this case, «follow the engine clock» could be satisfied by returning any fixed date."""
    hoy = time.strftime("%Y-%m-%d")
    assert hoy in dp._today_block()


def test_si_el_reloj_del_motor_NO_esta_no_se_cae(monkeypatch):
    """Fail-soft: this is built on the path of every escalation. An exception here leaves the worker without a prompt."""
    class _Roto:
        @staticmethod
        def time():
            raise RuntimeError("sin reloj")

    monkeypatch.setattr(scheduler, "time", _Roto, raising=False)
    assert "FECHA/HORA REAL DE HOY" in dp._today_block()


def test_es_UN_solo_reloj_y_no_dos_copias():
    """SOURCE GUARD: the failure originates from having two sources of «now». If someone puts an argument-less
    `strftime()` back here, it opens up again without failing noisily."""
    import inspect
    src = inspect.getsource(dp._today_block)
    assert "_sched.time.time()" in src
    assert "_t.strftime('%A %d %b %Y')" not in src, "un strftime sin `_ahora` vuelve al reloj de pared"

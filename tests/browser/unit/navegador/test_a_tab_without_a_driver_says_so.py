"""A browser tab whose worker DIED must not be reported as «YA EN CURSO» (V2-310).

Measured on 2026-08-25 04:36: the Brain Worker plan hit its session limit («You've hit your session limit ·
resets 6:10am»), the worker died on the spot — and its tab stayed `working` in the registry, so the state
block said «NAVEGADOR — YA EN CURSO» over an errand nobody was driving. zaelar told the TRUTH («se cortó por
el límite de sesión») against a block asserting the opposite; the judge filed it as hallucination and the
round scored 2/1/1/2/1. A prompt that contradicts itself makes being right impossible (V2-222).

The fact is read from BOTH registries: the tab carries an ERRAND STAMP (`sheet`, which only
`dispatch._prepare_web` sets) and no live session drives it (`record_by_nav_task`, which also finds an
automatic resume — while somebody is going to pick it up, it is not orphaned).
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.pop("v310", None)
    yield
    T._tasks.clear()
    D._SESSIONS.pop("v310", None)


class _Rec:
    status = "running"
    kind = "web"
    nav_task = ""


def _errand_tab(*, driver: bool) -> str:
    tid = T.create("Busca una guitarra acústica de segunda mano", sheet="v310-1")
    T.set_status(tid, "working")
    if driver:
        rec = _Rec()
        rec.nav_task = tid
        D._SESSIONS["v310"] = rec
    return tid


def _state() -> str:
    return "\n".join(LB.navegador_lines())


def test_an_errand_tab_with_no_live_session_is_reported_as_driverless():
    _errand_tab(driver=False)
    state = _state()
    assert "SU WORKER MURIÓ" in state
    assert "SE QUEDÓ SIN CONDUCTOR" in state
    assert "ofrécele RELANZARLA" in state, "sin conductor, relanzar es lo único que puede traer el resultado"


def test_a_tab_with_its_worker_alive_says_nothing_of_the_sort():
    _errand_tab(driver=True)
    state = _state()
    assert "SIN CONDUCTOR" not in state and "worker murió" not in state


def test_a_hand_driven_tab_without_an_errand_stamp_is_never_orphaned():
    """An operator driving manually (`browse_web`) or a login opens a tab WITHOUT an errand stamp: there is no
    worker there that can die, and shouting «sin conductor» would be inventing a failure."""
    tid = T.create("Abrir Booking")           # without a sheet
    T.set_status(tid, "working")
    assert "SIN CONDUCTOR" not in _state()


def test_delivering_still_wins_but_the_fact_travels_with_it():
    """When rows are waiting, the correct response is still to deliver them — and the fact is stated anyway,
    because saying «no está bloqueada ni esperando» about a tab without a driver is the contradiction again."""
    tid = _errand_tab(driver=False)
    SHEET.apply_action("present", {"sheet": "v310-1", "title": "R",
                                   "items": [{"title": "Fender CD-60", "price": "120 €"}]})
    state = _state()
    assert "YA HA ENCONTRADO" in state, "entregar gana a anunciar la muerte"
    assert "su worker murió" in state, "…pero el hecho compone, no desaparece"
    assert tid


def test_unreadable_registries_mean_NO_orphan():
    """Fail-open with direction: saying that an errand died when it is still alive is worse than keeping quiet."""
    assert LB._driver_is_gone("no-existe", {}) is False

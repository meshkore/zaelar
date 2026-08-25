"""V2-314 — when EVERY worker tier is in cooldown, no session is spawned: launching is a guaranteed death.

Measured in `find-concert-tickets__es` (2026-08-25 10:53-10:56). The license tier answered «You've hit your
session limit · resets 2:20pm», we recorded the cooldown, and then spawned into it TWICE more inside three
minutes — 1.8 s, 3.9 s and 1.9 s of worker life, four minutes of the round, and a person told three times that
a search was starting. Eleven of the twenty-eight empty-sheet rounds have that shape.

The reason the cooldown could not bite is the whole point of this test: `providers.pick()` returns `None` for
two different worlds — an EMPTY chain (self-host with no keys, where `env_for_worker() == {}` means «use the
local license», the fail-open this module promises) and a chain whose every tier is ASLEEP (where `{}` means
«use the local license» too, except the license is one of the sleeping tiers). One value, two meanings, and the
caller picked the wrong one every time.
"""
import time

import pytest

from nucleo.workers import providers


@pytest.fixture
def chain_of(monkeypatch):
    """Build a chain and a cooldown store from scratch — a unit test never touches the live KV."""
    def _make(tiers: list[str], asleep: dict[str, float] | None = None):
        monkeypatch.setattr(providers, "chain", lambda: [{"name": n, "base_url": "", "env": []} for n in tiers])
        sleeping = dict(asleep or {})

        class _Store:
            def until(self, name):
                return sleeping.get(name, 0.0)

            def available(self, name):
                return sleeping.get(name, 0.0) <= time.time()

        monkeypatch.setattr(providers, "_store", _Store())
    return _make


def test_una_cadena_VACIA_no_es_una_cadena_dormida(chain_of):
    """La sensibilidad que importa: sin escalones configurados NO se bloquea nada — es el self-host de siempre."""
    chain_of([])
    assert providers.exhausted_until() == 0.0
    assert providers.exhausted_reason() == ""


def test_con_UN_escalon_sano_se_lanza(chain_of):
    chain_of(["licencia-claude"])
    assert providers.exhausted_until() == 0.0


def test_un_escalon_sano_basta_aunque_los_demas_duerman(chain_of):
    chain_of(["z.ai", "licencia-claude"], asleep={"z.ai": time.time() + 3600})
    assert providers.exhausted_until() == 0.0, "un escalón dormido no puede parar a la cadena entera"


def test_TODOS_dormidos_devuelve_la_hora_del_PRIMERO_que_vuelve(chain_of):
    pronto, tarde = time.time() + 600, time.time() + 7200
    chain_of(["z.ai", "licencia-claude"], asleep={"z.ai": tarde, "licencia-claude": pronto})
    assert providers.exhausted_until() == pytest.approx(pronto)


def test_el_motivo_LLEVA_LA_HORA(chain_of):
    """«sin cuota» invita a reintentar en diez segundos; «vuelve a las 14:20» no. La hora es lo accionable."""
    vuelve = time.time() + 900
    chain_of(["licencia-claude"], asleep={"licencia-claude": vuelve})
    texto = providers.exhausted_reason()
    assert texto
    assert time.strftime("%H:%M", time.localtime(vuelve)) in texto


def test_el_caso_MEDIDO_la_licencia_sola_dormida_para_el_lanzamiento(chain_of):
    """La cadena del plató tiene UN escalón. Con él dormido, `pick()` decía None y `env_for_worker()` {} —
    o sea «usa la licencia», que es justo la que acababa de decir que no."""
    chain_of(["licencia-claude"], asleep={"licencia-claude": time.time() + 3600})
    assert providers.pick() is None                 # el None ambiguo de siempre…
    assert providers.env_for_worker() == {}         # …y su lectura, que mandaba lanzar
    assert providers.exhausted_until() > 0          # el hecho que lo desambigua


def test_el_dispatcher_LO_CONSULTA():
    """La mitad de cableado: el predicado puede acertar y no llegar a la puerta (V2-199)."""
    import inspect

    from nucleo import dispatch
    src = "\n".join(ln for ln in inspect.getsource(dispatch._run_session).splitlines()
                    if not ln.strip().startswith("#"))
    assert "exhausted_reason()" in src, "el dispatcher dejó de preguntar si la cadena está dormida"
    i_ask = src.find("exhausted_reason()")
    i_pool = src.find("async with _pool()")
    assert 0 <= i_ask < i_pool, "se pregunta DESPUÉS de coger el pool: la espera de 30 s se paga igual"


def test_y_lo_cuenta_como_NO_ARRANCADA_no_como_rota():
    """`provider_asleep` y no un `end` pelado: la ronda no falló, no llegó a empezar. El Master y el arnés
    necesitan distinguir «lo intentamos y se rompió» de «sabíamos que era inútil», o una cuota agotada se sigue
    puntuando como producto roto."""
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch._run_session)
    assert '"provider_asleep"' in src

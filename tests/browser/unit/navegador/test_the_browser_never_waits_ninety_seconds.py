"""The browser is a DIRECT connection: what works, works in seconds (2026-08-24).

Operator rule, with the trace in front of us: *“browsers must not have any kind of waiting… everything is
immediate, and if something fails, it fails within the next few seconds… under no circumstances should it have
ninety-second timeouts.”*

What existed, measured against the live set on a real site: `navigate` 4.2 s · `look` 4.2 s · `extract`
0.05 s — and a **90 s** cap, twenty times the cost. That is not ample headroom: it means a hang consumes
one third of the round before anyone notices.

And the hang did exist, with its exact cause. `page.evaluate` **has no timeout in Playwright**: it waits for an
execution context, and a NAVIGATING page—the Enter key after typing in a search box—does not have one
until the new document is ready. Reproduced in `search-buy-guitar__es`:

    18:03:45  type «guitarra acustica»      ← se escribe
    18:03:48  screenshot                     ← la captura SALE, o sea que la acción funcionó
    18:05:15  ERROR: no ha contestado en 90s ← 90 s de una ronda de 250

The costly part is not the wait: it is what the wait TURNS INTO. The action had worked and the worker received a
FAILURE, so it repeated it. Now a slow read returns whatever it has, SAYING that the view is only partially
loaded, and the action continues to count as what it was.
"""
import inspect

from nucleo.cli import nav as nav_cli
from widgets.navegador import owner


def test_ninguna_espera_llega_a_noventa_segundos():
    """The number forbidden by the rule, in the three places that could impose it."""
    assert nav_cli._ACT_TIMEOUT_S < 90, "el tope del puente era 90 s y es el que se lleva la ronda"
    assert owner._DOM_TIMEOUT_S < 90
    assert owner._NAV_TIMEOUT / 1000.0 < 90


def test_los_topes_son_de_SEGUNDOS_no_de_minutos():
    """Measured: a real action costs ~4 s. A cap is set against the real cost, not against fear."""
    assert nav_cli._ACT_TIMEOUT_S <= 30
    assert owner._DOM_TIMEOUT_S <= 15
    assert owner._NAV_TIMEOUT / 1000.0 <= 20


def test_el_tope_del_PUENTE_es_mayor_que_el_de_dentro():
    """If the bridge cut off before the reads, the worker would see “did not respond” for actions that were
about to respond—the same failure with a different number."""
    assert nav_cli._ACT_TIMEOUT_S > owner._DOM_TIMEOUT_S
    assert nav_cli._ACT_TIMEOUT_S > owner._NAV_TIMEOUT / 1000.0


def test_el_consentimiento_es_por_DOMINIO_no_por_URL():
    """A `type --submit` in a search box CHANGES the URL, and with the URL guard the following read used to
    sweep everything again. Measured in the 19:39 run on `search-buy-guitar__es`: `type` worked—at
    19:39:07 the screenshot was already from `/search?keywords=guitarra+acustica`—and the bridge still
    reported a timeout at 25 s, three times in a row. A CMP is domain-specific: once accepted on wallapop.com,
    it does not reappear while moving within that domain.

        type --submit   25 s (timeout) → 3,84 s
        navigate                       → 4,85 s
        snapshot                       → 0,38 s
    """
    src = "\n".join(l for l in inspect.getsource(owner.TaskBrowser.snapshot_for_agent).splitlines()
                    if not l.strip().startswith("#"))
    assert "_host_of" in src, "por URL vuelve a barrer en cada página del mismo sitio"
    assert "_overlays_host" in src
    assert owner._host_of("https://es.wallapop.com/search?keywords=x") == "es.wallapop.com"
    assert owner._host_of("https://es.wallapop.com/") == owner._host_of("https://es.wallapop.com/app/search?k=1")


def test_OTRO_dominio_si_vuelve_a_barrer():
    """Sensitivity in the opposite direction: remembering the domain cannot turn into never sweeping—the
    worker constantly changes sites and each one brings its own banner."""
    assert owner._host_of("https://www.milanuncios.com/x") != owner._host_of("https://es.wallapop.com/x")

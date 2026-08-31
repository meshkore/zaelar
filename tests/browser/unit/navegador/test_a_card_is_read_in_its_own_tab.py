"""Read a listing without losing the results list (2026-08-24).

Operator request: *“the brain worker itself has to handle extracting data, modeling the
different listings, opening enough tabs to investigate, and evaluating each of the result
listings”*. It could not: the bridge only knew `navigate`, which takes over the ONLY tab — so looking at an
item meant losing the results list and searching for it again, **two navigations per listing**, with the search box and
filters in between. At 7–11 s each, evaluating three listings consumed the entire conversation.

Measured with the new verb against the live site (es.wallapop.com):

    navigate to the results list   8.24 s
    extract                        0.02 s → 6 listings
    visit listing #1               0.85 s   ← and the results list remains where it was
    visit (repeated)               0.59 s
    extract                        0.01 s → the SAME 6

What it returns is what is needed to EVALUATE —title, listing text, declared lists— and not a
screenshot: evaluating ten listings by vision means ten PNG reads, and this has to be possible many
times.
"""
import inspect

from nucleo import nav_cli
from widgets.navegador import act_api, owner


def _code(fn):
    return "\n".join(l for l in inspect.getsource(fn).splitlines() if not l.strip().startswith("#"))


def test_la_ficha_se_lee_en_OTRA_pestana():
    src = _code(owner.TaskBrowser.visit)
    assert "ctx.new_page()" in src, "sin pestaña propia esto es un `navigate` con otro nombre"


def test_NUNCA_se_toca_la_pestana_del_listado():
    """This is the verb's reason for existing: if it touched `self.page`, the results list would still be lost."""
    src = _code(owner.TaskBrowser.visit)
    assert "self.page =" not in src and "self._goto" not in src


def test_la_pestana_se_cierra_SIEMPRE():
    """One orphaned tab per listing is how you end up with the thirty already measured by `_reap_popups`. Closing
    happens in `finally`, so it also occurs when the read blows up."""
    src = _code(owner.TaskBrowser.visit)
    i = src.find("finally:")
    assert i > 0, "sin `finally` una ficha que falla deja su pestaña abierta"
    assert "tab.close()" in src[i:]


def test_prefiere_el_CONTENIDO_al_MENU():
    """Measured in the first test: `body.innerText` started with “All categories Cars Motorcycles Motor and
    accessories…”. With the text truncated, that leaves the worker evaluating a listing by the site's menu —
    the same way V2-234 measured during extraction, through the other entrance.

    The rule is STRUCTURAL, not a list of sites: if the page declares its main content, read that;
    otherwise, the entire body, which is what existed."""
    src = _code(owner.TaskBrowser.visit)
    assert "main, article, [role=main]" in src
    assert "document.body" in src, "sin contenido declarado hay que caer al cuerpo, no devolver vacío"


def test_las_lecturas_estan_ACOTADAS():
    """Same reason as the inspection: `evaluate` has no timeout in Playwright, and a slow listing cannot
    consume the round."""
    src = _code(owner.TaskBrowser.visit)
    assert src.count("asyncio.wait_for") >= 3
    assert "_DOM_TIMEOUT_S" in src


def test_un_fallo_de_la_ficha_NO_lanza():
    """The worker will visit many: a failed listing must return a readable `ok:false` and continue, not
    bring down the action."""
    src = _code(owner.TaskBrowser.visit)
    assert '"ok": False' in src and "error" in src


def test_el_WORKER_puede_llamarlo():
    """A capability that the bridge does not expose does not exist for the worker (the same lesson as node 4.20)."""
    src = inspect.getsource(nav_cli.main)
    assert 'sub.add_parser("visit"' in src
    assert '_act("visit"' in src
    assert "NO pierdes el listado" in src, "el worker tiene que saber PARA QUÉ sirve, o seguirá usando navigate"


def test_el_puente_HTTP_lo_enruta():
    src = inspect.getsource(act_api)
    assert 'if action == "visit":' in src


def test_el_PROMPT_del_worker_lo_nombra_y_dice_para_que_sirve():
    """A verb that the prompt does not explain goes unused — the lesson of V2-219, where the worker was dying
    while learning its own CLI by trial and error. And the closed inventory of subcommands must include it, or the
    prompt itself tells it that it does not exist."""
    import inspect
    from nucleo import dispatch_prompts as dp
    src = inspect.getsource(dp)
    assert "nav_cli visit" in src
    assert "sin perder el listado" in src, "hay que decirle PARA QUÉ, no solo que existe"
    i = src.find("ESOS son TODOS los subcomandos")
    assert i > 0 and "visit" in src[i:i + 400], (
        "el inventario cerrado le diría que `visit` no existe y no lo usaría nunca")

"""V2-227 ámbito A — DÓNDE va a mirar el operador, decidido al ENCARGAR y no al entregar.

Operator, 2026-08-20: «si el worker tarda, el usuario se aburre y la experiencia es mala. Necesita ver EN TIEMPO
REAL lo que está pasando». Un worker puede tardar siete minutos y hoy la superficie donde caerá la respuesta solo
se elige cuando la respuesta YA existe — que es exactamente demasiado tarde para abrirla antes y verter progreso
dentro. Sin este campo, la pestaña de proceso es una pestaña vacía.

Tres reglas, y cada una está por su fallo contrario:
  1. se decide al ENCARGAR (si no, no hay nada que abrir mientras se trabaja);
  2. vocabulario CERRADO de cinco valores (una cadena libre deriva en una taxonomía que nadie mantiene y el
     frontend acaba adivinando);
  3. se decide UNA vez (cambiar de superficie a mitad mueve lo que el operador YA está mirando).

Y por la doctrina de los Brain Workers esto es un RECURSO: no puede saber de hoteles, ni de coches, ni de casas.
Nada de este módulo conoce un dominio y nada puede aprenderlo.
"""
import json

import pytest

from nucleo import surfaces
from nucleo.flash import router


# ── el vocabulario, que es lo que impide que esto derive ─────────────────────────────────────────────────────
def test_there_are_exactly_five_and_no_more():
    assert surfaces.SURFACES == ("lista", "item", "widget", "voz", "silenciosa")


@pytest.mark.parametrize("said,expected", [
    ("lista", "lista"), ("LISTA", "lista"), ("listado", "lista"), ("results", "lista"),
    ("item", "item"), ("ficha", "item"), ("detalle", "item"),
    ("widget", "widget"), ("app", "widget"),
    ("voz", "voz"), ("voice", "voz"),
    ("silenciosa", "silenciosa"), ("none", "silenciosa"),
])
def test_the_wording_maps_onto_the_same_five(said, expected):
    assert surfaces.normalize(said) == expected


def test_something_outside_the_vocabulary_is_NOT_invented_as_a_sixth():
    """Devuelve "" y no el valor por defecto: el llamante tiene que poder distinguir «no dijo nada» de «dijo algo
    que no entendemos», porque solo lo segundo merece un aviso."""
    assert surfaces.normalize("pantalla completa en 3D") == ""
    assert surfaces.normalize(None) == ""


# ── la resolución, que es el respaldo para las puertas donde nadie declaró nada ───────────────────────────────
def test_what_the_brain_declared_wins():
    assert surfaces.resolve("item", kind="web") == "item"


@pytest.mark.parametrize("kind,expected", [
    ("web", "lista"),          # navegar acaba en algo que se mira
    ("research", "lista"),
    ("code", "widget"),        # el generador de widgets: su desenlace ES un widget
    ("generic", "voz"),
    ("", "voz"),
])
def test_and_if_nobody_said_anything_it_comes_from_the_KIND(kind, expected):
    """Auto-resume, confirm-gate, peers de cluster y el Susurro entran por la misma puerta sin declarar nada.
    Un encargo sin superficie no puede quedarse sin pantalla."""
    assert surfaces.resolve(None, kind=kind) == expected


def test_an_UNKNOWN_word_falls_back_instead_of_breaking():
    assert surfaces.resolve("pantalla completa en 3D", kind="web") == "lista"


# ── la regla 3, que es la que protege al operador que ya está mirando ─────────────────────────────────────────
class _Rec:
    def __init__(self, kind="generic", surface=""):
        self.kind, self.surface = kind, surface


def test_it_is_stamped_the_first_time():
    r = _Rec(kind="web")
    assert surfaces.set_once(r, "item") == "item" and r.surface == "item"


def test_and_NEVER_re_decided():
    """Cambiar de superficie a mitad no es una corrección: mueve lo que el operador ya tiene delante. Si un paso
    posterior no está de acuerdo, lo que hay que arreglar es la decisión del encargo."""
    r = _Rec(kind="web", surface="lista")
    assert surfaces.set_once(r, "widget") == "lista" and r.surface == "lista"


def test_stamping_without_a_declaration_still_leaves_one():
    r = _Rec(kind="code")
    assert surfaces.set_once(r, None) == "widget"


def test_the_sheet_opens_only_for_the_two_that_show_things():
    assert [s for s in surfaces.SURFACES if surfaces.opens_sheet(s)] == ["lista", "item"]


# ── el cableado: declararlo y no llevarlo es no haberlo declarado ─────────────────────────────────────────────
def _escalate_tool():
    return next(t for t in router.TOOLS if t["function"]["name"] == "escalate_to_slowbrain")


def test_the_tool_ASKS_for_it_and_offers_only_the_five():
    fn = _escalate_tool()["function"]
    par = fn["parameters"]["properties"]["surface"]
    assert par["enum"] == list(surfaces.SURFACES)
    assert "surface" in fn["parameters"]["required"], (
        "opcional = el modelo la omite y todo cae al respaldo por kind, que es adivinar la pantalla")


def test_the_tool_did_not_GROW_to_fit_it():
    """Se pagó por SUSTITUCIÓN: la frase en prosa sobre dónde se enseñan los hallazgos pasó a ser este campo. El
    catálogo se paga en CADA turno de voz, y esta tool ya iba a 1979 de 2000."""
    assert len(json.dumps(_escalate_tool(), ensure_ascii=False)) <= 2_000


def test_the_router_carries_it():
    d = router.decide("escalate_to_slowbrain", {"request": "busca hoteles", "surface": "lista"})
    assert d.payload["surface"] == "lista"


def test_the_router_does_not_normalize_it_here():
    """A propósito: `resolve()` necesita el `kind`, que este punto no conoce. Normalizar dos veces borra la
    diferencia entre «no dijo nada» y «dijo algo raro», que es la que decide si hay que avisar."""
    assert router.decide("escalate_to_slowbrain", {"request": "x", "surface": "inventada"}).payload["surface"] == "inventada"


def test_a_turn_with_THREE_errands_keeps_three_surfaces():
    """Un turno puede encargar una lista, una ficha y un widget (V2-118). Quedarse con la primera superficie le
    daría a las otras dos la pantalla equivocada desde el segundo cero — por eso viaja por petición y no en una
    variable suelta. Asserted on the source: el alternativo es una llamada a un modelo real."""
    import inspect

    from nucleo.flash import probe
    src = inspect.getsource(probe)
    assert '_surf[_r] = str(_tc["args"].get("surface")' in src
    assert '"surface": _surf.get(_r, "")' in src


def test_BOTH_channels_carry_it():
    """`probe` y el provider de voz son implementaciones PARALELAS del turno: cablear una sola es el fallo que
    esta base de código ha cometido tantas veces que tiene nombre propio en varios docstrings."""
    import inspect

    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as vp
    for mod in (probe, vp):
        assert '"surface"' in inspect.getsource(mod), mod.__name__


def test_the_dispatcher_stamps_it_at_the_ONLY_door_they_all_pass_through():
    import inspect

    from nucleo import dispatch
    src = inspect.getsource(dispatch.run_listener)
    assert 'surfaces.set_once(rec, ctx.get("surface"))' in src


def test_and_the_live_projection_publishes_it():
    """El frontend abre la hoja ANTES de que haya un resultado, así que la superficie tiene que viajar en la
    proyección VIVA (`/api/tasks`), no en la entrega."""
    import inspect

    from nucleo import dispatch
    assert '"surface": r.surface,' in inspect.getsource(dispatch.active_sessions)


def test_the_module_knows_NOTHING_about_any_domain():
    """La doctrina, hecha test: esto es un RECURSO. Si algún día aparece aquí «hotel», «coche» o «casa», alguien
    convirtió una pantalla general en un atajo para un caso de uso."""
    import inspect
    # Solo el CÓDIGO: el docstring del módulo cita a propósito los ejemplos del operador (hoteles, Wallapop,
    # casas en Los Ángeles) para decir que NINGUNO de ellos puede aparecer debajo.
    body = inspect.getsource(surfaces).split('"""', 2)[-1].lower()
    for domain in ("hotel", "restaurante", "coche", "casa", "vuelo", "wallapop", "booking", "sevilla"):
        assert domain not in body, f"«{domain}» en el código de surfaces.py: una pantalla general convertida en atajo"

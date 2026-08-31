"""V2-227 scope A — WHERE the operator will look, decided when COMMISSIONED and not when delivered.

Operator, 2026-08-20: «if the worker takes a long time, the user gets bored and the experience is bad. They need to see IN REAL
TIME what is happening». A worker can take seven minutes, and today the surface where the response will land is only
chosen when the response ALREADY exists — which is exactly too late to open it beforehand and pour progress into it.
Without this field, the process tab is an empty tab.

Three rules, each one enforced because of its opposite failure:
  1. it is decided when COMMISSIONED (otherwise there is nothing to open while work is in progress);
  2. CLOSED vocabulary of five values (a free-form string leads to a taxonomy nobody maintains, and the
     frontend ends up guessing);
  3. it is decided ONCE (changing surfaces halfway through moves what the operator is ALREADY looking at).

And under the Brain Workers doctrine this is a RESOURCE: it cannot know about hotels, cars, or houses.
Nothing in this module knows a domain, and nothing can learn one.
"""
import json

import pytest

from nucleo import surfaces
from nucleo.flash import router


# ── the vocabulary, which is what prevents this from drifting ─────────────────────────────────────────────────
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
    """Returns "" rather than the default value: the caller must be able to distinguish «said nothing» from «said something
    we do not understand», because only the latter warrants a warning."""
    assert surfaces.normalize("pantalla completa en 3D") == ""
    assert surfaces.normalize(None) == ""


# ── resolution, which is the fallback for entry points where nobody declared anything ─────────────────────────
def test_what_the_brain_declared_wins():
    assert surfaces.resolve("item", kind="web") == "item"


@pytest.mark.parametrize("kind,expected", [
    ("web", "lista"),          # browsing ends up in something you look at
    ("research", "lista"),
    ("code", "widget"),        # the widget generator: its outcome IS a widget
    ("generic", "voz"),
    ("", "voz"),
])
def test_and_if_nobody_said_anything_it_comes_from_the_KIND(kind, expected):
    """Auto-resume, confirm-gate, cluster peers, and the Whisper enter through the same door without declaring anything.
    A commission without a surface cannot be left without a screen."""
    assert surfaces.resolve(None, kind=kind) == expected


def test_an_UNKNOWN_word_falls_back_instead_of_breaking():
    assert surfaces.resolve("pantalla completa en 3D", kind="web") == "lista"


# ── rule 3, which protects the operator who is already looking ───────────────────────────────────────────────
class _Rec:
    def __init__(self, kind="generic", surface=""):
        self.kind, self.surface = kind, surface


def test_it_is_stamped_the_first_time():
    r = _Rec(kind="web")
    assert surfaces.set_once(r, "item") == "item" and r.surface == "item"


def test_and_NEVER_re_decided():
    """Changing surfaces halfway through is not a correction: it moves what the operator already has in front of them. If a later step
    disagrees, the commission decision is what needs fixing."""
    r = _Rec(kind="web", surface="lista")
    assert surfaces.set_once(r, "widget") == "lista" and r.surface == "lista"


def test_stamping_without_a_declaration_still_leaves_one():
    r = _Rec(kind="code")
    assert surfaces.set_once(r, None) == "widget"


def test_the_sheet_opens_only_for_the_two_that_show_things():
    assert [s for s in surfaces.SURFACES if surfaces.opens_sheet(s)] == ["lista", "item"]


# ── the wiring: declaring it and not carrying it means it was not declared ─────────────────────────────────
def _escalate_tool():
    return next(t for t in router.TOOLS if t["function"]["name"] == "escalate_to_slowbrain")


def test_the_tool_ASKS_for_it_and_offers_only_the_five():
    fn = _escalate_tool()["function"]
    par = fn["parameters"]["properties"]["surface"]
    assert par["enum"] == list(surfaces.SURFACES)
    assert "surface" in fn["parameters"]["required"], (
        "optional = the model omits it and everything falls back by kind, which means guessing the screen")


def test_the_tool_did_not_GROW_to_fit_it():
    """It was paid for by SUBSTITUTION: the prose phrase about where findings are shown became this field. The
    catalog is paid for on EVERY voice turn, and this tool was already at 1979 out of 2000."""
    assert len(json.dumps(_escalate_tool(), ensure_ascii=False)) <= 2_000


def test_the_router_carries_it():
    d = router.decide("escalate_to_slowbrain", {"request": "busca hoteles", "surface": "lista"})
    assert d.payload["surface"] == "lista"


def test_the_router_does_not_normalize_it_here():
    """Deliberately: `resolve()` needs the `kind`, which this point does not know. Normalizing twice erases the
    difference between «said nothing» and «said something strange», which determines whether a warning is needed."""
    assert router.decide("escalate_to_slowbrain", {"request": "x", "surface": "inventada"}).payload["surface"] == "inventada"


def test_a_turn_with_THREE_errands_keeps_three_surfaces():
    """A turn can commission a list, a detail view, and a widget (V2-118). Keeping the first surface would
    give the other two the wrong screen from the very first second — that is why it travels per request and not in a
    loose variable. Asserted on the source: the alternative is a call to a real model."""
    import inspect

    from nucleo.flash import probe
    src = inspect.getsource(probe)
    assert '_surf[_r] = str(_tc["args"].get("surface")' in src
    assert '"surface": _surf.get(_r, "")' in src


def test_BOTH_channels_carry_it():
    """`probe` and the voice provider are PARALLEL implementations of the turn: wiring only one is the failure this
    codebase has committed so many times that it has its own name in several docstrings."""
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
    """The frontend opens the sheet BEFORE there is a result, so the surface has to travel in the
    LIVE projection (`/api/tasks`), not in the delivery."""
    import inspect

    from nucleo import dispatch
    assert '"surface": r.surface,' in inspect.getsource(dispatch.active_sessions)


def test_the_module_knows_NOTHING_about_any_domain():
    """The doctrine, turned into a test: this is a RESOURCE. If «hotel», «car», or «house» ever appears here, someone
    turned a general screen into a shortcut for a use case."""
    import inspect
    # CODE only: the module docstring deliberately cites the operator's examples (hotels, Wallapop,
    # houses in Los Angeles) to say that NONE of them may appear below.
    body = inspect.getsource(surfaces).split('"""', 2)[-1].lower()
    for domain in ("hotel", "restaurante", "coche", "casa", "vuelo", "wallapop", "booking", "sevilla"):
        assert domain not in body, f"«{domain}» en el código de surfaces.py: una pantalla general convertida en atajo"

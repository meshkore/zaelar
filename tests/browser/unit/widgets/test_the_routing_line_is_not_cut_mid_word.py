"""V2-547 — the line that routes a turn to a widget must carry the clause that routes it.

Measured live on the operator's own engine (2026-09-01 23:25:19):

    «Enséñame mis restaurantes favoritos.»
    → escalada a un Brain Worker (claude_code)
    → «Sigo con ello; te aviso en cuanto lo tenga.»

`contactos` names that phrase in its own manifest — «o por sus favoritos ("mi restaurante favorito en
Barcelona", "los fontaneros que tenemos en Soria")» — and has `show_view`, a declared view action that answers
it instantly. The model never saw either: the catalog cut `whenToUse` at 80 characters, MID-WORD, and the
clause starts at character 100.

All eleven widgets were truncated, and several lost precisely the sentence that tells them apart:

    clock       «…un reloj. NO para el‹CUT› tiempo meteorológico (eso es 'tiempo/clima' → widget de search)»
    search      «…FRONTERA con `result‹CUT›s`: esto es el CARTEL DE PROGRESO mientras se busca…»
    mensajeria  «…qué debe responder‹CUT›, su WhatsApp/Telegram/correo…»

That last one is the same widget V2-545 spent a whole initiative on: «ábreme el Telegram» reaching a model
whose catalog never mentions Telegram.

This text is written BY US, FOR routing. Cutting it mid-word cuts the only thing the block is for — and a
fragment left inside a word does not merely lose meaning, it invents one («result‹CUT›» for `results`).
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def catalog_lines():
    import sys
    sys.path.insert(0, str(ENGINE))
    from widgets import brief
    return [l for l in brief.for_prompt().splitlines() if l.startswith("- ") and "· datos:" in l]


def _purpose_of(line):
    return line.split("  · datos:")[0].split(" — ", 1)[-1].split("  ◀")[0].split("  ·")[0].strip()


def test_the_operators_own_phrase_reaches_the_model(catalog_lines):
    """THE failure, as one assertion. «restaurantes favoritos» is in `contactos`'s manifest; the only question
    is whether the catalog still carries it by the time a model reads it."""
    line = next((l for l in catalog_lines if l.startswith("- contactos")), None)
    assert line, "contactos is not in the catalog at all"
    assert "favorito" in line, \
        "the clause that routes «enséñame mis restaurantes favoritos» is being cut off before the model sees it"


def test_no_routing_line_ends_INSIDE_a_word(catalog_lines):
    """A cut inside a word does not lose meaning, it fabricates one: `search`'s «FRONTERA con `result‹CUT›»
    reads as a different widget's name. Every line ends on a sentence or a word."""
    bad = []
    for line in catalog_lines:
        p = _purpose_of(line)
        if not p:
            continue
        # A truncated line is marked with «…»; anything else must be the manifest's own complete sentence.
        if p.endswith("…"):
            assert p[-2] == " " or not p[-2].isalnum(), f"cut inside a word: …{p[-40:]!r}"
        else:
            assert p[-1] in ".!?)»\"'", f"line ends mid-sentence with no ellipsis: …{p[-40:]!r}"
        if len(p) < 40:
            bad.append(p)
    assert not bad, f"routing lines too short to route with: {bad}"


def test_the_disambiguating_clauses_survive(catalog_lines):
    """The clauses are NEGATIVE routing rules — «NO para X», «FRONTERA con Y» — which is the kind a small model
    most needs and the kind a blind cut removes first, because they come after the positive description."""
    joined = "\n".join(catalog_lines)
    for wid, needle, why in [
        ("clock", "meteorol", "«NO para el tiempo meteorológico» is what stops clock stealing a weather turn"),
        ("mensajeria", "Telegram", "the connector names are how «ábreme el Telegram» finds its widget (V2-545)"),
        ("imagenes", "foto de algo", "the examples are what make «enséñame la foto de X» land here"),
    ]:
        line = next((l for l in catalog_lines if l.startswith(f"- {wid}")), None)
        if line is None:
            continue                                  # the selector did not pick it this run; nothing to assert
        assert needle in line, f"{wid}: {why}"
    assert joined


def test_it_is_still_BOUNDED_because_a_catalog_has_to_stay_cheap(catalog_lines):
    """Un-truncating is not un-bounding. The number of widgets listed is already bounded by
    `selection.candidates`; this bounds the prose per widget, so one verbose manifest cannot flood a prompt
    that is paid for on EVERY turn (V2-526)."""
    import sys
    sys.path.insert(0, str(ENGINE))
    from widgets import brief
    assert brief._purpose("x" * 4000) != "x" * 4000, "an unbounded purpose can flood every turn's prompt"
    assert len(brief._purpose("x" * 4000)) <= brief._PURPOSE_CAP + 1
    for line in catalog_lines:
        assert len(_purpose_of(line)) <= brief._PURPOSE_CAP + 1, line[:120]


def test_a_short_purpose_is_left_exactly_as_written(catalog_lines):
    import sys
    sys.path.insert(0, str(ENGINE))
    from widgets import brief
    short = "Cuando el usuario pide su agenda."
    assert brief._purpose(short) == short, "a description that fits must not be touched at all"


def test_every_widget_manifest_still_declares_a_whenToUse():
    """The catalog can only route on what the manifests write. A widget with none would be invisible to it."""
    missing = []
    for mf in sorted((ENGINE / "widgets").glob("*/manifest.json")):
        m = json.loads(mf.read_text(encoding="utf-8"))
        if not str(m.get("whenToUse") or "").strip():
            missing.append(mf.parent.name)
    assert not missing, f"widgets with no routing description: {missing}"

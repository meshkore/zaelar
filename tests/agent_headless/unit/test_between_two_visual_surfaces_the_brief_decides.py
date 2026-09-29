"""Demo passes 36-51 (2026-09-29): the escalation's surface when the model's declaration and the brief's reading differ.
Between two VISUAL surfaces the brief was right 6 of 7 times — «plan a five day trip… show me when it's ready»
declared `informe` (a document sheet and the browser card on screen) against `lista`; «a one page summary… in a
document» declared `item` (an empty results sheet) against `informe`. A non-visual declaration (a setup list done
silently, a message sent) was right, and is left as it was."""
from pathlib import Path

from nucleo import surfaces as s


def test_between_two_visual_surfaces_the_brief_decides():
    assert s.pick("informe", "lista") == "lista"
    assert s.pick("item", "informe") == "informe"


def test_a_non_visual_declaration_stands():
    assert s.pick("silenciosa", "lista") == "silenciosa"
    assert s.pick("voz", "silenciosa") == "voz"


def test_agreement_and_absence():
    assert s.pick("lista", "lista") == "lista"
    assert s.pick("", "lista") == "lista"
    assert s.pick("informe", "") == "informe"


def test_both_channels_pick():
    root = Path(__file__).resolve().parents[3]
    assert "_surfaces_mod.pick(escalate_req[\"surface\"].get(req, \"\")" in (root / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert ".pick(_surf.get(_r, \"\")" in (root / "nucleo/flash/probe.py").read_text("utf-8")

"""A card opens at a readable footprint (V2-773, operator's rule 2026-09-27).

«Los widgets tienen que abrirse a tamaños correctos… el de mensajes se abre alargado, muy alargado.» Measured on
his 16" desk: the messaging card, which declared no size, froze at its first rendered footprint — 1700×380.
The first render is judged against the desk before it is frozen; the messaging card declares its size too."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_card_opens_at_a_readable_footprint.mjs")
DESKTOP = Path("frontend/app/widgets/desktop.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_a_strip_becomes_a_card_and_a_clock_stays_a_clock():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_freeze_judges_the_first_render_before_keeping_it():
    src = DESKTOP.read_text(encoding="utf-8")
    assert 'saneFootprint' in src and 'from "./footprint.js' in src
    body = src[src.index("_freezeSize(card, id){"):src.index("_wireResize(card, id){")]
    assert "saneFootprint({" in body and "sane.w" in body and "sane.h" in body, "the measured size is judged, not copied"
    assert "if(!haveW)" in body and "if(!haveH)" in body, "the operator's own dimensions stay his"


def test_the_messaging_card_declares_a_size_a_message_can_be_read_in():
    d = json.loads(Path("widgets/mensajeria/manifest.json").read_text(encoding="utf-8"))
    s = d.get("size") or {}
    assert 600 <= int(s.get("w", 0)) <= 900 and 520 <= int(s.get("h", 0)) <= 760, s

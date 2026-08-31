"""V2-289 — the worker was told to look at a screenshot that its model cannot read.

Measured in `search-buy-guitar__es` (2026-08-24 11:23), with the fallback activated because the quota was exhausted
(«z.ai → fallback to deepseek»). The bus events, verbatim:

    task 💬 worker | La captura no se pudo leer (formato no soportado). Sigo por DOM
    task 💬 worker | La visión no carga la PNG (formato no soportado), así que trabajo con el snapshot DOM

Twice in the same run. **The PNG was perfect** —`PNG image data, 1280 x 800, 8-bit/color RGB` on
disk— so it was not a broken screenshot: DeepSeek V4 is the one that cannot read images. And we asked it to do so in TWO places
at once: step 1 of the prompt method («vision is your PRIMARY path») and the response to EVERY bridge action
(«LOOK AT IT with Read …»). Cost per action: a 300-530 KB `Read` to rediscover the same thing, plus the
failure narration to the operator, who has no use for it.

It is the V2-284 family seen from the other side: there, the turn was told to count something it did not support; here it is
told to look at something the model cannot see. An impossible instruction is not disobeyed — it collides with it.

⚠️ **And the direction of the fail-open is half the fix.** Absent = it DOES see, which is the usual behavior. An
incorrect «cannot see» leaves a worker that could see BLIND, and a blind worker is the hardest failure in this module to
attribute (`workers/workdir.py` says so about `read_dirs`); an incorrect «can see» costs a failed `Read`
and continues through the DOM, which is exactly what was already happening. That is why it is declared only where it has been MEASURED.
"""
import os

import pytest

from nucleo import nav_cli
from nucleo.dispatch_prompts import _web_prompt
from nucleo.workers import providers


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ZAELAR_NAV_VISION", raising=False)
    yield


# ── the rung DECLARES the capability ───────────────────────────────────────────────────────────────────────
def test_the_measured_rung_declares_it_cannot_see():
    """The DeepSeek rung is the one measured colliding with it; the verdict lives with it, not in a separate list."""
    ds = next(t for t in providers.KNOWN if t["name"] == "deepseek")
    assert ds.get("vision") is False


def test_a_rung_that_says_nothing_keeps_the_vision_path():
    """A new rung does NOT inherit a verdict that nobody has verified — and silence falls on the safe side."""
    assert providers.vision_env({"name": "nuevo"}) == {}
    assert providers.vision_env(None) == {}
    assert providers.vision_env({"vision": True}) == {}


def test_only_an_explicit_no_turns_it_off():
    assert providers.vision_env({"vision": False}) == {"ZAELAR_NAV_VISION": "0"}


# ── the BRIDGE stops offering the screenshot ──────────────────────────────────────────────────────────────────
_RES = {"ok": True, "url": "https://es.wallapop.com", "title": "Wallapop", "shot": "/tmp/shot-t1.png",
        "viewport": {"width": 1280, "height": 800}, "elements": "[2] caja de búsqueda\n[29] Precio"}


def test_the_bridge_offers_the_capture_when_the_model_can_see(capsys):
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "MÍRALA con Read" in out and _RES["shot"] in out


def test_the_bridge_does_not_send_a_blind_model_to_read_a_png(capsys, monkeypatch):
    monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "MÍRALA con Read" not in out
    assert _RES["shot"] not in out, "la ruta del PNG sigue delante: la va a abrir igual"
    assert "click_at" in out, "no basta con callar la captura: hay que decir que esos comandos tampoco valen"


def test_the_blind_bridge_still_says_there_is_no_view(capsys, monkeypatch):
    """Silencing it would read as though the screenshot FAILED, which is a different thing and has its own warning (V2-205)."""
    monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
    nav_cli._print_state(_RES)
    out = capsys.readouterr().out
    assert "VISTA:" in out and "no lee imágenes" in out
    assert "no llegó a escribirse" not in out


def test_the_elements_survive_either_way(capsys, monkeypatch):
    """The text path is what REMAINS when there is no vision: losing it here would leave the worker with neither."""
    for blind in (False, True):
        if blind:
            monkeypatch.setenv("ZAELAR_NAV_VISION", "0")
        nav_cli._print_state(_RES)
        assert "[29] Precio" in capsys.readouterr().out


# ── and the PROMPT stops ordering it ───────────────────────────────────────────────────────────────────────
def test_the_method_stops_calling_vision_the_main_path():
    con = _web_prompt("busca una guitarra", "")
    sin = _web_prompt("busca una guitarra", "", vision=False)
    assert "abre el PNG con Read" in con
    assert "abre el PNG con Read" not in sin
    assert "NO LEE IMÁGENES" in sin


def _paso_uno(prompt: str) -> str:
    """The line for STEP 1, not the entire prompt. Asserting on the complete prompt passed GREEN with the order
    deleted: `click <ref>`/`type <ref>` also appear in the command list above, so the
    check was satisfied by another block. The teardown caught it, not the reading."""
    return next(l for l in prompt.splitlines() if l.startswith("1) MIRA"))


def test_the_blind_method_names_the_path_that_is_left():
    """Removing the impossible instruction without adding the possible one leaves the worker without step 1."""
    paso = _paso_uno(_web_prompt("busca una guitarra", "", vision=False))
    assert "click <ref>" in paso and "type <ref>" in paso, paso


def test_the_rest_of_the_method_is_untouched():
    """Splitting one block into two is how a rule gets lost along the way (the lesson of V2-185)."""
    con = _web_prompt("busca una guitarra", "")
    sin = _web_prompt("busca una guitarra", "", vision=False)
    for paso in ("2) DESBLOQUEA", "3) RECONOCE", "MÉTODO — como lo haría"):
        assert paso in con and paso in sin, paso


def test_vision_is_the_default():
    """Without saying anything, the prompt is the usual one — a change that accidentally turns off vision is SILENT."""
    assert _web_prompt("x", "") == _web_prompt("x", "", vision=True)

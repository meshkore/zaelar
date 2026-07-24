"""Tests de widgets/background.py — ejecución en background con ciclo (V2-034)."""
import asyncio
import types

from widgets import background as bg, generator


def test_parse_period_units_and_min():
    assert bg.parse_period("1s") == 1
    assert bg.parse_period("30s") == 30
    assert bg.parse_period("5m") == 300
    assert bg.parse_period("1h") == 3600
    assert bg.parse_period("1d") == 86400
    assert bg.parse_period("90") == 90
    assert bg.parse_period(60) == 60
    assert bg.parse_period({"every": "2m"}) == 120
    assert bg.parse_period("0") == 1              # mínimo 1s
    assert bg.parse_period(True) is None          # bool no es un periodo
    assert bg.parse_period("bad") is None
    assert bg.parse_period(None) is None


def test_background_period_reads_manifest():
    assert bg.background_period({"background": "1m"}) == 60
    assert bg.background_period({"background": {"every": "1h"}}) == 3600
    assert bg.background_period({}) is None       # sin background → foreground-only


# ── validación del generador ────────────────────────────────────────────────────────────────────────────
_TICK_SRC = "def view_data(q=''):\n    return {}\ndef tick():\n    return None\n"
_NOTICK_SRC = "def view_data(q=''):\n    return {}\n"


def test_generator_passive_background_requires_tick():
    err = generator._validate_background({"kind": "passive", "background": "1m"}, _NOTICK_SRC)
    assert err and "tick()" in err
    assert generator._validate_background({"kind": "passive", "background": "1m"}, _TICK_SRC) is None


def test_generator_backed_background_needs_no_tick():
    # un backed se auto-agenda por su owner → no exige tick() en data.py
    assert generator._validate_background({"kind": "backed", "background": "1m"}, _NOTICK_SRC) is None


def test_generator_rejects_bad_period():
    err = generator._validate_background({"kind": "passive", "background": "nunca"}, _TICK_SRC)
    assert err and "background" in err.lower()


def test_generator_no_background_is_fine():
    assert generator._validate_background({"kind": "passive"}, _NOTICK_SRC) is None


# ── el planificador llama a tick() en su ciclo (integración; sin pytest-asyncio) ──────────────────────────
def test_scheduler_ticks_a_passive_widget(monkeypatch):
    calls = {"n": 0}
    fake = types.ModuleType("widgets.faketick.data")
    fake.tick = lambda: calls.__setitem__("n", calls["n"] + 1)

    import importlib
    real_import = importlib.import_module
    monkeypatch.setattr(bg.runtime, "catalog", lambda: [{"id": "faketick", "background": "1s"}])
    monkeypatch.setattr(bg.importlib, "import_module",
                        lambda n, *a, **k: fake if n == "widgets.faketick.data" else real_import(n, *a, **k))

    async def _drive():
        bg.start()
        assert "faketick" in bg.scheduled()
        await asyncio.sleep(1.4)                  # arranca tras min(period,2)=1s, luego ≥1 tick
        n = calls["n"]
        await bg.stop()
        return n

    n = asyncio.run(_drive())
    assert n >= 1
    assert bg.scheduled() == []


def test_scheduler_skips_widget_without_tick(monkeypatch):
    fake = types.ModuleType("widgets.notick.data")      # sin tick()
    import importlib
    real_import = importlib.import_module
    monkeypatch.setattr(bg.runtime, "catalog", lambda: [{"id": "notick", "background": "1s"}])
    monkeypatch.setattr(bg.importlib, "import_module",
                        lambda n, *a, **k: fake if n == "widgets.notick.data" else real_import(n, *a, **k))

    async def _drive():
        bg.start()
        sched = bg.scheduled()
        await bg.stop()
        return sched

    assert "notick" not in asyncio.run(_drive())        # sin tick() → no se agenda (aviso, no rompe)

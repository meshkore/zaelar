"""Under remote control the pulse keeps beating, in the remote-control blue (operator, 2026-09-28).

«Una vez te pones a controlar el sistema… el botón en azul… yo pondría también la línea del pulso en azul y
enseñarme el pulso, para que se vea cuando está en reposo, cuando está trabajando». The ECG only beat when the
agent was `live`, so a tab whose voice another session holds (`remote`) showed a flat line in the accent colour.
Verified rendered (2026-09-28): a second page in `remote` → 2,030 lit pixels, all blue, QRS visible.
"""
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[4] / "frontend/app/lib/ecg.js").read_text("utf-8")


def test_remote_is_a_beating_state():
    assert 'const beating = () => store.agentLive() || remote();' in SRC
    assert "if (!beating()) return;" in SRC, "a pulse event beats in remote too"


def test_remote_draws_in_the_remote_blue():
    assert 'remote() ? css("--hb-remote"' in SRC

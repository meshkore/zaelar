"""V2-464 — the round leaves a VIDEO: what the user would have seen, linked from the report.

Operator request (2026-08-28): record the screen while the case runs in the background — chat open
to read the conversation, widgets aligned like the system window snap — and save the silent .webm
alongside the session and its flows, as showcase material.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import recorder as R, report as REP


# ── the viewer protocol ─────────────────────────────────────────────────────────────────────────────────
def test_parar_sin_haber_arrancado_es_seguro():
    """The runner calls stop in the finally block of a crashed round; without this, cleaning up the rare
    failure would create a new failure."""
    assert R.Recorder("http://127.0.0.1:1").stop("x") == ""


def test_un_arranque_imposible_se_dice_y_no_revienta():
    """Fail-soft by contract: the video mirrors the round; it is not a prerequisite — a recording that does not start
    must never bring down a measurement that has already been paid for."""
    r = R.Recorder("http://127.0.0.1:1")           # nobody is listening there
    assert r.start(timeout_s=10) is False
    assert r.error, "sin el motivo, el operador no sabe por qué no hay vídeo"


def test_el_video_va_a_la_carpeta_de_la_campaña():
    assert str(R.VIDEO_DIR).endswith("tests/runs/use_cases/videos")


def test_la_parada_es_por_stdin_y_no_por_señal():
    """The .webm is materialized only when the Playwright context is CLOSED: killing the viewer with signals loses
    the entire file — the most expensive failure mode, because the round has already run. The protocol is a command via
    stdin (and EOF counts as a command, so no orphan is left behind if the runner dies)."""
    src = R._WATCHER_SRC
    assert "sys.stdin.readline()" in src and "ctx.close()" in src
    assert "record_video_dir" in src


# ── the report ───────────────────────────────────────────────────────────────────────────────────────────
def _fila(**extra) -> dict:
    return {"scenario": "x", "tier": 2, "channel": "probe",
            "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": []},
            "verdict": {"scores": {}, "overall": 5, "findings": [], "improvements": [],
                        "veredicto": "ok"}, **extra}


def _md(fila, tmp_path) -> str:
    out = REP.build([fila], "x", tmp_path)
    return out.read_text(encoding="utf-8")


def test_el_informe_enlaza_el_video_de_su_ronda(tmp_path):
    assert "🎥 vídeo: /ruta/x.webm" in _md(_fila(video="/ruta/x.webm"), tmp_path)


def test_sin_video_no_hay_linea_fantasma(tmp_path):
    assert "🎥" not in _md(_fila(), tmp_path)

"""V2-464 — la ronda deja un VÍDEO: lo que habría visto el usuario, enlazado desde el informe.

Petición del operador (2026-08-28): grabar la pantalla mientras el caso corre en background — chat abierto
para leer la conversación, widgets alineados como el snap de ventanas del sistema — y guardar el .webm sin
sonido junto a la sesión y sus flujos, como material de showcase.
"""
from __future__ import annotations

import pathlib

from tests.use_cases.e2e.agent import recorder as R, report as REP

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── el protocolo del espectador ─────────────────────────────────────────────────────────────────────────
def test_parar_sin_haber_arrancado_es_seguro():
    """El runner llama a stop en el finally de una ronda reventada; sin esto, la limpieza del fallo raro
    fabricaría un fallo nuevo."""
    assert R.Recorder("http://127.0.0.1:1").stop("x") == ""


def test_un_arranque_imposible_se_dice_y_no_revienta():
    """Fail-soft por contrato: el vídeo es espejo de la ronda, no condición — una grabación que no arranca
    nunca puede tirar una medición que ya se pagó."""
    r = R.Recorder("http://127.0.0.1:1")           # nadie escucha ahí
    assert r.start(timeout_s=10) is False
    assert r.error, "sin el motivo, el operador no sabe por qué no hay vídeo"


def test_el_video_va_a_la_carpeta_de_la_campaña():
    assert str(R.VIDEO_DIR).endswith("tests/runs/use_cases/videos")


def test_la_parada_es_por_stdin_y_no_por_señal():
    """El .webm solo se materializa al CERRAR el contexto de Playwright: matar al espectador a señales pierde
    el fichero entero — el modo de fallo más caro, porque la ronda ya corrió. El protocolo es una orden por
    stdin (y el EOF cuenta como orden, para no dejar huérfanos si el runner muere)."""
    src = R._WATCHER_SRC
    assert "sys.stdin.readline()" in src and "ctx.close()" in src
    assert "record_video_dir" in src


# ── el informe ──────────────────────────────────────────────────────────────────────────────────────────
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


# ── el modo escaparate, las TRES mitades del frontend ───────────────────────────────────────────────────
def test_el_frontend_lleva_el_modo_escaparate_completo():
    """Tres ficheros y un endpoint; cablear una parte sola no falla con ruido — falla grabando un vídeo con
    las tarjetas amontonadas y el chat cerrado, que parece un defecto del producto."""
    desk = (ENGINE / "frontend" / "app" / "widgets" / "desktop.js").read_text(encoding="utf-8")
    assert "arrange(){" in desk, "la rejilla vive en el canvas, que es su autoridad (V2-035)"
    sse = (ENGINE / "frontend" / "app" / "services" / "sse.js").read_text(encoding="utf-8")
    assert 'd.label === "arrange"' in sse, "la orden viaja por el MISMO rail SSE que show/close"
    assert "_SHOWCASE" in sse, "en showcase cada apertura re-ordena sola"
    chat = (ENGINE / "frontend" / "app" / "components" / "ChatWall.js").read_text(encoding="utf-8")
    assert 'has("showcase")' in chat, "el chat arranca abierto y acoplado para que la conversación se lea"
    api = (ENGINE / "server" / "voice_api.py").read_text(encoding="utf-8")
    assert "/api/canvas/arrange" in api, "el snap es invocable por API, como pidió el operador"

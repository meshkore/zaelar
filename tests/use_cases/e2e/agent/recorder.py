"""V2-464 — la GRABACIÓN de una ronda: lo que habría visto el usuario, en vídeo y sin manos.

El operador lo pidió con la analogía exacta (2026-08-28): un espectador de pantalla mientras el caso corre
en background — chat abierto para leer la conversación, widgets colocados «bien bonito, bien alineado» como
el snap de ventanas de macOS/Windows — y el resultado guardado como vídeo sin sonido, enlazado desde el
informe del caso junto a la sesión y sus flujos. Material directo para un showcase.

CÓMO. Playwright graba vídeo de forma nativa (`record_video_dir` en el contexto): un Chromium headless de
1920×1080 carga el plató con `?showcase=1` —que abre el chat acoplado y auto-ordena la rejilla en cada
apertura (V2-464 en `sse.js`/`ChatWall.js`/`desktop.js`)— y se queda MIRANDO mientras el runner conduce la
ronda por el canal probe. El vídeo solo se materializa al CERRAR el contexto, así que el espectador vive en
un SUBPROCESO con un protocolo explícito de parada por stdin: matarlo a señales perdería el fichero entero,
que es el modo de fallo más caro posible aquí (la ronda ya corrió y ya se pagó).

Fail-soft de punta a punta: una grabación que no arranca NUNCA tira la medición — el vídeo es un espejo de
la ronda, no parte de ella.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from . import config

VIDEO_DIR = config.RUNS_DIR / "videos"

# El espectador, como TEXTO de un subproceso y no como función: Playwright sync no puede convivir con un
# loop asyncio ya corriendo, y el runner tiene uno. Un proceso aparte no comparte loop ni GIL con la ronda.
_WATCHER_SRC = r'''
import json, sys
from playwright.sync_api import sync_playwright

url, out_dir = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                              record_video_dir=out_dir,
                              record_video_size={"width": 1920, "height": 1080})
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    print("READY", flush=True)
    # Espera la orden de parar por stdin. EOF cuenta como orden: si el runner muere, esto no queda huérfano.
    try:
        sys.stdin.readline()
    except Exception:
        pass
    video = page.video
    ctx.close()      # ← aquí se materializa el .webm
    browser.close()
    try:
        print("VIDEO " + json.dumps(video.path()), flush=True)
    except Exception:
        print("VIDEO null", flush=True)
'''


class Recorder:
    """Un espectador por ronda. `start()` espera a que la página esté cargada; `stop(nombre)` cierra, espera
    el volcado y renombra el .webm a un nombre que diga QUÉ ronda es."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.proc: subprocess.Popen | None = None
        self.error = ""

    def start(self, timeout_s: float = 60.0) -> bool:
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        url = self.base_url.rstrip("/") + "/?showcase=1"
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-c", _WATCHER_SRC, url, str(VIDEO_DIR)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True)
        except Exception as e:  # noqa: BLE001
            self.error = f"no arrancó: {e}"
            return False
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                self.error = f"murió al arrancar: {(self.proc.stderr.read() or '')[-300:]}"
                return False
            line = self.proc.stdout.readline()
            if line.strip() == "READY":
                return True
        self.error = "no llegó a READY"
        self.stop("")
        return False

    def stop(self, name: str) -> str:
        """Cierra el espectador y devuelve la ruta final del vídeo ('' si no hubo)."""
        if not self.proc:
            return ""
        import json as _json
        path = ""
        try:
            if self.proc.poll() is None:
                try:
                    self.proc.stdin.write("stop\n")
                    self.proc.stdin.flush()
                except Exception:  # noqa: BLE001
                    pass
            out, _ = self.proc.communicate(timeout=60)
            for line in (out or "").splitlines():
                if line.startswith("VIDEO ") and line != "VIDEO null":
                    try:
                        path = _json.loads(line[6:])
                    except Exception:  # noqa: BLE001
                        path = ""
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.error = "no cerró a tiempo: el vídeo puede haberse perdido"
        finally:
            self.proc = None
        if path and name:
            # El nombre dice QUÉ ronda es — el hash aleatorio de Playwright no se lo dice a nadie.
            dst = VIDEO_DIR / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.webm"
            try:
                Path(path).rename(dst)
                return str(dst)
            except Exception:  # noqa: BLE001
                return str(path)
        return str(path or "")

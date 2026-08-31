"""nucleo/engine_url.py — the address of ESTE motor, for the bridges with the that a worker le contesta.

Extraido of `nucleo/dispatch.py` the 2026-08-24 for pagar the trinquete of arquitectura al add the cosecha of
the sheet (V2-296). Sale entero because no touches NADA of the gestor of sessions: es a funcion pura of two variables
of entorno, and quien the needs —the `env` that is le pasa al worker— only needs the result.

Vive aparte also because es the response a V2-152, that costo a tanda whole: the seis bridges resuelven
`ZAELAR_BASE` with a `localhost:43917` cableado by defecto and NADIE ponia esa variable, so that a motor in
any another puerto lanzaba workers that conducian the browser, the memory and the tarjetas of OTRO motor.
"""
from __future__ import annotations

import os


def _own_base_url() -> str:
    """The URL of THIS engine, for the bridges a worker uses to talk back to it.

    Reads the same `HOST`/`PORT` the server binds with, so a sandbox on a free port and the operator's engine on
    43917 each hand their workers their OWN address instead of a shared constant. `127.0.0.1` rather than the
    bind host when that is `0.0.0.0`: a worker is a local subprocess, and the wildcard is not a dialable address.
    """
    port = (os.getenv("PORT") or "43917").strip() or "43917"
    host = (os.getenv("HOST") or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::", "*", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}"

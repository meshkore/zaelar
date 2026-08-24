"""nucleo/engine_url.py — la dirección de ESTE motor, para los puentes con los que un worker le contesta.

Extraído de `nucleo/dispatch.py` el 2026-08-24 para pagar el trinquete de arquitectura al añadir la cosecha de
la hoja (V2-296). Sale entero porque no toca NADA del gestor de sesiones: es una función pura de dos variables
de entorno, y quien la necesita —el `env` que se le pasa al worker— solo necesita el resultado.

Vive aparte además porque es la respuesta a V2-152, que costó una tanda entera: los seis puentes resuelven
`ZAELAR_BASE` con un `localhost:43917` cableado por defecto y NADIE ponía esa variable, así que un motor en
cualquier otro puerto lanzaba workers que conducían el navegador, la memoria y las tarjetas de OTRO motor.
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

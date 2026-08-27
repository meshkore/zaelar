"""nucleo/bridge_usage.py — a bridge's argument error says what to DO, not just what the shape is.

V2-212 taught this on `nav_cli type_at`: argparse prints the FORM (`usage: … x y text`) and the parser's own
complaint (`invalid int value: 'Hotel Palacio…'`), and neither tells a headless worker how to get out. It burns
the turn. That is the same dead end four bridges paid for on 2026-08-20 — a message that says WHAT failed and
nothing about WHAT NOW.

The MECHANISM is shared here because a second copy of it is a copy that drifts (V2-153). The KNOWLEDGE is not:
each bridge passes its own `hint_for(prog)`, because what to do about a bad `scroll` has nothing to do with what
to do about a bad `ask`.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable


def guided(hint_for: Callable[[str], str]) -> type[argparse.ArgumentParser]:
    """An ArgumentParser class whose `error()` adds `hint_for(self.prog)` between the complaint and the usage.

    The hint goes in the MIDDLE on purpose: a worker reads top-down, so the way out has to arrive before the
    wall of syntax it is already staring at.
    """

    class _GuidedParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write(f"{self.prog}: error: {message}\n")
            hint = hint_for(self.prog) or ""
            if hint:
                sys.stderr.write(hint + "\n")
            sys.stderr.write(self.format_usage())
            raise SystemExit(2)

    return _GuidedParser


def what_is_here(limit: int = 8) -> str:
    """Los ficheros que SÍ están en el directorio de trabajo, para acompañar a un «no existe».

    «No such file or directory: progreso.json» es verdad y no sirve para nada: deja al worker sin saber si
    escribió el fichero en otro sitio, si lo escribió con otro nombre, o si no llegó a escribirlo. Las tres
    salidas son distintas y desde ese mensaje se ven igual, así que el modelo elige a ciegas — medido en
    `best-plumber-same-day__es` (2026-08-28), donde el paso murió ahí y la ronda entera se fue en ocho minutos
    sin entregar lo que el operador pidió tres veces.

    Es la norma de «si tienes la respuesta, imprímela»: el puente está PARADO en ese directorio y sabe lo que
    hay dentro. Costó ocho horas la vez que un preflight sostuvo un 402 diciendo «mira el log».

    Acotado y best-effort: esto va a stderr de un puente, no es un explorador de ficheros, y un directorio
    ilegible no puede convertir un error claro en una excepción.
    """
    import os
    try:
        nombres = sorted(n for n in os.listdir(".") if not n.startswith("."))
    except OSError:
        return ""
    if not nombres:
        return "el directorio está VACÍO: el fichero no llegó a escribirse"
    jsons = [n for n in nombres if n.endswith(".json")]
    muestra = (jsons or nombres)[:limit]
    cola = f" (+{len(jsons or nombres) - len(muestra)} más)" if len(jsons or nombres) > len(muestra) else ""
    que = "json que SÍ hay aquí" if jsons else "lo que SÍ hay aquí (ningún .json)"
    return f"{que}: {', '.join(muestra)}{cola}"


def read_payload(raw: str) -> tuple[str, str, str]:
    """`(texto, de_dónde, error)` para un payload que puede venir en línea, por `@fichero` o por `-` (stdin).

    V2-379 — la convención existía SOLO en `widget_cli` y `worker_bridge act` no la tenía, así que a ese puente
    el JSON solo se le podía pasar en línea… y en línea NO CABE: nuestra propia puerta de permisos rechaza un
    argumento con llaves y comillas dentro («Contains brace with quote character (expansion obfuscation)»).

    Medido en `best-rated-rental-car__es` (2026-08-27), y el rastro se lee de corrido:

        63,5 s  ⚠️ Contains brace with quote character   ← la puerta bloquea el JSON en línea
        67,6 s  ✏️ escribe 24316c-1/search.json          ← el worker se inventa el rodeo por fichero
        69,2 s  ⚠️ Exit code 1 payload JSON inválido     ← y el puente no sabe leer ficheros
        73,1 s  usage: worker_bridge act …               ← a ciegas
        77,5 s  usage: worker_bridge act …               ← otra vez
        85,1 s  ✏️ escribe 24316c-1/use_tool.json        ← y otra

    Ocho errores internos y cero resultados. El worker dio con la solución correcta él solo —escribir el JSON a
    un fichero— y le dijimos que no. `act` es por donde PIDE una búsqueda, así que cerrado ahí se queda ciego.

    El MECANISMO se comparte (misma razón que `guided`): dos lectores de payload se separan, y entonces un
    puente acepta `@fichero` y el otro no, que es exactamente el estado del que se sale. El MENSAJE lo pone
    cada puente, porque lo que hay que hacer con un fichero que falta depende de quién pregunta.
    """
    raw = (raw or "").strip()
    if not raw:
        return "", "argumento", ""
    if raw == "-":
        import sys as _sys
        return _sys.stdin.read(), "stdin", ""
    if raw.startswith("@"):
        path = raw[1:]
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read(), f"fichero {path}", ""
        except OSError as e:
            return "", f"fichero {path}", str(e)
    return raw, "argumento", ""

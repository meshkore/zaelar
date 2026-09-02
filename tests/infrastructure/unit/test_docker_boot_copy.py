"""The cloud image must include EVERYTHING the engine imports at startup.

Why it exists: on 2026-08-12, `observability/` (V2-090) was deployed and the Machine crash-looped at boot with
`ModuleNotFoundError: No module named 'observability'` — its `COPY` was missing from the `Dockerfile`. The unpleasant
thing about the failure is that **the image builds perfectly**: there are no imports at build time, so nothing
raises an alert until the process starts in production. The smoke test caught it and rolled it back, meaning the
cost was a lost deployment rather than an outage — but the release workflow recorded it as a **manual probe
before cutting the tag**, and a manual probe is one that eventually goes unrun.

This makes it automatic. It does not replace the smoke test (which tests the actual image); it runs earlier, where
the cost is low.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]

# Top-level packages that must NOT be in the image, each with its reason. As with Energy's gate `_EXENTOS`,
# bypassing the rule requires writing down why, and that text is what someone else can challenge.
_FUERA_DE_LA_IMAGEN: dict[str, str] = {
    "files":
        "SHIM de compatibilidad (V2-003 · T55): el módulo se plegó en la memoria central y el boot importa "
        "`memory.server_api`, no éste. Nadie dentro del repo lo importa — meterlo en la imagen sería enviar "
        "código muerto a producción.",
    "tests":
        "el arnés de pruebas no viaja en la imagen de producción.",
}


def _paquetes_top_level() -> set[str]:
    return {p.name for p in RAIZ.iterdir()
            if p.is_dir() and (p / "__init__.py").exists() and not p.name.startswith((".", "_"))}


def _copiados() -> set[str]:
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    return set(re.findall(r"^COPY (\S+) ", dockerfile, re.M))


def test_todo_paquete_del_motor_viaja_en_la_imagen():
    faltan = sorted(_paquetes_top_level() - _copiados() - set(_FUERA_DE_LA_IMAGEN))
    assert not faltan, (
        f"paquetes top-level que NO están en el COPY del Dockerfile: {faltan}\n"
        "La imagen construirá bien y la Machine morirá al arrancar con ModuleNotFoundError. Añade su COPY, "
        "o —si de verdad no tiene que viajar— añádelo a _FUERA_DE_LA_IMAGEN con el motivo escrito."
    )


def test_una_exencion_apunta_a_algo_que_existe():
    """An exemption for a deleted package is a permission that no longer protects anything and makes it seem that
    the gate covers something that does not exist. It expires on its own."""
    muertas = [n for n in _FUERA_DE_LA_IMAGEN if n != "tests" and not (RAIZ / n).is_dir()]
    assert not muertas, f"exenciones que ya no apuntan a un paquete: {muertas}"


# ── …and the COPY is only half the question ──────────────────────────────────────────────────────────────────
#
# `COPY nucleo ./nucleo` looks like it puts `nucleo/` in the image, but `.dockerignore` is applied to the build
# CONTEXT before any COPY runs, so a pattern can quietly take files out of a directory that is copied in full.
# The image still builds — there is nothing to resolve at build time — and the Machine dies on the first read.
#
# MEASURED 2026-09-02, auditing the release that was about to be cut: `config/models.default.json` (V2-500, the
# single public model table) is tracked, is read at boot by `config/models.py`, `provider_chain`,
# `workers/providers` and `memory/embeddings` — and was being dropped by `config/*.json`, a rule written in
# 2026-07-23 to keep the OPERATOR'S per-install json out of a tenant image. Both files match the same glob and
# they are opposite kinds of thing: one is gitignored per-install state, the other is versioned code-adjacent
# data. Proven before fixing: with `config/` copied minus its json, `config.models.titular("voice_brain")`
# raises `FileNotFoundError`.
#
# The rule this pins is the one that separates them and needs no judgement: **what git TRACKS inside a COPYed
# path must reach the image.** Untracked runtime state is exactly what `.dockerignore` is for and is untouched
# by this.

#: Tracked files that are deliberately kept OUT of the image, each with its reason. Empty today, and that is
#: its correct state — as with `_FUERA_DE_LA_IMAGEN`, bypassing the rule costs writing down why.
_EXCLUIDOS_A_PROPOSITO: dict[str, str] = {}


def _patrones_dockerignore() -> list[str]:
    return [ln.strip() for ln in (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def _excluido(ruta: str, patrones: list[str]) -> str | None:
    """Docker semantics, in the part that matters: patterns are evaluated IN ORDER and the LAST one that
    matches decides, so a `!pat` line re-includes what an earlier line dropped."""
    import fnmatch
    from pathlib import PurePath

    veredicto: str | None = None
    for patron in patrones:
        negado = patron.startswith("!")
        p = patron[1:] if negado else patron
        casa = (fnmatch.fnmatch(ruta, p)
                or fnmatch.fnmatch(ruta, p.rstrip("/") + "/*")
                or fnmatch.fnmatch(PurePath(ruta).name, p))
        if casa:
            veredicto = None if negado else patron
    return veredicto


def _rutas_copiadas() -> set[str]:
    return _copiados()


def test_lo_que_git_versiona_dentro_de_un_COPY_llega_a_la_imagen():
    import subprocess

    copiados = _rutas_copiadas()
    patrones = _patrones_dockerignore()
    tracked = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True,
                             check=True).stdout.split()
    perdidos = []
    for f in tracked:
        if f.split("/")[0] not in copiados and f not in copiados:
            continue
        if f in _EXCLUIDOS_A_PROPOSITO:
            continue
        patron = _excluido(f, patrones)
        if patron:
            perdidos.append(f"{f}  (lo tira «{patron}» de .dockerignore)")
    assert not perdidos, (
        "ficheros VERSIONADOS que el COPY mete y .dockerignore vuelve a sacar:\n  " + "\n  ".join(perdidos)
        + "\nLa imagen construye igual y la Machine muere al leerlos. Añade la excepción «!ruta» en "
          ".dockerignore, o —si de verdad no debe viajar— apúntalo en _EXCLUIDOS_A_PROPOSITO con el motivo."
    )


def test_una_exclusion_deliberada_apunta_a_algo_que_existe():
    muertas = [f for f in _EXCLUIDOS_A_PROPOSITO if not (RAIZ / f).exists()]
    assert not muertas, f"exclusiones deliberadas que ya no apuntan a un fichero: {muertas}"

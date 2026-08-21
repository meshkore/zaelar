"""DeepSeek V4 Pro is the ONLY titular — and no banned provider can creep back in unnoticed.

Operator's norm, 2026-08-19, stated twice and then made absolute: *«de momento vamos a trabajar con DeepSeek V4
Pro […] ya no quiero volver a ver el nombre de <ese modelo> en ningún sitio más ni enterarme de que haces pruebas
con él ni que en ningún sitio se fuerza»*. The banned name is assembled from pieces below and never spelled in
this file, so the sweep does not catch itself — a guard that has to exclude itself from its own sweep is the first
place the name comes back.

A norm written only in prose is a norm that comes back. It had already come back twice here:

  · `.env` pinned the fast layer to a broker-served Anthropic model and, because the use-case sandbox copies
    `os.environ`, **the whole use-case board was measured against a different brain than production** — no error,
    no warning, just numbers that were not comparable to anything the operator runs.
  · `config/profiles.py`'s cloud profile still named a two-versions-old titular, so anyone picking that profile in
    the wizard silently overwrote the live default.

So this is a GREP over the tree, not a config assertion: the failure mode is a NAME reappearing in a default, a
candidate list or a benchmark, and only a sweep sees all three at once.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]

# Names that must not appear anywhere in the tree. Substring match, case-insensitive.
BANNED = ("hai" + "ku",)

# Directories that are ARCHIVES of measurements already taken, not instructions to anyone: raw benchmark reports
# keep whichever model ids the run actually swept, and rewriting them would falsify the record. Nothing reads them
# to decide what to call.
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "resultados", "snapshots", "timeline",
             ".runtime", "logs", "_data", "vendor", "certs", "dist", "build",
             # Artefactos de corridas ya hechas (logs, eventos): registran el modelo que corrió DE VERDAD ese
             # día. Reescribirlos falsificaría la evidencia, igual que los informes de banco.
             "runs"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".wav", ".mp3", ".pdf", ".ico", ".woff", ".woff2",
                 ".onnx", ".bin", ".so", ".dylib", ".zip", ".gz"}


def _files():
    for root, dirs, names in os.walk(ENGINE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".venv")]
        for n in names:
            p = Path(root) / n
            if p.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield p


def test_no_banned_model_name_anywhere_in_the_tree():
    hits: list[str] = []
    for p in _files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = text.lower()
        for bad in BANNED:
            if bad in low:
                for i, line in enumerate(text.splitlines(), 1):
                    if bad in line.lower():
                        hits.append(f"{p.relative_to(ENGINE)}:{i}: {line.strip()[:100]}")
    assert not hits, (
        "Un modelo RETIRADO por norma del operador ha vuelto al árbol. Si es un default o un candidato de "
        "banco, quítalo; si de verdad hace falta nombrarlo, la norma se cambia con el operador primero.\n  "
        + "\n  ".join(hits[:20]))


def test_the_fast_layer_defaults_to_the_titular_ON_ITS_OWN_ENDPOINT():
    """The model name TRAVELS WITH ITS ENDPOINT. The broker prefixes it (`deepseek/deepseek-v4-pro`) and the
    native API does not, so a default that carries one without the other buys a 400 on every call — which is
    exactly how the workers' DeepSeek rung shipped broken, invisible because a relay rung only runs once the
    titular is already down."""
    from nucleo.flash import model_spec as M
    assert M._FALLBACK_MODEL == "deepseek-v4-pro"
    assert M._FALLBACK_BASE == "https://api.deepseek.com"
    assert not M._FALLBACK_MODEL.startswith("deepseek/"), "ese prefijo es el catálogo del BROKER, no el nativo"


def test_the_emergency_fallback_is_the_SAME_brain_as_the_config():
    """A fallback pointing at a different model is a SILENT brain swap at the worst possible moment — the one
    where the config cannot be read. It shows up in answer quality and in the bill, never as an error.

    Se compara contra el default QUE SE ENVÍA (`config/v2.py`), no contra `config/v2.json`. Ese fichero está
    gitignoreado: es la config LOCAL de cada máquina, así que la versión anterior de este test afirmaba que una
    constante del código coincide con un fichero privado — y por tanto se ponía roja en cuanto alguien elegía
    otro titular, que es su derecho y no una avería. Pasó el 2026-08-21: bastó cambiar el titular del operador a
    `deepseek-v4-flash` para que este guarda acusara al código. Misma familia que el suelo absoluto de
    `test_accumulator` calibrado contra los logs vivos: un test unitario no puede depender de un artefacto vivo.
    Lo que sí es un defecto del PRODUCTO —y es lo que el docstring de arriba quiere cazar— es que el fallback de
    emergencia del código no coincida con el titular que el producto declara por defecto."""
    import config.v2 as v2
    from nucleo.flash import model_spec as M
    shipped = str((v2._DEFAULTS.get("fast") or {}).get("model") or "")
    if not shipped:
        pytest.skip("el default enviado no nombra modelo: el fallback ES la respuesta")
    assert M._FALLBACK_MODEL in shipped, (
        f"el fallback ({M._FALLBACK_MODEL}) no es el titular que el producto envía por defecto ({shipped})")


def test_no_task_of_memllm_routes_to_a_banned_provider():
    """`nucleo/memllm.py` is where the per-task routing lives (rem/i18n/turn_complete/directed/paraphrase). The
    i18n task was the LAST one still choosing an Anthropic model, on a measurement whose premise (the broker's
    ignored reasoning switch) the direct endpoint removes."""
    from nucleo import memllm
    blob = str(memllm._DEFAULTS) + str(memllm._FAILOVER)
    for bad in BANNED:
        assert bad not in blob.lower(), f"{bad} sigue en el enrutado por tarea de memllm"


def test_the_browser_loop_defaults_to_the_titular():
    from widgets.navegador import agent as A
    assert A.DEFAULT_MODEL == "deepseek-v4-pro"
    assert A.DEFAULT_BASE_URL == "https://api.deepseek.com"
    # The judge rides the SAME endpoint, so it must use the native (unprefixed) catalog too.
    assert not re.match(r"^deepseek/", A._judge_model()), "nombre del broker sobre el endpoint nativo → 400"


# ── OpenAI: en el CATÁLOGO sí, corriendo solo no (norma del operador, 2026-08-21) ─────────────────────────────
#
# La norma ya estaba escrita en el árbol —el escalón i18n de `memllm._FAILOVER` la cita como «the operator's
# standing norm (no OpenAI models)»— pero se aplicaba en un sitio y no en los otros cuatro, que es la forma en que
# una norma en prosa vuelve. El operador la acotó: «por defecto no los usamos —ni la config de pruebas, ni su
# instancia local, ni la nube— pero si un usuario quiere cambiarlo, que lo haga».
#
# Así que NO es un barrido del árbol como el de arriba: la línea está entre lo que se OFRECE y lo que CORRE sin
# que nadie lo elija. Por eso el test tiene dos filos, y el segundo importa tanto como el primero — un barrido a
# secas habría "limpiado" también el catálogo y roto el principio de auto-hospedaje del repo.
_OPENAI_RE = re.compile(r"\bopenai/|\bgpt-[0-9]", re.I)


def test_no_relay_rung_runs_an_openai_model():
    """Los escalones corren SOLOS: nadie los elige, se llega a ellos porque el anterior falló."""
    from nucleo import memllm

    culpables = []
    for tarea, escalones in memllm._FAILOVER.items():
        for url, modelo in escalones:
            if _OPENAI_RE.search(str(modelo)):
                culpables.append(f"{tarea} → {modelo}")
    assert not culpables, f"escalones de relevo con modelo de OpenAI: {culpables}"


def test_no_config_default_runs_an_openai_model():
    """Y los DEFAULTS igual: son lo que corre en una instalación que nadie ha tocado."""
    from config import v2

    culpables = []
    for seccion, cuerpo in v2._DEFAULTS.items():
        if not isinstance(cuerpo, dict):
            continue
        for clave, valor in cuerpo.items():
            if clave in ("model", "fast_model", "slow_model") and _OPENAI_RE.search(str(valor or "")):
                culpables.append(f"{seccion}.{clave} = {valor}")
    assert not culpables, f"defaults con modelo de OpenAI: {culpables}"


def test_the_susurro_fallback_literal_matches_its_config_default():
    """El último recurso del susurro solo se usa cuando la config NO se puede leer — o sea, cuando algo ya va mal.
    Un literal que se separe del default es una deriva que por definición nadie ve hasta ese momento, y así fue
    como este quedó apuntando a OpenAI después de que la config se moviera al broker."""
    import inspect

    from config import v2
    from nucleo.susurro import client

    literal = re.search(r'c\.get\("model"\)\s*or\s*"([^"]+)"', inspect.getsource(client.audit_llm))
    assert literal, "el último recurso del susurro dejó de ser un literal legible"
    assert literal.group(1) == v2._DEFAULTS["susurro"]["model"], \
        "el último recurso del susurro no coincide con su default de config"


def test_but_the_CATALOGUE_still_offers_one():
    """El otro filo, y no es simetría de adorno: `engine/` es OSS y quien se autohospeda tiene que poder poner
    OpenAI en su motor. Si un barrido futuro «limpia» también el catálogo, este test lo para."""
    fuente = (ENGINE / "server" / "config_api.py").read_text()
    assert _OPENAI_RE.search(fuente), \
        "el catálogo dejó de ofrecer OpenAI: la norma prohíbe que CORRA solo, no que exista"

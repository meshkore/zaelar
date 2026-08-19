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
    where the config cannot be read. It shows up in answer quality and in the bill, never as an error."""
    import config.v2 as v2
    from nucleo.flash import model_spec as M
    real = v2.fast_model_spec()
    if not real.get("model"):
        pytest.skip("config/v2.json sin modelo (instalación fresca): el fallback ES la respuesta")
    assert M._FALLBACK_MODEL in real["model"], (
        f"el fallback ({M._FALLBACK_MODEL}) no es el titular de config/v2.json ({real['model']})")


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

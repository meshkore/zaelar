"""Energy COVERAGE gate (T299).

Why it exists: the rate table has been fixed three times (on 2026-08-05 FlashBrain was metered at
zero; on 2026-08-13 four more gaps were found in the workers), and each time the failure was found
manually by looking at a number that was too low. None of those times did anything fail: **under-metering
is indistinguishable from working correctly.** The tests in `test_energy_meter.py` check that the
arithmetic is correct; this one checks the other thing, which is what actually breaks—that nobody is
spending OUTSIDE the meter.

The approach is deliberately simple: search the code for who talks to a paid provider and require
that same file to mention `energy_meter`. It does not prove that the call is metered correctly (a grep
cannot know that); it proves that SOMEONE remembered. The exception is an explicit entry in
`_EXENTOS` with its reason written down, which is exactly what we want: bypassing the meter should cost
a comment that someone else can read and debate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[4]

# Signals that "this file calls a paid external provider."
_SENALES = (
    "chat/completions", "chat.completions.create",
    "AsyncOpenAI", "OpenAI(",
    "aimlapi.com", "api.x.ai", "api.z.ai", "moonshot.ai", "api.openai.com",
    "api.anthropic.com", "api.elevenlabs.io", "api.deepgram.com",
    "api.perplexity.ai", "api.tavily.com", "api.search.brave.com",
    "api.brightdata.com",
)

# Proof that the file participates in the energy system.
_MARCAS = ("energy_meter", "report_llm_usage", "report_worker_usage",
           "report_tts_usage", "report_stt_usage", "report_search_usage")

# Folders that are not the production engine.
_FUERA = ("tests/", ".venv/", "node_modules/", "widgets/_data/", "vendor/", "scripts/")

# EXEMPTIONS, each with its reason. Adding one is a decision, not a formality: if the reason cannot be
# written in one honest line, the file probably needs to meter usage.
_EXENTOS: dict[str, str] = {
    "nucleo/energy_meter.py":
        "ES el contador: aquí viven las tarifas, no un llamante que deba usarlas.",
    "config/v2.py":
        "guarda los DEFAULTS de routing (base_url como texto de config); no invoca a nadie.",
    "voice/engine/core/config.py":
        "perfiles remote/local; el mismo caso, solo declara endpoints.",
    "config/model_benchmarks.py":
        "réplica CURADA de los benchmarks para la UI; texto, sin tráfico.",
    "voice/llm.py":
        "cliente del ARNÉS de evaluación (tests/agent_headless/harness) — corre en la máquina del "
        "desarrollador, nunca dentro de una Machine de inquilino, y su coste no es de ningún usuario.",
    "nucleo/llm_egress.py":
        "mapa de ENRUTADO: nombra hosts de proveedor para saber a qué familia iba dirigida una "
        "llamada, pero no abre ninguna conexión. Quien llama —y quien mide— es el call site.",
    "config/balances.py":
        "consulta SALDO de las cuentas de proveedor; no consume nada facturable.",
    "server/config_api.py":
        "cataloga proveedores/modelos para la UI; nunca invoca un modelo.",
    "nucleo/workers/providers.py":
        "resuelve la cadena de endpoints; quien EJECUTA y mide es workers/session.py.",
    "nucleo/flash/provider_chain.py":
        "hermano del anterior: elige escalón, no llama.",
    "connectors/registry.py":
        "inventario de conectores; sin tráfico.",
    "nucleo/flash/model_spec.py":
        "resuelve base_url/api_key del modelo elegido (texto de config, sin tráfico); quien EJECUTA y "
        "mide la llamada es fast_client.py::stream() (split de modularización, 2026-08-17).",
}


def _ficheros_py() -> list[Path]:
    return [p for p in RAIZ.rglob("*.py")
            if not any(s in p.relative_to(RAIZ).as_posix() for s in _FUERA)]


def _sospechosos() -> dict[str, str]:
    """rel_path → first signal found, for files WITHOUT a metering marker."""
    out: dict[str, str] = {}
    for p in _ficheros_py():
        rel = p.relative_to(RAIZ).as_posix()
        if rel in _EXENTOS:
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        senal = next((s for s in _SENALES if s in src), None)
        if senal and not any(m in src for m in _MARCAS):
            out[rel] = senal
    return out


def test_todo_lo_que_llama_a_un_proveedor_de_pago_reporta_a_energy():
    faltan = _sospechosos()
    assert not faltan, (
        "Estos ficheros llaman a un proveedor de pago y NO nombran el contador de Energy:\n"
        + "\n".join(f"  {k}  (señal: {v!r})" for k, v in sorted(faltan.items()))
        + "\n\nEn una cuenta de nube eso es dinero saliendo sin factura. Reporta el consumo con "
          "nucleo.energy_meter, o —si de verdad no cuesta— añádelo a _EXENTOS con el motivo escrito."
    )


def test_las_exenciones_siguen_existiendo():
    """An exemption for a deleted or renamed file is a permission that no longer protects anything, and worse:
    it makes people believe the gate covers something that does not exist. It expires on its own."""
    muertas = [rel for rel in _EXENTOS if not (RAIZ / rel).exists()]
    assert not muertas, f"exenciones de _EXENTOS que ya no apuntan a un fichero: {muertas}"


@pytest.mark.parametrize("rel", sorted(_EXENTOS))
def test_una_exencion_lleva_motivo_de_verdad(rel):
    assert len(_EXENTOS[rel].strip()) > 20, f"la exención de {rel} no explica nada"


# ── THE GATEWAY (architecture, 2026-08-15) ──────────────────────────────────────────────────────────────────
# Operator request: *"the billing module must be a completely separate module, acting as a gateway, and
# calls to services that consume money must go through it"*. It was separate, but without a gateway:
# all eleven callers repeated the same eight-line block, and that copy-paste had a measurable cost (only one
# of the eleven read `prompt_cache_hit_tokens`). These tests defend the structure, not the arithmetic.
def test_medir_una_llamada_es_UNA_linea_y_el_contador_sabe_de_cache():
    """The gateway extracts `usage` from the provider's raw response—the caller does not unpack anything, which is
    exactly the knowledge that had been missed by ten of the eleven."""
    from nucleo import energy_meter as em
    visto = {}
    orig = em.report_llm_usage
    try:
        em.report_llm_usage = lambda **kw: visto.update(kw)
        em.meter_openai_response(
            {"usage": {"prompt_tokens": 900, "completion_tokens": 40, "prompt_cache_hit_tokens": 830}},
            base_url="https://api.deepseek.com", model="deepseek-v4-flash")
    finally:
        em.report_llm_usage = orig
    assert visto["prompt_tokens"] == 900 and visto["completion_tokens"] == 40
    assert visto["cache_hit_tokens"] == 830, "la caché es del contador, no de cada llamante"


def test_la_puerta_traga_una_respuesta_rara_sin_tumbar_al_llamante():
    """“Metering never brings down the call it was metering” is a property of the MODULE. Previously it was a
    `try/except` copied eleven times: a new caller that forgot it turned an accounting failure into a crash."""
    from nucleo import energy_meter as em
    for payload in (None, "no soy una respuesta", {"usage": None}, object()):
        em.meter_openai_response(payload, base_url="https://api.x.ai/v1", model="grok-4-fast")


def test_ninguna_puerta_publica_del_contador_puede_lanzar():
    """The PROPERTY is checked across all of them at once, so adding a new gateway without the decorator is noticed
    here rather than in production."""
    from nucleo import energy_meter as em
    puertas = [n for n in dir(em) if n.startswith("report_") or n.startswith("meter_")]
    assert len(puertas) >= 6, f"esperaba las puertas públicas del contador, encontré {puertas}"
    for n in puertas:
        assert getattr(getattr(em, n), "__wrapped__", None) is not None, \
            f"«{n}» es una puerta pública del contador y le falta @_never_raises"


def test_todo_proveedor_de_busqueda_de_pago_tiene_tarifa():
    """The search chain degrades by QUALITY, so adding a paid search provider is tempting and
    cheap. Without a rate it would be charged at the catch-all—which exists so that nothing is free,
    not to be anyone's permanent price."""
    from nucleo import energy_meter, websearch
    sin_tarifa = [p for p in websearch._PAID_BACKENDS
                  if p not in energy_meter._SEARCH_USD_PER_REQUEST]
    assert not sin_tarifa, (
        f"buscadores de pago sin tarifa propia: {sin_tarifa} — añádela a "
        "energy_meter._SEARCH_USD_PER_REQUEST con su fuente y fecha."
    )


def test_un_buscador_gratis_no_se_cobra():
    """Google (our Chromium) and DDG are the normal path in production. Charging for them by mistake
    would inflate every user's bill for the most frequent operation the agent performs."""
    from nucleo import websearch
    assert "google" not in websearch._PAID_BACKENDS
    assert "ddg" not in websearch._PAID_BACKENDS

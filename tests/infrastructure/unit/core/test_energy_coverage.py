"""Gate de COBERTURA de Energy (T299).

Por qué existe: la tabla de tarifas se ha arreglado tres veces (2026-08-05 el FlashBrain metraba a
cero, 2026-08-13 cuatro agujeros más en los workers) y cada vez el fallo se encontró a mano, mirando
un número que salía bajo. Ninguna de esas veces falló nada: **medir de menos es indistinguible de
funcionar bien.** Los tests de `test_energy_meter.py` comprueban que la aritmética es correcta; este
comprueba lo otro, que es lo que de verdad se rompe — que no haya nadie gastando FUERA del contador.

La forma es deliberadamente tonta: buscar en el código quién habla con un proveedor de pago y exigir
que ese mismo fichero nombre `energy_meter`. No prueba que la llamada esté bien medida (eso no lo
puede saber un grep); prueba que ALGUIEN se acordó. La excepción es una entrada explícita en
`_EXENTOS` con su motivo escrito, que es justo lo que se quiere: que saltarse el contador cueste un
comentario que otro puede leer y discutir.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[4]

# Señales de "este fichero llama a un proveedor externo de pago".
_SENALES = (
    "chat/completions", "chat.completions.create",
    "AsyncOpenAI", "OpenAI(",
    "aimlapi.com", "api.x.ai", "api.z.ai", "moonshot.ai", "api.openai.com",
    "api.anthropic.com", "api.elevenlabs.io", "api.deepgram.com",
    "api.perplexity.ai", "api.tavily.com", "api.search.brave.com",
)

# Prueba de que el fichero participa del sistema energético.
_MARCAS = ("energy_meter", "report_llm_usage", "report_worker_usage",
           "report_tts_usage", "report_stt_usage", "report_search_usage")

# Carpetas que no son el motor en producción.
_FUERA = ("tests/", ".venv/", "node_modules/", "widgets/_data/", "vendor/", "scripts/")

# EXENCIONES, cada una con su motivo. Añadir una es una decisión, no un trámite: si el motivo no se
# puede escribir en una línea honesta, probablemente el fichero deba medir.
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
    """rel_path → primera señal encontrada, para los ficheros SIN marca de medición."""
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
    """Una exención sobre un fichero borrado o renombrado es un permiso que ya no protege nada, y peor:
    hace creer que el gate cubre algo que no existe. Se caduca sola."""
    muertas = [rel for rel in _EXENTOS if not (RAIZ / rel).exists()]
    assert not muertas, f"exenciones de _EXENTOS que ya no apuntan a un fichero: {muertas}"


@pytest.mark.parametrize("rel", sorted(_EXENTOS))
def test_una_exencion_lleva_motivo_de_verdad(rel):
    assert len(_EXENTOS[rel].strip()) > 20, f"la exención de {rel} no explica nada"


# ── LA PUERTA (arquitectura, 2026-08-15) ─────────────────────────────────────────────────────────────────────
# Petición del operador: *«el módulo de cobro tiene que ser un módulo totalmente separado, a modo de gateway, y
# que cuando haya llamadas a servicios que consumen dinero se pase por ahí»*. Estaba separado, pero sin puerta:
# los once llamantes repetían el mismo bloque de ocho líneas, y esa copia-pega tenía coste medible (solo uno de
# los once leía `prompt_cache_hit_tokens`). Estos tests defienden la forma, no la aritmética.
def test_medir_una_llamada_es_UNA_linea_y_el_contador_sabe_de_cache():
    """La puerta saca `usage` de la respuesta cruda del proveedor — el llamante no desempaqueta nada, que es
    justo el conocimiento que se le escapaba a diez de los once."""
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
    """«Medir nunca tumba la llamada que estaba midiendo» es propiedad del MÓDULO. Antes era un `try/except`
    copiado once veces: un llamante nuevo que se olvidara convertía un fallo de contabilidad en caída."""
    from nucleo import energy_meter as em
    for payload in (None, "no soy una respuesta", {"usage": None}, object()):
        em.meter_openai_response(payload, base_url="https://api.x.ai/v1", model="grok-4-fast")


def test_ninguna_puerta_publica_del_contador_puede_lanzar():
    """Se comprueba la PROPIEDAD sobre todas a la vez, para que añadir una puerta nueva sin el decorador se note
    aquí y no en producción."""
    from nucleo import energy_meter as em
    puertas = [n for n in dir(em) if n.startswith("report_") or n.startswith("meter_")]
    assert len(puertas) >= 6, f"esperaba las puertas públicas del contador, encontré {puertas}"
    for n in puertas:
        assert getattr(getattr(em, n), "__wrapped__", None) is not None, \
            f"«{n}» es una puerta pública del contador y le falta @_never_raises"


def test_todo_proveedor_de_busqueda_de_pago_tiene_tarifa():
    """La cadena de búsqueda degrada por CALIDAD, así que añadir un buscador de pago es tentador y
    barato. Sin tarifa se cobraría al catch-all — que existe para que nada sea gratis, no para ser el
    precio de nadie de forma permanente."""
    from nucleo import energy_meter, websearch
    sin_tarifa = [p for p in websearch._PAID_BACKENDS
                  if p not in energy_meter._SEARCH_USD_PER_REQUEST]
    assert not sin_tarifa, (
        f"buscadores de pago sin tarifa propia: {sin_tarifa} — añádela a "
        "energy_meter._SEARCH_USD_PER_REQUEST con su fuente y fecha."
    )


def test_un_buscador_gratis_no_se_cobra():
    """Google (nuestro Chromium) y DDG son el camino normal en producción. Cobrarlos por descuido
    inflaría la factura de cada usuario en la operación más frecuente que hace el agente."""
    from nucleo import websearch
    assert "google" not in websearch._PAID_BACKENDS
    assert "ddg" not in websearch._PAID_BACKENDS

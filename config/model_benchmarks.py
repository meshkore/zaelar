"""config/model_benchmarks.py — réplica CURADA, visible al usuario, de las decisiones de modelo del sistema
(V2-077, 2026-07-26). Fuente de verdad DETALLADA: `.meshkore/docs/ops/zaelar-model-benchmarks.md` (interno,
denso, con trazas/incidentes). Este módulo NO lo parsea — es un resumen a mano, igual que `web/src/pages/technology/`
es una foto curada de la arquitectura interna, no un espejo automático. Al tocar una decisión de modelo (routing
nuevo, benchmark nuevo, candidato descartado/adoptado) actualiza AMBOS: el doc denso Y este resumen — están
enlazados en los dos sentidos (ver la cabecera de `zaelar-model-benchmarks.md`).

Sirve `GET /api/config/benchmarks` (server/config_api.py) → el botón "¿Quieres ver los benchmarks…?" al fondo de
la sección "Cerebro rápido" del área de configuración (frontend/app/components/BenchmarksPanel.js). Puramente
informativo — no hay POST, nada de esto se guarda ni se aplica; cambiar un modelo de verdad se hace en las
secciones normales de configuración (`/api/config/v2`)."""
from __future__ import annotations

UPDATED = "2026-07-26"
SOURCE_DOC = ".meshkore/docs/ops/zaelar-model-benchmarks.md"

MODULES = [
    {
        "id": "fast",
        "label": "Cerebro rápido · FlashBrain",
        "role": "Responde CADA turno de voz/chat en tiempo real: charla, tool-calling (mostrar/cerrar widgets, "
                "buscar, música, memoria, escalar) — nunca puede razonar (thinking OFF), el turno debe cerrar en "
                "~1-3s o la voz se queda muda.",
        "current": {"model": "anthropic/claude-haiku-4.5", "provider": "AIMLAPI", "cost_in": 1.00, "cost_out": 5.00,
                    "ttft_ms": 900, "since": "2026-07-12 (V2-034)"},
        "why": "A/B en el canal de prueba (mismo prompt + catálogo de tools reales) sobre grok-4-fast-non-reasoning: "
               "grok 'parecía tonto' — no buscaba cuando debía (alucinaba), no introspeccionaba su propia "
               "contradicción y reaccionaba con acciones espurias a preguntas meta. Haiku buscaba fiable, "
               "explicaba en vez de actuar sobre dudas, a latencia comparable.",
        "hallucination_note": "Grok (xAI) SIGUE baneado en este puesto: en pruebas mezcla memoria↔widget_data y "
                               "responde 'Hecho' a preguntas que no eran órdenes — el fallo más caro en un cerebro "
                               "no-razonador es actuar con seguridad sobre un malentendido.",
        "candidates_2026_07_26": [
            {"model": "glm-4.5-air (Z.AI directo)", "cost_in": 0.20, "cost_out": 1.10,
             "tool_calling": "#1 en BFCL, 90.6% (vs Sonnet 4 89.5%)", "ttft_ms": "sub-segundo (reportado)",
             "status": "en evaluación — puente ya construido y verificado en producción (canal de cluster)",
             "verdict": None},
            {"model": "qwen3-turbo/flash (Alibaba DashScope)", "cost_in": "0.05–0.19", "cost_out": "0.26–1.13",
             "tool_calling": "96.5% en eval independiente — el mejor medido", "ttft_ms": "2600–3000 (tier Plus, más lento que Haiku)",
             "status": "candidato, TTFT preocupante para voz en tiempo real", "verdict": None},
            {"model": "groq · llama-3.1-8b-instant", "cost_in": 0.05, "cost_out": 0.08,
             "tool_calling": "89-90% BFCL, pero dato de 2024 sobre checkpoints ya retirados — sin verificar en el modelo actual",
             "ttft_ms": "muy rápido (600-1000+ tok/s reportado)",
             "status": "requiere cuenta Groq nueva (aún no configurada) + eval propio antes de confiar en routing",
             "verdict": None},
            {"model": "kimi k2 (Moonshot)", "cost_in": "0.375-1.00", "cost_out": "2.0-4.0",
             "tool_calling": "25-65% según versión, con bucles documentados de tool incorrecta",
             "ttft_ms": "2-3s por defecto", "status": "descartado", "verdict": "no usar — fiabilidad de tool-calling insuficiente"},
            {"model": "gemini flash-lite", "cost_in": 0.25, "cost_out": 1.50,
             "tool_calling": "sin dato fiable", "ttft_ms": "n/d",
             "status": "descartado", "verdict": "no puede apagar el razonamiento de verdad (thinking_level mínimo, no OFF); "
                                                 "la versión que sí podía (2.5 flash-lite) se retira en oct-2026"},
        ],
    },
    {
        "id": "memory_processor",
        "label": "Memoria · CORAZÓN de escritura",
        "role": "Destila cada turno en píldoras (dato + metadatos + capa + slot). Off-hot-path (nunca toca la "
                "latencia de voz) — pero la WRITE-COMPLETENESS es la palanca nº1 del recall (V2-031): un dato mal "
                "escrito no hay retriever que lo recupere.",
        "current": {"model": "gpt-4.1-mini", "provider": "OpenAI directo", "cost_in": None, "cost_out": None,
                    "since": "2026-07-20 (V2-056)"},
        "why": "Bench de write-completeness (casos difíciles, es+en): gpt-4o-mini se comía la alergia (0 píldoras); "
               "gpt-4.1-mini y gpt-4o la captan. gpt-4.1-mini es el punto dulce — 98.3% vs qwen2.5:7b local 86.2%, "
               "que queda de opción si se quiere volver a 100% local.",
        "hallucination_note": "Regla dura del operador: la memoria SIEMPRE va por OpenAI (nunca modelos baratos de "
                               "terceros para esta pieza) — un hecho perdido en la escritura es irrecuperable.",
        "candidates_2026_07_26": [],
    },
    {
        "id": "triage",
        "label": "Triaje de mensajería (WhatsApp/Telegram)",
        "role": "Clasifica relevancia de mensajes entrantes — tarea simple, NO tool-routing.",
        "current": {"model": "grok-4.20-0309-non-reasoning", "provider": "xAI directo", "cost_in": None, "cost_out": None},
        "why": "Clasificación simple (no enrutado de acciones) → grok vale aquí, aunque esté baneado del "
               "FlashBrain. Aprovecha saldo de xAI ya pagado. El operador aceptó que el contenido personal salga "
               "a la nube (antes era local, por privacidad) a cambio de simplicidad de batería.",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
    {
        "id": "susurro",
        "label": "«Susurro» — auditor conversacional",
        "role": "Fuera del camino de voz por completo: revisa tramos con fricción (queja/repetición/fallo) y "
                "devuelve correcciones de un catálogo cerrado. Aquí SÍ puede ser un razonador.",
        "current": {"model": "gpt-4.1-mini", "provider": "OpenAI directo", "cost_in": None, "cost_out": None},
        "why": "Misma key que la memoria; benchmark dedicado pendiente (§10 del doc denso).",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
    {
        "id": "cluster",
        "label": "Canal de cluster (conversación con otros agentes, off-voz)",
        "role": "El MISMO motor del FlashBrain en perfil untrusted, tier off-voz — no tiene la presión de latencia "
                "del turno de voz síncrono, puede ser algo más lento/potente.",
        "current": {"model": "glm-5.2", "provider": "Z.AI directo (Anthropic Messages, cuenta de coding-plan)",
                    "cost_in": None, "cost_out": None, "since": "2026-07-26 (fix de coste)"},
        "why": "Antes pasaba por AIMLAPI (con margen) aunque ya había cuenta Z.AI propia. Verificado en vivo: el "
               "endpoint pay-as-you-go de Z.AI (/chat/completions) devuelve 429 sin fondos con esa key — pero su "
               "endpoint de coding-plan (/v1/messages, saldo SEPARADO) sí responde. Migrado; verificado end-to-end "
               "con `tests/e2e/cluster/run_cluster_suite.py` — más rápido que la ruta AIMLAPI anterior.",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
]


def snapshot() -> dict:
    """Vista completa para el frontend — de solo lectura, nada de esto se guarda desde aquí."""
    return {"updated": UPDATED, "source_doc": SOURCE_DOC, "modules": MODULES}

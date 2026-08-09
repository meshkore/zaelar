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

UPDATED = "2026-08-09"
SOURCE_DOC = ".meshkore/docs/ops/zaelar-model-benchmarks.md"

MODULES = [
    {
        "id": "fast",
        "label": "Cerebro rápido · FlashBrain",
        "role": "Responde CADA turno de voz/chat en tiempo real: charla, tool-calling (mostrar/cerrar widgets, "
                "buscar, música, memoria, escalar) — nunca puede razonar (thinking OFF), el turno debe cerrar en "
                "~1-3s o la voz se queda muda.",
        "current": {"model": "deepseek/deepseek-v4-flash · non-thinking", "provider": "AIMLAPI", "cost_in": 0.14,
                    "cost_out": 0.28, "ttft_ms": 1170, "since": "2026-07-31 — Haiku queda de FALLBACK (_FALLBACK_MODEL)"},
        "why": "CAMBIO 2026-07-31 (Haiku→DeepSeek V4 Flash non-thinking): A/B robusto (tests/voice/e2e/agent/model_bench, 16 turnos "
               "inequívocos ×4 reps, mismo prompt+tools reales) → deepseek non-thinking ROUTING 10/10 (vs Haiku 8/10, "
               "que INFRA-actuaba: no buscaba horarios ni añadía cita), INTEL 6/6 (tras acotar la regla 'insiste→"
               "ejecuta' que hacía sobre-actuar en meta/contradicción — fix flash/prompt.py 3bd8c29), TTFT p50 1170ms "
               "(vs Haiku 1821ms) y ~7x más barato. El MODO importa: v4-flash PIENSA por defecto (sobre-actúa, +latencia) "
               "→ fast_client fuerza thinking:disabled cuando el modelo es deepseek. Haiku es el _FALLBACK_MODEL. "
               "[HISTÓRICO] A/B previo (grok-4-fast-non-reasoning): "
               "grok 'parecía tonto' — no buscaba cuando debía (alucinaba), no introspeccionaba su propia "
               "contradicción y reaccionaba con acciones espurias a preguntas meta. Haiku buscaba fiable, "
               "explicaba en vez de actuar sobre dudas, a latencia comparable.",
        "hallucination_note": "Grok (xAI) SIGUE baneado en este puesto: en pruebas mezcla memoria↔widget_data y "
                               "responde 'Hecho' a preguntas que no eran órdenes — el fallo más caro en un cerebro "
                               "no-razonador es actuar con seguridad sobre un malentendido.",
        "candidates_2026_07_26": [
            {"model": "deepseek-v4-flash · NON-THINKING (AIMLAPI)", "cost_in": 0.14, "cost_out": 0.28,
             "tool_calling": "propio A/B 2026-07-31 (tests/voice/e2e/agent/model_bench, mismo prompt+tools reales): routing 4/5 y "
                             "🧠 INTEL 5/5 — IGUALA a Haiku en inteligencia (no alucina, no actúa de más, resuelve "
                             "la contradicción). CLAVE: el modo importa — v4-flash PIENSA por defecto y en thinking "
                             "baja a 4/5 (sobre-actuó: abrió un widget en el turno de contradicción); con "
                             "thinking:disabled sube a 5/5.",
             "ttft_ms": "1683 (p50) vs Haiku 2222 → ~24% MÁS RÁPIDO al primer token; total p50 2331 vs 2676. "
                        "Nota: total con picos (5-6.6s) en algún turno verboso, pero TTFT —la métrica reina de "
                        "voz— es netamente mejor",
             "status": "★ CANDIDATO FUERTE para sustituir a Haiku: + rápido, MISMA inteligencia, ~mucho más barato. "
                        "fast_client ya fuerza thinking:disabled cuando el modelo del path rápido es deepseek "
                        "(voz=no-razonador). Pendiente: flip de config §fast + spot-check de voz REAL (el A/B son "
                        "10 turnos por un proxy AIMLAPI; una key DeepSeek directa daría el modelo más fresco y "
                        "menos hop). deepseek-v4-flash ES la última (snapshot 0731); no hay v4.x más nuevo.",
             "verdict": "recomendado sustituir a Haiku en non-thinking, tras spot-check de voz real"},
            {"model": "glm-4.5-air (Z.AI directo)", "cost_in": 0.20, "cost_out": 1.10,
             "tool_calling": "propio A/B 2026-07-26: 85/90 (94.4%) vs Haiku 87/90 (96.7%) en el mismo arnés real "
                             "de 90 casos (tests/agent_headless/e2e/search/bot) — cerca, no empatado; falló 'hora en Tokio' "
                             "(el caso que SÍ arreglamos hoy en Haiku) y 2 escalate→chat en tareas reales",
             "ttft_ms": "no medido de forma justa aún — el adaptador de hoy usa complete() no-streaming (el "
                        "canal de cluster no necesita streaming); comparar latencia real exige construir "
                        "streaming Z.AI primero, no solo tool-calling",
             "status": "prometedor a ~5x menos coste, pero NO listo para sustituir Haiku todavía — brecha de "
                       "precisión real (no solo ruido) + falta soporte de streaming para el turno de voz",
             "verdict": "seguir evaluando: repetir con muestra mayor + construir streaming antes de decidir"},
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
        "current": {"model": "deepseek-v4-flash", "provider": "AIMLAPI", "cost_in": 0.14, "cost_out": 0.28,
                    "since": "2026-08-09 (bench §12.3)"},
        "why": "Elegido por PRECIO a igualdad de calidad útil: 21 candidatos comerciales × 34 casos × 4 ejes, 3 "
               "pasadas a los finalistas. Empata con el anterior titular (gpt-4.1-mini) en los dos ejes que "
               "destruyen datos — captar el hecho (98,5% vs 98,9%: un hecho de 90) y no ensuciar con descartes "
               "(100% los dos) — por 0,68 $ frente a 1,516 $ los 1.000 turnos, un 55% menos. Escribir va "
               "off-hot-path, así que su mayor lentitud no le cuesta nada al turno de voz.",
        "hallucination_note": "gpt-4o-mini es aún más barato (0,567 $) y está VETADO: con la alergia dicha en "
                              "inglés le pone slot=operator.diet (3/3 pasadas). Un slot invalida todo lo anterior "
                              "con ese slot, así que un futuro «ahora soy vegetariano» borraría la alergia — "
                              "pérdida de datos silenciosa. El destilador se elige con el bench, nunca por "
                              "reputación del proveedor (esto derogó la vieja regla «memoria = siempre OpenAI»).",
        "candidates_2026_07_26": [
            {"model": "gpt-4.1-mini", "cost_in": 0.40, "cost_out": 1.60, "status": "alternativa",
             "verdict": "titular hasta 2026-08-09; único con metadato 100% y varianza cero, pero 2,2x el precio"},
            {"model": "grok-4-fast-non-reasoning", "cost_in": 0.20, "cost_out": 0.50, "status": "alternativa",
             "verdict": "la conservadora: 100% en precisión y capa/slot, pierde 3 pts de completeness"},
            {"model": "gemini-2.5-flash", "cost_in": 0.30, "cost_out": 2.50, "status": "alternativa",
             "verdict": "fallback nº1 si DeepSeek cae — metadato perfecto, 96,7% de completeness"},
            {"model": "gpt-4o-mini", "cost_in": 0.15, "cost_out": 0.60, "status": "descartado",
             "verdict": "VETADO — mete una alergia dicha en inglés en el slot de dieta; un cambio de dieta la borraría"},
            {"model": "gpt-5-mini / gpt-5-nano", "cost_in": 0.25, "cost_out": 2.00, "status": "descartado",
             "verdict": "razonadores: 50-60% de precisión — convierten preguntas y órdenes en recuerdos"},
            {"model": "gpt-4.1-nano", "cost_in": 0.10, "cost_out": 0.40, "status": "descartado",
             "verdict": "el más barato de OpenAI, pero pierde un tercio de los hechos y 6 de cada 10 slots"},
        ],
    },
    {
        "id": "memory_rem",
        "label": "Memoria · sueño REM (consolidación)",
        "role": "Una vez al día agrupa los recuerdos durables por concepto y destila 1 INSIGHT de alto nivel por "
                "grupo (kind='insight'). Es lo que hace que la memoria APRENDA patrones en vez de solo acumular "
                "hechos. Off-hot-path total: corre de madrugada.",
        "current": {"model": "deepseek-v4-flash", "provider": "AIMLAPI", "cost_in": 0.14, "cost_out": 0.28,
                    "since": "2026-08-09 (bench §12.4)"},
        "why": "Aquí manda la CALIDAD, no el precio, y es por la forma del código: TODOS los grupos van en UNA "
               "llamada, con topes de 8 grupos × 12 recuerdos, una vez al día — el coste NO crece con el tamaño "
               "de la memoria. Todo el barrido cabía entre 0,14 y 2,17 dólares AL AÑO por usuario, así que "
               "optimizar precio aquí sería optimizar ruido. deepseek-v4-flash saca 97,8-99% y es el que mejor "
               "conserva nombres y cifras al resumir (98,4-100%), que es el dato que de verdad se puede perder.",
        "hallucination_note": "El titular anterior (gpt-4.1-mini) fallaba el eje que el bench viejo no medía: ante "
                              "un grupo de trivialidades («tomó un café», «se le olvidó dónde dejó las llaves») "
                              "SIEMPRE fabricaba un insight, 0% de aciertos en 3 pasadas — convertía un despiste "
                              "en un rasgo durable del operador. Callar cuando no hay patrón es parte de la tarea. "
                              "Los modelos más POTENTES (v4-pro, reasoner, gpt-4.1) NO mejoran: la tarea es "
                              "mecánica y razonar solo añade verbosidad.",
        "candidates_2026_07_26": [
            {"model": "grok-4-fast-non-reasoning", "cost_in": 0.20, "cost_out": 0.50, "status": "alternativa",
             "verdict": "fallback: mejor forma y el más barato, pero pierde algún nombre propio al sintetizar"},
            {"model": "deepseek-v4-pro", "cost_in": 0.435, "cost_out": 0.87, "status": "descartado",
             "verdict": "el DeepSeek potente NO mejora al flash (98,1%) y cuesta el triple"},
            {"model": "gpt-4.1-mini", "cost_in": 0.40, "cost_out": 1.60, "status": "descartado",
             "verdict": "titular hasta 2026-08-09; nunca devuelve null ante un grupo sin sustancia"},
            {"model": "gemini-2.5-flash / gpt-5-mini", "cost_in": 0.30, "cost_out": 2.50, "status": "descartado",
             "verdict": "no devuelven nada usable en esta tarea (validez 0%)"},
        ],
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
        "current": {"model": "openai/gpt-4.1-mini", "provider": "AIMLAPI", "cost_in": 0.40, "cost_out": 1.60,
                    "since": "2026-08-09 (movido al broker)"},
        "why": "El MODELO no se ha elegido con datos todavía — su benchmark sigue pendiente (§10 del doc denso). "
               "Lo que sí cambió el 2026-08-09 es el CAMINO: iba por OpenAI directo, una cuenta que en la nube no "
               "existe, así que allí habría fallado en silencio. Ahora va por el broker como todo lo demás, con el "
               "mismo modelo — ninguna calidad que re-medir.",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
    {
        "id": "i18n",
        "label": "Traducción del interfaz a un idioma nuevo",
        "role": "La primera vez que alguien habla un idioma que no viene de fábrica (solo inglés y castellano son "
                "PRESET), un modelo traduce los 514 textos del interfaz. Corre una vez por idioma, en la "
                "inicialización — nunca durante una conversación.",
        "current": {"model": "anthropic/claude-haiku-4.5", "provider": "AIMLAPI", "cost_in": 1.00, "cost_out": 5.00,
                    "since": "2026-08-09 (sonda §12.5)"},
        "why": "Aquí no manda el precio ni la calidad marginal, sino la FIABILIDAD: se paga UNA vez por idioma "
               "(11 lotes, unos 8 céntimos) y un lote que falle deja 50 textos del interfaz en inglés, sin una "
               "segunda pasada que lo arregle. Probado al tamaño real del lote (50 claves, 15 con variables) hacia "
               "japonés y árabe: haiku devuelve el 100% con las variables intactas en ambos, en 7-10 segundos.",
        "hallucination_note": None,
        "candidates_2026_07_26": [
            {"model": "gemini-2.5-flash", "cost_in": 0.30, "cost_out": 2.50, "status": "descartado",
             "verdict": "correcto casi siempre, pero una pasada de árabe devolvió 0 de 50 (respuesta cortada)"},
            {"model": "deepseek-v4-flash", "cost_in": 0.14, "cost_out": 0.28, "status": "descartado",
             "verdict": "acierta, pero razona: 6-8 veces más tokens de los que entrega y ~1 minuto por lote"},
        ],
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
               "con `tests/cluster/e2e/run_cluster_suite.py` — más rápido que la ruta AIMLAPI anterior.",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
]


def snapshot() -> dict:
    """Vista completa para el frontend — de solo lectura, nada de esto se guarda desde aquí."""
    return {"updated": UPDATED, "source_doc": SOURCE_DOC, "modules": MODULES}

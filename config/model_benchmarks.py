"""config/model_benchmarks.py — CURATED, user-visible replica of system model decisions (V2-077, 2026-07-26).
DETAILED source of truth: `.meshkore/docs/ops/zaelar-model-benchmarks.md` (internal, dense, with traces/incidents).
This module does NOT parse it — it is a manual summary, just like `web/src/pages/technology/` is a curated snapshot
of the internal architecture, not an automatic mirror. When touching a model decision (new routing, new benchmark,
discarded/adopted candidate), update BOTH the dense doc AND this summary — they are linked both ways (see the
header of `zaelar-model-benchmarks.md`).

Serves `GET /api/config/benchmarks` (server/config_api.py) → the "Want to see the benchmarks…?" button at the
bottom of the "Fast brain" section in the configuration area (frontend/app/components/BenchmarksPanel.js). Purely
informational — no POST, none of this is saved or applied; changing a real model happens in the normal configuration
sections (`/api/config/v2`)."""
from __future__ import annotations

UPDATED = "2026-08-13"
SOURCE_DOC = ".meshkore/docs/ops/zaelar-model-benchmarks.md"

MODULES = [
    {
        "id": "fast",
        "label": "Cerebro rápido · FlashBrain",
        "role": "Responde CADA turno de voz/chat en tiempo real: charla, tool-calling (mostrar/cerrar widgets, "
                "buscar, música, memoria, escalar) — nunca puede razonar (thinking OFF), el turno debe cerrar en "
                "~1-3s o la voz se queda muda.",
        "current": {"model": "deepseek/deepseek-v4-flash · non-thinking", "provider": "AIMLAPI", "cost_in": 0.14,
                    "cost_out": 0.28, "ttft_ms": 1170, "since": "2026-07-31 — sustituye al titular anterior"},
        "why": "CAMBIO 2026-07-31 (titular anterior → DeepSeek V4 Flash non-thinking): A/B robusto (tests/voice/e2e/agent/model_bench, 16 turnos "
               "inequívocos ×4 reps, mismo prompt+tools reales) → deepseek non-thinking ROUTING 10/10 (vs 8/10 del "
               "anterior, "
               "que INFRA-actuaba: no buscaba horarios ni añadía cita), INTEL 6/6 (tras acotar la regla 'insiste→"
               "ejecuta' que hacía sobre-actuar en meta/contradicción — fix flash/prompt.py 3bd8c29), TTFT p50 1170ms "
               "(vs 1821ms del anterior) y ~7x más barato. El MODO importa: v4-flash PIENSA por defecto (sobre-actúa, +latencia) "
               "→ fast_client fuerza thinking:disabled cuando el modelo es deepseek. El fallback de emergencia apunta al MISMO titular. "
               "[HISTÓRICO] A/B previo (grok-4-fast-non-reasoning): "
               "grok 'parecía tonto' — no buscaba cuando debía (alucinaba), no introspeccionaba su propia "
               "contradicción y reaccionaba con acciones espurias a preguntas meta. El titular de entonces buscaba fiable, "
               "explicaba en vez de actuar sobre dudas, a latencia comparable.",
        "hallucination_note": "Grok (xAI) SIGUE baneado en este puesto: en pruebas mezcla memoria↔widget_data y "
                               "responde 'Hecho' a preguntas que no eran órdenes — el fallo más caro en un cerebro "
                               "no-razonador es actuar con seguridad sobre un malentendido.",
        "candidates_2026_07_26": [
            {"model": "deepseek-v4-flash · NON-THINKING (AIMLAPI)", "cost_in": 0.14, "cost_out": 0.28,
             "tool_calling": "propio A/B 2026-07-31 (tests/voice/e2e/agent/model_bench, mismo prompt+tools reales): routing 4/5 y "
                             "🧠 INTEL 5/5 — IGUALA al titular anterior en inteligencia (no alucina, no actúa de más, resuelve "
                             "la contradicción). CLAVE: el modo importa — v4-flash PIENSA por defecto y en thinking "
                             "baja a 4/5 (sobre-actuó: abrió un widget en el turno de contradicción); con "
                             "thinking:disabled sube a 5/5.",
             "ttft_ms": "1683 (p50) vs 2222 del anterior → ~24% MÁS RÁPIDO al primer token; total p50 2331 vs 2676. "
                        "Nota: total con picos (5-6.6s) en algún turno verboso, pero TTFT —la métrica reina de "
                        "voz— es netamente mejor",
             "status": "★ CANDIDATO FUERTE para sustituir al titular: + rápido, MISMA inteligencia, ~mucho más barato. "
                        "fast_client ya fuerza thinking:disabled cuando el modelo del path rápido es deepseek "
                        "(voz=no-razonador). Pendiente: flip de config §fast + spot-check de voz REAL (el A/B son "
                        "10 turnos por un proxy AIMLAPI; una key DeepSeek directa daría el modelo más fresco y "
                        "menos hop). deepseek-v4-flash ES la última (snapshot 0731); no hay v4.x más nuevo.",
             "verdict": "recomendado sustituir al titular en non-thinking, tras spot-check de voz real"},
            {"model": "glm-4.5-air (Z.AI directo)", "cost_in": 0.20, "cost_out": 1.10,
             "tool_calling": "propio A/B 2026-07-26: 85/90 (94.4%) vs 87/90 (96.7%) del titular en el mismo arnés real "
                             "de 90 casos (tests/agent_headless/e2e/search/bot) — cerca, no empatado; falló 'hora en Tokio' "
                             "(el caso que SÍ arreglamos ese día) y 2 escalate→chat en tareas reales",
             "ttft_ms": "no medido de forma justa aún — el adaptador de hoy usa complete() no-streaming (el "
                        "canal de cluster no necesita streaming); comparar latencia real exige construir "
                        "streaming Z.AI primero, no solo tool-calling",
             "status": "prometedor a ~5x menos coste, pero NO listo para sustituir al titular todavía — brecha de "
                       "precisión real (no solo ruido) + falta soporte de streaming para el turno de voz",
             "verdict": "seguir evaluando: repetir con muestra mayor + construir streaming antes de decidir"},
            {"model": "qwen3-turbo/flash (Alibaba DashScope)", "cost_in": "0.05–0.19", "cost_out": "0.26–1.13",
             "tool_calling": "96.5% en eval independiente — el mejor medido", "ttft_ms": "2600–3000 (tier Plus, más lento que el titular)",
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
        "current": {"model": "deepseek/deepseek-v4-flash", "provider": "AIMLAPI", "cost_in": 0.40,
                    "cost_out": 1.60, "since": "2026-08-21 (norma sin OpenAI en defaults)"},
        "why": "El MODELO sigue sin elegirse con datos — su benchmark continúa pendiente (§10 del doc denso), y "
               "eso vale igual para el de ahora que para el de antes. El 2026-08-09 cambió el CAMINO: iba por "
               "OpenAI directo, una cuenta que en la nube no existe, así que allí habría fallado en silencio; "
               "pasó al broker con el mismo modelo. El 2026-08-21 cambió el MODELO: `openai/gpt-4.1-mini` no "
               "podía seguir siendo lo que corre por defecto (norma del operador, ya escrita en el escalón i18n "
               "de `memllm._FAILOVER`). Sigue en el CATÁLOGO para quien se autohospede y lo quiera: lo que la "
               "norma prohíbe es que corra sin que nadie lo elija, no que exista.",
        "hallucination_note": None,
        "candidates_2026_07_26": [],
    },
    {
        "id": "i18n",
        "label": "Traducción del interfaz a un idioma nuevo",
        "role": "La primera vez que alguien habla un idioma que no viene de fábrica (solo inglés y castellano son "
                "PRESET), un modelo traduce los 514 textos del interfaz. Corre una vez por idioma, en la "
                "inicialización — nunca durante una conversación.",
        "current": {"model": "deepseek-v4-pro", "provider": "DeepSeek (directo)", "cost_in": 0.28, "cost_out": 0.42,
                    "since": "2026-08-19 (norma del operador: DeepSeek V4 Pro y nada más)"},
        "why": "Aquí no manda el precio sino la FIABILIDAD: se paga UNA vez por idioma (11 lotes, unos céntimos) y "
               "un lote que falle deja 50 textos del interfaz en inglés, sin una segunda pasada que lo arregle. La "
               "sonda de agosto (§12.5) había descartado DeepSeek en esta tarea porque RAZONABA de más —6-8 veces "
               "los tokens que entregaba, 50-60 s por lote—, pero esa medición era del modelo FLASH servido por el "
               "BROKER, que es justo donde el interruptor de razonamiento se acepta y se ignora. Por el endpoint "
               "propio SÍ se obedece, así que el motivo del descarte desaparece con el cambio de endpoint. Si "
               "vuelve a razonar de más, se mide y se cambia con la medición delante.",
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
    {
        "id": "code_agent",
        "label": "Brain Workers (el trabajo largo: investigar, navegar, escribir código)",
        "role": "Cada tarea escalada es un worker headless que RAZONA con sus propias tools durante minutos, fuera "
                "del turno de voz. Son DOS decisiones, no una: quién CONDUCE (el CLI) y quién RAZONA (endpoint + "
                "modelo). Por eso se eligen como PRESET — moverlas por separado produce desajustes que no fallan al "
                "guardar, sino minutos después dentro de una tarea ya muerta.",
        "current": {"model": "glm-5.2 · conducido por Claude Code", "provider": "Z.AI (coding plan, suscripción)",
                    "cost_in": 1.40, "cost_out": 4.40,
                    "since": "2026-08-13 — el único de los tres PROBADO de punta a punta sobre una tarea real"},
        "why": "Banco serializado del 2026-08-13 sobre una tarea de varias piezas encadenadas (ferry + hotel + "
               "restaurante, con enlace y precio por pieza y obligación de marcar como PROVISIONAL lo no "
               "confirmado). Claude Code + Z.AI la completó: 12 min, 10 propuestas en la hoja de resultados, el "
               "ferry CONFIRMADO con fuente y lo no confirmable (horarios exactos, que viven en el motor de "
               "reservas) marcado como provisional en vez de inventado — que es justo el eje que distingue a un "
               "worker que investiga de uno que redacta algo plausible. Y lo hizo con la búsqueda web del relay "
               "AGOTADA: la cuota MCP de Z.AI estaba consumida, así que atacó las webs una a una con WebFetch, se "
               "comió 403 de DirectFerries/Booking/Baleària y siguió. Un candidato que solo funcione con la "
               "búsqueda buena no vale para producción.",
        "hallucination_note": "El eje de calidad aquí NO es la elocuencia: es si marca lo que no pudo confirmar. Un "
                              "worker que rellena un horario de ferry que no encontró produce una entrega que se ve "
                              "MEJOR y vale menos que nada, porque el operador la usaría para reservar.",
        "candidates_2026_07_26": [
            {"model": "grok-4.5 · conducido por Grok Build", "cost_in": 2.00, "cost_out": 6.00,
             "tool_calling": "El backend funciona (traduce su stream, usa los puentes, trae evidencia real de la "
                             "web_search propia de Zaelar y lee la memoria del operador — sacó su 4x4 sin que "
                             "nadie lo mencionara). Dos defectos del ADAPTADOR encontrados corriéndolo, no "
                             "leyéndolo: le faltaba `write` (sin con qué escribir su informe, rodeaba por la "
                             "terminal y la allowlist lo denegaba) y una denegación se le presenta como «User "
                             "cancelled the execution», que un modelo lee como que el humano lo abortó — así que "
                             "PARABA con entrega vacía tras haber trabajado bien. Ambos arreglados.",
             "ttft_ms": None,
             "status": "candidato REAL, con un hueco de capacidad conocido: Grok Build NO tiene `web_fetch` (su "
                        "catálogo se sondeó entero). Descubre páginas y no puede abrirlas — justo lo que hizo TODO "
                        "el trabajo en la corrida que sí terminó. Esa pata la dan los puentes (la web_search propia "
                        "y el navegador real), no el CLI.",
             "verdict": "en evaluación — el backend ya es correcto; lo que falta es una entrega completa medida"},
            {"model": "deepseek-v4-flash · conducido por Claude Code", "cost_in": 0.14,
             "cost_out": 0.28,
             "tool_calling": "SIN PROBAR — no hay ninguna DEEPSEEK_API_KEY en ningún store. Es el único de los tres "
                             "que sigue sin medir, y es 10 veces más barato que los otros dos, así que es el que "
                             "más interesa medir.",
             "status": "bloqueado por credencial",
             "verdict": "⚠️ su gateway NO mapea alias de Claude —creerlo dejó este escalón roto, 400 en cada "
                        "v4-pro), o sea que se le manda el alias de Claude, no un nombre de DeepSeek"},
            {"model": "gpt-5.5 · conducido por Codex", "cost_in": None, "cost_out": None,
             "tool_calling": "Verificado en vivo de punta a punta (13 consultas por el puente de memoria, fase y "
                             "progreso reportados, entrega con ok=true), pero su frontera de seguridad es DISTINTA: "
                             "Codex no tiene allowlist de comandos, solo modos de sandbox, y headless exige "
                             "workspace-write — o sea shell COMPLETO.",
             "status": "usable para trabajo normal, NUNCA para lo que existe para estar acotado",
             "verdict": "las tareas con entrada no confiable (deny_tools) o de dev de un peer se desvían a "
                        "claude_code aunque la config diga Codex — elegir Codex no puede costar las capacidades "
                        "de cluster, ni de forma visible ni invisible"},
        ],
    },
]


def snapshot() -> dict:
    """Full frontend view — read-only; none of this is saved from here."""
    return {"updated": UPDATED, "source_doc": SOURCE_DOC, "modules": MODULES}

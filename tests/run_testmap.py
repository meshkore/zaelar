"""EL MAPA DE TESTS — «¿funciona todo?» respondido por DOMINIO → CASO DE USO → CANAL (2026-07-25).

Petición del operador: que el testing esté tan ordenado que a "¿funciona todo bien?" se pueda responder
"1.1 ✅, 1.2 ✅, 2.1 ✅…". Este fichero es la ÚNICA fuente de verdad de esa taxonomía: cada nodo N.M declara qué
ficheros lo cubren, por qué CANAL entran (voz / chat-sobre-livekit / peer-de-cluster / http-api / unidad-directa) y
si es DETERMINISTA (pytest, corre en CI sin servidor) o VIVO (e2e, exige `make run` + proveedores reales).

Correr:
  ./.venv/bin/python tests/run_testmap.py                # todo lo DETERMINISTA (pytest), árbol numerado + veredicto
  ./.venv/bin/python tests/run_testmap.py --domain 1     # solo el dominio 1 (MEMORIA)
  ./.venv/bin/python tests/run_testmap.py --list         # solo listar la taxonomía (no ejecuta nada)
  ./.venv/bin/python tests/run_testmap.py --live         # incluye los nodos VIVOS (los lista + su comando; no los lanza)

La narrativa (canales, huecos conocidos, duplicación) vive en tests/TESTMAP.md — este fichero es el ejecutable.
Se EXTIENDE (1000→10000 casos) añadiendo ficheros a los nodos de abajo o nodos nuevos, no reescribiendo la espina.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── LA TAXONOMÍA ────────────────────────────────────────────────────────────────────────────────────────────────
# Cada nodo: (id, título, canal, ["ruta/pytest", ...] | comando-vivo). `live=True` = exige servidor vivo (no en CI).
# Canales: unit=unidad-directa · http=http-api · voice=voz(livekit) · chat=chat-sobre-livekit · peer=peer-de-cluster.
UNIT = "unit"; HTTP = "http"; VOICE = "voice"; CHAT = "chat"; PEER = "peer"

DOMAINS: list[dict] = [
    {"id": "1", "name": "MEMORIA", "nodes": [
        {"id": "1.1", "title": "BD y primitivas de estado", "ch": UNIT, "paths": [
            "tests/memory/unit/test_db.py", "tests/memory/unit/test_journal.py",
            "tests/memory/unit/test_graph.py", "tests/memory/unit/test_state.py",
            "tests/memory/unit/test_compose_state.py", "tests/memory/unit/test_bitemporal.py",
            "tests/memory/unit/test_memory_boundary.py"]},
        {"id": "1.2", "title": "Embeddings y recuperación (retriever+reranker)", "ch": UNIT, "paths": [
            "tests/memory/unit/test_embeddings.py", "tests/memory/unit/test_retriever.py",
            "tests/memory/integration/test_rerank.py", "tests/memory/unit/test_graph_ppr.py"]},
        {"id": "1.3", "title": "Escritura / ingest / destilador", "ch": UNIT, "paths": [
            "tests/memory/integration/test_memory_agent.py", "tests/memory/integration/test_writer_queue.py",
            "tests/memory/integration/test_write_precision_v2033.py",
            "tests/memory/integration/test_write_precision_v2050.py",
            "tests/memory/integration/test_write_changes_20260712.py",
            "tests/memory/integration/test_episodic.py", "tests/memory/integration/test_episodic_bytes.py",
            "tests/memory/unit/test_consolidator.py",
            "tests/memory/unit/test_distiller_tape.py"]},
        {"id": "1.4", "title": "Recall correcto (comportamiento, corpus)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v1 --next 10",
            "nested_events": True},
        {"id": "1.5", "title": "Sueño REM / síntesis", "ch": UNIT, "paths": ["tests/memory/unit/test_rem.py"]},
        {"id": "1.6", "title": "Bóveda y secretos", "ch": UNIT, "paths": [
            "tests/memory/unit/test_vault.py", "tests/memory/unit/test_vault_flow.py",
            "tests/memory/unit/test_vault_ingest.py", "tests/memory/unit/test_vault_rules.py",
            "tests/memory/unit/test_secrets.py", "tests/memory/unit/test_pill_slot.py",
            "tests/memory/unit/test_slots_audit.py", "tests/memory/unit/test_location_grounding.py",
            "tests/memory/unit/test_critical_health.py", "tests/memory/integration/test_seed_from_hermes.py"]},
        {"id": "1.7", "title": "API HTTP de memoria", "ch": HTTP, "paths": [
            "tests/memory/integration/test_api.py", "tests/memory/integration/test_vault_api.py",
            "tests/memory/e2e/test_server_api.py"]},
        {"id": "1.8", "title": "Contexto de UI en el estado", "ch": UNIT, "paths": [
            "tests/memory/integration/test_ui_context.py"]},
    ]},
    {"id": "2", "name": "FLASHBRAIN (nucleo)", "nodes": [
        {"id": "2.1", "title": "Enrutado / elección de tool", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_router.py", "tests/agent_headless/unit/flash/test_music_flow.py", "tests/agent_headless/unit/test_account_routing.py"]},
        {"id": "2.2", "title": "Bucle de diálogo y anti-degeneración", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_dialog.py", "tests/agent_headless/unit/test_loop.py",
            # veredicto de latencia del turno: prompt grande vs proveedor vs frío vs trabajo real
            "tests/agent_headless/unit/test_turn_perf.py",
            # el recall no busca por una nota [SISTEMA] antepuesta (2026-08-17, alucinación de un familiar)
            "tests/agent_headless/unit/flash/test_probe_recall_notes.py",
            # un turno de charla pura que vuelve MUDO (sin tool, sin texto) dice algo con sentido en vez de
            # callar — sin esto el turno siguiente acababa ecoando la propia pregunta del operador (2026-08-17)
            "tests/agent_headless/unit/flash/test_probe_never_mute.py"]},
        {"id": "2.3", "title": "Prompt / skeleton / chispas", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_prompt.py", "tests/agent_headless/unit/test_skeleton.py", "tests/agent_headless/unit/test_sparks.py"]},
        {"id": "2.4", "title": "Cliente LLM rápido, reintento y RELEVO por latencia", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_fast_client.py", "tests/agent_headless/unit/flash/test_fast_client_retry.py",
            "tests/agent_headless/unit/flash/test_procs.py",
            # V2-094 (2026-08-14): la cadena de proveedores existía desde agosto pero solo para el cerebro de
            # CLUSTER y solo relevaba por proveedor ROTO (429/cuota). El fallo que el operador vive es el proveedor
            # LENTO — TTFT de 25 s con el prompt constante — y no había a dónde ir. Aquí se fija la política, que
            # es donde está el riesgo de gastar dinero sin querer: racha de lentos, cooldown corto, TECHO de turnos
            # en el escalón caro, y self-host SIN relevo de fábrica.
            "tests/agent_headless/unit/flash/test_voice_failover.py"]},
        {"id": "2.5", "title": "Escalado / dispatch / workers", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_escalate.py", "tests/agent_headless/unit/test_dispatch.py", "tests/agent_headless/unit/workers/test_workers.py",
            "tests/agent_headless/unit/agentes/test_agentes.py", "tests/agent_headless/unit/agentes/test_work_agents.py",
            # las 3 decisiones que hundieron la sesión del 2026-08-02 (llenar≠programar · confirm-gate sobre una
            # investigación · la frase del operador perdida al pisarse los turnos del STT)
            "tests/agent_headless/unit/test_search_report_flow.py",
            # el worker se ve trabajar desde el primer segundo (narración → observabilidad, nunca voz)
            "tests/agent_headless/unit/workers/test_worker_narration.py",
            # el worker puede llamar a sus puentes a la primera (intérprete real + allowlist completo)
            "tests/agent_headless/unit/workers/test_bridge_interpreter.py",
            # cadena de proveedores del worker + relevo por cuota agotada + alerta en el panel
            "tests/agent_headless/unit/workers/test_provider_failover.py",
            # el contexto del worker: cwd propio (el motor no le mete su CLAUDE.md), vigía que le pide entregar antes
            # del techo, «compactar y continuar» al desbordarse, y NUNCA un error crudo del proveedor como informe
            "tests/agent_headless/unit/workers/test_context_budget.py",
            # el OTRO backend (Codex): traducción de su JSONL a WorkerEvent con trazas REALES del CLI + la postura
            # FAIL-CLOSED — Codex no sabe acotar sus tools, así que rechaza justo las tareas que existen acotadas
            # (entrada no confiable, dev worker de cluster) en vez de correr con menos contención de la pedida
            "tests/agent_headless/unit/workers/test_codex_session.py",
            # y el TERCER backend (Grok Build): mismo wire format que Claude Code → hereda el traductor; se prueba
            # que la herencia aguante y las 3 diferencias reales (nombres de tools, sus argumentos, el envoltorio de
            # su evidencia) + que el prompt vaya por fichero (`-p -` no lee stdin: avería cara y MUDA)
            "tests/agent_headless/unit/workers/test_grok_session.py",
            # DIRECCIÓN de una investigación (2026-08-09): el brief que convierte «las mejores vacaciones» en una
            # selección defendible — amplitud mínima de candidatos, criterios duros vs blandos, baremo de calidad,
            # y la ronda 2 cuando el operador dice que siga buscando. Sin esto el worker se autoimponía el criterio
            # mínimo y devolvía los tres primeros resultados de la primera página.
            "tests/agent_headless/unit/test_research.py",
            # REHIDRATACIÓN (2026-08-12): un reinicio en mitad de una búsqueda del operador se la llevó por delante
            # sin dejar rastro — ni evento, ni ledger, ni aviso. Aquí se fija qué se reanuda solo, qué se reporta y
            # por qué, y que un reset NO resucite el trabajo que el operador acaba de mandar parar.
            "tests/agent_headless/unit/test_rehydrate.py",
            # V2-092 — el INTERRUPTOR GLOBAL (⏻). Su estado vivía solo en el localStorage, así que el backend no
            # sabía que el operador había parado: seguían los ciclos de background, los crons y la reproducción de
            # los widgets. Se fija la POLÍTICA, que es lo que se pierde en una refactorización: parar congela a
            # TODOS y persiste; arrancar continúa el TRABAJO pero NO reanuda la música (asimetría pedida por el
            # operador); y un fallo de una pieza no puede dejar la parada a medias.
            "tests/agent_headless/unit/test_runstate.py"]},
        {"id": "2.6", "title": "Scheduler / rails / workspace / frontend-glue", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_scheduler.py", "tests/agent_headless/unit/test_rails.py", "tests/agent_headless/unit/test_workspace.py",
            "tests/agent_headless/unit/flash/test_frontend.py", "tests/agent_headless/unit/flash/test_memory_cache.py"]},
        {"id": "2.7", "title": "Susurro (auto-reparación)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/susurro/test_susurro.py",
            "tests/agent_headless/unit/susurro/test_phantom_dataop.py"]},
        {"id": "2.8", "title": "Búsqueda web (comportamiento)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/agent_headless/e2e/search/bot/runner.py"},
        # Coste/latencia del PROMPT del turno, medido contra el modelo vivo. Responde con números —no con
        # opinión— a «¿cuánto pesan las tools?» y «¿compensa partir el turno en dos peticiones?».
        {"id": "2.12", "title": "Coste del prompt: tools, dos-pasadas vs una, catálogo compacto", "ch": UNIT,
            "live": True,
            "cmd": "./.venv/bin/python -m tests.agent_headless.e2e.prompt_cost.bench_tools"},
        # ¿Qué modelo rápido aguanta el turno de voz? Mide latencia, enrutado y ráfaga en paralelo contra el
        # prompt REAL (compuesto con `prompt.build_flash_system`, no una maqueta). Repásalo al cambiar de modelo
        # o de proveedor: es el que demostró que el candidato veloz de turno enruta peor que el que ya está.
        {"id": "2.13", "title": "Modelo rápido: latencia + enrutado + paralelo (prompt real)", "ch": UNIT,
            "live": True,
            "cmd": "./.venv/bin/python -m tests.agent_headless.e2e.prompt_cost.bench_fast_model"},
        # 2026-08-14: un turno CANCELADO (38 de 54 en la sesión b70a45d0) ya se le pidió al proveedor y ya se pagó,
        # pero su `usage` real viaja en el ÚLTIMO chunk del stream y nunca llega → lo factura un ESTIMADO. Este nodo
        # fija las dos ramas (cancelado→estimado, completo→verdad del proveedor) y la DENSIDAD del estimado, que
        # asumía 4 chars/token (inglés) cuando el input real va a 3,36 y cobraba un 16% de menos.
        {"id": "2.14", "title": "Un turno CANCELADO también se factura (y con el estimado bien calibrado)",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/flash/test_cancelled_turn_billing.py"]},
        {"id": "2.9", "title": "Sandbox de ejecución ligero (V2-076)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_sandbox.py"]},
        {"id": "2.10", "title": "Puente git acotado + dev worker (V2-076)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_git_cli.py", "tests/agent_headless/unit/test_dev_worker.py",
            "tests/agent_headless/unit/test_dev_worker_guard.py"]},
        {"id": "2.11", "title": "Conversación sintética + juez", "ch": CHAT, "live": True,
            "cmd": "./.venv/bin/python -m tests.agent_headless.harness.run"},
    ]},
    {"id": "3", "name": "VOZ", "nodes": [
        {"id": "3.1", "title": "Atención / VAD / endpointing", "ch": VOICE, "paths": [
            "tests/voice/unit/test_attention.py", "tests/voice/unit/test_endpointing.py",
            "tests/voice/unit/test_turn_boundaries.py"]},
        {"id": "3.2", "title": "Puente voz→nucleo + trazas", "ch": VOICE, "paths": [
            "tests/voice/unit/providers/test_nucleo.py", "tests/voice/unit/providers/test_nucleo_guards.py",
            # 2026-08-14 (sesión b70a45d0): los dos eslabones que dejaron la agenda sin vaciar. (1) El backstop de
            # promesa escalaba con `kind:"web"` FIJO → una data-op local abrió dos navegadores y pasó a llamarse
            # «la tarea del navegador»; (2) ese nombre hizo que un `stop_worker` arrastrado del turno anterior la
            # encontrara y la matara EN EL MISMO turno en que se le entregaba la autorización que esperaba.
            "tests/voice/unit/providers/test_stop_and_route_guards.py",
            # V2-109 (2026-08-17): evaluate_content()'s directed-vs-ambient judge got `brain._last_spoken` as
            # context, which a lead-in filler ("Pues…") overwrites — a real follow-up question asked right after
            # a filler got classified `ambiente` with zero topic to judge against. New `_last_reply` field, filler
            # path never touches it.
            "tests/voice/unit/providers/test_nucleo_directed_context.py",
            # V2-108 cont. modularization pass (2026-08-17): vault_intercept.py split out of `_run_inner`'s
            # security-config-command + spoken-secret intercept — first standalone unit coverage for this path.
            "tests/voice/unit/providers/test_vault_intercept.py",
            "tests/voice/unit/test_trace.py", "tests/voice/e2e/agent/interlocutor/test_trace.py"]},
        {"id": "3.3", "title": "Mic→STT (transporte WebRTC)", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.mic.mic_selftest"},
        {"id": "3.4", "title": "Bucle de voz completo", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.agent.smoke"},
        {"id": "3.5", "title": "Escenarios voz/chat/paste + juez", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.agent.run --no-open --hold 0"},
        # 2026-08-09: el defecto del producto es INGLÉS y, mientras no hay idioma elegido, el STT transcribe en
        # AUTO — sin eso la autodetección de la 1ª frase clasificaba texto ya transcrito por el modelo equivocado
        # (y en el perfil de NUBE, el de producción, no funcionaba en absoluto).
        {"id": "3.6", "title": "Arranque idiomático: defecto inglés + STT en auto en primera ejecución",
            "ch": VOICE, "paths": ["tests/voice/unit/test_language_bootstrap.py"]},
        # V2-093 (2026-08-14): el relleno de espera («Mmm…», «A ver…») llevaba desde julio SIN SONAR NUNCA. Viajaba
        # por el stream del modelo, y el tokenizador de frases de LiveKit solo entrega un segmento cuando tiene DOS
        # → un relleno suelto (sin punto y de menos de 20 chars) se quedaba en el buffer y salía PEGADO a la
        # respuesta. 48 generados, 0 oídos a tiempo, y el operador diciéndole «parece que te has quedado tonto» a un
        # agente que estaba trabajando. Aquí se reproduce el pegado y se fija la costura fuera de banda.
        {"id": "3.7", "title": "Relleno de espera: suena MIENTRAS se espera (fuera del stream del modelo)",
            "ch": VOICE, "paths": ["tests/voice/unit/test_lead_in.py",
                                    # V2-122 (2026-08-17): el pool de rellenos ya no es solo un literal hardcodeado
                                    # — pick_filler() mira PRIMERO un pack generado por idioma antes de caer al
                                    # catálogo es/en; este test file nuevo cubre esa ruta de lectura.
                                    "tests/voice/unit/test_lang_fillers_store.py"]},
        # V2-095 (2026-08-14): el límite del turno era SOLO acústico, así que un operador que piensa en voz alta
        # abría un turno por pausa y el siguiente fragmento lo cancelaba — 22 prompts, 18 cancelados y CERO
        # respuestas en 161 s de dictado. El corpus del test son las 89 transcripciones REALES de esa sesión: la
        # regla léxica reconoce 43 como incompletas (48% de llamadas evitadas) con CERO falsos positivos sobre las
        # órdenes cortas, que es lo único que no se puede retener.
        # `test_segmenter_corpus.py` es el MISMO contrato medido contra las 195 sesiones del registro LOCAL (804
        # transcripciones) en vez de contra una sola: una regla afinada sobre una sesión está ajustada a esa sesión,
        # y así se cazó que «Y que lo pares todo.» se RETENÍA (acaba en «todo»), justo lo que V2-092 prohíbe. Se
        # SALTA en un clon limpio — el registro es del operador y no se publica (ver el docstring).
        {"id": "3.8", "title": "Turnos por SENTIDO: la frase se cierra cuando está acabada, no cuando hay silencio",
            "ch": VOICE, "paths": ["tests/voice/unit/test_segmenter.py",
                                   "tests/voice/unit/test_segmenter_corpus.py"]},
        # V2-096 (2026-08-14): V2-095 resolvía esto RETRASANDO el turno, o sea con un TIEMPO FIJO — y medido sobre
        # 372 pausas reales del registro el `max_delay` de 2,2 s solo cubría el 48,7% (p50 2,3 s · p90 4,9 s · max
        # 19,5 s). Acumular el trozo saca el reloj de la ecuación: la pausa dura lo que quiera porque lo que se juzga
        # son los trozos JUNTOS (156 frases recompuestas sobre 79 cadenas reales). Los tres primeros tests son de
        # SEGURIDAD (una orden de parar o una autorización tragadas serían peores que el bug que arregla) y uno
        # documenta a propósito el límite del léxico: no ve que falte el OBJETO («quiero que busques»).
        {"id": "3.10", "title": "Selección PROGRESIVA de tools: el turno lleva su rumbo, no el catálogo entero",
            "ch": VOICE, "paths": ["tests/voice/unit/test_tool_selection.py"]},
        {"id": "3.9", "title": "Frase partida en dos tiempos = UNA petición (el fragmento no genera nada)",
            "ch": VOICE, "paths": ["tests/voice/unit/test_accumulator.py"]},
    ]},
    {"id": "4", "name": "WIDGETS", "nodes": [
        {"id": "4.1", "title": "Ciclo de vida / acciones / refs / generador / background", "ch": UNIT, "paths": [
            "tests/browser/unit/widgets/test_lifecycle_confirm.py", "tests/browser/unit/widgets/test_actions.py", "tests/browser/unit/widgets/test_refs.py",
            "tests/browser/unit/widgets/test_generator_sync.py", "tests/browser/unit/widgets/test_background.py",
            "tests/browser/unit/widgets/test_aliases.py", "tests/browser/unit/widgets/test_identify_context.py",
            "tests/browser/unit/widgets/test_resolver_certainty.py", "tests/browser/unit/widgets/test_system_surfaces_sync.py"]},
        {"id": "4.2", "title": "Navegador (browser)", "ch": UNIT, "paths": [
            "tests/browser/unit/navegador/test_auth.py", "tests/browser/unit/navegador/test_tasks_dedup.py",
            # 2026-08-17 modularization pass: DOM/human-input primitives split out of owner.py into dom.py
            # (page-parametric, no module-global coupling) -- first standalone coverage for this path, plus a
            # regression lock on `mouse` now being required (the old None-fallback was dead code).
            "tests/browser/unit/navegador/test_dom.py"]},
        {"id": "4.3", "title": "Widget de música", "ch": UNIT, "paths": ["tests/browser/unit/musica/test_data.py"]},
        {"id": "4.4", "title": "Widget de YouTube", "ch": UNIT, "paths": ["tests/browser/unit/youtube/test_youtube.py"]},
        {"id": "4.5", "title": "Widget de mensajería", "ch": UNIT, "paths": ["tests/browser/unit/mensajeria/test_owner_v2.py"]},
        {"id": "4.6", "title": "Agenda: contrato XSS del renderer", "ch": UNIT, "paths": [
            "tests/browser/unit/agenda/test_xss_contract.py"]},
        # V2-085 — la garantía de ESCALA: el prompt es O(K) y no O(N) por muchos widgets que haya. Nodo propio (no
        # dentro de 4.1) porque lo que prueba no es el contrato de UN widget sino el del CATÁLOGO: sintéticos de
        # 100/1.000/10.000, promoción del widget nombrado desde la cola, e índice compacto del endpoint.
        {"id": "4.7", "title": "Selección progresiva del catálogo (escala 100/1k/10k)", "ch": UNIT, "paths": [
            "tests/browser/unit/widgets/test_selection_scale.py"]},
        # Contrato de la 4ª pestaña NATIVA «Clusters» (V2-086). Va en WIDGETS/superficies —no en CLUSTER— porque
        # lo que fija es la UI y su contrato de datos; la lógica de red vive en 6.9.
        {"id": "4.8", "title": "Pestaña nativa «Clusters» (contrato UI ↔ ruteo ↔ backend, V2-086)", "ch": UNIT,
            "paths": ["tests/browser/unit/widgets/test_clusters_tab.py"]},
        # V2-088: el chat es una VISTA, no un modo. Estos tests impiden que alguien vuelva a cablear el panel
        # con el altavoz — el acoplamiento anterior era indistinguible de un TTS averiado.
        {"id": "4.9", "title": "Chat y voz INDEPENDIENTES (el icono es el único dueño del silencio, V2-088)",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_chat_voice_independent.py"]},
        # 2026-08-02: «busca X y ponme el informe en pantalla» no llegaba NUNCA a pantalla. Nodo propio porque lo
        # que fija no es un widget temático sino la SUPERFICIE GENÉRICA de presentación: hoja en blanco sin
        # contenido propio, se rellena por acción declarada (no reescribiendo su código) y lo entregado PERSISTE.
        # 2026-08-09: además de la hoja en blanco, la superficie sostiene PROPUESTAS COMPUESTAS (un plan = varias
        # piezas con su propio precio/enlace/horarios) y su SEGUNDA PÁGINA de detalle; y el canal por el que se
        # llenan en vivo tenía que dejar de depender de la sesión de voz (sin micro o con la voz parada, la tarjeta
        # se quedaba congelada en su primer render sin ningún síntoma).
        {"id": "4.10", "title": "Superficie genérica de presentación de resultados (hoja en blanco + present/append "
                                "+ propuestas compuestas + detalle + refresco en vivo sin voz)",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_results_presentation.py",
                                  "tests/browser/unit/widgets/test_live_updates_independent_of_voice.py",
                                  "tests/browser/unit/widgets/test_presentation_quality.py"]},
        # 2026-08-12: el operador recargó con una búsqueda en marcha y el escritorio se quedó EN BLANCO. La tarjeta
        # del navegador estaba excluida del guardado por nombre —la única, y justo la que se ve durante una tarea
        # web— y el único almacén era el localStorage, que es per-origen y per-navegador. El escritorio ahora se
        # rehidrata, y Procesos deja de pintar con un ✓ lo que un reinicio cortó a medias.
        {"id": "4.13", "title": "Rehidratación del escritorio (tarjetas + posiciones tras recargar o cambiar de "
                                "navegador) · «interrumpido» visible en Procesos",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_desktop_rehydrate.py"]},
        # 2026-08-12: tras un reset, la hoja de resultados sacó ENTERA la búsqueda anterior mientras el worker de la
        # nueva trabajaba — el reset cerraba las tarjetas pero no vaciaba sus DATOS. Aquí van las dos mitades: lo
        # derivado se vacía y el registro del operador (agenda, credenciales, perfil del navegador) NO; y el worker
        # llena la hoja MIENTRAS trabaja en vez de solo al final.
        {"id": "4.14", "title": "Reset = superficies EN BLANCO (sin borrar el registro del operador) · la hoja se "
                                "llena mientras el worker trabaja",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_reset_blank_surfaces.py"]},
        # 2026-08-10: el operador estuvo hablándole a un agente MUERTO porque los iconos seguían azules y el ECG
        # latía (lo late el servidor, no el agente). El estado del agente pasa a ser UNA verdad derivada y todo lo
        # que se ve deriva de ella; «parado» significa congelado de verdad y a la vista. Incluye el vúmetro del
        # icono del micro, para saber que se te está escuchando sin medidor aparte.
        {"id": "4.12", "title": "Estado del agente: una sola verdad · parado = congelado (real y visible) · vúmetro",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_agent_state_freeze.py"]},
        # i18n de la UI (V2-089). Estaba SIN mapear: `test_bundles.py` guarda los presets (mismas claves en/es,
        # español no vacío, placeholders alineados) y `test_bundle_reactivity.py` el contrato RUNTIME —
        # `t()` re-renderiza cuando el bundle gana claves, no solo cuando cambia el idioma (fallo 2026-08-09:
        # los rótulos nuevos del visor salían como su clave cruda porque `setLang` al mismo valor es no-op).
        {"id": "4.11", "title": "i18n de la UI: presets alineados + t() reactivo al CONTENIDO del bundle",
            "ch": UNIT, "paths": ["tests/browser/unit/i18n/test_bundles.py",
                                  "tests/browser/unit/i18n/test_bundle_reactivity.py"]},
        # LA PILA de Energy (2026-08-13). El operador se quedó sin energía a mitad de trabajo y se enteró por un
        # cartel, sin haber visto nunca cuánta le quedaba. Aquí se guarda la ESCALA —huecos fijos y valor por
        # rayita variable, con el color atado a la CAPACIDAD y no al saldo para que no cambie mientras gastas—
        # con los casos que dio él: demo 10, cuota $10 → 10 de un dólar, $50 → los 50, $100 → 50 de dos dólares,
        # techo en $250. Es pura, así que falla sola y sin navegador.
        {"id": "4.15", "title": "Pila de Energy: la escala (huecos fijos · valor por rayita · color por capacidad)",
            "ch": UNIT, "paths": ["tests/browser/unit/energy/test_energy_scale.py"]},
        # V2-092 — PARAR ES PARAR. El operador vio, con el agente parado: un vídeo reproduciéndose, que volvía a
        # arrancar al RECARGAR, y sonando encima de la música. Lo que faltaba no era un `if` para YouTube sino un
        # CONTRATO declarable (`runtime` del manifest) del que salen la parada global, la exclusividad del altavoz
        # y la puerta del agente parado — para cualquier widget, incluidos los que genera el agente mañana. Este
        # nodo cubre el lado del canvas; el interruptor global es el 3.x de workers (test_runstate.py).
        {"id": "4.16", "title": "Widgets que PRODUCEN: parada global · un solo dueño del altavoz · nada arranca con "
                                "el agente parado", "ch": UNIT,
            "paths": ["tests/browser/unit/widgets/test_producers.py"]},
        # 2026-08-18 (V2-116): el muro de chat solo se alimentaba del `transcript` de LiveKit, que no llega hasta
        # que el TTS ha terminado de hablar la respuesta ENTERA — 5,4 s y 12,2 s medidos en una sesión real, y el
        # operador lo vivió como «la he oído por voz y el texto llegó un minuto después». La respuesta se pinta
        # ahora al generarse y el transcript posterior se funde por PREFIJO (que es también lo que hace bien el
        # caso del barge-in, donde el transcript llega truncado).
        {"id": "4.17", "title": "El muro de chat no espera a la voz (y el transcript posterior no duplica)",
            "ch": UNIT, "paths": ["tests/browser/unit/chat/test_chat_wall_promptness.py"]},
        # V2-124: el shell MÓVIL (PWA) es un SEGUNDO host de los dos contratos que ya hablaban `services/sse.js` y
        # cada widget. El riesgo no es que hoy funcione —funciona— sino que alguien añada un método al protocolo de
        # host, o renombre uno, y el ESCRITORIO siga verde porque tiene su propio host: el fallo saldría en el
        # teléfono, en silencio, ignorando al cerebro. El test DERIVA lo que exige del propio código (los métodos
        # que sse.js llama, las rutas que el backend declara), nunca de una lista copiada a mano.
        {"id": "4.18", "title": "Shell MÓVIL: contrato de host + del widget · paleta compartida · el service worker "
                                "no cachea", "ch": UNIT,
            "paths": ["tests/browser/unit/mobile/test_mobile_host_contract.py"]},
    ]},
    {"id": "5", "name": "CONECTORES", "nodes": [
        {"id": "5.1", "title": "Email", "ch": UNIT, "paths": [
            "tests/connectors/unit/email/test_mailbox.py", "tests/connectors/unit/email/test_oauth.py",
            "tests/connectors/unit/email/test_providers.py"]},
        {"id": "5.2", "title": "Mensajería (ingest/reply)", "ch": UNIT, "paths": [
            "tests/connectors/unit/messaging/test_ingest.py", "tests/connectors/unit/messaging/test_reply.py",
            "tests/connectors/unit/messaging/test_memory_dump.py"]},
        {"id": "5.3", "title": "Música / Spotify / YouTube-audio", "ch": UNIT, "paths": [
            "tests/connectors/unit/music/test_music.py", "tests/connectors/unit/music/test_youtube_audio.py",
            "tests/connectors/unit/spotify/test_auth.py", "tests/connectors/unit/spotify/test_provider.py"]},
        {"id": "5.4", "title": "Architect", "ch": UNIT, "paths": ["tests/connectors/unit/architect/test_architect.py"]},
        {"id": "5.5", "title": "WhatsApp: normalización y allowlist", "ch": UNIT, "paths": [
            "tests/connectors/unit/whatsapp/test_allowlist_contract.py"]},
    ]},
    {"id": "6", "name": "CLUSTER (meshkore)", "nodes": [
        {"id": "6.1", "title": "Cápsula / framing (una sola mente)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_capsule.py", "tests/cluster/unit/test_capsule_flow.py"]},
        {"id": "6.2", "title": "Seguridad del canal", "ch": PEER, "paths": ["tests/cluster/unit/test_security.py"]},
        {"id": "6.3", "title": "Ingesta cluster→memoria", "ch": PEER, "paths": [
            "tests/cluster/unit/test_mem_ingest.py"]},
        {"id": "6.5", "title": "Protección de recursos (balance/anti-offload, V2-071)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_resource.py"]},
        {"id": "6.6", "title": "Pacto de conversación agente-agente (reglas negociadas, V2-072)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_pact.py"]},
        {"id": "6.7", "title": "Criterio de conversación por INTELIGENCIA (evaluador modelo, genérico, V2-075)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_pace.py"]},
        {"id": "6.8", "title": "Permisos por-cluster + contrato de catálogo (V2-076)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_perms.py"]},
        {"id": "6.9", "title": "Clusters PÚBLICOS (tokenless) + red como superficie nativa (V2-086)", "ch": PEER,
            "paths": ["tests/cluster/unit/test_public_cluster.py"]},
        {"id": "6.4", "title": "Conversación con peer (comportamiento)", "ch": PEER, "live": True,
            "cmd": "./.venv/bin/python tests/cluster/e2e/run_cluster_suite.py"},
    ]},
    {"id": "7", "name": "SERVER / OBSERVABILIDAD", "nodes": [
        {"id": "7.1", "title": "Bus de eventos y log", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/test_bus.py", "tests/infrastructure/unit/test_bus_log.py",
            "tests/platform/tests/test_events.py", "tests/platform/tests/test_catalog.py",
            "tests/platform/tests/test_pytest_plugin.py"]},
        {"id": "7.2", "title": "Observer SSE", "ch": HTTP, "paths": [
            "tests/infrastructure/integration/test_sse_observer.py", "tests/infrastructure/unit/test_zai_sse.py"]},
        # 2026-08-10: un RESET deliberado abre una SESIÓN DE TRABAJO NUEVA (id nuevo + observabilidad a cero). Antes
        # vaciaba el log pero NO rotaba el id, así que lo de después seguía colgando de la sesión vieja. El test
        # también guarda el contrapeso: una RECONEXIÓN no es una sesión nueva.
        # OJO: este nodo nació como «7.6» y COLISIONABA con el inventario de categorías, que también era 7.6 —
        # el mapa es la respuesta a «¿funciona todo bien?», así que dos nodos con el mismo número hacen que uno se
        # cuente dos veces y el otro no exista. Renumerado a 7.8 (2026-08-10).
        {"id": "7.8", "title": "Sesión de trabajo: el reset abre una NUEVA (id nuevo, observabilidad a cero)",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_session_rotation.py"]},
        {"id": "7.5", "title": "Sello de versión (instancia + observabilidad, V2-074)", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/test_version.py"]},
        # 2026-08-09: el filtro del visor solo es fiable si TODO kind emitido pertenece a una familia. El test
        # recorre el código y falla si alguien estrena un kind sin clasificarlo (el operador veía filas que
        # ningún chip gobernaba).
        {"id": "7.6", "title": "Inventario de categorías del visor (ningún kind sin familia)", "ch": UNIT,
            "paths": ["tests/infrastructure/unit/core/test_observer_categories.py"]},
        # INI-021 (2026-08-09): la observabilidad pasa de «ver líneas» a «analizar procesos». Un estímulo y todo
        # lo que desencadena comparten CORRELATION ID; cada evento dice de qué instalación y de qué sesión de
        # trabajo salió; y todo eso es consultable por columnas indexadas, no escaneando JSON.
        {"id": "7.7", "title": "Flujos por correlation ID + identidad de instalación + sesión de trabajo",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_observability_flows.py"]},
        # 2026-08-12: por la RAÍZ del repo se escapó información personal del operador a un repo PÚBLICO — un
        # borrador de Brain Worker (`informe.json`) acabó versionado dos veces. El guarda no mira nombres: mira que
        # en la raíz no se versione nada que no sea del proyecto, se llame como se llame.
        {"id": "7.9", "title": "La raíz del repo no versiona datos (fuga de PII, 2026-08-12)", "ch": UNIT,
            "paths": ["tests/infrastructure/unit/test_repo_root_clean.py"]},
        # 2026-08-14: que el CONTEXTO no se quede atrás del código. La deriva era medible — el log de alineación de
        # contenido iba por la 2.88 con el motor en la 2.94, y 21 decisiones de CLAUDE.md sin iniciativa. Este nodo
        # es la mitad AUTOMÁTICA del cierre (ids únicos, frontmatter cuadrado, decisión↔iniciativa en los dos
        # sentidos), como TRINQUETE: la deuda histórica está declarada y solo puede bajar. La mitad que cruza a
        # `web/` no se puede vigilar desde aquí (vive en el repo privado) → `zaelar-initiative-closure.md`.
        {"id": "7.12", "title": "Cierre de iniciativa: toda decisión tiene iniciativa y al revés (trinquete)",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/test_roadmap_closure.py"]},
        # 2026-08-10: un guarda SOBRE LOS GUARDAS. Aparecieron tests verdes por la MÁQUINA y no por el código (la
        # config del operador —idioma, proveedores, atención, perfil— pisaba el entorno de la suite vía
        # `settings.load_into_env`). No es que fallaran: es que no se podía confiar en el verde.
        {"id": "7.10", "title": "Aislamiento de la suite (la máquina del que corre no decide el resultado)",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/test_suite_isolation.py"]},
        # 2026-08-13: el middleware de routing servía en LAS CUATRO ramas de rechazo (sin cookie, sin
        # config, lookup caído, token no reconocido). No era una debilidad teórica: una GET anónima al
        # hostname compartido devolvía datos de un inquilino. Estos casos fijan las cuatro cerradas y,
        # a la vez, lo que NO puede cerrarse (shell, assets, sonda de vida — cerrar la sonda deja al
        # proceso sin tráfico).
        {"id": "7.11", "title": "Admisión de peticiones: sin sesión verificada no se sirve nada",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_ingress.py",
                                  "tests/agent_headless/unit/test_account_routing.py"]},
        {"id": "7.3", "title": "Chat por transporte LiveKit REAL", "ch": CHAT, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_chat_over_livekit.py"},
        {"id": "7.4", "title": "Smoke INTEGRAL de salud", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py"},
        # 2026-08-15 (V2-092 addenda): la sesión de trabajo se cierra por techo de INACTIVIDAD REAL (el ruido de
        # fondo no cuenta ni para el reloj ni, desde este cambio, para reabrir una sesión que se acaba de cerrar
        # — hallazgo real: el propio evento "end" resucitaba una sesión nueva en el acto) y se anuncia al
        # control-plane con un LATIDO periódico mientras siga abierta (reemplaza la adivinanza-por-ruido de la
        # nube por una señal pensada para esto). Este nodo faltaba del mapa — ninguno de los dos ficheros estaba
        # registrado — así que "tests run infrastructure" nunca los ejecutaba pese a existir.
        {"id": "7.13", "title": "Sesión de trabajo: cierre por inactividad real + latido hacia el control-plane",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_session_idle_rollover.py",
                                  "tests/infrastructure/unit/core/test_session_heartbeat.py"]},
    ]},
    {"id": "8", "name": "ENERGÍA / CONFIG", "nodes": [
        {"id": "8.1", "title": "Medidor de energía y límites de cuenta", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_meter.py", "tests/infrastructure/unit/core/test_account_limits.py", "tests/infrastructure/unit/config/test_balances.py"]},
        {"id": "8.1b", "title": "Cobertura de Energy: nadie gasta fuera del contador", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_coverage.py"]},
        {"id": "8.1c", "title": "Arriendo de energía: techo local y fusible", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_lease.py"]},
        {"id": "8.1d", "title": "Egress de modelos: un código, dos despliegues", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_llm_egress.py"]},
        {"id": "8.1e", "title": "Tarifas: el precio SIGUE al proveedor que corre", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_tariffs.py"]},
        {"id": "8.2", "title": "Perfiles / v2 / doctor / credenciales", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/config/test_profiles.py", "tests/infrastructure/unit/config/test_v2.py",
            "tests/infrastructure/unit/config/test_doctor.py", "tests/infrastructure/unit/config/test_credentials.py"]},
    ]},
    {"id": "9", "name": "HOMEOSTASIS (latido autónomo)", "nodes": [
        {"id": "9.1", "title": "Detección/seguridad/eviction/rotación (V2-070)", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_homeostasis.py"]},
        {"id": "9.2", "title": "Salud viva de la máquina", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py --no-pytest"},
    ]},
]

_SUMMARY = re.compile(r"(\d+) passed|(\d+) failed|(\d+) error")


def _run_node(paths: list[str]) -> tuple[bool, str]:
    existing = [p for p in paths if os.path.exists(os.path.join(ENGINE, p))]
    missing = [p for p in paths if p not in existing]
    if not existing:
        return False, "sin ficheros (¿movidos?)"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", *existing],
                       cwd=ENGINE, capture_output=True, text=True)
    tail = [l for l in (r.stdout or r.stderr).splitlines() if l.strip()]
    summary = tail[-1] if tail else ""
    note = summary.strip("= ")
    if missing:
        note += f" · ⚠ faltan {len(missing)}"
    return r.returncode == 0, note


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", help="solo este dominio (id, p.ej. 1)")
    ap.add_argument("--list", action="store_true", help="solo listar la taxonomía")
    ap.add_argument("--live", action="store_true", help="incluir los nodos VIVOS (lista su comando; no los lanza)")
    args = ap.parse_args()

    print("═" * 74 + "\nMAPA DE TESTS — zaelar · dominio → caso de uso → canal\n" + "═" * 74)
    fails: list[str] = []
    for dom in DOMAINS:
        if args.domain and dom["id"] != args.domain:
            continue
        print(f"\n{dom['id']}. {dom['name']}")
        for n in dom["nodes"]:
            live = n.get("live")
            if args.list:
                tag = f"[VIVO · {n['ch']}]" if live else f"[{n['ch']}]"
                print(f"  {n['id']} {n['title']}  {tag}")
                continue
            if live:
                if args.live:
                    print(f"  🔌 {n['id']} {n['title']} — VIVO ({n['ch']}): {n.get('cmd','')}")
                else:
                    print(f"  ⏭  {n['id']} {n['title']} — VIVO ({n['ch']}), omitido (usa --live para verlo)")
                continue
            ok, note = _run_node(n["paths"])
            print(f"  {'✅' if ok else '❌'} {n['id']} {n['title']} — {note}")
            if not ok:
                fails.append(n["id"])

    if args.list:
        return 0
    print("\n" + "═" * 74)
    if fails:
        print("❌ FALLAN:", ", ".join(fails), "\n→ el sistema NO está plenamente verde")
        return 1
    print("✅ TODO VERDE (deterministas). Los nodos VIVOS exigen `make run` — corre con --live para su lista.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

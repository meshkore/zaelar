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
        # 2026-08-26: el bloque de estado presentaba un ENCARGO igual que un hecho permanente de la persona,
        # bajo la misma orden («dalo por sabido sin buscar»). Medido: el agente arrancó hablando de coches al
        # preguntarle por un monitor, y en la memoria VIVA del operador 3 de 5 plazas eran encargos (V2-337).
        {"id": "1.1", "title": "BD y primitivas de estado, y un ENCARGO no se presenta como hecho de la persona",
            "ch": UNIT, "paths": [
            "tests/memory/unit/test_db.py", "tests/memory/unit/test_journal.py",
            "tests/memory/unit/test_graph.py", "tests/memory/unit/test_state.py",
            "tests/memory/unit/test_compose_state.py", "tests/memory/unit/test_bitemporal.py",
            "tests/memory/unit/test_memory_boundary.py",
            "tests/memory/unit/test_memory_owes_nucleo_nothing.py",
            "tests/memory/unit/test_the_suite_owns_its_own_environment.py",
            "tests/memory/unit/test_widget_slot_migration.py"]},
        {"id": "1.2", "title": "Embeddings y recuperación (retriever+reranker)", "ch": UNIT, "paths": [
            "tests/memory/unit/test_embeddings.py", "tests/memory/unit/test_retriever.py",
            "tests/memory/integration/test_rerank.py", "tests/memory/unit/test_graph_ppr.py",
            "tests/memory/unit/test_rerank_abs.py",
            "tests/memory/unit/test_rerank_local_load_budget.py",
            "tests/memory/unit/test_model_cache.py",
            # 2026-08-25: `query()` decide QUÉ píldoras cuentan como usadas; el CUÁNDO se lo lleva quien
            # entrega (V2-311). 21 de 27 recalls vivos se abandonaban y reforzaban igual.
            "tests/memory/unit/test_reinforce_follows_delivery.py"]},
        {"id": "1.3", "title": "Escritura / ingest / destilador", "ch": UNIT, "paths": [
            "tests/memory/integration/test_memory_agent.py", "tests/memory/integration/test_writer_queue.py",
            "tests/memory/unit/test_embed_pending_marker.py",
            "tests/memory/integration/test_write_precision_v2033.py",
            "tests/memory/integration/test_write_precision_v2050.py",
            "tests/memory/integration/test_write_changes_20260712.py",
            "tests/memory/integration/test_episodic.py", "tests/memory/integration/test_episodic_bytes.py",
            "tests/memory/unit/test_consolidator.py",
            "tests/memory/unit/test_distiller_tape.py",
            "tests/memory/unit/test_paraphrase_lifecycle.py",
            "tests/memory/unit/test_slot_supersede_guard.py",
            "tests/memory/unit/test_distiller_time_anchor.py",
            "tests/memory/unit/test_provider_failover.py",
            "tests/memory/unit/test_locomo_name_swaps.py",
            "tests/memory/integration/test_realistic_session.py",
            "tests/memory/unit/test_writer_dedup.py",
            "tests/memory/unit/test_writer_paraphrase.py"]},
        {"id": "1.4", "title": "Recall correcto (comportamiento, corpus)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v1 --next 10",
            "nested_events": True},
        {"id": "1.5", "title": "Sueño REM / síntesis", "ch": UNIT, "paths": [
            "tests/memory/unit/test_rem.py", "tests/memory/unit/test_rem_prompt.py"]},
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
        # El ARNÉS de evaluación tiene sus PROPIOS tests: mide la memoria, así que un fallo suyo no sale
        # como error — sale como un número creíble y equivocado (cuatro instrumentos rotos en una sola
        # noche, 2026-08-20/21). Nodo propio y NO `live`: son deterministas y tienen que correr en CI,
        # cosa que no pasaría colgados del 1.4, porque `deterministic_paths` salta los nodos live.
        {"id": "1.9", "title": "El arnés de evaluación se prueba a sí mismo", "ch": UNIT, "paths": [
            "tests/memory/unit/test_bot_runner_setup.py", "tests/memory/unit/test_judge.py",
            "tests/memory/unit/test_timeline_cases.py"]},
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
            "tests/agent_headless/unit/flash/test_probe_never_mute.py",
            # V2-305: una respuesta de pura espera con la hoja llena sale CON las filas — el imperativo del
            # prompt pierde contra el reflejo de espera una ronda de cada tres (delivery_lag 98,9 s, ronda 34).
            "tests/agent_headless/unit/flash/test_the_wait_goes_out_with_the_rows.py",  # familia del backstop → nucleo/flash/delivery.py (V2-340)
            # V2-336: el backstop calló en toda una ronda con las entradas correctas y sus tests verdes — el
            # try/except pass se tragaba la avería. Ahora el silencio emite las ENTRADAS de la decisión.
            "tests/agent_headless/unit/flash/test_the_backstop_silence_is_visible.py",
            # V2-339: la guarda anti-feed miraba UNA señal (vocabulario compartido) y silenciaba los dominios
            # donde los resultados buenos no se parecen — coches, hoteles, vuelos. Ahora exige DOS.
            "tests/agent_headless/unit/flash/test_a_feed_is_two_signals_not_one.py"]},
        {"id": "2.3", "title": "Prompt / skeleton / chispas", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_prompt.py",
            # V2-130: a definite reference to a habitual thing ("la de siempre", "mi peluqueria") is a memory
            # question in disguise, and the prefetch was shaped by grammar so an ORDER never fired it.
            "tests/agent_headless/unit/flash/test_recall_habitual.py",
            # V2-132: a promise whose request was made a turn or two back — the backstop only ever looked
            # at THIS turn, and buying tickets had no catalog category so the task got no browser.
            "tests/agent_headless/unit/flash/test_promise_backstop_window.py",
            # V2-134: a reminder is only a reminder if something got SCHEDULED — and the cron must not
            # compete for the turn's single `action`, or booking the appointment kills the alert.
            "tests/agent_headless/unit/flash/test_probe_cron_and_agenda.py",
            # V2-141: a secret spoken INSIDE a request must not swallow the request — and a polite
            # question («¿puedes pagarla?») is still an irreversible order.
            "tests/agent_headless/unit/flash/test_secret_inside_a_request.py",
            # V2-142: a task from another request bleeding into this one, and the search handed back to
            # the operator on a turn where zaelar has web_search and a browser.
            "tests/agent_headless/unit/flash/test_handback_and_task_bleed.py",
            # V2-143: a loop that rephrases itself every turn (invisible to the word-overlap detector),
            # and a promise the backstop could not see because the task was about money.
            "tests/agent_headless/unit/flash/test_rephrased_loop.py",
            # V2-144: a LOCAL business errand (hairdresser/pharmacy/gym) had no catalog category, so it
            # got a worker with no browser — one gap behind three cases.
            "tests/agent_headless/unit/flash/test_local_business.py",
            # V2-135: the composing pass of a web search saw the QUERY as the question, so half of a
            # two-part question was gone before the answer was written.
            "tests/agent_headless/unit/flash/test_search_answers_the_whole_question.py",
            # V2-138: cancelling costs nothing, so the money signal said no and the promise backstop
            # could not fire for the whole cancel family.
            "tests/agent_headless/unit/flash/test_ending_a_commitment.py",
            # V2-145: the brain narrated what the browser «was doing» from the clock, while that task had
            # opened nothing at all — the truth lived in tasks.py and never reached the prompt.
            "tests/agent_headless/unit/flash/test_browser_progress_is_stated.py",
            # V2-146: «te avisaré el miércoles» con scheduled_jobs vacío — el modelo prometía en prosa
            # y no emitía la tag; el backstop resuelve el día por posición y se niega si es ambiguo.
            "tests/agent_headless/unit/flash/test_promised_reminder_backstop.py",
            # V2-209: abrir una tarjeta NO es entregar un resultado. «Aquí lo tienes» es un ack NUESTRO y
            # lo decía sobre una tarea de navegador todavía trabajando (`book-hotel-night-known__es` 13:49).
            "tests/agent_headless/unit/flash/test_opening_a_card_is_not_delivering.py",
            # V2-210: un dato del mundo no se improvisa. Medido en `quick-fact-opening-hours`: «abre a
            # las 10:00 y cuesta 15 €» con CERO herramientas, y las cifras casi correctas, que es lo que
            # lo hace peligroso.
            "tests/agent_headless/unit/flash/test_a_fact_about_the_world_is_not_improvised.py",
            # V2-213: un muro dice ADÓNDE ir. El catálogo tenía UN sitio por categoría, así que ante un
            # muro no había, literalmente, ningún sitio escrito al que mandar al worker.
            "tests/agent_headless/unit/flash/test_a_wall_names_where_to_go_next.py",
            # V2-214: el aviso existía y su CONTENIDO estaba roto — la tag del propio modelo metía la
            # frase del operador («el jueves tengo que renovar…») y el cron se lo entrega al agente como
            # un «apunta esto». El backstop ya componía la forma segura; la otra puerta no.
            "tests/agent_headless/unit/flash/test_the_cron_hands_back_an_instruction.py",
            # V2-147: preguntó EN QUÉ WEB teniendo el motor la respuesta — el catálogo de sitios llega
            # al worker y nunca ha estado a la vista del prompt que decide si preguntar.
            "tests/agent_headless/unit/flash/test_never_ask_which_website.py",
            # V2-148: todo pago iba a un worker SIN navegador, así que la tarea no podía ni llegar al
            # muro de login — el hueco que yo mismo había dejado abierto dos veces.
            "tests/agent_headless/unit/flash/test_money_work_gets_a_browser.py",
            # V2-149: cuatro turnos preguntando DÓNDE está la farmacia y ni uno preguntando QUÉ receta
            # reponer — el objeto del encargo nunca se pidió.
            "tests/agent_headless/unit/flash/test_ask_for_everything_missing.py",
            # V2-150: una tarea de navegador que TERMINA desaparecía del estado, así que no quedaba
            # ningún hecho que contradijera al turno diciendo que «sigue en marcha».
            "tests/agent_headless/unit/flash/test_finished_browser_task_is_a_fact.py",
            "tests/agent_headless/unit/test_skeleton.py", "tests/agent_headless/unit/test_sparks.py"]},
        {"id": "2.4", "title": "Cliente LLM rápido, reintento y RELEVO por latencia", "ch": UNIT, "paths": [
            # ⚠️ ESTE FICHERO NO ESTABA EN EL MAPA (2026-08-21). 22 casos verdes e INVISIBLES para `tests run all`,
            # incluidos los de V2-243. Es la avería de V2-158: un test que ninguna suite ejecuta deja de ser
            # verdad sin avisar. Lo mismo con `test_brain_relay.py`, que además llevaba ROTO desde el refactor de
            # V2-098 (`pc._cooldown` dejó de existir) sin que nadie lo viera.
            "tests/agent_headless/unit/flash/test_provider_chain.py",
            # V2-275: el techo del relevo por LATENCIA levantaba el cooldown del titular fuera cual fuera su
            # motivo — y en la ronda medida se lo quitó a un «z.ai» sin cuota semanal, 260 s después de
            # ponérselo. El techo no tenía ni un test, que es por lo que vivió. Las DOS direcciones: no
            # resucitar a un roto, y seguir resucitando a un lento (o el agente se clava en el escalón caro).
            "tests/agent_headless/unit/flash/test_the_relay_ceiling_does_not_revive_a_dead_tier.py",
            # V2-252: el canal de TEXTO capturaba el fallo, apuntaba el cooldown… y devolvía, con un escalón sano
            # esperando. Ocho horas del arnés sin poder medir. Es la TERCERA vez que muerde la misma forma —
            # `probe.py` es la implementación PARALELA del provider de voz—, así que la DECISIÓN pasa a
            # `provider_failure.py` y la leen los dos canales.
            "tests/agent_headless/unit/flash/test_the_text_channel_relays_too.py",
            # V2-254: la TERCERA superficie que enseña píldoras a un modelo, y la que corre CADA TURNO. La regla
            # («una píldora de fondo no es un hecho sobre la persona») estaba escrita en tres sitios y aplicada
            # en uno; las otras dos hubo que descubrirlas con un fallo en vivo cada una. Aquí se APLICA la que ya
            # existe (`memory.api.background_slot_off_topic`), no se escribe una cuarta copia.
            "tests/agent_headless/unit/flash/test_the_third_surface_shows_pills_too.py",
            # V2-255: para poder vigilar el ARTEFACTO en vez de la lista de superficies (propuesta del arnés), el
            # artefacto tiene que CONTENER lo que se comprueba — y el bloque de memoria caía en el hueco omitido
            # del prompt guardado. Un verificador habría dicho «limpio» sobre un prompt sucio.
            "tests/agent_headless/unit/flash/test_the_artifact_shows_the_memory_it_was_given.py",
            "tests/cluster/unit/test_brain_relay.py",
            # V2-243/244: un saldo agotado no es una cuota, y un escalón CALLADO por la regla de self-host se
            # nombra en vez de decir «SIN RELEVO disponible» a secas.
            "tests/agent_headless/unit/workers/test_deepseek_rung.py",
            "tests/agent_headless/unit/flash/test_fast_client.py", "tests/agent_headless/unit/flash/test_fast_client_retry.py",
            "tests/agent_headless/unit/flash/test_procs.py",
            # V2-094 (2026-08-14): la cadena de proveedores existía desde agosto pero solo para el cerebro de
            # CLUSTER y solo relevaba por proveedor ROTO (429/cuota). El fallo que el operador vive es el proveedor
            # LENTO — TTFT de 25 s con el prompt constante — y no había a dónde ir. Aquí se fija la política, que
            # es donde está el riesgo de gastar dinero sin querer: racha de lentos, cooldown corto, TECHO de turnos
            # en el escalón caro, y self-host SIN relevo de fábrica.
            "tests/agent_headless/unit/flash/test_voice_failover.py"]},
        {"id": "2.5", "title": "Escalado / dispatch / workers", "ch": UNIT, "paths": [
            # V2-345: lo que el worker NARRA (82 eventos en 21,6 min, uno cada 16 s) llega a la pestaña de
            # Proceso MARCADO con «💬». Es la señal más rica que tenemos —lleva sitio, precio, modelo y el
            # porqué del paso— y no salía en ninguna pantalla. El marcador la separa de lo que verificamos
            # nosotros: el worker AFIRMA cosas (V2-249).
            "tests/agent_headless/unit/workers/test_what_the_worker_says_reaches_the_screen.py",
            "tests/agent_headless/unit/test_one_errand_at_a_time.py",
            "tests/agent_headless/unit/flash/test_escalate.py", "tests/agent_headless/unit/test_dispatch.py",
            # V2-301: el brief se compone EN PARALELO con el spawn — el compositor razonador (15-30 s) corría
            # en serie antes del worker, que luego gastaba sus propios ~20 s de preámbulo; solapados, la
            # búsqueda entra en los 2-3 min del operador. El brief tardío llega por inyección (V2-038).
            "tests/agent_headless/unit/test_parallel_brief.py",
            # V2-314: `pick()` devolvía None por DOS motivos —cadena vacía (self-host sin claves: usa la
            # licencia local, el fail-open prometido) y cadena entera en cooldown— así que el cooldown de la
            # licencia no podía morder y se relanzaba contra el proveedor que acababa de decir que no.
            "tests/agent_headless/unit/test_an_asleep_chain_does_not_spawn.py",
            # V2-325: el worker escribía `widget_cli --help` —lo primero que hace cualquiera— y recibía
            # «comando desconocido» con exit 2. Medido: 3 de las 5 sesiones que llegan a ese puente mueren ahí,
            # y es la ÚNICA forma que tiene de poner en la hoja lo que aprende abriendo fichas.
            "tests/agent_headless/unit/workers/test_asking_for_help_is_not_a_failure.py",
            # V2-320: `code_agent.providers` es una COPIA del catálogo, y una copia hecha antes de medir tira
            # la medida. El escalón DeepSeek a mano perdía su `vision: False` → el navegador mandaba una PNG
            # de 300-530 KB en cada acción a un modelo que no puede abrirla.
            "tests/agent_headless/unit/workers/test_a_hand_ordered_tier_keeps_what_we_measured.py",
            # V2-290: el navegador extraía filas reales y caían en la caja PELADA, que no es de nadie desde
            # V2-259. Solo `kind="web"` reserva pestaña, así que el resto la nombra como su TAREA — y esa
            # vuelta no existía en la resolución de la hoja.
            "tests/agent_headless/unit/test_a_finding_always_has_a_box.py",
            # V2-238: un RELEVO no es una muerte. `_finish` releva de proveedor (o compacta el contexto), relanza
            # el encargo y deja `ok=False` a propósito — y con eso la sesión quedaba indistinguible de un worker
            # muerto: aviso falso de muerte al operador, DOS escaladas para una, y una muerte contada de más.
            "tests/agent_headless/unit/workers/test_a_handoff_is_not_a_death.py",
            # V2-288: el cajón privado del worker no lo era — `escalate._seq` arranca en 0 en cada proceso, así
            # que el primer encargo tras un reinicio caía en el mismo directorio que el primero del arranque
            # anterior y heredaba su `informe.json`. Medido: 6 guitarras entregadas en 27 s con CERO navegaciones.
            "tests/agent_headless/unit/workers/test_a_restart_does_not_inherit_a_report.py",
            # V2-289: al worker se le mandaba mirar una captura que su modelo no puede leer. Con el relevo a
            # DeepSeek puesto: `Read` de la PNG → «formato no soportado» → «sigo por DOM», dos veces en una
            # corrida. La PNG estaba perfecta; el que no ve es el modelo.
            "tests/agent_headless/unit/workers/test_a_blind_model_is_not_sent_to_look.py",
            # V2-237: tres workers reanudando LA MISMA sesión del CLI y los tres muertos a los ~400 ms (3 de 3,
            # contra 0 de 3 entre los que abrieron sesión propia). `_find_resume` leía la entrada sin consumirla.
            "tests/agent_headless/unit/test_a_native_session_is_resumed_once.py",
            # V2-250: al worker se le DICE qué día es, y ese bloque leía el reloj de PARED mientras el resto del
            # razonamiento con fechas va por `scheduler.time.time()` («ONE clock»). Invisible en producción,
            # letal al medir — la forma gemela la midió memoria-dev en el dosier (75f2a34).
            "tests/agent_headless/unit/test_the_worker_is_told_the_same_today.py",
            # V2-249: la «píldora que se auto-avala». Un worker al que se le encargaba «recuérdaselo el
            # miércoles» decía que lo había programado y NO existía ninguna entrada — porque la capacidad no
            # existía. Ahora existe, con su filtro (tope por tarea, atribución, y lo ambiguo NO se adivina).
            "tests/agent_headless/unit/workers/test_a_scheduled_reminder_exists_or_is_not_claimed.py",
            # V2-152: a worker resolved its bridges against a HARDCODED localhost:43917 that nobody ever set,
            # so an engine on any other port spawned workers that drove a DIFFERENT engine.
            "tests/agent_headless/unit/test_worker_own_engine.py",
            # V2-167: preguntar a la red MeshKore ANTES de abrir un navegador. Solo agentes GRATIS, un 402
            # nunca se paga, el campo que leen los agentes es `prompt` (no `query`) y de su ficha se toma la
            # RUTA pero jamás el host. Sin red: todo está fingido a propósito.
            "tests/agent_headless/unit/test_mesh_agents.py",
            # V2-219: el worker se murió DOS veces en la aridad de nuestro propio CLI, en casos sin relación
            # (`scroll down` cuatro veces, `worker_bridge act` sin payload) — y la ronda acabó con CERO
            # búsquedas. Una mitad es que el CLI estaba equivocado (una dirección es una forma legítima de
            # escribirlo) y la otra que el fallo tiene que decir cómo se escribe.
            "tests/agent_headless/unit/workers/test_the_bridge_takes_what_the_worker_writes.py",
            # V2-203: el puente del payload contestaba a un fichero que falta con el OSError pelado, y el worker
            # lo leía como un callejón sin salida (`cheapest-monitor` ronda 21: Exit code 2, nada entregado).
            # Mismo contrato que el nodo 4.20 para `nav_cli`: lo que el puente sabe, lo DICE — y un fallo dice
            # además cómo se sale de él.
            "tests/agent_headless/unit/workers/test_the_bridge_says_how_to_fix_it.py",
            # V2-274: `ERROR: timed out` — las dos palabras que devuelve `str(socket.timeout())`— era todo lo
            # que el worker sabía cuando el navegador tardaba más de 90 s. Misma familia, con un agravante: la
            # reacción natural (repetir) es la única que no puede funcionar, porque el plazo agotado es el
            # NUESTRO y la pestaña puede seguir trabajando.
            "tests/agent_headless/unit/workers/test_a_bridge_timeout_says_what_to_do.py",
            # V2-211: la puerta es NUESTRA. Tres casos el mismo día murieron en un permiso del propio
            # cajón del worker (`cd` bloqueado, comando compuesto, `curl`) sin decirlo. Reglas por delante
            # + un turno correctivo si aun así choca.
            "tests/agent_headless/unit/workers/test_the_gate_is_ours.py",
            # V2-277: le decíamos al worker WEB que corría «desde la raíz del repo» —falso desde V2-117— y
            # luego le bloqueábamos el `cd` con el que iba a llegar; y las reglas del cajón de V2-211 solo se
            # las dábamos al worker GENÉRICO, o sea a todos menos al que más shell compone. El guarda es de la
            # FORMA: todo prompt que ofrezca un puente lleva las reglas, y ninguno afirma dónde no está.
            "tests/agent_headless/unit/workers/test_the_drawer_rules_reach_every_bridge_prompt.py",
            # V2-344: tercera vez la misma forma (V2-257, V2-277). La orden de GUARDAR lo averiguado existía y
            # decía literalmente «aunque el flujo se reinicie», pero vivía en la rama de GESTIÓN; una BÚSQUEDA
            # nunca la leía como suya. Medido: 21 min de dos workers muertos, cero filas en memoria. El guarda
            # mira el prompt RENDERIZADO, porque que la orden exista en el fichero es lo que ya pasaba.
            "tests/agent_headless/unit/workers/test_what_the_worker_learns_outlives_it.py",
            # V2-158: este fichero NUNCA estuvo en el testmap, así que `tests run all` no lo corría y sus
            # afirmaciones llevaban desde V2-132/V2-144/V2-148 contradiciendo el comportamiento buscado en
            # silencio. Un test que ninguna suite ejecuta es un test que deja de ser verdad sin avisar.
            "tests/agent_headless/unit/agentes/test_web_cc_site_catalog.py",
            # V2-140: an allusion («¿y el del coche?») must reach the task it names — the punctuation
            # was glued to the word, the same defect V2-123 fixed in this file's sibling function.
            "tests/agent_headless/unit/test_task_attribution.py", "tests/agent_headless/unit/workers/test_workers.py",
            # V2-139: the chain «móntame un widget» → code → GENERATOR backend → card on screen, walked.
            # V2-115 left this written down as its own primary open task: every link was tested in
            # isolation and the chain was not, which is what let a created widget be opened by nobody.
            "tests/agent_headless/unit/workers/test_widget_creation_chain.py",
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
            "tests/agent_headless/unit/workers/test_the_process_tab_gets_the_steps.py",
            # V2-236: lo que devuelve una BÚSQUEDA WEB moría dentro del worker (7 búsquedas, 5 respuestas con el
            # dato exacto que pidió el operador, 0 notas al cerebro). Se empuja en cuanto existe, el JUICIO se
            # queda en el cerebro, y un `is_error` no es un hallazgo.
            "tests/agent_headless/unit/workers/test_the_search_answer_reaches_the_conversation.py",
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
        # V2-227 ámbito A — DÓNDE va a mirar el operador, decidido al ENCARGAR y no al entregar. Sin este campo
        # no hay nada que abrir mientras el worker trabaja, y la pestaña de proceso es una pestaña vacía. Aquí se
        # fijan las tres reglas (se decide al encargar · vocabulario CERRADO de cinco · se decide UNA vez) y que
        # el módulo no sepa de ningún dominio, que es la doctrina hecha test.
        {"id": "2.14", "title": "La SUPERFICIE se decide al encargar, con vocabulario cerrado y una sola vez",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_the_surface_is_decided_when_the_errand_is_commissioned.py"]},
        # V2-227 ámbito B — el CAUDAL: fases que lee una persona («entrando en booking.com», «12 resultados»),
        # con latido para que una fase de 90 s no parezca un worker muerto. La materia prima ya existía desde
        # V2-048 (`{where,action,target}`); lo que faltaba era decirla, y por el carril que ya existe.
        # 2026-08-24, medido por el arnés en tres casos (guitarra 49 s, hotel 42 s, vuelos 113 s): las filas
        # entraban en la hoja DECENAS DE SEGUNDOS antes del último turno y el agente seguía diciendo «todavía no
        # tengo nada». No era un olvido: `results.intake.push` es la puerta única de las FILAS (V2-257) pero no
        # lleva nota —la empuja el llamante— y de los tres llamantes el único que no la empujaba era
        # `dispatch._finalize_web`, que hace su propia extracción final cuando el worker termina o muere. La otra
        # mitad pesa igual: si la extracción de esa pestaña YA salió por `_hand_over`, la barrida final es casi la
        # misma página, y una segunda nota se lee como «ha encontrado más» cuando ha encontrado lo mismo.
        # V2-320-C (2026-08-25, el ejemplar más limpio de la familia: kid-friendly, worker vivo 709 s, 8 búsquedas,
        # 7 returns, 0 navegaciones — hoja vacía SIEMPRE). El return de búsqueda tenía un solo camino: la nota que
        # el turno lee una vez. La hoja no los rechazaba (`_to_item` acepta título+url sin precio): no tenían
        # puerta. Ahora entran por la única de V2-257 (intake.push, snippet→subtitle), con el dedup de la hoja
        # haciendo converger las búsquedas solapadas.
        {"id": "2.31", "title": "Un return de BÚSQUEDA llega a la hoja del encargo — buscar también es "
                                "encontrar",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/workers/test_a_search_return_reaches_the_sheet.py"]},
        # V2-342 (2026-08-26, sesión 7575e81a): ante la QUEJA por un worker vivo, el circuito mataba y
        # relanzaba de cero — 3 workers en 21,6 min, 2/3 del tiempo en trabajo descartado, con el bucle
        # retroalimentándose (lento → queja → relanzar → más lento). Tres cortes de un mismo defecto: la
        # directiva enseña la bifurcación de la queja (INYECTA «entrega YA», matar se reserva a orden o
        # atasco), una gestión CANCELADA conserva su rastro reanudable (parar borra el PROCESO, no lo andado
        # — el auto-resume sigue excluido: parar es parar), y el matcher puntúa contra el conjunto MENOR
        # (la orden real de relanzar traía 47 palabras y Jaccard puntuaba 0,208 la gestión CONTENIDA en ella).
        {"id": "2.32", "title": "Una QUEJA no tira el trabajo: la directiva inyecta, la cancelada deja rastro "
                                "reanudable y el relanzamiento real CASA",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_complaint_does_not_throw_the_work_away.py"]},
        {"id": "2.30", "title": "Lo que la última barrida deja en la hoja llega a la conversación — y NO se "
                                "cuenta dos veces",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/workers/test_the_last_sweep_tells_someone.py"]},
        {"id": "2.25", "title": "El progreso se lee como una frase, y una fase larga dice que sigue viva",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_the_progress_reads_like_a_sentence.py"]},
        {"id": "2.6", "title": "Scheduler / rails / workspace / frontend-glue", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_scheduler.py", "tests/agent_headless/unit/test_rails.py", "tests/agent_headless/unit/test_workspace.py",
            "tests/agent_headless/unit/test_confirm_gate_task.py", "tests/agent_headless/unit/test_escalate_hygiene.py",
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
        {"id": "2.24", "title": "Un turno CANCELADO también se factura (y con el estimado bien calibrado)",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/flash/test_cancelled_turn_billing.py"]},
        # 2026-08-20: una SESIÓN de worker que acaba desaparecía del estado sin dejar rastro — el mismo hueco
        # que V2-150 cerró para las tareas de navegador, un nivel por encima y peor: una tarea de navegador
        # solo existe con kind=web, y TODA escalada abre una sesión.
        {"id": "2.18", "title": "El final de una sesión de worker es un HECHO (y sus estados, una sola lista)",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/test_ended_session_is_a_fact.py"]},
        # 2026-08-21, medido en el motor del OPERADOR (no en un plató): SEIS workers para una sola búsqueda de
        # coches. Los dos relevos automáticos de `_finish` —contexto agotado y proveedor sin cuota— dicen
        # relanzarse «UNA vez», pero el booleano que lo guarda vive en el RECORD y cada relevo estrena uno, así
        # que el contador vuelve a cero y la cadena no acaba. `depth` viajaba SIN incrementar y tampoco contaba.
        # Misma forma que el id de hoja que se reiniciaba con el proceso (32c7dc6): un contador de instancia
        # leído como si fuera global — con el agravante de que aquí el error NO es reintentable, así que el bucle
        # gasta dinero real ($2,09 el primer worker, cuatro cadáveres de 17 s detrás). Incluye la frase honesta:
        # sin ella el resumen capado sigue prometiendo «la retomo», que es esperar a nadie.
        {"id": "2.23", "title": "Una cadena de relevo tiene final: la generación viaja, el tope corta y al cortar "
                                "dice la verdad (sin prometer una retoma que no va a pasar)",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/test_a_relay_chain_has_an_end.py"]},
        # F4 de la auditoría de arquitectura (2026-08-23). El hallazgo H3, medido en vivo el 2026-08-21: DOS
        # jueces de «¿es el mismo encargo?» se contradijeron sobre el MISMO par de textos — find_duplicate
        # (Jaccard ≥0.60) abrió tres workers y tasks._similar (≥0.40) les dio UNA pestaña, con el Jaccard real
        # (0.333-0.375) cayendo en el hueco entre las dos varas. El primitivo vive ahora UNA vez en
        # nucleo/matching.py y ambos jueces lo importan; el del dispatcher pasa a CONTENCIÓN (mismo encargo
        # 0.571-0.893 vs distintos 0.062-0.227, poblaciones sin solape donde Jaccard no separa), lo que además
        # disuelve el bug del goal truncado a 200 (el lado recortado es el min por el que se divide).
        {"id": "2.26", "title": "UNA vara de parecido: contención en el dispatcher, el primitivo compartido por "
                                "los dos jueces, y ninguna copia privada de la aritmética",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/test_one_yardstick_of_similarity.py"]},
        # F1 paso 1 de la auditoría (2026-08-23). El TURNO está implementado dos veces —`_run_inner` 2.603
        # líneas para voz, `run_turn` 1.051 para texto— cosidas por 21 marcas de espejo. La primera que se
        # retira es la puerta de la bóveda, y ya había derivado: la copia del probe contestaba con la acotación
        # «(secreto cifrado)» donde la voz decía una frase localizada, y V2-141 hubo que arreglarlo dos veces.
        # La DECISIÓN vive en `nucleo/turn/vault_gate.py`; la ENTREGA sigue siendo de cada canal (voz habla y
        # emite, probe devuelve un dict) porque esa diferencia es real. El guarda de cableado es el corazón: sin
        # él la puerta puede estar perfecta mientras un canal decide por su cuenta en silencio. 21 → 18 espejos.
        {"id": "2.27", "title": "Una puerta de bóveda, dos bocas: la decisión se toma UNA vez y ningún canal "
                                "conserva su copia",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/turn/test_the_vault_gate_is_decided_once.py"]},
        # F1 (2026-08-24) — el espejo que DERIVÓ, y el defecto que escondía. Hay TRES puertas de confirmación
        # (widget · tarea parada por el confirm-gate · clic irreversible del navegador) y pueden estar abiertas a
        # la vez. En VOZ las dos últimas se resolvían con el MISMO guarda, que mira la de widget, así que nada
        # registraba que la de tarea acabara de resolverse: un solo «sí» hablado autorizaba LAS DOS. El comentario
        # de ese bloque afirmaba justo lo contrario —«solo si el sí no ha resuelto ya otra cosa»— y eso es lo que
        # hizo que nadie mirara: un invariante en prosa, cero tests. El `probe` lo tenía bien.
        # El guarda de cableado se comprueba por AST y sobre la propiedad correcta: que las dos puertas viajen en
        # la MISMA llamada. La primera versión contaba llamadas sueltas y se quedó VERDE al reintroducir el
        # defecto — contaba el arreglo, no la propiedad.
        {"id": "2.29", "title": "Un «sí» contesta a UNA pregunta: la precedencia de las tres puertas de "
                                "confirmación se decide una vez, y los dos canales la usan",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/turn/test_one_yes_answers_one_question.py"]},
        # F1 paso 2 (2026-08-23), reportado por el arnés con el coste medido: con la memoria lenta (descarga de
        # 1,1 GB) `probe.py` componía el recall DENTRO del event loop y bloqueaba el motor ENTERO — todos los
        # endpoints en timeout y la tanda muerta como «INFRA: timed out», sin nombrar a la memoria. La voz ya
        # tenía la guarda. Y el defecto lo decía el docstring de `build_flash_system`: `recall_query=` es la
        # ruta de COMPATIBILIDAD PARA TESTS y compone en línea. Una PROTECCIÓN que existe en un canal y no en
        # el otro no se distingue de no tenerla.
        # 2026-08-25: el trinquete se quedaba a un paso. `recall_timeout` se ponía —y este nodo lo afirmaba— y
        # NADIE lo leía: 21 de 27 recalls de sesiones vivas volvieron con `mem_ms: null` y «0 tarjetas», que es
        # idéntico a una memoria que de verdad no tenía nada. Un aviso sin lector no es un rastro.
        # V2-311 paso 2 (2026-08-25): el 77% de los recalls vivos se abandonaba al vencer el presupuesto y TODOS
        # terminaban igualmente — el hilo corre hasta el final y el bloque moría en un futuro sin lector. Ahora un
        # recall tardío se entrega como nota al turno SIGUIENTE, con el corte de frescura en TURNOS y no en reloj
        # («ningún turno ha preguntado desde entonces»): la cola de producción llegaba a 21 s, y V2-254 midió lo
        # que la memoria rancia hace a una conversación que ya se movió. Solo texto (sin ids: no se refuerza lo
        # que no se usó) y la nota no ordena anunciar — el juicio es del cerebro (doctrina de findings.py).
        {"id": "2.28", "title": "El recall se compone fuera del loop y acotado en LOS DOS canales; el que NO "
                                "llega se VE, y el que llega TARDE es la nota del turno siguiente — o de nadie",
            "ch": UNIT, "paths": ["tests/agent_headless/unit/turn/test_the_recall_budget_is_shared.py"]},
        {"id": "2.15", "title": "Idioma del operador en un canal SIN voz (primera ejecución)", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_first_run_language.py"]},
        # 2026-08-20: el relleno de nunca-mudo decía CUATRO veces la misma frase («Vale, dame un momento que lo
        # miro.») mientras el operador contestaba «vale, quedo atento» cada vez. `data_acks` tiene el
        # tratamiento anti-repetición desde V2-038; al relleno de espera, que se dice mucho más, nunca se le
        # aplicó.
        {"id": "2.16", "title": "El relleno de espera no se repite, y pasada la 2ª dice cuánto lleva", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_holding_line_never_repeats.py"]},
        # 2026-08-20: «Sí, adelante» → «Hecho.» → «¿Ya está cancelada del todo?». El ack de TERMINADO puesto
        # sobre una tarea que acababa de ARRANCAR, con el daño en las palabras del propio operador dos líneas
        # después. No lo dijo el modelo: `confirm_task` compartía rama con `widget_data`.
        # V2-350 — las DOS puertas del motor le contestaban cosas opuestas al mismo worker relevado, y en el
        # peor orden: `/api/worker/act` le devolvía 403 (no podía ENTREGAR sus 7 coches verificados) y
        # `/api/agent/report` no miraba el token (sí podía CONTAMINAR el estado de su relevo). El juez leyó las
        # notas del fantasma como hechos de la ronda.
        # V2-352 — el escritor resolvía la hoja por DOS caminos (sello de la pestaña, y si está vacío el
        # registro de sesiones vivas) y los lectores por UNO. Ronda 12 del coche, 1/5: el backstop de entrega
        # emitió su silencio NUEVE veces con rows=0 mientras la hoja tenía DOCE coches con enlace.
        # V2-353 — la pregunta y su respuesta en el MISMO prompt. «lleva ya 18 minutos, ¿la paro?» sale a los
        # 15 min y la muerte por presupuesto a los 21,5; sin voz viva ninguna se entrega al vuelo, así que si
        # el operador tarda en hablar se drenan juntas. Cuarta vez que un prompt que se contradice se lee como
        # desobediencia del modelo.
        # V2-354 — la TERCERA cara de la familia. `restaurant-tonight-madrid` (primera ronda del supervisor):
        # plan de 4 pasos a los 49 s, primer paso reportado a los 380 — 331 s en «0/4, 0%» navegando y leyendo
        # capturas, y ninguna cara salió: ENCALLADA mira el silencio (y no callaba) y «sin paso reportado» no
        # aplica con plan declarado. El plan lo empeoraba: «0/4, 0%» se lee como «acaba de empezar».
        # V2-358 — «Preparando entrega: 10 propuestas en la hoja de resultados» con la hoja en CERO filas, y
        # pintado sin marca junto a líneas verificadas. Misma enfermedad que V2-357 una capa más abajo, misma
        # respuesta que V2-345: no se tira, se MARCA.
        # V2-394 — `dispatch_tag` se traga el resultado, así que el turno no podía saber si la op ocurrió y la
        # boca decía «Hecho.» pase lo que pase. Dos ops fallidas anunciadas como hechas (resultado 2/5).
        {"id": "4.56", "title": "«Hecho.» solo si la data-op OCURRIÓ · y lo que el widget rechaza se DICE",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_hecho_sobre_una_op_que_fallo.py"]},
        # V2-391 — «UNA data-op por turno» convirtió dos enlaces pegados en una alucinación: solo entró el
        # primer `add`, el `next` no encontró segundo vídeo y el turno anunció que sonaba igualmente.
        {"id": "4.55", "title": "Dos enlaces pegados son dos `add` · sin reabrir la cita doble ni la enumeración",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_dos_enlaces_pegados_son_dos_adds.py"]},
        # V2-383 — hermano exacto de V2-380, una rama más abajo en el mismo `elif`: `play_video` se resolvía a
        # la etiqueta «canvas:show:youtube» y ahí acababa, sin `load`. Ocho turnos pidiendo el tráiler de Dune
        # y cuatro veces «Te lo abro, aunque de momento está vacío» — con seis tráileres reales encontrados y
        # mandados a la HOJA en vez de al reproductor. Cuarta vez de la familia en `probe.py`.
        # V2-401 — la captura del OPERADOR: «This video is unavailable» con el estado declarado diciendo
        # `paused: false`. El widget solo escuchaba onStateChange; onError no lo leía nadie, así que
        # /widgets/producing —en el que confían el cerebro, el juez y el master (V2-392/395)— contaba como
        # SONANDO un reproductor roto. Ahora el error se reporta de vuelta y active_when lo excluye.
        {"id": "4.57", "title": "Un vídeo que el sitio no deja reproducir NO está sonando",
            "ch": UNIT,
            "paths": ["tests/browser/unit/youtube/test_an_unplayable_video_is_not_playing.py"]},
        # V2-402 — la captura del OPERADOR (2026-08-27): «buscando vídeos estás utilizando el widget de
        # resultados». Una búsqueda de contenido multimedia no tenía dueño: play_video cargaba UNO, play_music
        # reproducía, y el plural caía a escalate → worker → hoja. Regla del operador: lo que se VE u OYE se
        # canaliza por su widget dedicado (buscarlo incluido); la hoja es para INFORMACIÓN, aunque un hotel
        # tenga vídeos en su web. `search` llena la LISTA sin reproducir (la ley de V2-366 vale para buscar);
        # la normalización play/list vive UNA vez en video_turn y la consumen voz y probe.
        {"id": "4.58", "title": "Buscar vídeos va al REPRODUCTOR, no a la hoja: `search` llena la lista sin "
                                "reproducir · play/list normalizado UNA vez para voz y probe",
            "ch": UNIT,
            "paths": ["tests/browser/unit/youtube/test_a_media_search_fills_the_list_not_the_sheet.py",
                      "tests/agent_headless/unit/flash/test_searching_videos_goes_to_the_player_not_the_sheet.py"]},
        # 2026-08-27, medido en el plató: el 402 de las 18:55 castigó al titular SEIS HORAS, el operador recargó
        # a las 19:40, y el motor siguió mandándolo todo al relevo. Cuando ese relevo se cayó a su vez, el cerebro
        # se quedó MUDO con el titular sano una fila más arriba — y no había forma de decirle que ya había saldo.
        # 2026-08-27, medido en vivo con las consultas de los casos US: 4 de 6 volvieron vacías porque DDG
        # servía un desafío anti-bot como HTTP 202 (un estado de ÉXITO). Ni el clasificador —que buscaba las
        # palabras que usaríamos nosotros, no las de la página— ni la fila del buscador —que llevaba `n: 0` y
        # nada más— lo decían, así que el arnés declaraba sana una capa de búsqueda muerta y el juez calificaba
        # al agente por no encontrar lo que nadie nos dejó mirar.
        # 2026-08-28, primera ronda del plató 24/7: `weekend-plan-barcelona__es` se archivó con dos anomalías
        # `error_interno` y el juez escribió «el worker falló técnicamente al extraer el precio». Lo que el
        # worker hizo fue lanzar `nav_cli` y `worker_bridge` SIN subcomando — argparse contesta `usage:` y sale
        # con 2, así que una sonda de descubrimiento llega vestida de caída. El instrumento acusando al
        # producto: dos de los cuatro fallos marcados no existieron, y la nota de mecanismo los pagó.
        # 2026-08-28 — «No such file or directory: progreso.json» es verdad y no sirve para nada: no distingue
        # entre escribirlo en otro sitio, escribirlo con otro nombre y no escribirlo, que piden acciones
        # distintas. Medido en `best-plumber-same-day__es`: el paso murió ahí y la ronda se fue en ocho
        # minutos sin entregar lo que el operador pidió tres veces. `widget_cli` YA listaba los .json
        # presentes y `worker_bridge` no — la misma divergencia entre puentes de la que salió V2-379.
        # 2026-08-28, plató 24/7 — `weekend-plan-barcelona__es`: 56 búsquedas web, 31 consultas, 0 candidatos
        # verificados, repitiendo la misma sin cambiar un criterio. «Eso no es diligencia, es dar vueltas»
        # (juez). No se BLOQUEA la repetición —rompería un reintento legítimo—: se contesta al instante con lo
        # ya traído y se MARCA, que es lo que convierte «dio vueltas» de impresión en dato.
        {"id": "4.66", "title": "La misma búsqueda dos veces no son dos búsquedas — TTL corto, marcada, y sin "
                                "cobrar dos veces",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_the_same_search_twice_is_not_two_searches.py"]},
        # 2026-08-28 — contadas las anomalías de las 44 filas del marcador: `payload JSON inválido` sale **18
        # veces**, más del DOBLE que la siguiente firma, y el mensaje era literalmente eso: ni qué tenía de
        # inválido ni qué se leyó. El worker reintenta lo mismo tres y cuatro veces. Y la causa más probable
        # —la valla de markdown que a un modelo le sale sola al escribir JSON— no es ambigua, así que
        # rechazarla no protegía de nada: solo gastaba la vuelta.
        # 2026-08-28 — cuatro rechazos distintos de la puerta de permisos en una noche («simple_expansion»,
        # «brace with quote», el `&`, el `cd`) y en los CUATRO el evento decía qué regla se rompió y nada del
        # comando. Eso no distingue «el worker escribió algo raro» (conducta) de «nuestro prompt se lo enseñó»
        # (culpa nuestra), que piden acciones opuestas — y dos de las cuatro eran lo segundo.
        # 2026-08-28, plató 24/7 — `find-concert-tickets__es`: no había concierto de Rosalía en Madrid ese mes
        # (una respuesta COMPLETA) y el worker llenó la hoja de eventos que no eran, dejando a la persona
        # siete minutos esperando. El método cubría «no puedo certificarlo»; lo contrario —«lo he certificado
        # y no existe»— no estaba, y sin eso el único final que le queda al worker es seguir buscando.
        # 2026-08-28 — la avería de V2-432 no hace ruido: `_sheet_of_tab` devuelve "" y el prompt se compone
        # como si no hubiera nada, indistinguible de que de verdad no lo haya. Encontrarla exigió cruzar el
        # instante en que la hoja se llenó con el texto de cada prompt, ronda por ronda.
        # 2026-08-28 — el puente del worker contestaba «el widget «music» no existe» a un nombre que el resto
        # del sistema resuelve sin pestañear: `paths.dir_for` casa con la CARPETA y nada más, mientras el
        # registro trae la identidad (id, nombre, alias) de los 26. Y no era solo cosa del inglés: la misma
        # búsqueda rechazaba `reloj`, el nombre castellano del widget cuya carpeta es `clock`.
        # 2026-08-28 — el final de V2-432. En `compare-flights-madrid-lisboa` el bloque vivo miró `f1743e-2`
        # (vacía, 7 veces) mientras las filas estaban en `f1743e-1`: un RELEVO hereda la hoja del predecesor,
        # pero el sello de la pestaña «se escribe una sola vez, en tasks.create()» y el relevo crea pestaña
        # nueva. El sello no falta: está RANCIO. Arregla el lado del LECTOR y nada más.
        # 2026-08-28 — le pedíamos escribir un fichero y no le dábamos la tool. El payload de los puentes va
        # por `@fichero` desde V2-379 y el prompt lo dice con todas las letras, pero `Write` no estaba en la
        # allowlist: el CLI pedía una aprobación que en headless nadie da. Medido en `find-best-hotel-city__us`
        # con la cadena entera visible: «requested permissions to write to …/informe.json» y acto seguido «no
        # puedo leer el payload de informe.json». Nueve turnos ciegos y 1/5.
        # 2026-08-28 — cinco intentos del worker de guardar hallazgos operativos («Wallapop filtro que
        # funciona…», «Milanuncios bloqueado por anti-bot», «coches.net da error persistente») murieron con
        # «HTTP Error 422: Unprocessable Entity» y NADA MÁS. El servidor sí dice por qué, en el cuerpo, y
        # `HTTPError` solo trae el número: el worker reintenta o se rinde a ciegas y el hallazgo se pierde.
        # 2026-08-28 — siete «Element is not attached to the DOM» en dos rondas, con el worker repitiendo
        # `click 13` una y otra vez. El mensaje era el crudo de Playwright y nada más, mientras su hermano —el
        # ref fuera de la mirada— dice desde siempre «haz `look`… no reintentes el mismo». Mismo problema, un
        # ref caducado, contado de dos maneras, y solo una servía.
        # 2026-08-28 — `results::82d86e-2` y `82d86e-2` son la misma hoja dicha de dos maneras, y la primera
        # devolvía VACÍO: el saneado se comía los dos puntos y componía `results--results82d86e-2`, una clave
        # que no existe. Una hoja vacía es indistinguible de «aún no ha encontrado nada»: el fallo no hace
        # ruido, cambia la respuesta.
        # V2-443 — sin filas, `_found_candidates` solo puede leer `kept`, la cuenta que escribe el propio
        # worker. Se renderizaba como hecho («YA HA ENCONTRADO algo») y se le prohibía al turno decir lo
        # contrario. Medido: 11 disparos con la hoja vacía en todas partes y el worker sin encontrar nada.
        # V2-444 — el MISMO defecto en el bloque de TAREAS DE FONDO, que lee el mismo `kept` y además ordenaba
        # tratarlo como entrega. Y era el que disparaba: 7 turnos medidos con la cara del navegador apagada.
        # V2-451 — el bloque de filas colgaba de la PESTAÑA del navegador, así que un encargo resuelto por
        # búsqueda llenaba la hoja y el prompt no nombraba ni una fila (ni emitía el aviso de V2-438).
        # V2-452 — el prompt entero está en castellano y el operador puede hablar otro idioma: el modelo
        # copiaba el de las notas. 8 de 40 rondas US, tres de ellas contestando entero en castellano.
        {"id": "2.40", "title": "No se copia el idioma de las NOTAS INTERNAS del prompt",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_no_se_copia_el_idioma_de_las_notas_internas.py"]},
        {"id": "4.79", "title": "Las filas de la hoja viajan aunque NO haya navegador",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_las_filas_viajan_aunque_no_haya_navegador.py"]},
        {"id": "4.78", "title": "El `kept` del bloque de tareas también es del WORKER, no un hecho",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_el_kept_del_bloque_de_tareas_tambien_es_suyo.py"]},
        {"id": "4.77", "title": "Sin filas, lo único que hay es la PALABRA del worker — y se marca",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_sin_filas_lo_unico_que_hay_es_la_palabra_del_worker.py"]},
        {"id": "4.76", "title": "El id del canvas y la instancia son la misma hoja — y una devolvía vacío",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_the_canvas_id_and_the_instance_are_the_same_sheet.py"]},
        {"id": "4.75", "title": "Un elemento muerto dice qué hacer — sin perder el mensaje crudo",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_dead_element_says_what_to_do.py"]},
        {"id": "4.74", "title": "Una memoria rechazada dice POR QUÉ — el motivo viaja en el cuerpo",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_rejected_memory_says_why.py"]},
        {"id": "4.73", "title": "El worker PUEDE escribir lo que le decimos que escriba — solo `Write`",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_the_worker_can_write_what_we_told_it_to_write.py"]},
        {"id": "4.72", "title": "Un RELEVO no es un encargo nuevo, tampoco para quien LEE la hoja",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_a_relay_is_not_a_new_errand_for_the_reader.py"]},
        {"id": "4.71", "title": "El puente del worker habla el vocabulario de widgets — y una colisión es una "
                                "negativa, no una apuesta",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_the_bridge_speaks_the_widget_vocabulary.py"]},
        {"id": "4.70", "title": "Una hoja de encargo SIN RESOLVER lo dice — el fallo dejaba de ser mudo",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_an_unresolved_errand_sheet_is_not_silent.py"]},
        {"id": "4.69", "title": "Un «no» bien fundado es una ENTREGA — y rellenar para no volver vacío, no",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_well_founded_no_is_a_delivery.py"]},
        {"id": "4.68", "title": "Un comando RECHAZADO dice qué se intentó — solo cuando el paso falla",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_rejected_command_says_what_was_tried.py"]},
        {"id": "4.67", "title": "El error de payload dice QUÉ falló — y la valla de markdown se tolera, el "
                                "casi-JSON no",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_the_payload_error_says_what_is_wrong.py"]},
        {"id": "4.65", "title": "Un payload que falta dice lo que SÍ hay — y los dos puentes miran el mismo "
                                "sitio",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_missing_payload_says_what_is_there.py"]},
        {"id": "4.64", "title": "Un worker MIRANDO EL MENÚ no es un worker estrellado — falta `cmd` = sonda, "
                                "falta otro argumento = llamada rota",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_reading_the_menu_is_not_crashing.py"]},
        {"id": "4.63", "title": "Que nos BLOQUEEN no es que el mundo esté vacío — el motor lo dice y el arnés "
                                "lee el campo, no la prosa",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_blocked_search_is_not_an_empty_world.py"]},
        {"id": "4.62", "title": "Una recarga es INVISIBLE desde aquí, así que se vuelve a probar — libertad "
                                "condicional al saldo agotado, en las DOS cadenas",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_top_up_is_invisible_so_we_try_again.py"]},
        # 2026-08-27, las cuatro rondas de la primera tanda US: los mismos errores internos en todas
        # («Contains simple_expansion», «Contains brace with quote character»), y en cheapest-monitor se
        # llevaron la ronda entera — 3 navegaciones, 10 búsquedas, CERO productos. La causa era nuestra: el
        # prompt enseñaba `worker_bridge act <accion> {json en línea}`, justo lo que la puerta de permisos
        # rechaza. El rodeo por `@fichero` existía desde V2-379, ese mismo día, y nadie tocó la frase que
        # enseñaba lo contrario.
        {"id": "4.61", "title": "El prompt no enseña lo que el guarda bloquea — payload por `@fichero` y los "
                                "dos rechazos nombrados con las palabras del propio guarda",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_the_prompt_does_not_teach_what_the_guard_blocks.py"]},
        # 2026-08-27, primera tanda US: doce hoteles REALES de Nueva Orleans, en EUROS, contra un presupuesto
        # de $150. Los candidatos eran correctos e inservibles — un sitio decide moneda y mercado por el locale
        # del navegador y la cabecera Accept-Language, no por las palabras de la consulta, y las dos estaban
        # clavadas a España para todo el mundo. El catálogo de sitios YA era locale-aware, así que al worker se
        # le mandaba a los sitios americanos correctos y se les preguntaba en español: media localización.
        {"id": "4.60", "title": "La búsqueda mira desde donde vive la persona — locale del navegador y "
                                "Accept-Language siguen al idioma del motor (con escotilla de env)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_the_search_looks_from_where_the_person_lives.py"]},
        # 2026-08-27 — al poner Z.AI de titular del Brain Worker (decisión del operador) salieron DOS fallos
        # mudos del mismo tronco: un modelo que RAZONA carga su deliberación contra `max_tokens`, así que el
        # brief del compositor volvía truncado con un 200 y sin error («respuesta ilegible» en el log, worker
        # sin dirección); y ese mismo escalón, preguntado por una imagen, no dice que no ve — se la INVENTA
        # (rojo→«Orange», azul→«Teal», un PNG con texto descrito como un CAPTCHA de pasos de cebra).
        {"id": "4.59", "title": "El compositor pide el BRIEF, no la deliberación · y un escalón que no ve se "
                                "declara ciego (no lo que anuncia el proveedor)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/"
                      "test_the_composer_asks_for_the_brief_not_the_deliberation.py"]},
        {"id": "4.54", "title": "El vídeo se PONE, no se rotula · y la boca NOMBRA el que cargó",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_the_video_is_played_not_labelled.py"]},
        # V2-359 — V2-354 puso el hecho delante y el modelo lo contó UNA DE CADA DOS: en bilbao sí («va
        # encallada, no te la estoy escondiendo»), en el coche no, con el operador preguntando tres veces. Esa
        # variancia es la que V2-305 dejó escrita: la conducta determinista la garantiza el código.
        {"id": "2.39", "title": "Una espera nunca calla un atasco que el sistema YA sabe · y si el turno ya lo "
                                "dice, o ya está entregando, el backstop no lo pisa",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_the_music_is_played_not_labelled.py",
                      # V2-380 — el canal de TEXTO resolvía `play_music` a una etiqueta y contestaba «Hecho.»
                      # sobre una reproducción que no existía. La primera ronda que ese caso ha tenido nunca
                      # salió 1/5 con `familias faltantes: ['widget']`: medía un mecanismo INALCANZABLE.
                      "tests/agent_headless/unit/flash/test_a_stall_the_system_knows_is_never_silent.py",
                      # V2-371 — y una PREGUNTA tampoco calla una entrega. La puerta de V2-364 silenciaba el
                      # backstop, el flujo caía al de atasco, y las dos «¿la paro o le doy margen?» que el
                      # juez le reprochó a zaelar en `search-buy-motorcycle__es` las escribimos nosotros —
                      # con once candidatos sin entregar y la segunda ya contestada por el operador.
                      "tests/agent_headless/unit/flash/test_a_question_is_no_reason_to_withhold.py"]},
        {"id": "2.37", "title": "Un paso del worker que afirma la PANTALLA sin respaldo sale marcado «💬» · y "
                                "uno mecánico, o con la hoja llena, no se toca",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_worker_phase_that_claims_the_screen.py"]},
        # V2-359 — el opener VIVO de la tarjeta fantasma que el barrido de V2-351 no alcanza: el verbo del
        # worker show_widget pasaba «results» TAL CUAL (el worker conoce el NOMBRE, nunca su instancia) y el
        # frontend abría la BASE vacía encima de la hoja del encargo. Intermitente: solo los workers que lo
        # invocan (bilbao 08:38 — 85 escrituras, 22 presentaciones — y coche 08:03). La decisión de 246007a
        # aplicada al canal worker: con hoja, «results» resuelve a results::<hoja>; sin hoja, la base se
        # conserva (la hoja de siempre ES su hoja).
        {"id": "2.38", "title": "«show results» de un worker es SU hoja — la base no se abre encima de su "
                                "propia instancia",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_show_results_means_my_results.py"]},
        {"id": "2.36", "title": "Una tarea que HABLA y no avanza un paso de su plan se dice (SIN AVANZAR) · y "
                                "avanzar rearma el reloj, repetir el mismo done no",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_a_task_that_talks_but_never_advances.py"]},
        {"id": "2.35", "title": "Una nota que afirma estado VIVO se puede RETRACTAR: quien mata la tarea retira "
                                "la pregunta de si pararla · y una llave repetida sustituye, no acumula",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_question_the_system_already_answered.py"]},
        {"id": "2.34", "title": "El lector resuelve la hoja como el escritor (sello, y el registro de respaldo) "
                                "· sin los dos caminos el backstop de entrega no ve una hoja llena",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_the_reader_resolves_the_sheet_like_the_writer.py"]},
        {"id": "2.33", "title": "Un worker RELEVADO deja de escribir en el estado de su relevo · y se le dice "
                                "que lo es, en vez de dejarle reintentar a ciegas",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/workers/test_a_relieved_worker_stops_writing_the_state.py"]},
        {"id": "2.17", "title": "Un «sí» a la confirmación arranca la tarea; no la termina", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_confirm_ack_is_a_start.py"]},
        # 2026-08-20: el turno que llevaba «Resérvame mesa en Casa Lucio» falló en el proveedor y devolvió
        # `ok: False` — la ventana se escribía SOLO al final, así que la petición se fue con él. Cinco turnos
        # después zaelar hablaba del encargo ANTERIOR y decía «no tengo constancia de ese encargo en mi
        # estado»: el juez lo llamó gaslighting y era verdad. Y el fallo del proveedor no se reportaba a nadie,
        # así que un titular muerto seguía muerto turno tras turno (tres silencios seguidos, medidos).
        # 2026-08-20: `authenticate_web` y `login_done` se resolvían en el canal de TEXTO —el que usan los casos
        # de uso— a una ETIQUETA y nada más; la voz llamaba a sus dos closures. Medido: «Aquí lo tienes» con
        # `navegador_task` vacío, así que «ya he entrado» no tenía tarea que reanudar. Los 54 escenarios del
        # segmento `credentials` pasan por ese traspaso.
        # 2026-08-20: el backstop de promesa-sin-acción se gateaba por «nada vivo», y lo que decide es «nada
        # vivo PARA ESTO». Medido: el encargo del hotel no escaló porque seguía vivo un worker del encargo
        # anterior, y luego cuatro turnos de «la reserva sigue en marcha» sobre una tarea de Ticketmaster ya
        # cancelada. Conservador a propósito: ante la duda, la conducta de antes.
        {"id": "2.22", "title": "«¿Hay algo corriendo PARA ESTO?» — un encargo ajeno no suprime la escalada del "
                                "nuevo", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_running_for_THIS_not_just_running.py"]},
        # 2026-08-20: `websearch.search()` devuelve `results: []` con `source: "none"` cuando TODA la cadena
        # falla — indistinguible de «busqué y no hay nada», y el único rastro era un `logger.warning`. Medido en
        # `cheapest-monitor`: veinte búsquedas, cero candidatos, diez turnos de «te aviso en cuanto lo tenga»
        # con la cadena abajo (cuota + CAPTCHA). El resultado no era alcanzable; decirlo sí, y tampoco.
        {"id": "2.21", "title": "Una capa de búsqueda CAÍDA se dice (con su motivo), no se disfraza de «no hay "
                                "nada»", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_a_dead_search_layer_says_so.py"]},
        {"id": "2.20", "title": "El traspaso de inicio de sesión OCURRE en el canal de texto (una decisión, dos "
                                "canales)", "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_login_handoff_actually_happens.py"]},
        {"id": "2.19", "title": "Lo que el operador dijo sobrevive a un turno que falla (y el fallo se reporta)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_what_was_said_survives_a_failed_turn.py"]},
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
            "tests/voice/unit/test_attention.py",
            # V2-338: un 200 con cuerpo vacío no es una respuesta del juez — la regla existía solo en la pata
            # de DeepSeek; GLM vacío se devolvía como respuesta y el relevo (que salta por excepción) no corría.
            "tests/voice/unit/test_an_empty_judge_body_is_not_an_answer.py", "tests/voice/unit/test_endpointing.py",
            "tests/voice/unit/test_turn_boundaries.py"]},
        {"id": "3.2", "title": "Puente voz→nucleo + trazas", "ch": VOICE, "paths": [
            "tests/voice/unit/providers/test_nucleo.py", "tests/voice/unit/providers/test_nucleo_guards.py",
            # ⚠️ SIN MAPEAR hasta el 2026-08-21 (V2-245), los cinco: el acumulador que perdía 64 s del operador en
            # silencio, su acuse hablado, la corrección que NO puede abrir un flujo nuevo, las guardas de fuente
            # de quién puede etiquetar con `voice.trace.active()`, y el latido de cluster que se abría una sesión
            # propia después de que el operador parase el agente. Todos verdes, ninguno corriendo.
            "tests/voice/unit/providers/test_nucleo_accumulator_notice.py",
            "tests/voice/unit/providers/test_nucleo_speak_acc_drop.py",
            "tests/voice/unit/providers/test_nucleo_trace_merge.py",
            "tests/voice/unit/test_agent_trace_source_guards.py",
            "tests/voice/unit/test_trace_cluster_session.py",
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
            "ch": VOICE, "paths": [
            # sin mapear hasta el 2026-08-21: el backend del modal bloqueante de primera ejecución (V2-101)
            "tests/infrastructure/unit/core/test_language_onboarding.py","tests/voice/unit/test_language_bootstrap.py"]},
        # V2-093 (2026-08-14): el relleno de espera («Mmm…», «A ver…») llevaba desde julio SIN SONAR NUNCA. Viajaba
        # por el stream del modelo, y el tokenizador de frases de LiveKit solo entrega un segmento cuando tiene DOS
        # → un relleno suelto (sin punto y de menos de 20 chars) se quedaba en el buffer y salía PEGADO a la
        # respuesta. 48 generados, 0 oídos a tiempo, y el operador diciéndole «parece que te has quedado tonto» a un
        # agente que estaba trabajando. Aquí se reproduce el pegado y se fija la costura fuera de banda.
        # V2-393 — un barge-in no tiene OBJETO: «páralo» va sobre una cosa y se comía el turno entero.
        {"id": "3.14", "title": "«páralo» lleva objeto: no es un barge-in · y «párate» lo sigue siendo",
            "ch": UNIT,
            "paths": ["tests/voice/unit/test_paralo_lleva_objeto.py"]},
        {"id": "3.7", "title": "Relleno de espera: suena MIENTRAS se espera (fuera del stream del modelo)",
            "ch": VOICE, "paths": ["tests/voice/unit/test_lead_in.py",
                                    # V2-122 (2026-08-17): el pool de rellenos ya no es solo un literal hardcodeado
                                    # — pick_filler() mira PRIMERO un pack generado por idioma antes de caer al
                                    # catálogo es/en; este test file nuevo cubre esa ruta de lectura.
                                    "tests/voice/unit/test_lang_fillers_store.py"]},
        # V2-220 (2026-08-20): la OTRA entrega fuera de banda, y llevaba rota para medio producto. La nota al
        # cerebro de `proactive.notify` vivía DENTRO del `if speak and _speaker is not None`, así que sin sesión
        # de voz viva —el canal de TEXTO, que es lo que conduce el arnés y lo que usa un operador en chat— un
        # aviso proactivo llegaba al panel de observabilidad y se quedaba ahí. Afecta al aviso de atasco del
        # bucle, al final de un worker, a mensajería y a Architect.
        {"id": "3.11", "title": "Un aviso proactivo llega a la conversación TAMBIÉN sin sesión de voz",
            "ch": VOICE, "paths": ["tests/voice/unit/test_proactive_reaches_the_text_channel.py"]},
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
        # 2026-08-21, encargo del operador: «seteamos un punto en el tiempo y le pasamos ese texto a partir de ahí
        # al modelo». Actuar era TODO-O-NADA (`clear()` en las cuatro salidas), así que un fragmento que cerraba la
        # frase A y empezaba la B mandaba las DOS dentro de la petición de A — B no se borraba, VIAJABA dentro, y
        # solo A se contestaba. Por eso el test afirma «B no viajó en la petición de A y sigue en el buffer» y no
        # «B no se perdió»: lo segundo pasa en verde sobre el código roto. Solo se pela una cola COLGANDO (resto
        # incompleto por capa 1); dos frases completas de un tirón son UNA petición y viajan juntas. Incluye la
        # otra mitad de «nada se pierde»: el rescate de lo descartado por hueco largo vivía detrás del guarda de
        # «¿hay altavoz?», así que en el canal de prueba —o hablando encima— desaparecía sin nota ni juez.
        {"id": "3.12", "title": "Marca de agua: se entrega la frase cerrada, el principio de la siguiente SIGUE "
                                "vivo, y lo descartado se rescata aunque no haya boca para decirlo",
            "ch": VOICE, "paths": ["tests/voice/unit/test_the_watermark_leaves_the_tail_alive.py"]},
        # 2026-08-23 — la MISMA sesión que motivó la marca de agua, pero una capa antes: el segmentador solo pegó
        # basura porque el STT se la dio. Deepgram partió «Calatayud» en «cal»+«a» y el destilador acabó
        # escribiendo que el operador vive donde no vive. El refuerzo de términos actúa ANTES del daño; todo lo
        # demás es reparar una frase que ya nació mal. Medido contra la API viva: el tope es de 500 SUB-TOKENS
        # (≈114 nombres reales), y pasarse es un 400 en la petición de escucha — o sea el motor SORDO, que es peor
        # que el fallo que arregla. De ahí que la mitad de los tests sean el sobre y no la función.
        {"id": "3.13", "title": "Refuerzo de términos del STT: los topónimos que nova-3 destroza, y una lista que "
                                "no puede crecer hasta dejar el motor sordo",
            "ch": VOICE, "paths": ["tests/voice/unit/test_stt_gazetteer.py"]},
    ]},
    {"id": "4", "name": "WIDGETS", "nodes": [
        {"id": "4.1", "title": "Ciclo de vida / acciones / refs / generador / background", "ch": UNIT, "paths": [
            # sin mapear hasta el 2026-08-21 (V2-158 otra vez): todo `widget.js` del catálogo tiene que PARSEAR
            "tests/browser/unit/widgets/test_widget_js_parses.py",
            "tests/browser/unit/widgets/test_lifecycle_confirm.py", "tests/browser/unit/widgets/test_actions.py", "tests/browser/unit/widgets/test_refs.py",
            "tests/browser/unit/widgets/test_generator_sync.py", "tests/browser/unit/widgets/test_background.py",
            # V2-242: una píldora escrita por un cron de widget no es un hecho sobre la persona. Los lectores
            # separan «hechos del operador» de «píldoras de fondo» POR LA FORMA DE LA CLAVE, y nada impedía que
            # un tick escribiera `operator.location` — ni que una nota sin slot cayera bajo «LO QUE SABES DEL
            # OPERADOR». El candado va en la escritura, que es lo único que sabe quién es el autor.
            "tests/browser/unit/widgets/test_a_background_pill_is_not_an_operator_fact.py",
            "tests/browser/unit/widgets/test_aliases.py", "tests/browser/unit/widgets/test_identify_context.py",
            "tests/browser/unit/widgets/test_resolver_certainty.py", "tests/browser/unit/widgets/test_system_surfaces_sync.py",
            "tests/browser/unit/widgets/test_paths_workspace.py"]},
        {"id": "4.2", "title": "Navegador (browser)", "ch": UNIT, "paths": [
            # V2-247: traer el elemento a la vista es una CORTESÍA, no el clic. Iba SIN proteger, así que un
            # elemento tapado o despegado tumbaba la acción entera — tres `scroll_into_view_if_needed` con Exit
            # code 1 en un mismo worker, y ese worker muerto (arnés, 2026-08-21).
            "tests/browser/unit/navegador/test_the_courtesy_does_not_kill_the_click.py",
            # V2-253: unos argumentos ILEGIBLES no son una acción sin argumentos. `_next_action` devolvía el
            # nombre con `{}` y el bucle ejecutaba `click` sin ref o `type` sin texto — la familia de V2-171, y
            # peor, porque no se descartaba: se actuaba. Sale del barrido de topes del cluster (2026-08-21).
            "tests/browser/unit/navegador/test_illegible_args_are_not_an_action.py",
            # V2-248: un `ref` caducado decía QUÉ pasaba y no CÓMO salir (`ref 26 no existe`, la forma de
            # V2-212). Mismo contrato que el nodo 4.20 — y NO se reintenta con la mirada nueva: los números se
            # reparten al mirar, así que el mismo número es otro elemento.
            "tests/browser/unit/navegador/test_a_stale_ref_says_how_to_get_out.py",
            # V2-281: una PESTAÑA sobrevive al worker que la abrió, y su hoja se resolvía por el registro de
            # sesiones VIVAS — así que un hallazgo que llega tras la muerte del record (o tras un relevo) caía
            # en la hoja PELADA, la que no es de nadie: 24 filas ahí contra 12 en la del encargo, y esa caja
            # huérfana es la «tarjeta fantasma» del canvas. Se sella al nacer, como el `trace` de V2-108.
            "tests/browser/unit/navegador/test_the_tab_remembers_its_errand.py",
            # V2-284: la señal de «ya encontró algo» era un REPORTE VOLUNTARIO (`hbnote considered --kept N`) y
            # el worker no siempre lo hace: en tres de los cuatro casos de la tanda del 2026-08-24 la cara no
            # salió NI UNA VEZ mientras el navegador extraía resultados reales, y el veredicto de los tres fue
            # «tuvo resultados y no los entregó». Las filas de la hoja no dependen de que nadie se acuerde.
            "tests/browser/unit/navegador/test_the_found_signal_does_not_wait_to_be_told.py",
            # V2-298: la cara ORDENABA contar «QUÉ ha encontrado, con nombre y precio» y el bloque solo
            # llevaba el CUÁNTO — la hoja tenía 27 candidatas 250 s antes del último turno y el modelo
            # contestó «déjame ver» (guitarra, ronda 21). Las filas van en el bloque; el DÓNDE (pantalla/
            # hoja) sigue prohibido de afirmar, que es la frontera de V2-278.
            "tests/browser/unit/navegador/test_the_face_carries_the_rows_it_orders_to_tell.py",
            # V2-302: a los 21 s de tarea el turno dijo «lleva un rato… ¿la paro?» — sin la EDAD delante, el
            # modelo rellena el hueco con «un rato» y ofrece matar una tarea recién nacida (ronda 29).
            "tests/browser/unit/navegador/test_a_young_task_says_its_age.py",
            # V2-308: «SIN MOVERSE de esa página» exige que HAYA página — sin url ni pasos, `stalled_s` mide
            # desde el nacimiento y declaraba BLOQUEADA una tarea que solo arrancaba (ofreció relanzar ×4).
            "tests/browser/unit/navegador/test_a_task_without_a_page_is_not_stuck.py",
            # V2-310: una pestaña de ENCARGO cuyo worker murió seguía contándose «YA EN CURSO» — zaelar decía
            # la verdad («se cortó por el límite de sesión») contra un bloque que afirmaba lo contrario.
            "tests/browser/unit/navegador/test_a_tab_without_a_driver_says_so.py",
            # V2-321: `telText` leía `2026-08-25 12` como teléfono (ISO: 10 dígitos, guiones y espacio, los
            # tres separadores admitidos). Y un teléfono falso ASCIENDE la fila por `by_amount`, así que el
            # mobiliario del pie se llevaba el top-5 que ve el cerebro.
            "tests/browser/unit/navegador/test_a_date_is_not_a_phone_number.py",
            # V2-323: un listado VIRTUALIZADO no tiene sus fichas hasta que te acercas. Medido en autoscout24:
            # 0 anclas sin desplazarse, 40 tras hacerlo. «Cero filas» no es «sin resultados», y el
            # discriminador es el ALTO de la página (11,5× frente a 0,2× de una búsqueda vacía de verdad).
            "tests/browser/unit/navegador/test_a_page_that_paints_on_approach.py",
            # V2-324: dos anclas al mismo anuncio y ganaba la PRIMERA del DOM, que era la muda («Abrir detalles
            # del anuncio»); la que nombraba se tiraba por duplicada y el borrado de genéricos —correcto— dejaba
            # las 19 filas sin nombre. El dato estaba en la página y lo tirábamos.
            "tests/browser/unit/navegador/test_the_anchor_that_names_wins.py",
            # V2-318: la cabeza mandaba «cuenta QUÉ ha encontrado» y el bloque de filas «di solo lo que
            # RESPONDE»; ganaba la primera. Con tres filas y ninguna válida, ofreció un COLGADOR de guitarra.
            "tests/browser/unit/navegador/test_when_nothing_in_the_sheet_fits.py",
            # V2-330: sin filas escritas, la cara ordenaba «CUÉNTALE con nombre y precio» — un imperativo
            # IMPOSIBLE. Medido: 14 turnos sin filas, 79 % contestan «te aviso». Cinco de los diez casos con
            # mecanismo ≥4 y resultado ≤3 traían ese veredicto.
            "tests/browser/unit/navegador/test_no_rows_no_order_to_recite.py",
            # V2-334: una ruta que comparten decenas de anclas no es la ficha de nada. Medido: ficha real 2
            # anclas · /redirigir 26 · /privacy-policy 297 · enlace a la propia página 2083.
            "tests/browser/unit/navegador/test_a_shared_destination_is_not_a_listing.py",
                                  # V2-293: el worker pidió precio MÁXIMO 150 € y la página aplicó
                                  # `min_sale_price=750`. La URL venía entera y el parámetro nuevo no se
                                  # ve dentro de una línea larga; lo que faltaba era el DELTA.
                                  "tests/browser/unit/navegador/test_the_url_says_what_changed.py",
                                  # V2-294: una página a medio hidratar devuelve filas HUECAS (enlace
                                  # puesto, título vacío, «0 €») y eso no es «sin resultados». El worker lo
                                  # diagnosticaba él solo y gastaba dos vueltas; en dos casos la ronda se
                                  # acabó antes de que se recuperara.
                                  "tests/browser/unit/navegador/test_a_half_loaded_page_is_not_empty.py",
            # sin mapear hasta el 2026-08-21: el muro de login en la NUBE cierra en limpio en vez de dar vueltas
            "tests/browser/unit/navegador/test_cloud_login_bailout.py",
            "tests/browser/unit/navegador/test_auth.py", "tests/browser/unit/navegador/test_tasks_dedup.py",
            # 2026-08-20: dos filtros enumeraban a mano subconjuntos de los estados de una tarea, y un estado
            # que no estaba en ninguno era una tarea que el estado vivo NO MENCIONABA — ni viva ni terminada.
            # Costó `cancelled` (V2-196) y, al unificar, apareció `open` en el mismo hueco desde siempre.
            "tests/browser/unit/navegador/test_task_states_are_enumerated_once.py",
            # 2026-08-20: dos arreglos seguidos pasaron sus tests sin hacer NADA en producción (V2-199, V2-200).
            # Los dos se encontraron preguntándole al código si el estado que el test construye llega a
            # existir. Este fichero es esa pregunta, hecha una vez: cada cara del bloque tiene que tener quien
            # la escriba fuera de los tests.
            "tests/browser/unit/navegador/test_every_face_is_reachable.py",
            # 2026-08-17 modularization pass: DOM/human-input primitives split out of owner.py into dom.py
            # (page-parametric, no module-global coupling) -- first standalone coverage for this path, plus a
            # regression lock on `mouse` now being required (the old None-fallback was dead code).
            "tests/browser/unit/navegador/test_dom.py",
            # V2-152: a worker-driven task never wrote a milestone, so `active_progress` reported 0 steps for
            # its whole life and the brain had a step COUNT of zero to describe it with.
            "tests/browser/unit/navegador/test_navigate_milestone.py",
            # V2-167: tres corridas acabaron con la tarea en `working`/`results:null` después de que el operador
            # se rindiera. Faltaban DOS hechos, no uno: cuánto lleva sin MOVERSE (recapturar la misma página no
            # es avanzar) y si la página en la que está es un MURO — Booking `chal_t`, el CAPTCHA de Google, un
            # error de carga. Sin ellos el turno solo podía decir la verdad inútil de que la tarea seguía viva.
            "tests/browser/unit/navegador/test_task_stall_and_wall.py",
            # V2-167 SEGUNDA ronda: con el arreglo, las tareas ya TERMINAN — pero llegan a `status=done` con
            # `phase_active=True` y la fase de vuelo intacta, así que el turno vuelve a leer un estado que miente,
            # solo del revés. Los xfail son la deuda DECLARADA: cuando el arreglo entre, saldrán XPASS.
            "tests/browser/unit/navegador/test_task_finish_is_coherent.py"]},
        {"id": "4.3", "title": "Widget de música", "ch": UNIT, "paths": ["tests/browser/unit/musica/test_data.py",
                                                                 "tests/browser/unit/musica/test_anothers_player_never_advances_the_music_queue.py"]},
        {"id": "4.4", "title": "Widget de YouTube", "ch": UNIT, "paths": ["tests/browser/unit/youtube/test_youtube.py"]},
        {"id": "4.5", "title": "Widget de mensajería", "ch": UNIT, "paths": ["tests/browser/unit/mensajeria/test_owner_v2.py"]},
        {"id": "4.6", "title": "Agenda: contrato XSS del renderer", "ch": UNIT, "paths": [
            # sin mapear hasta el 2026-08-21: vaciar la agenda en UNA acción, y que un «sí» a una data-op
            # irreversible la EJECUTE (por voz y por botón) — el «no funciona el borrado» del operador
            "tests/browser/unit/agenda/test_agenda_clear_all.py",
            "tests/browser/unit/agenda/test_confirm_data_op.py",
            "tests/browser/unit/agenda/test_xss_contract.py",
            # V2-208: la MISMA cita dos veces. V2-194 lo cerró para el BACKSTOP y la data-op del propio modelo no
            # tenía guarda — dos turnos, dos `add_meeting`, nadie comparando. Ahora vive junto a la ESCRITURA,
            # que es por donde pasan todos los que escriben.
            "tests/browser/unit/agenda/test_the_same_meeting_twice.py"]},
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
                                  "tests/browser/unit/widgets/test_presentation_quality.py",
                                  # 2026-08-24: la hoja llevaba 42 anuncios con su enlace y el digest del prompt
                                  # cargaba todos los campos del item MENOS ése, así que un «pásame el enlace»
                                  # se contestaba relanzando la búsqueda.
                                  "tests/browser/unit/widgets/test_the_link_is_on_the_card.py"]},
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
        # The source-level node above cannot see that the orb is a black hole in the middle of the bar: on
        # 2026-08-18 it was, at 0 painted pixels, while that node stayed green counting canvases. This one
        # RENDERS the shell at phone size and measures it. Self-contained (it starts its own preview server,
        # so it needs no `make run`) and non-destructive (it taps the power switch, which against a live
        # engine would stop the operator's agent).
        # 2026-08-20: V2-167 puso `wall` y V2-186 puso `hint` en cada respuesta del puente PARA EL WORKER, y
        # `nav_cli._print_state` —su única vista de la página— no imprimía ninguno de los dos. Dos arreglos que
        # viajaban por HTTP y morían a una línea de su lector. El último test es el contrato: lo que el puente
        # anota, el CLI lo dice (impreso o renderizado por otro campo que sí se imprime).
        {"id": "4.20", "title": "Al worker se le DICE qué le paró: el muro y el atasco salen por su CLI",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_the_worker_is_told_what_stopped_it.py",
                      # V2-205: y no se le OFRECE lo que no existe — `_shot_path` devolvía la ruta del PNG
                      # estuviera o no en disco, y el CLI convierte cualquier valor en la orden «MÍRALA con
                      # Read». Medido en dos corridas: «File does not exist».
                      "tests/browser/unit/navegador/test_we_only_offer_a_screenshot_that_exists.py",
                      # V2-207: y los MUROS salen por la vista de la tarjeta. Desde fuera del proceso «no se
                      # anotó» y «se anotó y el turno lo ignoró» se veían idénticos, y son diagnósticos
                      # opuestos.
                      "tests/browser/unit/navegador/test_the_card_view_carries_the_walls.py",
                      # V2-369: y un verbo que va a una URL, sin la URL, decía solo la FORMA. Medido en
                      # `rental-car-automatic-airport__es`: `navigate` pelado DOS veces con 42 s de por
                      # medio, mientras el `act` pelado —que sí lleva pista— falló una vez y no se repitió.
                      "tests/agent_headless/unit/test_a_url_verb_without_its_url_says_how_to_get_out.py",
                      # V2-379 — y el JSON que no cabe en la línea de comandos. NUESTRA puerta rechaza un
                      # argumento con llaves y comillas; el worker dio con el rodeo por fichero él solo y el
                      # puente `act` no sabía leerlo, mientras `widget_cli` lo acepta desde V2-203.
                      "tests/agent_headless/unit/test_a_payload_that_does_not_fit_the_command_line.py"]},
        # 2026-08-20: el confirm-gate paraba un clic irreversible y no preguntaba a NADIE — la pregunta se
        # escribía en la tarea y nada la sacaba de ahí, y `waiting_id()` no tenía ni un llamador en producción,
        # así que el «sí» del operador tampoco tenía dónde aterrizar. Este nodo cubre las dos mitades: que la
        # pregunta llega al estado que lee el cerebro, y que la respuesta vuelve al clic que está esperando.
        {"id": "4.21", "title": "El confirm-gate PREGUNTA a alguien, y su «sí» vuelve al clic parado",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_the_confirm_gate_asks_someone.py"]},
        # V2-215 — la OTRA mitad de 4.21, y la que faltaba: 4.21 cubre que la pregunta llegue al estado que el
        # cerebro lee CUANDO le preguntan cómo va. Esto cubre que el muro y la pregunta lleguen a la conversación
        # SIN que nadie pregunte. Medido con brain-notes=0 en dos rondas mientras la tarea llevaba `wall` y
        # `question` puestos: el hecho estaba en el registro y en la tarjeta, y en ningún sitio que el operador
        # oyera.
        {"id": "4.22", "title": "El muro y la pregunta ENTRAN en la conversación, sin que él pregunte",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_the_task_tells_the_conversation.py"]},
        # V2-221 — la otra mitad, y la que queda: ENTREGA vs OBEDIENCIA. El arnés leyó el prompt de cada turno
        # de `hotel-under-15-days` y encontró OCHO turnos seguidos con «… FALLÓ» delante contestando «sigo con
        # ello, te aviso», sin muro ni pregunta de por medio. El hecho llegaba; la instrucción de V2-198 era
        # CONDICIONAL («si el operador pregunta por ello») y una tarea muerta no es una pregunta pendiente.
        {"id": "4.23", "title": "Una tarea de fondo MUERTA se dice sin que él pregunte",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_a_dead_task_is_not_a_pending_question.py"]},
        # V2-222 — y por qué 4.23 midió 0 de 7 en la ronda que lo llevaba: el mismo prompt decía la tarea VIVA al
        # 40 % y MUERTA, con la misma cadena de objetivo, en siete de los ocho turnos. El turno no desobedecía —
        # elegía la mitad cierta. Un encargo que se reintenta solo no es un encargo que acabó.
        {"id": "4.24", "title": "Una tarea que se reintenta sola no se declara muerta (y la muerta se EMPUJA)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_a_retried_task_is_not_a_dead_task.py"]},
        # V2-223 — el bloqueador de verdad del caso: el navegador SACÓ «Exe Sevilla Macarena, 65 €» con enlace y
        # dieciséis segundos después el turno dijo «sigo pendiente». No estaba en el prompt ni en la hoja.
        {"id": "4.25", "title": "Lo que el navegador ENCUENTRA llega a la hoja y a la conversación",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_what_the_browser_finds_reaches_someone.py"]},
        # V2-224 — la cláusula anti-repetición de 4.23 medida en DOS rondas del MISMO commit dio fallos OPUESTOS:
        # en una repitió el aviso cinco turnos, en la otra se calló entero y volvió a «sigo con ello». «¿Ya se lo
        # dije?» era una deducción del modelo; ahora es un hecho que contamos. Callar la repetición ≠ callar el
        # estado.
        {"id": "4.26", "title": "Decirlo una vez no es olvidarlo: el aviso se calla, el estado no",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_saying_it_once_is_not_the_same_as_forgetting_it.py"]},
        # V2-225 — el compositor de investigación LEÍA la cadena de proveedores y nunca la ESCRIBÍA, así que su
        # relevo no podía dispararse: mismo proveedor agotado elegido tres veces seguidas y worker a ciegas.
        {"id": "4.27", "title": "El compositor REPORTA el proveedor muerto y releva (no solo lo lee)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/flash/test_the_composer_reports_a_dead_provider.py"]},
        # V2-227 ámbito C — el contrato de PANTALLA (4.29) monta `widget.js` en una página en blanco y le pasa a
        # mano tres cargas útiles: prueba que la hoja se COMPORTA cuando le llegan los datos, no que alguien los
        # produzca. Faltaba justo eso — `view_data()` no devolvía `progress` y nadie abría la hoja al encargar —,
        # o sea un contrato cumplido en un test y ausente en el producto. Este nodo es el CABLEADO: el progreso
        # derivado del registro vivo (nunca guardado), la hoja abierta al ENCARGAR, el clic del operador en
        # «Proceso» persistido, y el final que para el loader y deja la historia con el informe.
        {"id": "4.28", "title": "La hoja es la superficie del PROGRESO EN VIVO: se abre al encargar, deriva las "
                                "fases del registro vivo y al acabar conserva la historia",
            "ch": UNIT,
            "paths": ["tests/browser/unit/widgets/test_sheet_is_the_live_process_surface.py"]},
        # V2-296 (encargo del operador, 2026-08-24). La pestaña contaba QUÉ hacía y no CUÁNTO llevaba hecho. Dos
        # nodos porque son dos averías distintas: la rejilla puede pintar perfecto cifras que nadie produce, y la
        # cadena puede producirlas y no llegar a pantalla. El de PANTALLA fija sobre todo cuándo CALLARSE —`{}`
        # no es cero— y que el embudo se lea como una resta: eso salió de RENDERIZARLO, porque la geometría estaba
        # bien a los cinco anchos y la captura seguía leyéndose mal (siete cajas iguales convierten una resta en
        # cinco cifras sueltas, y a 360 px «22 candidatos» cae al lado de «5 sin precio» como si fuera su par).
        {"id": "4.30", "title": "La cosecha en pantalla: «no lo sabemos» no es cero, un pilar en cero SÍ se "
                                "pinta, un descarte en cero no, y el embudo se lee como una resta",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_harvest_grid.py"]},
        # …y el CABLEADO: tally → sheet_harvest → view_data → persistido por end_task. El eslabón que de verdad
        # cubre es el último: cuando el encargo muere no hay registro vivo del que leer, y sin persistir la rejilla
        # se apaga justo cuando el operador va a leer el informe.
        # La pestaña DICE de qué hoja es. El sello existe desde V2-281 y vivía solo dentro del proceso, así
        # que desde fuera «nunca se selló» y «se selló y algo lo ignoró» se leían igual — y por ese sello
        # resuelve `_sheet_has_rows` si el encargo ya tiene filas. Mismo hueco que cerró V2-207 con `wall`.
        # El navegador es conexión DIRECTA y no espera. Medido: una acción real cuesta ~4 s y el tope estaba
        # en 90 — veinte veces. Y lo caro no era esperar: `page.evaluate` no tiene timeout en Playwright, así
        # que una página navegando colgaba la mirada POSTERIOR a una acción que YA había funcionado, y el
        # worker recibía un fallo y la repetía. Norma del operador: ni noventa segundos bajo ningún concepto.
        # LEER UNA FICHA SIN PERDER EL LISTADO (petición del operador: «abrir bastantes pestañas para
        # investigar y valorar cada una de las fichas»). Antes solo existía `navigate`, que se lleva la
        # ÚNICA pestaña: mirar un anuncio costaba perder el listado y volver a buscarlo, dos navegaciones
        # por ficha. Medido: navigate al listado 8,24 s · extract 0,02 s · visit 0,85 s con el listado intacto.
        {"id": "4.46", "title": "Una ficha se lee en SU pestaña y el listado no se pierde (visit)",
            "ch": UNIT, "paths": ["tests/browser/unit/navegador/test_a_card_is_read_in_its_own_tab.py"]},
        {"id": "4.45", "title": "Ninguna espera del navegador llega a 90 s, y una lectura lenta no falsea un fallo",
            "ch": UNIT, "paths": ["tests/browser/unit/navegador/test_the_browser_never_waits_ninety_seconds.py"]},
        {"id": "4.44", "title": "La pestaña expone su hoja (el sello que lee _sheet_has_rows)",
            "ch": UNIT, "paths": ["tests/browser/unit/navegador/test_the_tab_says_which_sheet_it_belongs_to.py"]},
        {"id": "4.43", "title": "La cosecha LLEGA a la hoja y sobrevive a que el encargo muera (y la de otra "
                                "hoja no se cuela)",
            "ch": UNIT, "paths": ["tests/browser/unit/widgets/test_the_harvest_reaches_the_sheet.py"]},
        # Del arnés (`arnes-use-cases`), no se toca desde el motor: es la especificación EJECUTABLE de lo que ve
        # una persona esperando. RENDERIZA a propósito — un test de fuente puede dar por buena una pestaña que no
        # pinta nada o un loader que está en el DOM y no anima (la lección del orbe del móvil, nodo 4.19).
        # V2-320-A (2026-08-25, familia «hoja vacía» del arnés, 9/28 rondas). Medido en vivo en kayak.es/cars:
        # «381 resultados» en pantalla, 27 nodos con precio, y el extractor a CERO por construcción — cada oferta
        # es un div con botón «Ver oferta», y el bucle de candidatos solo recorre a[href]. El recolector nuevo
        # parte de las HOJAS con precio, sube hasta el límite de la tarjeta (un solo precio) y coge el nombre del
        # aria-label más largo (el único sitio donde kayak escribe el modelo). GATED en que el de anclas salga
        # VACÍO: Wallapop/Amazon no pueden ni enterarse. Se prueba RENDERIZANDO un fixture con la forma medida.
        {"id": "4.47", "title": "Una tarjeta SIN ancla también es un resultado (y el camino de anclas no se "
                                "mueve ni un pelo)",
            "ch": UNIT, "paths": ["tests/browser/unit/navegador/test_a_card_without_an_anchor_is_still_a_result.py"]},
        # V2-335 (2026-08-26, medido en vivo en tres comparadores con el extractor real): un importe dentro de
        # la PROSA del enlace se convertía en el precio de la fila — acierto.com entregaba 8/8 basura (los
        # enlaces de prestamos del footer, «Préstamos 2.000 euros», con el patrón casando el PREFIJO de la
        # palabra «euros»), kompara.es servía teasers de artículo con el importe a mitad de frase («…cobrar
        # hasta 314 € de penalización…»), kelisto.es colaba «Los mejores préstamos de 1.000 euros» entre las
        # 25 tarifas reales. La propiedad: un precio se escribe «€» o «EUR» y vive casi solo en su nodo
        # (priceIn, UNA disciplina para el propio ancla y para el paseo de tarjeta). El superviviente se
        # afirma por su ENLACE: el rescate sin anclas fabrica títulos pero jamás una URL.
        {"id": "4.48", "title": "Un importe dentro de la PROSA del enlace no es un precio (y la tarjeta real no "
                                "pierde el suyo)",
            "ch": UNIT, "paths": ["tests/browser/unit/navegador/test_an_amount_in_the_prose_is_not_a_price.py"]},
        {"id": "4.29", "title": "Contrato de PANTALLA de la hoja de proceso RENDERIZADO (pestaña activa, fases en "
                                "orden, loader ANIMANDO, salto al primer resultado, historia al acabar)",
            "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/browser/e2e/results/render_process_tab.py"},
        # V2-234 — V2-223 hizo que lo extraído llegara al cerebro; nadie miró QUÉ tres filas llegaban. `items[:3]`
        # en orden de DOM, y los enlaces de categoría salen antes que las fichas de producto en cualquier listado,
        # así que el corte se comía el resultado por construcción: el turno describió «categorías de portátiles,
        # móviles y tablets» con tres monitores reales a 99 € dos líneas más abajo, fuera de la nota.
        # V2-343 — la FRECUENCIA de lo que se enseña. Medido en la sesión `7575e81a` (2026-08-26, 21,6 min):
        # el motor capturó 292 eventos de navegador —uno cada 4 s— y a la pestaña de Proceso llegaron 8 líneas,
        # una cada 162 s. El dedup no se comía nada (las 8 eran distintas y buenas): es que nadie mandaba las
        # demás. `_say_phase` tenía UN llamante —`found()`, tras extraer— y la otra vía llega por Bash, o sea
        # como «ejecutando un paso», constante que el dedup colapsa con razón a una línea.
        {"id": "4.49", "title": "Cada paso del navegador llega a la pestaña de Proceso · con el host que lo "
                                "distingue, y sin romper el dedup que protege del ruido",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_every_browser_step_reaches_the_screen.py"]},
        # V2-346 — y el mismo corte UNA CAPA MÁS ARRIBA, entre filas. Las nueve de cabeza llevaban nombre y
        # precio, así que pasaban las dos guardas de abajo; el nombre era el enlace «ver todos los vehículos de
        # este concesionario» que cada tarjeta lleva dentro. El turno anunció «en OcasionPlus Arganda hay uno
        # por 11.565 euros» y el juez lo puso de bloqueador nº1. Un nombre que comparten todas no nombra a
        # ninguna: es la regla de `cardWalk`, subida de los nodos a las filas.
        {"id": "4.50", "title": "Un nombre de plantilla compartido por las filas no identifica a ninguna (el "
                                "concesionario no es un coche) · y el mismo producto en cuatro tiendas sí",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_a_name_shared_by_every_row_names_none.py",
                      # V2-375 — la MISMA regla por el otro extremo: los 16 candidatos de
                      # `weekend-plan-barcelona__es` acababan en «- Actividad relacionada». Trato distinto:
                      # el prefijo DEGRADA (sin él no hay identidad), la coletilla se RECORTA (la identidad
                      # está entera delante).
                      "tests/browser/unit/navegador/test_a_tail_shared_by_every_row_is_not_a_name.py"]},
        # V2-347 — la causa RAÍZ de las filas de arriba: RUTAS no es FICHAS. El <article> real de autoscout24
        # lleva 2 rutas (la ficha ×2 + el CONCESIONARIO) y el paseo del precio con maxPaths=1 rompía en el
        # nivel 1 → cero candidatos con ancla → el respaldo por hojas fabricaba filas sin url (el worker
        # degradado a leer capturas, ~14 s por ciclo). Cuando el ancla ES de clase ficha, el tope cuenta solo
        # rutas de esa clase; la rejilla (19+ fichas) sigue rompiendo — la protección anti-vecina, re-afirmada.
        # Fixture: EXTRACTO VERBATIM de la página real guardada — un lookalike a mano es como este defecto
        # se quedó invisible.
        {"id": "4.51", "title": "El enlace del concesionario no cierra la tarjeta: autoscout sale con "
                                "título=coche y url=ficha (y la rejilla sigue frenando el paseo)",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_a_dealer_link_does_not_close_the_card.py"]},
        {"id": "4.52", "title": "El widget de YouTube tiene LISTA: los vídeos suenan uno detrás de otro (add nunca autoreproduce, ended avanza solo, next/previous/play_item, close conserva la lista)",
         "ch": UNIT, "paths": ["tests/browser/unit/youtube/test_a_playlist_plays_one_after_another.py"]},
        {"id": "4.53", "title": "La lista de YouTube RENDERIZA: filas de texto, click reproduce, el ended del player avanza SOLO desde nuestro player (cross-talk con musica) y un agente parado no avanza",
         "ch": UNIT, "paths": ["tests/browser/unit/youtube/test_the_list_renders_and_the_player_drives_it.py"]},
        {"id": "4.31", "title": "El cromo de navegación no ocupa la cabecera de la nota (una fila sin título no "
                                "es un resultado) · y lo que queda fuera se cuenta, no se calla",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_the_junk_row_does_not_win_the_turn.py",
                      # V2-370 — la misma nota, con el encargo YA entregado detrás. «Esa página no está dando
                      # lo que pidió» es correcto en mitad de la búsqueda y es un veredicto falso al final:
                      # el turno cerró `search-buy-bicycle__es` con esa frase casi literal tras haber
                      # entregado dos bicis reales. Lo que cambia es el ALCANCE, no el hecho.
                      "tests/browser/unit/navegador/test_an_empty_page_is_not_the_end_of_the_errand.py",
                      # V2-374 — y la SEGUNDA mitad de V2-234, que la CARA nunca tuvo: cortaba en cinco y se
                      # callaba, así que para el turno esas cinco eran la hoja entera. Con catorce candidatos
                      # dentro, las cinco visibles fueron una cámara y cuatro accesorios.
                      "tests/browser/unit/navegador/test_five_rows_of_fourteen_are_not_the_sheet.py",
                      # V2-376 — y lo que vuelve de una BÚSQUEDA es una pista, no un candidato: 52
                      # «candidatos» en `weekend-adventure-sports-bilbao__es` que eran una comparativa, una
                      # noticia y dos portadas. V2-320 sigue en pie (la hoja no puede quedarse vacía cuando
                      # el encargo se resuelve buscando); lo que faltaba es que la fila diga lo que es.
                      "tests/browser/unit/navegador/test_a_search_return_is_a_lead_not_a_candidate.py",
                      # V2-377 — y un hallazgo SIN encargo no es del encargo de ahora. En
                      # `best-plumber-same-day__es` llegaron un Audi y un SEAT etiquetados «trabajando en la
                      # tarea del navegador» mientras el operador pedía un fontanero: eran de la búsqueda de
                      # coches anterior, con su pestaña aún viva sobre autoscout24.
                      "tests/browser/unit/navegador/test_a_finding_without_an_errand_is_not_yours.py"]},
        # V2-295 — el mismo corte una capa más adentro. Las cuatro filas de cabeza llevaban NOMBRE, así que
        # `by_identity` las dejaba pasar, pero ninguna llevaba precio: lo que se le ofreció a quien pidió «un
        # monitor de 27 pulgadas por menos de 150 €» fueron «Monitores», «Monitor SAMSUNG» y «Monitor de Hípica»
        # a 0 €, con dos MSI de 27" a 100 € justo debajo del corte. Un cero no es un precio.
        {"id": "4.42", "title": "Una fila con nombre pero sin importe ni teléfono no ocupa la cabecera · y el "
                                "directorio sin precios conserva su orden",
            "ch": UNIT,
            "paths": ["tests/browser/unit/navegador/test_a_row_without_a_price_is_not_a_candidate.py"]},
        # V2-235 — el extractor partía el precio («169,00 €» → «00 €»: la coma decimal faltaba de la clase de
        # caracteres) y no cogía el nombre, porque en una rejilla el importe vive en su propio enlace y el nombre
        # en el encabezado de la tarjeta. RENDERIZA a propósito: el fallo solo existe cuando el navegador compone
        # `innerText`, que no es el HTML — leyendo el selector no se ve.
        {"id": "4.32", "title": "El extractor RENDERIZADO contra cinco formas de listado: el precio entero, el "
                                "nombre de la tarjeta, y sin inventarlo cuando no lo hay",
            "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/browser/e2e/navegador/extract_shapes.py"},
        # V2-257 — the browser card was showing findings and the results sheet was opening EMPTY, in the same
        # errand. A `kind:"web"` errand resolves `surface = LIST`, so the sheet opens the moment it is placed —
        # and the three paths that find things (`act_api._hand_over`, `owner._automate`,
        # `dispatch._finalize_web`) all ended at `navegador.tasks.set_results`, which writes the CARD. The WEB
        # worker prompt named `widget_cli` zero times, while the GENERIC one had known about the sheet all
        # along: the same request filled the sheet or did not, depending on which worker it was routed to.
        # That is the `missing_signals: ['widget']` of V2-223, and it was never an extraction failure.
        {"id": "4.35", "title": "El navegador MUESTRA y la hoja GUARDA: una puerta para los tres caminos, la "
                                "tarjeta con título de TAREA y estado en 3 líneas, y el worker sabe que la hoja "
                                "existe",
            "ch": UNIT,
            "paths": ["tests/browser/unit/frontera/test_the_browser_shows_the_sheet_keeps.py",
                      "tests/browser/unit/frontera/test_the_card_paints_a_monitor.py"]},
        # V2-259 F3 — el operador: «si hay 2 widgets de results y el usuario dice "cierra los resultados", la
        # orden debería generar una pregunta de: ¿cuál de las 2 búsquedas cierro, la del coche o la del
        # fontanero?». Es una ambigüedad de OTRO EJE que la de `runtime.identify()`: aquella decide qué PIEZA y
        # ésta llega después, con la pieza clara y sin saber cuál de sus TARJETAS. Antes no podía existir.
        {"id": "4.38", "title": "«Cierra los resultados» con dos abiertas PREGUNTA cuál —nombrando los encargos, "
                                "no los ids— y con una sigue cerrando",
            "ch": UNIT,
            "paths": ["tests/browser/unit/frontera/test_closing_one_of_two_is_a_question.py"]},
        # 2026-08-21, medido en vivo por el arnés: TRES workers conduciendo la MISMA pestaña (46+27+7 acciones
        # entrelazadas), y uno pulsando `click [29]` sobre una página que otro acababa de cambiar. Las refs se
        # reparten al MIRAR (V2-248), así que el mismo número es otro elemento: en una página con botón de pagar
        # eso es una ACCIÓN equivocada, no un resultado sucio. La causa son DOS jueces de parecido que se
        # contradicen sobre el mismo par de textos —`find_duplicate` (Jaccard ≥0.60) dice «distintos» y abre tres
        # workers; `tasks._similar` (≥2 raíces o Jaccard ≥0.40) dice «misma navegación» y les da una pestaña— con
        # los textos reales cayendo en el hueco entre las dos varas (0.333-0.375). Unificar la vara es otro
        # trabajo; esto resuelve la contradicción donde se vuelve física.
        {"id": "4.39", "title": "Una pestaña, un conductor: un worker nunca hereda la pestaña que otro está "
                                "conduciendo, y la continuación sigue reabriendo la de quien ya terminó",
            "ch": UNIT,
            "paths": ["tests/browser/unit/frontera/test_one_tab_one_driver.py"]},
        # V2-261 — el operador lo vio en pantalla: dos segundos después de la tarjeta buena aparecía otra de
        # navegador, BASE y vacía, encima. No la abría nadie: `desktop._persist()` informa del canvas, la ruta
        # NORMALIZA `navegador::t2` a su base, el diff dice «se ha abierto navegador» y esa AUDITORÍA (V2-039)
        # viajaba por el mismo canal que las órdenes. Visto desde V2-047 F9 y solo instrumentado.
        {"id": "4.37", "title": "El canvas no obedece su propio informe: la auditoría de lo que el operador abre "
                                "a mano deja de pintar una tarjeta fantasma",
            "ch": UNIT,
            "paths": ["tests/browser/unit/frontera/test_the_canvas_does_not_obey_its_own_echo.py"]},
        # V2-259 — el operador: «si tenemos un widget de results abierto, búsqueda terminada, y lanzamos otra, se
        # abre un widget nuevo. Con esta regla no cometeremos errores de borrar búsquedas». El borrado ESTABA en
        # el código: la hoja era una sola clave y `begin_task(fresh=True)` la estrenaba —sin resultados ni
        # historial— al llegar el encargo siguiente. La alternativa (reutilizarla) enseñaba los resultados de la
        # búsqueda anterior bajo el título de ésta. Con una clave por encargo la disyuntiva desaparece.
        {"id": "4.36", "title": "Dos búsquedas son dos hojas: estrenar deja de significar borrar, cada tarjeta "
                                "cuenta SU relato, y quien escribe dice en cuál",
            "ch": UNIT,
            "paths": ["tests/browser/unit/frontera/test_two_searches_are_two_sheets.py"]},
        # La otra cara de 4.36, medida el 2026-08-23: si dos búsquedas son dos hojas, un RELEVO de proveedor no
        # puede ser una búsqueda nueva. `session._finish` relanza el mismo objetivo con el escalón siguiente y ese
        # relanzamiento estrenaba `task_id` → hoja nueva: dos cajas para un encargo, una vacía y otra con los 13
        # hallazgos, con el turno señalando la que no era. Heredar la clave y NO estrenarla son la misma decisión.
        {"id": "4.40", "title": "Una entrega YA HECHA no deja de serlo porque la tarea siga corriendo: la nota "
                                "del paso llega ENTERA y el bloque autoriza contarla",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_delivery_in_flight_is_still_a_delivery.py"]},
        {"id": "4.41", "title": "Un RELEVO no es un encargo nuevo: hereda la hoja del encargo y no la estrena "
                                "(estrenarla borra lo que la predecesora ya había entregado)",
            "ch": UNIT,
            "paths": ["tests/agent_headless/unit/test_a_relay_is_not_a_new_errand.py"]},
        # V2-256 — a feedback submission was refused and the panel said NOTHING. Measured on a live engine:
        # `POST /api/feedback` answered `{"ok":false,"error":"send_failed","status":401}` and `send()` was an
        # `if (res && res.ok) {…}` with no else. The thank-you was invisible too, for TWO independent reasons
        # (a bare ternary read once while the tree was built, and its home inside `.fw-new`, which a successful
        # send hides by switching tabs). And an unreachable list was painted as "nothing sent yet" — not a
        # smaller truth, a different and false one.
        {"id": "4.33", "title": "Un envío de feedback que falla lo DICE (y una lista inalcanzable no es una "
                                "lista vacía) · una sola lectura para móvil y escritorio",
            "ch": UNIT,
            "paths": ["tests/browser/unit/feedback/test_a_send_that_fails_says_so.py"]},
        # RENDERS on purpose: 4.33 proves the decision and the wiring, and would still pass with the node in
        # the DOM and zero pixels — which is exactly how the thank-you shipped. This measures box, opacity and
        # that the text is the translation and not the key (a key is truthy and passes any source-level test).
        {"id": "4.34", "title": "El aviso de fallo del feedback RENDERIZADO: conectado, con caja, traducido y "
                                "nombrando el 401 · y el gracias visible en la pestaña a la que se salta",
            "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/browser/e2e/feedback/render_send_failure.py"},
        {"id": "4.19", "title": "Shell MÓVIL RENDERIZADO: el orbe centrado y PINTADO, la barra alcanzable",
            "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/browser/e2e/mobile/render_dock.py"},
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
        # El motor DESECHABLE es uno solo y compartido (`journey` + `use_cases`, unificado el 2026-08-20).
        # `journey` levantaba el suyo y a esa copia le faltaba `ZAELAR_LOG_DIR`, así que sus eventos iban al
        # timeline REAL del operador — medido en vivo: 80 → 243 líneas en una corrida de 4 pasos.
        {"id": "7.14", "title": "Aislamiento del motor desechable: el timeline del operador nunca es el destino",
            "ch": UNIT, "paths": ["tests/platform/tests/test_sandbox_isolation.py"]},
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
        # 2026-08-20: la captura forense de un turno guardaba `system[:8000]` de un prompt de ~19.000, y el
        # estado vivo se compone al FINAL — o sea que tiraba justo la mitad que responde «¿qué vio el modelo?».
        # Casi cuesta un diagnóstico falso: cinco turnos parecían no tener el bloque del navegador con el
        # navegador emitiendo 74 eventos en esa misma corrida.
        {"id": "7.20", "title": "La captura forense de un turno guarda el ESTADO, no solo la persona",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_turn_capture_keeps_the_state.py"]},
        # INI-021 (2026-08-09): la observabilidad pasa de «ver líneas» a «analizar procesos». Un estímulo y todo
        # lo que desencadena comparten CORRELATION ID; cada evento dice de qué instalación y de qué sesión de
        # trabajo salió; y todo eso es consultable por columnas indexadas, no escaneando JSON.
        {"id": "7.7", "title": "Flujos por correlation ID + identidad de instalación + sesión de trabajo",
            "ch": UNIT, "paths": [
            # sin mapear hasta el 2026-08-21 (V2-158): un flujo SOLO nace de cuatro fuentes legítimas
            "tests/cluster/unit/test_flow_origin.py","tests/infrastructure/unit/core/test_observability_flows.py"]},
        # 2026-08-12: por la RAÍZ del repo se escapó información personal del operador a un repo PÚBLICO — un
        # borrador de Brain Worker (`informe.json`) acabó versionado dos veces. El guarda no mira nombres: mira que
        # en la raíz no se versione nada que no sea del proyecto, se llame como se llame.
        {"id": "7.9", "title": "La raíz del repo no versiona datos (fuga de PII, 2026-08-12)", "ch": UNIT,
            "paths": ["tests/infrastructure/unit/test_repo_root_clean.py"]},
        # 2026-08-20: `widgets/clock/` —builtin versionado desde el commit inicial— había desaparecido del árbol
        # de trabajo sin que nadie commiteara el borrado, y la suite ENTERA pasaba igual: nada afirmaba que un
        # widget de sistema declarado exista. Lo que queda no es «un widget menos», es un registro que promete
        # algo que el disco no tiene.
        {"id": "7.19", "title": "Un widget de SISTEMA declarado existe en disco", "ch": UNIT,
            "paths": ["tests/infrastructure/unit/test_builtin_widgets_exist.py"]},
        # 2026-08-14: que el CONTEXTO no se quede atrás del código. La deriva era medible — el log de alineación de
        # contenido iba por la 2.88 con el motor en la 2.94, y 21 decisiones de CLAUDE.md sin iniciativa. Este nodo
        # es la mitad AUTOMÁTICA del cierre (ids únicos, frontmatter cuadrado, decisión↔iniciativa en los dos
        # sentidos), como TRINQUETE: la deuda histórica está declarada y solo puede bajar. La mitad que cruza a
        # `web/` no se puede vigilar desde aquí (vive en el repo privado) → `zaelar-initiative-closure.md`.
        {"id": "7.17", "title": "Un test fuera del mapa no es un test (trinquete de las TRES formas de desaparecer)",
         "ch": UNIT,
         "paths": ["tests/infrastructure/unit/test_a_test_outside_the_map_is_not_a_test.py"]},
        {"id": "7.12", "title": "Cierre de iniciativa: toda decisión tiene iniciativa y al revés (trinquete)",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/test_roadmap_closure.py"]},
        # 2026-08-21: SEGUNDA vez que un helper se cuela ENTRE `@router.<verbo>(ruta)` y el handler que la
        # ruta servía, así que FastAPI registra el helper y el handler real queda inalcanzable. La primera
        # (`_with_wall`, 2026-08-20) devolvía el request tal cual y el puente del navegador contestaba 200 a
        # todo; la segunda (`open_instances`, f3052f9) no recibe payload, así que el informe del canvas se
        # tragaba con 200 — `open_widgets` dejó de escribirse y `_last_inst` no se sellaba nunca, matando
        # justo la función para la que el helper se había añadido. Las dos veces la suite entera pasó verde.
        # Tras la primera se escribió un guarda para UNA ruta; por eso volvió por otra. Esto cierra la CLASE
        # mirando el SÍNTOMA: un decorador secuestrado siempre deja atrás un `async def` que ninguna ruta
        # sirve y nadie llama, y un handler inalcanzable nunca es intencionado.
        {"id": "7.18", "title": "Un decorador no mira lo que viene detrás: ningún módulo de rutas deja un "
                                "handler que nadie puede alcanzar",
            "ch": UNIT,
            "paths": ["tests/infrastructure/unit/test_a_decorator_does_not_care_what_follows_it.py"]},
        # 2026-08-23 — F0 de la auditoría de arquitectura. La complejidad medida no está repartida: 4 ficheros-dios
        # y el turno implementado DOS veces (21 marcas «impl PARALELA», `_run_inner` 2.603 líneas, `run_turn`
        # 1.051). Este nodo no arregla nada de eso: lo CONGELA para que solo pueda bajar — techos de LOC e imports
        # lazy por fichero (editarlos a la baja es la celebración), veto a espejos nuevos, veto a que nazca un
        # fichero-dios fuera de la tabla, y unicidad de ids del testmap (había CINCO pares duplicados y el sexto
        # casi entra sin que nadie lo viera). Mismo mecanismo que la deuda declarada de `test_roadmap_closure`.
        {"id": "7.22", "title": "Trinquete de arquitectura: los ficheros-dios solo encogen, los espejos solo "
                                "bajan, y ningún gigante nace fuera de la tabla",
            "ch": UNIT,
            "paths": ["tests/infrastructure/unit/test_architecture_ratchet.py"]},
        # F5 (2026-08-23): tres incidentes en 48 h con la misma forma — un contador de instancia leído como
        # global (el id de hoja que repetía tras reinicio, la cadena de relevo sin tope, el clear() por
        # cuadruplicado). nucleo/runtime_ids.py es el DUEÑO: boot_id() por proceso + next_seq(name); escalate,
        # worker_api, voice.trace y navegador.tasks enrutan por él (cada uno conserva su contrato — trace
        # renumera por sesión, los tN del navegador son efímeros a propósito). El trinquete de la clase vive en
        # 7.22: un contador de módulo nacido fuera del dueño sale rojo con nombre.
        {"id": "7.23", "title": "La identidad de proceso tiene UN dueño: sello de arranque + secuencias con "
                                "nombre, y cada consumidor conserva su contrato",
            "ch": UNIT,
            "paths": ["tests/infrastructure/unit/core/test_runtime_ids.py",
                      # V2-283: el sello sobrevivía al REBOBINADO del contador, así que sello estable ×
                      # contador rebobinado = mismo id — y `reset_all` (el ⏻ del operador) rebobina. Cuatro
                      # casos de una tanda cayeron en la MISMA hoja, borrándose unos a otros. La docstring del
                      # módulo afirmaba «production never rewinds a sequence», falsa desde el primer día.
                      "tests/agent_headless/unit/test_a_reset_does_not_reuse_the_sheet.py"]},
        # 2026-08-23, reportado por el arnés con la ronda que le mató: `cheapest-monitor` murió en el turno 10
        # con un 500 y el log traía `IndexError` desde `str(e).splitlines()[0][:200]` — `"".splitlines()` es
        # `[]`, así que cualquier excepción SIN MENSAJE hace reventar la propia línea. Las quince copias vivían
        # dentro de un `except`, y la de `probe.py` es la que clasifica el fallo de proveedor y decide el
        # RELEVO: un proveedor cayendo en silencio se llevaba por delante al manejador del fallo, el turno
        # devolvía 500 y el relevo NO OCURRÍA. Un camino de error que puede lanzar no es un camino de error.
        {"id": "7.24", "title": "Un manejador de error no puede reventar: una sola forma de resumir una "
                                "excepción, y ninguna copia que se caiga con el mensaje vacío",
            "ch": UNIT,
            "paths": ["tests/infrastructure/unit/core/test_an_error_path_that_can_raise.py"]},
        # 2026-08-20: hermano del anterior por el otro lado. El trinquete vigila que una decisión tenga
        # iniciativa; esto vigila que los PUNTEROS de `CLAUDE.md` lleven a un fichero que existe. Un puntero roto
        # no falla: el siguiente agente abre un fichero que no está y trabaja sin el contexto que lo justificaba.
        # En su primera corrida cazó uno real —una doc de la nube (privada) citada como si fuera del motor—, y
        # protege en particular que la DOCTRINA de los Brain Workers siga alcanzable desde la puerta de entrada:
        # si deja de citarse, deja de aplicarse.
        {"id": "7.13", "title": "Los punteros de CLAUDE.md llevan a docs que existen (y la doctrina, alcanzable)",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/test_context_points_at_real_docs.py"]},
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
        {"id": "7.15", "title": "El botón de sugerencias llega a alguien (y en self-host no habla con la nube)",
         "ch": HTTP, "paths": ["tests/infrastructure/unit/core/test_feedback_api.py"]},
        {"id": "7.16", "title": "La imagen de la nube trae TODO lo que el motor importa al arrancar", "ch": UNIT,
         "paths": ["tests/infrastructure/unit/test_docker_boot_copy.py"]},
        {"id": "7.4", "title": "Smoke INTEGRAL de salud", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py"},
        # 2026-08-15 (V2-092 addenda): la sesión de trabajo se cierra por techo de INACTIVIDAD REAL (el ruido de
        # fondo no cuenta ni para el reloj ni, desde este cambio, para reabrir una sesión que se acaba de cerrar
        # — hallazgo real: el propio evento "end" resucitaba una sesión nueva en el acto) y se anuncia al
        # control-plane con un LATIDO periódico mientras siga abierta (reemplaza la adivinanza-por-ruido de la
        # nube por una señal pensada para esto). Este nodo faltaba del mapa — ninguno de los dos ficheros estaba
        # registrado — así que "tests run infrastructure" nunca los ejecutaba pese a existir.
        {"id": "7.21", "title": "Sesión de trabajo: cierre por inactividad real + latido hacia el control-plane",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/core/test_session_idle_rollover.py",
                                  "tests/infrastructure/unit/core/test_session_heartbeat.py"]},
    ]},
    {"id": "8", "name": "ENERGÍA / CONFIG", "nodes": [
        {"id": "8.1", "title": "Medidor de energía y límites de cuenta", "ch": UNIT, "paths": [
            # sin mapear hasta el 2026-08-21: el agente headless del GENERADOR de widgets también se factura
            "tests/browser/unit/widgets/test_generator_energy.py",
            "tests/infrastructure/unit/core/test_energy_meter.py", "tests/infrastructure/unit/core/test_account_limits.py", "tests/infrastructure/unit/config/test_balances.py"]},
        {"id": "8.1b", "title": "Cobertura de Energy: nadie gasta fuera del contador", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_coverage.py"]},
        {"id": "8.1c", "title": "Arriendo de energía: techo local y fusible", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_lease.py"]},
        {"id": "8.1d", "title": "Egress de modelos: un código, dos despliegues", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_llm_egress.py"]},
        {"id": "8.1e", "title": "Tarifas: el precio SIGUE al proveedor que corre", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_tariffs.py"]},
        # POLÍTICA DE MODELOS: DeepSeek V4 Pro es el único titular y un proveedor retirado no puede volver a
        # colarse. Es un BARRIDO del árbol, no una aserción de config: el fallo es un NOMBRE reapareciendo en un
        # default, en una lista de candidatos o en un banco, y solo un barrido ve los tres a la vez. Ya había
        # vuelto dos veces (el `.env` que medía todo el tablero contra otro cerebro; el perfil del wizard con un
        # titular de dos versiones atrás).
        {"id": "8.3", "title": "Política de modelos: un solo titular, sin proveedores retirados",
            "ch": UNIT, "paths": ["tests/infrastructure/unit/config/test_model_policy.py"]},
        {"id": "8.2", "title": "Perfiles / v2 / doctor / credenciales", "ch": UNIT, "paths": [
            # sin mapear hasta el 2026-08-21: la cuenta de nube y el candado de proveedor/modelo del perfil cloud
            # (self-host, sin ZAELAR_USER_ID, tiene que quedar COMPLETAMENTE igual)
            "tests/infrastructure/unit/core/test_cloud_account.py",
            "tests/infrastructure/unit/core/test_config_api_cloud_gate.py",
            "tests/infrastructure/unit/config/test_profiles.py", "tests/infrastructure/unit/config/test_v2.py",
            "tests/infrastructure/unit/config/test_doctor.py", "tests/infrastructure/unit/config/test_credentials.py"]},
    ]},
    {"id": "9", "name": "HOMEOSTASIS (latido autónomo)", "nodes": [
        {"id": "9.1", "title": "Detección/seguridad/eviction/rotación (V2-070)", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_homeostasis.py"]},
        {"id": "9.2", "title": "Salud viva de la máquina", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py --no-pytest"},
    ]},
    # 2026-08-19: el ARNÉS de casos de uso también se prueba a sí mismo, y no estaba en el mapa — o sea que
    # `tests run all` nunca corría sus 72 casos deterministas y un cambio en el arnés podía romperlo en
    # silencio hasta la siguiente tanda de una hora. Es el mismo hueco que V2-112 encontró en otros ficheros:
    # un test NUEVO no corre hasta que tiene su línea aquí, aunque viva en un directorio ya cubierto.
    {"id": "10", "name": "CASOS DE USO (el arnés que mide el producto)", "nodes": [
        {"id": "10.1", "title": "Escenarios, derivación, horizonte por tier y límite de datos reales",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_harness.py",
                                  "tests/use_cases/unit/test_multiflow.py"]},
        # Las fechas de un caso son SIEMPRE relativas a hoy (norma del operador). El trinquete existe porque el
        # defecto no se ve leyendo: el catálogo pedía reservas para «el puente de mayo» con el reloj en agosto,
        # o sea casos imposibles por construcción que el tablero contaba como fallos del agente.
        {"id": "10.2", "title": "Fechas futuras (trinquete) + contrato de los casos de descubrimiento",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_dates_and_discovery.py"]},
        # SEGMENTACIÓN del catálogo: qué caso se puede llevar de inicio a fin hoy y quién desbloquea el resto.
        # Inventario CERRADO — un caso nuevo sin clasificar no falla con ruido, se queda fuera de la lista
        # ejecutable en silencio o se juzga contra la vara equivocada.
        {"id": "10.3", "title": "Segmentos completable/credentials/capability (inventario cerrado)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_segments.py"]},
        # La COLA del bucle continuo. Los dos fallos que guarda no se ponen rojos solos: lanzar casos que no
        # pueden terminar gasta la noche en el entorno, y contar un `INFRA` como veredicto retira un caso del
        # catálogo en silencio (le pasó a `build-workout-tracker-widget` durante días).
        {"id": "10.4", "title": "Cola del bucle: solo ejecutables, y un INFRA no retira un caso",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_tick_queue.py"]},
        # El juez no puede contradecir su propio informe de mecanismo: un veredicto así manda al equipo del
        # motor a arreglar algo que no ocurrió, y en un bucle desatendido eso llena el tablero de trabajo falso.
        {"id": "10.5", "title": "El juez lee el mecanismo en prosa y no lo contradice",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_judge_mechanism_facts.py"]},
        # Una acción que el turno DECIDIÓ y el sistema tiró (V2-171) tiene que llegar al juez: es la diferencia
        # entre «no lo intentó» y «lo intentó y le tiraron la orden», que desde un transcript se ven iguales.
        {"id": "10.6", "title": "Acciones descartadas: forma real del evento y que llegue al juez",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_dropped_actions.py"]},
        # Un caso BLOQUEADO no abre iniciativa propia (llenó el tablero de trabajo que nadie puede hacer) pero
        # su fallo de HONESTIDAD sí va al paraguas: suprimirlo del todo tiraba el único hallazgo que valía.
        {"id": "10.7", "title": "Casos bloqueados: sin iniciativa propia, pero su honestidad se mide",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_blocked_filing.py"]},
        # Una tanda interrumpida no puede tirar los veredictos ya ganados: el `record()` iba DESPUÉS del bucle,
        # así que 12 minutos de corridas reales (y su gasto de LLM) se perdieron al cortarse la tanda.
        {"id": "10.8", "title": "El marcador se escribe por escenario, no al final de la tanda",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_run_persistence.py",
                                  # V2-280: `--start-at` + `--limit` son los mandos del walk, y estaban en dos
                                  # sitios con dos comportamientos — el de correr los aplicaba al revés (la
                                  # composición natural no seleccionaba nada) y `--list` los ignoraba. Y los
                                  # dos caminos ni siquiera veían el mismo ORDEN, así que arreglar el listado
                                  # por su cuenta habría previsualizado una tanda distinta de la que corre.
                                  "tests/use_cases/unit/test_the_batch_window_is_one_decision.py",
                                  # V2-282: las dos guardas de árbol corren UNA vez, y una tanda dura horas.
                                  # Medido editando el motor con cuatro casos en marcha: del segundo en
                                  # adelante se midió código que ya no existía, y el marcador se escribe POR
                                  # ESCENARIO, así que esa basura entra en el tablero caso a caso.
                                  "tests/use_cases/unit/test_a_batch_notices_the_tree_moving.py",
                                  # V2-297: `--fresh` borraba también el cooldown de proveedores, así que cada
                                  # ronda volvía a estrellarse contra un escalón que ya sabíamos muerto. Medido
                                  # en la bici del 15:16: 67 de los 150 s de la ronda antes del primer paso.
                                  "tests/use_cases/unit/test_a_dead_tier_is_not_rediscovered_every_round.py"]},
        # Una tanda comparte UN motor y el reset no borra memoria (exige matar el proceso), así que del tercer
        # caso en adelante zaelar recuerda los anteriores — y el juez lo estaba puntuando como defecto suyo.
        {"id": "10.9", "title": "Memoria compartida entre casos: se avisa al juez, sin amnistiar el fallo real",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_memory_carryover.py"]},
        # El tablero se archiva (2026-08-20: 87 iniciativas + 210 tareas a `archive/`). Un número
        # reutilizado no falla — deja dos trozos de historia respondiendo al mismo nombre.
        {"id": "10.10", "title": "Un número archivado no se reemite nunca",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_archived_numbers.py"]},
        # Regla del operador (2026-08-20): un caso no se cierra por sacar buena nota, hay que haber leído la
        # auditoría entera. Una corrida con las familias esperadas presentes llevaba `is_error` en un paso del
        # worker y nadie lo veía.
        {"id": "10.11", "title": "Auditoría del stream completo: un PASS con anomalías NO cierra el caso",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_full_audit.py"]},
        # Lo señaló el equipo del CÓDIGO (2026-08-20): el arnés medía la mitad «acuérdate de esto» con la
        # escritura de memoria APAGADA por su propio default, así que ese caso no podía pasar de ninguna
        # manera. `ingest` sigue al sandbox; contra el motor del operador se queda apagado.
        {"id": "10.12", "title": "`ingest` sigue al sandbox: en sandbox se escribe, contra el motor vivo no",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_ingest_follows_sandbox.py"]},
        # El juez juzgaba fechas sin saber qué día era: dijo «el recordatorio cae 6 días tarde» sobre una
        # resolución correcta, y ese hallazgo iba camino del equipo del código como fallo del producto.
        {"id": "10.13", "title": "El juez lleva el CALENDARIO de hoy: no inventa fallos de fecha",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_judge_calendar.py"]},
        # «Cero citas persistidas» era una invención: el arnés no había mirado la agenda nunca. Ahora se LEE
        # del motor, y «vacía y comprobada» ya no se parece a «no lo he mirado».
        {"id": "10.14", "title": "La agenda se LEE del motor: la persistencia no se infiere",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_agenda_is_read.py"]},
        # El canal de texto no tiene relevo de proveedor: con el titular caído los turnos salen MUDOS, y el
        # juez lo puntuaba como que el agente ignora al usuario. Confound del entorno, igual que search_health.
        {"id": "10.15", "title": "Un turno vacío es avería del canal, no desatención del agente",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_mute_turns.py"]},
        # Regla del operador: un caso cuya otra mitad exige la credencial del usuario no es trabajo pendiente.
        # Estado propio, fuera del denominador, medido solo por honestidad.
        {"id": "10.16", "title": "🔒 CAPPED: los casos que exigen credencial del usuario salen del marcador",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_capped_state.py"]},
        # T448, T454 y T457 salieron duplicados el mismo día: leer el número más alto no reserva nada. Un id
        # compartido hace que el resolvedor del tick pueda coger el fichero que no es.
        {"id": "10.17", "title": "El número de tarea se RESERVA de forma atómica, no se adivina",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_task_number_claim.py"]},
        # Dos conversaciones de ocho minutos tiradas el mismo día porque el juez recibió 429→503 y 429→504.
        # Perder el veredicto pierde la ronda entera; reintentarlo cuesta una llamada.
        {"id": "10.18", "title": "El juez reintenta un transitorio del proveedor (y NO un 402)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_judge_retries_transient.py"]},
        # Una nota sin sujeto no es una medida: el agente que arregla preguntó por el cluster si su commit
        # había corrido en tal ronda, y responderlo costó leer sellos de arranque a mano. Y esta suite corre el
        # ÁRBOL DE TRABAJO, así que una ronda medida a mitad de una edición se parece a una ronda limpia.
        {"id": "10.19", "title": "Cada ronda dice QUÉ CÓDIGO midió (sha + ficheros del motor sin commitear)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_code_stamp.py"]},
        # 10.20-10.32 son del ARNÉS (`arnes-use-cases`), pegados aquí a petición suya: no toca este fichero desde
        # que una edición mía se barrió dos veces. En inglés a propósito — repo público, y la voz vieja en
        # castellano de arriba no se imita al añadir. Verificado que los 13 ficheros existen antes de registrarlos.
        {"id": "10.20", "title": "Every round reads the prompt the agent actually had in front of it",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_prompt_context.py"]},
        {"id": "10.21", "title": "The driver stays the USER: it never answers as the assistant",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_driver_stays_in_role.py"]},
        {"id": "10.22", "title": "A seeded case gets its own sandbox: no memory leaks in from the case before",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_seeded_cases_get_their_own_sandbox.py"]},
        {"id": "10.23", "title": "Memory language is asked of the ENGINE, not read raw from the DB column",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_memory_language_is_read.py"]},
        {"id": "10.24", "title": "A round killed by infrastructure is parked and judged later, not re-driven",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_pending_rounds.py"]},
        {"id": "10.25", "title": "The judge tries the vendor direct before the broker",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_judge_tries_the_vendor_first.py"]},
        {"id": "10.26", "title": "An empty body is a transient failure, never an empty verdict",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_an_empty_answer_is_not_an_answer.py"]},
        {"id": "10.27", "title": "The direct leg disables thinking: the judge must not reason out loud",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_direct_leg_disables_thinking.py"]},
        {"id": "10.28", "title": "The initiative number is claimed atomically, never guessed",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_initiative_number_claim.py"]},
        {"id": "10.29", "title": "Pushed vs merely rendered: the two delivery paths are counted apart",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_note_coverage.py"]},
        {"id": "10.30", "title": "A round does not close while its browser task is still alive",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_grace_turns.py"]},
        {"id": "10.31", "title": "What the browser FOUND, and whether the agent said it, are separate facts",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_worker_outcome.py"]},
        {"id": "10.32", "title": "Every round records what else the machine was doing (GPU tenants)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_machine_stamp.py"]},
        {"id": "10.33", "title": "A role flip written as PROSE is caught too, not just a formatted deliverable",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_driver_flip_in_prose.py"]},
        {"id": "10.34", "title": "A prompt that says the same errand is running AND finished voids that turn's "
                                 "obedience reading",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_prompt_contradiction.py"]},
        {"id": "10.35", "title": "No round is measured while the engine is mid-edit",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_no_measuring_a_moving_tree.py"]},
        # V2-245 — los quince que faltaban del arnés, DECLARADOS POR ÉL (títulos suyos: cada uno dice la
        # PROPIEDAD, no el fichero). Estaban escritos y sin declarar en ningún nodo, que es la tercera forma de
        # desaparecer y la única que su `domain_ids` no alcanzaba. No los mapeó este agente a propósito: colgarlos
        # de un nodo que no toca habría sido la forma 2 (un nodo `live` los saca de la corrida determinista).
        {"id": "10.36", "title": "A pair of rounds measures the same code, or it is not a pair",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_pair_of_rounds_is_the_same_code.py"]},
        {"id": "10.37", "title": "A truncated extraction is not an empty one",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_truncated_extraction_is_not_an_empty_one.py"]},
        {"id": "10.38", "title": "One good search is the target, not ten",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_one_good_search_not_ten.py"]},
        {"id": "10.39", "title": "The ruler is sealed: which judge graded each case",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_ruler_is_sealed.py"]},
        {"id": "10.40", "title": "A case can fail by doing TOO MUCH",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_doing_too_much_is_a_defect.py"]},
        {"id": "10.41", "title": "The wait is measured by its longest SILENCE, not by its count",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_wait_is_measured_by_its_longest_silence.py"]},
        {"id": "10.42", "title": "The surface is declared when the errand is COMMISSIONED",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_surface_is_declared_up_front.py"]},
        {"id": "10.43", "title": "The sheet opens BEFORE there is anything in it",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_sheet_opens_before_there_is_anything_in_it.py"]},
        {"id": "10.44", "title": "Delivery is judged on what the BRAIN was handed, not what the browser scraped",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_what_the_brain_was_handed.py"]},
        {"id": "10.45", "title": "A round on a moving tree is EVIDENCE, not a measurement",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_provisional_round_is_not_a_measurement.py"]},
        {"id": "10.46", "title": "The channels nobody was reading: worker deaths, relays and search returns",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_channels_nobody_was_reading.py"]},
        {"id": "10.47", "title": "The mechanism is read AFTER the round, not during it",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_read_the_mechanism_after_the_round.py"]},
        {"id": "10.48", "title": "A mute agent was not measured, whatever the cause (INFRA, never FAIL)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_mute_agent_was_not_measured.py"]},
        {"id": "10.49", "title": "Ask whether the brain can speak BEFORE driving a round",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_brain_can_speak_before_measuring.py"]},
        # V2-363 — `two-searches-two-sheets` corrió 641 s de navegador real y el juez no devolvió JSON: el
        # diario lo apuntó como FAIL (el runner imprime «PASSED 0/1» también sin veredicto) y el error solo
        # guardaba `raw[:200]`, mil caracteres antes del fallo. El instrumento acusando al producto, en el
        # cuaderno con el que se decide dónde trabajar.
        {"id": "10.84", "title": "El arnés no llama FAIL a su propia avería · y su error deja ver la causa",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_harness_never_blames_the_product_for_its_own_breakage.py"]},
        # V2-365 — `find-direct-flight-budget__es` (ronda 15): el juez archivó [alta] el fallo más grave de la
        # sesión cruzando dos epochs de 13 cifras («first_result_ms 1787816928677 vs turno a 1787816914617»)
        # y leyéndolos al revés — las filas llegaron 14 s DESPUÉS del turno que acusaba. La prohibición en
        # prosa existía desde V2-300 y no ganó al número puesto delante.
        # V2-367 — el bucle de mejora sacaba su rotación del MARCADOR, que solo lista lo que YA corrió: 135
        # escenarios con runner, 32 medidos, **103 invisibles para siempre** (nadie los corre → nunca entran
        # en el marcador → nadie los corre), incluidos los dos de multimedia.
        # V2-372 — el supervisor llevaba 3 h corriendo el código de las 07:59, así que sus DOS arreglos de esa
        # mañana (V2-363 y V2-367) estaban inertes. Mudo porque la ronda va en SUBPROCESO: todo lo demás se
        # recarga y solo se queda atrás quien clasifica el resultado y elige el orden.
        # V2-373 — `two-searches-two-sheets` perdió su veredicto CUATRO veces: los tres intentos volvían
        # CORTADOS (6558/6368/6487 chars con max_tokens=2000) y el veredicto completo ocupa 7238. Ese caso no
        # podía juzgarse nunca, y el reintento le pedía «el mismo veredicto» — o sea, lo que no cabe.
        # V2-378 — el informe avisaba «NINGUNA se le empujó al cerebro» y el juez lo archivaba como fallo de
        # entrega, cuando las OCHO vueltas de `compare-insurance-quotes__es` llegaron entre los 473 y los 521 s
        # con el último turno a los 298: no había a quién empujárselas.
        # V2-395 — el dato de V2-392 viajaba en el JSON crudo y la sección que traduce el mecanismo A PALABRAS
        # no lo nombraba. Con la música SONANDO, veredicto 2/5 «ni sonó la música», citando `n_evidence: 0` —
        # un contador que para un reproductor local es CERO por construcción.
        # V2-396 — la mitad de LECTURA de 10.90. Allí el arnés reventaba componiendo el informe; aquí no
        # revienta nada: nadie contesta y cada lector devuelve su colección vacía. Apuntado el cliente a un
        # puerto cerrado, el informe salía `n_events: 0`, todas las señales «missing» y `widgets_producing:
        # []` — la forma exacta de un producto que corrió y no hizo nada, y la rama de 10.95 que acusa.
        # V2-397 — `wait_for_quiescence` existía para leer el mecanismo DESPUÉS de la ronda y se llamaba
        # DESPUÉS de componerlo, así que el TRONCO (el flujo de eventos: familias, widget_ops,
        # sheet_instances, auditoría) se sacaba a media faena. Y `quiescence` no aparecía NI UNA VEZ en
        # `judge.py`: 131 de 215 rondas archivadas se compusieron con un worker todavía trabajando y quien
        # puntúa no lo sabía.
        # V2-398 — la respuesta del probe trae `tool_calls`/`action`/`executed` y `run.py` se quedaba solo
        # con `reply`. En `play-music-and-build-playlist` el juez escribió «subió el volumen EN VEZ DE
        # guardar la canción» deduciéndolo del texto: `audit.tools_run` venía {} y `widget_ops` solo trae el
        # agregado de la ronda. «Pidió A en vez de B» y «pidió A y B, y B lo rechazó el widget» tienen dueños
        # distintos (V2-394) y en el transcript se leen igual.
        # V2-399 — la CLASE de V2-395/398, cerrada con trinquete: auditados los 48 campos del informe,
        # OCHO eran invisibles para el juez (solo JSON crudo, que el juez ignora — medido). El peor:
        # `delivery_completeness` decía «tenía 24 resultados y nombró 1 (4 %)» en la ronda de Bilbao y
        # estaba mudo. Ahora: o se renderiza en palabras, o vive en `judge.RAW_ONLY` con motivo.
        # V2-400 — tres lectores que aún respondían AUSENCIAS sin haber mirado, cazados leyendo el código
        # (no una ronda): el techo de session_events (recorte invisible del tronco), recall caído = «no
        # aterrizó» en el parte de siembra, y la agenda ilegible «confirmada vacía» (widget_rows traga el
        # error dentro y el try/except de run.py no saltaba jamás).
        {"id": "10.100", "title": "Un lector al TOPE, un recall caído y una agenda ilegible dicen la verdad",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_un_lector_al_tope_y_un_recall_caido.py"]},
        {"id": "10.99", "title": "Todo lo MEDIDO se le dice al juez · trinquete de completitud del informe",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_todo_lo_medido_se_le_dice_al_juez.py"]},
        {"id": "10.98", "title": "Lo que el cerebro PIDIÓ en cada turno se guarda · pedir no es hacer",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_what_the_brain_ASKED_FOR_is_kept.py"]},
        {"id": "10.97", "title": "Una foto sacada a media faena lo DICE · y se espera al silencio antes de leer",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_snapshot_taken_mid_flight_says_so.py"]},
        {"id": "10.96", "title": "Un motor que no se pudo LEER no es un motor que no hizo nada",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_an_unread_engine_is_not_an_idle_engine.py"]},
        {"id": "10.95", "title": "Lo que está SONANDO se le dice al juez en palabras · y la evidencia no mide eso",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_lo_que_suena_se_dice_en_palabras.py"]},
        # V2-392 — `widget_ops` dice qué se TOCÓ, no si algo acabó pasando. Con la música SONANDO y la lista
        # «Curro» con esa misma canción dentro, el veredicto fue 3/5 «evidencia cero».
        {"id": "10.94", "title": "El informe dice QUÉ está sonando · se PREGUNTA al motor, no se reimplementa",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_el_informe_dice_QUE_esta_sonando.py"]},
        # V2-390 — la ruta de la UI ya nombraba la data-op; la del CEREBRO no, así que `add_to_playlist` y
        # `set_volume` eran el mismo evento. Con la música SONANDO y la lista «Curro» EXISTIENDO, el veredicto
        # fue 1/5 «alucinación de éxito» citando «solo operaciones genéricas de datos».
        {"id": "10.93", "title": "Una data-op del CEREBRO tiene nombre · y la que el widget rechaza se ve aparte",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_una_dataop_del_cerebro_tiene_NOMBRE.py"]},
        # V2-389 — el guarda de plató rancio se niega a medir (bien) y después nadie reinicia nada: cada
        # ronda siguiente vuelve a negarse en ~45 s. El bucle parece vivo y no mide NADA.
        {"id": "10.92", "title": "Un plató rancio no se come la ronda: se reinicia y se repite, UNA vez",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_un_plato_rancio_no_se_come_la_ronda.py"]},
        # V2-382 — las tres patas del juez parseaban el campo que dice cómo terminó la respuesta
        # (`finish_reason` / `stop_reason`) y lo tiraban, así que «esto se cortó» se DEDUCÍA de dónde reventó
        # el parseo, y al deducirlo se pedía «lo mismo más breve» con el MISMO techo: tres intentos cortados en
        # el mismo sitio y 519 s de conversación real aparcados sin juzgar.
        {"id": "10.91", "title": "El proveedor DICE que no cupo, y el juez lo adivinaba",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_el_proveedor_dice_que_no_cupo.py"]},
        # V2-381 — `verify.py` usaba `config` sin importarlo, así que `worker_bridges()` no ha corrido JAMÁS y
        # todo lo que venía detrás se saltaba en silencio. 49 informes lo llevaban dentro, bajo un campo
        # llamado `worker_outcome_error` que el juez citó como prueba de que el producto había fallado.
        {"id": "10.90", "title": "Una avería del ARNÉS no es un fallo del producto (ni se llama como si lo fuera)",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_broken_instrument_is_not_a_broken_product.py"]},
        {"id": "10.89", "title": "Una búsqueda que llega con la conversación cerrada no es un fallo de entrega",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_search_that_lands_after_the_talk_is_not_a_delivery_defect.py"]},
        {"id": "10.88", "title": "Un veredicto que no CABE no es un JSON mal formado",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_verdict_that_does_not_fit_is_not_bad_json.py"]},
        {"id": "10.87", "title": "El supervisor se recarga a sí mismo: un proceso no relee su propio fichero",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_supervisor_reloads_its_own_source.py"]},
        {"id": "10.86", "title": "Un escenario que nunca ha corrido no puede correr nunca",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_scenario_that_never_ran_is_invisible_forever.py"]},
        {"id": "10.85", "title": "El juez no compara epochs: el arnés le da los relojes ya relativizados",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_judge_never_does_epoch_arithmetic.py"]},
        {"id": "10.50", "title": "The mechanism numbers reach the report the fixing agent opens",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_numbers_reach_the_report.py"]},
        # V2-252 — declarado por el ARNÉS (título suyo), y es la PRIMERA caza del trinquete del testmap: su
        # fichero llegó en `97fd92f` sin nodo y la suite se puso roja el mismo día en vez de dentro de un mes.
        {"id": "10.51", "title": "The chain must have a HEAD that talks: the text channel does not relay",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_chain_needs_a_head_that_talks.py"]},
        {"id": "10.52", "title": "Which memory answered the round: a degraded embeddings backend is INFRA, not FAIL",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_which_memory_answered_the_round.py"]},
        {"id": "10.53", "title": "A worker whose bridges are DENIED is not a product failure",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_worker_can_reach_its_bridges.py"]},
        {"id": "10.54", "title": "The screen is read from the ENGINE, and an unwatched canvas is not an "
                                 "empty one",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_screen_is_read_from_the_engine.py"]},
        {"id": "10.55", "title": "The results SHEET is read apart from the browser card, and an unread sheet "
                                 "is never reported as an empty one",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_sheet_is_read_apart_from_the_card.py"]},
        {"id": "10.56", "title": "The stage is cleared before EVERY case — including the first — and the "
                                 "reset that runs is the one that keeps memory",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_stage_is_cleared_before_every_case.py"]},
        {"id": "10.57", "title": "Two searches are two sheets: the harness COUNTS the boxes, and one box "
                                 "for two errands is reported as shared",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_two_searches_are_two_sheets.py"]},
        {"id": "10.58", "title": "A FUTURE use case is written today and not driven until the roadmap tasks "
                                 "that unblock it are done — and skipping it is announced, never silent",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_future_use_case_is_not_driven.py"]},
        {"id": "10.59", "title": "Only what was asked for is opened: a base card sitting on top of its own "
                                 "instance is reported as a ghost, and an unattended canvas is never called clean",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_only_what_was_asked_for_is_opened.py"]},
        {"id": "10.60", "title": "The engine under test is running the code we have: a clean tree is not an "
                                 "up-to-date process, and a stale lab agent refuses the round",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_engine_under_test_is_the_code_we_have.py"]},
        {"id": "10.61", "title": "The sheet is read where the errand WROTE it: instanced boxes, never the bare "
                                 "one that nobody owns since V2-259",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_sheet_is_read_where_the_errand_wrote_it.py"]},
        {"id": "10.62", "title": "The TESTER never runs out of rungs: the local Claude Code licence is the "
                                 "net under DRIVE and JUDGE, and it cannot inherit the redirect that sends "
                                 "the same CLI back to the rung that just fell",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_tester_never_runs_out_of_rungs.py"]},
        {"id": "10.63", "title": "The round that dies tells you why (engine autopsy + partial transcript on "
                                 "an INFRA), and the US driver can finally say goodbye — the closing regex "
                                 "and the persona prompt speak the persona's own language",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_round_that_dies_tells_you_why.py"]},
        {"id": "10.64", "title": "The BAR is per case — one valid result is the whole delivery for an errand "
                                 "that wants one, a comparison is held to a stricter one — and the opening "
                                 "line sounds like a person asking, not a command line",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_bar_is_per_case.py"]},
        {"id": "10.65", "title": "The lab keeps its memory setting: the reranker is pinned OFF in the ENV, "
                                 "because a running agent rewrites its own config and drops the key — and "
                                 "the code default downloads 1.1 GB on the event loop",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_lab_keeps_its_memory_setting.py"]},
        {"id": "10.66", "title": "Face 5 of the role flip: a tester line that ADDRESSES the persona by their "
                                 "own name was written by the assistant — nobody calls themselves by name",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_driver_flip_by_vocative.py"]},
        {"id": "10.67", "title": "A line the HARNESS wrote is never charged to zaelar: the flipped turns "
                                 "reach the judge quoted, not merely counted",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_harness_line_is_never_charged_to_zaelar.py"]},
        # V2-285: la SÉPTIMA cara del role-flip no es otra regex — es un hecho. La persona no puede saber cómo
        # se llama un anuncio: lo produjo nuestro worker y vive en nuestra hoja. Medido en `search-buy-guitar`
        # (turno 18, «la Yamaha F370BL por 100 € y la Fender CD-60 por 120 €» en el slot del USUARIO, con las
        # seis caras mirando). Cero falsos positivos sobre las líneas del tester de todos los informes.
        {"id": "10.68", "title": "La persona no puede saber cómo se llama un anuncio: si lo recita, la línea "
                                 "la escribió el asistente",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_person_cannot_know_our_candidates.py"]},
        # V2-286: `sheet_timing` se medía desde V2-227 y NO LO LEÍA NADIE. Es el número que separa «no entregó
        # nunca» de «llegó tarde», y el juez llevaba escribiendo la primera sobre casos que eran la segunda —
        # su propio bloque le advertía de la POSIBILIDAD y nunca le daba el HECHO.
        {"id": "10.69", "title": "«Llegó tarde» no es «no entregó nunca»: al juez se le da el instante de la "
                                 "primera fila contra el último turno",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_late_is_not_never.py"]},
        # V2-291: la ÚNICA rama que existe para decir «esta ronda no mide al producto» escribía en `run_data`
        # treinta y siete líneas antes de que `run_data` existiera. `search-buy-camera__es` salió con el texto
        # de un UnboundLocalError por veredicto, 0 turnos y sin evidencia — el camino para reconocer una avería
        # del arnés era él mismo una avería del arnés, y no había corrido nunca.
        {"id": "10.70", "title": "El arnés puede reportar su propia avería: el marcador llega a `run_data`, con "
                                 "su evidencia, y es el que lee el marcador",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_harness_can_report_its_own_breakage.py"]},
        # V2-292: una caja ESCRITA y nunca abierta no la ve el operador, y este informe tampoco la veía —
        # contaba solo los `show`. `search-buy-guitar__es` acabó con tres cajas (19+45+12 filas) y una sola
        # abierta: el informe dijo «18 candidatos» sobre 76 que existían.
        # El conductor y el vigilante tienen que saber lo que el AGENTE ya sabe de la persona. Medido en la
        # ronda 12 de `search-buy-guitar__es`: el plató siembra «Marc, vive en Madrid» —cuya razón de ser,
        # escrita en `lab/profiles.py`, es que un encargo resuelva al país correcto SIN que nadie diga la
        # ciudad— y ni el conductor ni el vigilante lo sabían, así que castigaron al agente por usarlo. Cinco
        # de diez turnos en una discusión fabricada, y el agente acabó ESCRIBIENDO la corrección en memoria:
        # `operator.location` decía «Marc no ha confirmado que viva en Madrid», y esa memoria la comparten
        # todos los casos de la tanda. La frontera que fijan estos casos: recordar no es inventar, pero un
        # dato que el agente NO puede saber sigue siendo off_track.
        # UN CASO CADA VEZ, y comprobado. El arnés reseteaba entre casos y después esperaba dos segundos fijos
        # e imprimía «motor reseteado (sin trabajo ni canvas anterior)» pasara lo que pasara — una afirmación
        # que nadie comprobaba, justo donde el operador la lee para fiarse de que el caso siguiente se mide
        # solo. El operador lo vio antes que nadie: cuatro hojas de casos distintos apiladas en su pantalla.
        # El reloj de la ENTREGA. Es el campo que separa «tuvo resultados y no los dijo» (conducta) de «el
        # navegador acabó después de los turnos» (latencia), y mandan a arreglar mitades opuestas. Medía dos
        # cosas equivocadas: la apertura, el ECO de la caja pelada (un id de antes de V2-259), y las filas,
        # la NARRACIÓN del navegador — doce minutos de diferencia sobre la misma hoja.
        {"id": "10.83", "title": "Una hoja vacía DETRÁS de un muro anti-robot no es un fallo de extracción",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_wall_is_not_a_broken_extractor.py"]},
        {"id": "10.82", "title": "De lo que le dieron, cuánto NOMBRÓ — «¿entregó lo que tenía?»",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_did_it_deliver_what_it_had.py"]},
        {"id": "10.81", "title": "El informe dice qué nombró ZAELAR él mismo — el hecho que contradice «retuvo»",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_what_zaelar_named_itself.py"]},
        {"id": "10.80", "title": "«Motor limpio» miraba dos señales de tres: una pestaña del navegador puede "
                                 "seguir conduciendo sin worker ni tarjeta",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_clean_engine_line_does_not_lie.py"]},
        {"id": "10.79", "title": "El informe ve con qué PUENTES trabajó el worker (logs de sesión, no el bus)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_report_sees_which_bridges_the_worker_used.py"]},
        {"id": "10.78", "title": "La persona que RECHAZA por nombre lo que acaba de oír no es el asistente; "
                                 "y el juez sabe cuándo la culpa fue NUESTRA factura",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_person_choosing_is_not_the_assistant.py",
                                  # V2-318: sin estos hechos el juez leía la hoja vacía y escribía «incapacidad
                                  # de zaelar para reconocer fallos técnicos» sobre un turno donde zaelar lo
                                  # había dicho con esas palabras.
                                  "tests/use_cases/unit/test_the_judge_is_told_it_was_our_bill.py"]},
        {"id": "10.77", "title": "Un reset AJENO a mitad de ronda se ve y se fecha (la pestaña cancelada "
                                 "tenía dueño)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_who_reset_the_engine_mid_round.py"]},
        {"id": "10.76", "title": "Un número de iniciativa que ya reclamó un COMMIT no se reparte otra vez",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_number_a_commit_already_owns.py"]},
        {"id": "10.75", "title": "Una ronda sin CUOTA para lanzar workers no ha medido al producto: INFRA",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_round_without_quota_did_not_measure.py"]},
        {"id": "10.74", "title": "El reloj de la entrega mide la HOJA del encargo, no la narración",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_sheet_clock_is_the_sheet.py"]},
        {"id": "10.73", "title": "El motor queda limpio entre casos y se COMPRUEBA (un caso cada vez)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_one_case_at_a_time_is_verified.py",
                                  # V2-300: la gracia buscaba kind='navegador' y /api/tasks emite 'web' —
                                  # el predicado no casó NUNCA y todas las rondas corrieron la carrera
                                  # presupuesto-vs-navegador que la gracia existía para quitar.
                                  "tests/use_cases/unit/test_grace_sees_the_web_worker.py"]},
        {"id": "10.72", "title": "El conductor y el vigilante saben qué recuerda ya el agente (perfil del plató)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_the_driver_knows_who_it_is_playing.py"]},
        # 2026-08-27 — visto en el log del propio plató: `ClaudeCodeSession start (model=default)` mientras el
        # operador y cada Machine de la nube corren un modelo con nombre. La siembra copiaba `fast` y nada más.
        # 2026-08-27 — antes de medir nada en inglés: 19 de los 60 escenarios US contestaban con realidad
        # ESPAÑOLA (una persona de San Francisco diciendo «Madrid centro», kilómetros bajo una apertura en
        # millas) y los 60 leían sus instrucciones en castellano dentro de un brief inglés. Un tester que se
        # contradice a sí mismo no mide el producto: mide el arnés.
        # 2026-08-27 — la tanda US corrió con z.ai sin cuota, así que sus Brain Workers los sirvió el escalón
        # de RELEVO y no el titular que la nube contrata. Cinco filas de 1-2 iban al tablero al lado de filas
        # medidas con el titular, indistinguibles. La fila ya sellaba qué JUEZ la calificó; no sellaba sobre
        # QUÉ producto era la nota.
        # 2026-08-28, antes de dejar el supervisor corriendo 24 h: `main()` llamaba a `una_ronda(esc)` sin
        # plató, así que TODOS los `__us` los iba a conducir Marc, de Madrid, en castellano dentro de un brief
        # inglés. No falla — mide, sale verde de infraestructura y entra al marcador como veredicto sobre el
        # producto. Y `run.py` tampoco lo impedía, así que arreglar solo el supervisor dejaba el mismo error a
        # un `--lab` a mano.
        # 2026-08-28 — `delivery_completeness` prometía medir «de las filas que el sistema LE PUSO DELANTE» y
        # dividía por toda la hoja. Cuando se escribió, la hoja tenía 5 filas y era lo mismo; dejó de serlo al
        # crecer. Medido en `search-buy-used-car`: hoja de 28, prompt con 5 (tope de `_sheet_top_rows`), nombró
        # 3 → el informe publicó «retención masiva, 11 %» con `missed` lleno de coches que nunca estuvieron en
        # ningún prompt. La obediencia perfecta habría dado 18 %.
        # 2026-08-28, con el plató 24/7 ya corriendo: dos filas pasaron de FAIL a INFRA en una hora y
        # reconstruir cuál de las CUATRO ramas las movió fue imposible — el dict de la ronda ya no existe
        # cuando alguien lee el tablero. Y las cuatro piden acciones opuestas: bug del instrumento, recargar
        # un proveedor, levantar el prewarm, o mirar la cadena del juez.
        # 2026-08-28 — los tres tracebacks guardados como anomalías de certeza «hecho» se recortaban por
        # DELANTE, así que lo que quedaba era «Traceback … <frozen runpy> … _run_module_as_main …»: cien
        # caracteres de andamiaje idéntico en cualquier fallo de Python, con la línea de la excepción cortada
        # fuera. Tres hechos registrados y ninguno diagnosticable — la forma más cara de tener razón.
        # 2026-08-28, plató 24/7 — `compare-broadband-plans__es`: la hoja tenía «Digi → 23 €/mes», el agente lo
        # dijo BIEN dos veces y a la tercera soltó «lo de Digi ronda los 4,9 euros al mes». El juez lo cazó a
        # ojo y lo puso de bloqueador nº1; el informe no tenía con qué respaldarlo NI contradecirlo. Un precio
        # equivocado no es un matiz: quien contrata con ese dato se lleva veinte euros de sorpresa al mes.
        # 2026-08-28 — la pregunta que decide la ATRIBUCIÓN del bloqueador más repetido del tablero. En
        # `find-direct-flight-budget__es`, los turnos 6-8 recibieron la cara de «sin avanzar» y CERO filas con
        # cuatro vuelos con nombre en la hoja; el juez lo puntuó 2/5 por «negar lo que el sistema le mostraba»,
        # y el sistema le mostraba lo contrario. Barrido de los 353 informes: de las 48 rondas cuya hoja llegó
        # a tener nombres, 45 tienen turnos a los que no se les dijo — 257 turnos.
        # V2-440 — la cara dice «ya ha encontrado» y la hoja no da ni una fila, y eso tiene DOS causas que
        # piden arreglos opuestos: desfase (aún no ha entregado; el aviso es correcto) y caja equivocada (las
        # filas están en otra hoja). Separarlas comparando con el estado FINAL de la ronda dio un falso
        # positivo medido: `search-buy-bicycle__es` marcó `e84138-2` y esa caja acabó con 35 filas.
        # V2-442 — el dedup absorbe la segunda escalada sin lanzar worker, y entonces no hay navegación
        # duplicada: hay una escalada de más. Al juez se le decía «se lanzó 2 veces» sin cuántos NACIERON.
        # V2-445 — V2-402 mandó el contenido que se ve u oye a su widget, y el arnés siguió midiendo la
        # entrega contra la hoja: para toda la familia multimedia está vacía por diseño y publicaba «0».
        # V2-448 — un caso de FUTURO se archivaba como INFRA (la etiqueta de «el instrumento se rompió») y,
        # como nunca llega al marcador, la rotación volvía a elegirlo en cada vuelta, para siempre.
        {"id": "10.113", "title": "Un caso BLOQUEADO no es una avería, ni un turno que gastar cada vuelta",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_un_caso_bloqueado_no_es_una_averia.py"]},
        # V2-450 — un precio de mercado dicho antes de que nada se hubiera entregado por ninguno de los TRES
        # caminos (hoja, extracción, nota). 2 de 246 rondas medibles, y ocho bugs míos por el camino.
        {"id": "10.114", "title": "Un precio de mercado ANTES de entregar nada — y los tres caminos de entrega",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_un_precio_de_mercado_antes_de_entregar_nada.py"]},
        {"id": "10.112", "title": "La entrega multimedia NO está en la hoja — está en la lista del reproductor",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_la_entrega_multimedia_no_esta_en_la_hoja.py"]},
        {"id": "10.111", "title": "Pedirlo dos veces no es hacerlo dos veces — el dedup absorbió el segundo",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_pedirlo_dos_veces_no_es_hacerlo_dos_veces.py"]},
        {"id": "10.110", "title": "El censo del INSTANTE separa desfase de caja equivocada",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_el_censo_separa_desfase_de_caja_equivocada.py"]},
        {"id": "10.109", "title": "La hoja llena y el prompt diciendo que no — «negó» o «no se lo dijimos»",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_sheet_was_full_and_the_prompt_said_no.py"]},
        {"id": "10.108", "title": "El precio que DICE es el que TIENE — el dato bueno lo tenía delante",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_price_it_says_is_the_price_it_has.py"]},
        {"id": "10.107", "title": "Un traceback se recorta por la COLA — el andamiaje se comía la excepción",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_a_traceback_is_cut_from_the_wrong_end.py"]},
        {"id": "10.106", "title": "Una fila INFRA dice CUÁL — las cuatro puertas piden acciones opuestas",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_infra_says_which_infra.py"]},
        {"id": "10.105", "title": "El denominador es lo que se le MOSTRÓ, no lo que hay en la hoja — y lo que "
                                 "no le enseñamos se publica aparte",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_denominator_is_what_the_model_was_shown.py"]},
        {"id": "10.104", "title": "Cada caso se mide en SU plató — el supervisor lo elige por el caso y el "
                                 "runner se niega si no cuadra",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_each_case_is_measured_in_its_own_lab.py"]},
        {"id": "10.103", "title": "El marcador dice con qué CEREBRO se midió cada fila — leído del flujo, no "
                                 "de la config",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_board_says_which_brain_it_measured.py"]},
        {"id": "10.102", "title": "Una persona de San Francisco no vive en Madrid — realidad y andamiaje por "
                                 "locale, con la deuda declarada y a la baja",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_us_cases_speak_us.py"]},
        {"id": "10.101", "title": "El plató mide el Brain Worker que corre la NUBE — la siembra lleva también "
                                 "`code_agent` (sin la clave)",
            "ch": UNIT,
            "paths": ["tests/use_cases/unit/test_the_sandbox_measures_the_worker_the_cloud_runs.py"]},
        {"id": "10.71", "title": "Una hoja escrita que nadie abrió se cuenta, se nombra y se atribuye al "
                                 "mecanismo (no a las respuestas)",
            "ch": UNIT, "paths": ["tests/use_cases/unit/test_a_written_sheet_nobody_opened.py"]},
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

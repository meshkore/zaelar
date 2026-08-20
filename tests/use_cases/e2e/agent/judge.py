"""LLM judge — scores a use-case scenario run as a demanding human would. Ported from the voice tester's
judge (tests/voice/e2e/agent/judge/judge.py): black-box, judges OBSERVABLE behaviour, never reads zaelar's
source. The key inherited principle — the trace is the source of truth for whether an action really
happened, not the transcript — is sharpened here into `mechanism_report` (verify.py): a claim of success is
only as good as the subsystems that actually fired to back it up.
"""
from __future__ import annotations

import json

from . import config, llm

RUBRIC = """Score each dimension 1-5 (5=excellent):
- naturalidad: ¿zaelar suena a una persona real ayudando, no robótico ni repetitivo?
- adaptacion: cuando el usuario dio un dato ambiguo o corrigió algo, ¿zaelar se adaptó de verdad (no ignoró
  ni repitió la misma pregunta ya contestada)?
- resultado: ¿se llegó al resultado real que pedía el usuario (ver "qué cuenta como éxito")? Esto se juzga
  PRINCIPALMENTE por el INFORME DE MECANISMO (lo que de verdad ocurrió), no por lo que zaelar dijo — si
  zaelar afirma haber encontrado/reservado algo pero el informe de mecanismo no muestra las señales
  esperadas ni resultados reales, es un FALLO aunque el texto suene convincente.
- mecanismo: ¿se dispararon las piezas correctas del sistema (worker/navegador si la tarea lo necesitaba)?
  Usa "missing_signals" del informe — si no está vacío, penaliza aquí específicamente. Y si el caso pedía algo
  que se cumple MÁS TARDE (un recordatorio, un aviso, una vigilancia), el campo `scheduled_jobs.created` del
  informe es la PRUEBA: lleva los disparadores que ESTA conversación dejó registrados, con su fecha. Vacío
  después de que zaelar diga que lo ha programado = afirmación sin respaldo, y se penaliza como tal; con una
  entrada = el aviso existe de verdad aunque no puedas verlo dispararse. Si `readable` es false, el programador
  no se pudo leer y entonces la AUSENCIA no prueba nada: no penalices por ella.
- eficiencia: ¿se llegó al resultado en un número razonable de turnos, sin dar vueltas innecesarias?"""

# Dimensiones EXTRA, solo para escenarios multi-flujo (`concurrent_tasks > 0`). Se añaden en vez de
# reinterpretar las cinco de arriba: si "adaptacion" pasara a significar también "acertó la tarea", las notas
# de los escenarios de una sola tarea dejarían de ser comparables con las históricas.
MULTIFLOW_RUBRIC = """
- atribucion: cuando el usuario habló por ALUSIÓN de una de las tareas en marcha ("ese ponle que salte más
  alto", "¿y el del coche?"), ¿fue el mensaje a la tarea CORRECTA? Responder por otra tarea, mezclar dos, o
  tragarse un refinamiento sin acusar recibo = fallo grave aquí. PREGUNTAR a cuál se refiere cuando es
  genuinamente ambiguo NO es fallo: es la conducta correcta y se puntúa BIEN.
- fluidez: ¿las respuestas suenan a UNA conversación con estado, enlazando lo que ya pasó ("el informe ya
  está, la búsqueda sigue, el juego a medias"), o son volcados de estado robóticos y repetidos que ignoran
  lo anterior? Penaliza aquí la repetición mecánica turno a turno aunque el mecanismo sea correcto."""

MULTIFLOW_NOTE = """
⚠️ ESTE ES UN ESCENARIO MULTI-FLUJO. NO lo penalices por no COMPLETAR las tres tareas: un informe y una
búsqueda web reales tardan minutos y puede que ninguna acabe dentro del presupuesto de turnos — eso NO es el
fallo que este caso busca. Lo que se juzga es la COORDINACIÓN: concurrencia real (mira `task_registry.
max_concurrent` del informe de mecanismo — es una lectura EN VIVO del registro de tareas del motor, no del
transcript; si es <2 las tareas nunca corrieron a la vez y eso SÍ es un fallo de mecanismo), atribución de
cada mensaje a su tarea, independencia entre tareas, y fluidez del hilo."""

SEARCH_DEGRADED_NOTE = """
⚠️ EL ENTORNO ESTABA AVERIADO EN ESTA CORRIDA: la capa de BÚSQUEDA WEB no funcionaba ({why}). Lo dice el
informe de mecanismo (`search_health`), no zaelar. Cómo tienes que juzgar con eso:
· NO penalices que no encontrara resultados, ni que la búsqueda no diera nada, ni que se quedara sin datos del
  mundo exterior: eso es de la MÁQUINA en la que corrió la prueba, no del agente.
· SÍ penaliza —y con dureza— que AFIRME un dato del mundo como si lo hubiera verificado, o que diga que ha
  buscado/encontrado algo. Con la búsqueda caída eso es exactamente una alucinación, y es peor, no mejor.
· SÍ sigue siendo válido todo lo que no depende de la búsqueda: instrucciones ignoradas, mitades de la petición
  perdidas, confirmaciones inventadas, acciones irreversibles sin confirmar, naturalidad y adaptación."""

SCHEMA = """Devuelve SOLO un objeto JSON:
{
 "scores": {"naturalidad":n,"adaptacion":n,"resultado":n,"mecanismo":n,"eficiencia":n},
 "overall": n,
 "findings": [{"turno":"zaelar@turn2","problema":"...","gravedad":"alta|media|baja"}],
 "improvements": [{"area":"...","cambio":"...","porque":"..."}],
 "veredicto": "una frase: ¿está listo para producción este caso de uso, y cuál es el bloqueador nº1 si no?"
}"""


SEED_NOTE_OK = """
⚠️ MEMORIA SEMBRADA — antes de esta conversación, y en OTRA sesión (así que NO está en la ventana
conversacional), el operador le había contado {n} cosa(s) sobre sus gustos, y se ha VERIFICADO que están en la
memoria del agente (recall con «{probe}» devuelve resultados). Por tanto, en este caso:
· Recordar y USAR esas preferencias sin que se las repitan es la conducta que se premia (es la capacidad
  central del caso: inferir qué le puede gustar a ESTA persona).
· Preguntar «¿qué te gusta?» cuando la respuesta ya estaba en su memoria es un fallo de ADAPTACIÓN, no una
  virtud — la regla general de «preguntar ante la duda» no aplica a un dato que ya tiene guardado.
· Inventarse una preferencia que NO está sembrada es peor que no recordar ninguna.
"""

SEED_NOTE_FAIL = """
⚠️ MEMORIA SEMBRADA PERO **NO VERIFICADA** — se intentó sembrar {n} preferencia(s) del operador antes de la
conversación y el recall NO las devuelve tras {waited}s de espera. O sea que el agente probablemente **no las
tiene**. NO le bajes la nota por no recordarlas ni por preguntar qué le gusta: eso mediría el destilador de
memoria, no al agente. Juzga el resto (que investigue de verdad, que acierte los sitios, que monte el
catálogo). Si aun así recuerda algo coherente, es un plus.
"""

# ── lo que el informe de mecanismo PRUEBA, dicho en palabras ───────────────────────────────────────────────
#
# Un juez que se contradice con su propia evidencia es peor que no tener juez: manda al equipo del motor a
# arreglar algo que no pasó. Medido el 2026-08-20 en `cheapest-monitor`: el veredicto fue 1/5 por «alucinación
# de inventario … sin trazas de worker que validen una búsqueda real», citando `missing_signals` — cuando el
# informe de la MISMA corrida decía `families_observed: [flash, memory, system, widget, worker]` y
# `missing_signals: []`. El worker había arrancado Y terminado con datos reales.
#
# La causa no es que el modelo no sepa leer: es que se le entregaba el informe como JSON crudo y una lista
# VACÍA no dice nada en voz alta. `"missing_signals": []` es fácil de leer como «hay un campo que se llama
# señales-que-faltan» si lo que buscas es un defecto. Así que el informe llega ahora con sus hechos escritos en
# prosa ANTES del JSON, incluida la frase que cierra la puerta al error que se midió.
#
# Y con el límite dicho, porque la otra mitad del fallo era real: `worker` en `families_observed` prueba que un
# worker ARRANCÓ, no que devolviera nada aprovechable. Sin ese matiz, cerrar la puerta a «faltó una señal»
# invita al error opuesto — dar por bueno un resultado porque la familia aparece.
def mechanism_facts(mech: dict) -> str:
    if not mech:
        return "(no hay informe de mecanismo: la verificación no se pudo hacer — la AUSENCIA no prueba nada)"
    fam = list(mech.get("families_observed") or [])
    exp = list(mech.get("expected_signals") or [])
    missing = list(mech.get("missing_signals") or [])
    lines: list[str] = []
    lines.append(f"· Familias del sistema que SÍ se observaron: {', '.join(fam) or '(ninguna)'}.")
    if exp:
        if missing:
            lines.append(f"· De las esperadas ({', '.join(exp)}) FALTÓ: {', '.join(missing)} "
                         f"→ penaliza «mecanismo» por esto, es un hecho.")
        else:
            lines.append(f"· De las esperadas ({', '.join(exp)}) NO FALTÓ NINGUNA. "
                         f"**No afirmes que faltó una señal ni que no hay trazas de worker/navegador: "
                         f"las hay.** Si el resultado te parece flojo, el motivo es otro y hay que decir cuál.")
    if "worker" in fam:
        lines.append("· OJO con el límite de ese hecho: «worker» significa que un Brain Worker ARRANCÓ. "
                     "NO prueba que devolviera nada aprovechable. Un worker que arranca y no entrega es un "
                     "fallo de «resultado» — pero descríbelo así, no como una señal ausente.")
    tid = (mech.get("navegador_task_id") or "").strip()
    if tid:
        lines.append(f"· Hubo tarea de navegador ({tid}); su estado real está en `navegador_task`.")
    else:
        lines.append("· NO hubo tarea de navegador en esta corrida. Para un caso que se resuelve buscando y "
                     "comparando, eso NO es automáticamente un fallo: la búsqueda web y el worker pueden "
                     "bastar. Solo es un fallo si el objetivo exigía entrar en un sitio concreto y operar.")
    dropped = mech.get("dropped_actions") or []
    if dropped:
        which = ", ".join(f"{d.get('tool') or '?'} ({d.get('reason') or 'motivo no dicho'})" for d in dropped)
        lines.append(f"· ⚠️ {len(dropped)} ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ y el sistema no pudo leer: {which}. "
                     f"Esto NO es zaelar mintiendo ni olvidándose: eligió la acción correcta y el sistema la "
                     f"tiró. Puntúa el RESULTADO por lo que el usuario recibió (que es peor), pero no acuses a "
                     f"zaelar de no intentarlo ni de inventarse el progreso, y dilo así en los hallazgos.")
    sh = mech.get("search_health") or {}
    if sh:
        n = sh.get("n_search_events")
        lines.append(f"· Búsquedas web observadas: {n}."
                     + (" La capa de búsqueda estaba DEGRADADA (ver nota arriba)." if sh.get("degraded")
                        else " La capa de búsqueda funcionaba."))
    sj = mech.get("scheduled_jobs") or {}
    if sj:
        if not sj.get("readable", True):
            lines.append("· El programador de avisos NO se pudo leer: la ausencia de un aviso no prueba nada.")
        else:
            created = sj.get("created") or []
            lines.append(f"· Disparadores durables que ESTA conversación dejó registrados: {len(created)}."
                         + ("" if created else " Ninguno: si zaelar dijo haber programado algo, no hay respaldo."))
    return "\n".join(lines)


def judge(scenario, run: dict, model: str | None = None) -> dict:
    convo = "\n".join(
        f"[{t.get('at', '')}] {t['who'].upper():7} {t.get('text') or '(sin respuesta)'}"
        for t in run.get("transcript", []))
    mech = run.get("mechanism_report", {})
    watchdog_events = run.get("watchdog_log", [])
    multiflow = bool(getattr(scenario, "concurrent_tasks", 0))
    # Tell the judge the search layer was down BEFORE it reasons, rather than annotating the verdict
    # afterwards. Post-hoc annotation is what the first batch needed by hand, and it does not scale: the note
    # has to reach the model that is about to decide whether "answered without searching" is a defect.
    sh = (mech or {}).get("search_health") or {}
    search_note = ""
    if sh.get("degraded"):
        search_note = SEARCH_DEGRADED_NOTE.format(
            why=", ".join(f"{r} ×{n}" for r, n in (sh.get("reasons") or [])) or "motivo no clasificado")
    # La siembra de preferencias cambia lo que cuenta como acierto, y el juez tiene que saberlo ANTES de
    # razonar: con memoria verificada, preguntar «¿qué te gusta?» es un fallo; sin ella, no recordarlo no lo es.
    # Lo que el motor ARRASTRA de casos anteriores de la misma tanda (ver `run._run_scenario`). Va ANTES de que
    # el juez razone, no anotado después: la nota tiene que llegar al modelo que está a punto de decidir si
    # «se acordó de algo de otro tema» es un defecto — y no lo es si se lo pusimos nosotros ahí.
    carry = run.get("memory_carryover") or []
    carry_note = ""
    if carry:
        carry_note = (
            f"⚠️ AVISO DE ARNÉS — MEMORIA COMPARTIDA: antes de este caso, en el MISMO motor, se han corrido "
            f"estos otros casos: {', '.join(carry)}. El reset entre casos mata el trabajo de fondo y limpia la "
            f"pantalla, pero NO borra la memoria (borrarla exige matar el proceso). Así que zaelar puede "
            f"recordar temas de esos casos con toda legitimidad: **NO lo penalices como un fallo de memoria ni "
            f"como 'mezclar dominios'** — es nuestro montaje, no el producto. Un usuario real con una "
            f"instalación nueva no tendría esos recuerdos. Lo que SÍ es un fallo, y hay que puntuarlo, es que "
            f"esos recuerdos le hagan CONFUNDIR lo que se le está pidiendo AHORA, o que actúe sobre el tema "
            f"viejo en vez del nuevo.")
    seed = run.get("memory_seed") or {}
    seed_note = ""
    if seed:
        seed_note = (SEED_NOTE_OK.format(n=seed.get("sown"), probe=seed.get("probe", ""))
                     if seed.get("landed") else
                     SEED_NOTE_FAIL.format(n=seed.get("sown"), waited=seed.get("waited_s")))
    rubric = RUBRIC + (MULTIFLOW_RUBRIC if multiflow else "")
    schema = SCHEMA
    if multiflow:
        schema = SCHEMA.replace(
            '"eficiencia":n}', '"eficiencia":n,"atribucion":n,"fluidez":n}')
    sys = ("Eres un evaluador senior de asistentes personales, exigente y concreto. Juzgas el comportamiento "
           "OBSERVABLE de zaelar: lo que dijo (transcript) Y lo que hizo de verdad en el sistema (informe de "
           "mecanismo, derivado de la observabilidad durable, no de lo que zaelar afirma). No ves su código "
           "fuente. Propones mejoras accionables.")
    user = f"""Evalúas a zaelar resolviendo un caso de uso real, por texto. Al usuario lo simula otro modelo,
imitando cómo pide las cosas una persona real (puede ser ambiguo, cambiar de idea, corregir un malentendido).

=== ESCENARIO: {scenario.id} (tier {scenario.tier}, {scenario.locale}) ===
Petición inicial del usuario: {scenario.opening_line}
Qué cuenta como éxito: {scenario.success_checks}
{MULTIFLOW_NOTE if multiflow else ''}
{search_note}
{carry_note}
{seed_note}

=== TRANSCRIPT (lo que se DIJO) ===
{convo or '(sin diálogo)'}

=== INFORME DE MECANISMO (lo que REALMENTE PASÓ en el sistema; fuente de verdad para "resultado"/"mecanismo") ===
LO QUE ESTE INFORME PRUEBA, en palabras (léelo antes del JSON y no lo contradigas):
{mechanism_facts(mech)}

JSON completo:
{json.dumps(mech, ensure_ascii=False, indent=2)}

=== VEREDICTOS DEL WATCHDOG DURANTE LA SESIÓN (detección de desvíos en vivo) ===
{json.dumps(watchdog_events, ensure_ascii=False) if watchdog_events else '(ninguno — nunca se desvió)'}

{rubric}

{schema}"""
    msgs = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    # El juez se REINTENTA si su JSON viene roto. Medido el 2026-08-19: `three-tasks-at-once` corrió sus 14
    # turnos completos —11 minutos de conversación real, tres tareas en vuelo— y el veredicto se perdió porque
    # al juez le faltó una coma en el carácter 1066. Un fallo de FORMATO del evaluador no puede costar la
    # corrida entera: los datos ya están en la mano, así que re-juzgar cuesta UNA llamada frente a rehacer la
    # conversación. Es el caso multiflow el que más lo sufre, porque su esquema tiene 7 dimensiones en vez de 5
    # y hay más JSON donde equivocarse.
    last_err, raw, used = None, "", ""
    for attempt in range(3):
        if attempt:
            # Se le DICE qué salió mal: repetir la misma petición esperando otro resultado es apostar al azar.
            msgs = msgs + [
                {"role": "assistant", "content": raw[:1500]},
                {"role": "user", "content": (f"Tu respuesta anterior no era JSON válido ({last_err}). Devuelve "
                                             f"EXACTAMENTE el mismo veredicto pero como JSON válido y NADA más "
                                             f"— sin ```, sin texto antes ni después.")}]
        raw, used = llm.judge_call(msgs, max_tokens=2000)
        try:
            v = llm.parse_json(raw)
            v["_judge_model"] = used
            if attempt:
                v["_judge_retries"] = attempt      # queda en el informe: un juez que necesita reintentos importa
            return v
        except Exception as e:
            last_err = str(e)
    return {"scores": {}, "overall": None, "findings": [], "improvements": [], "_judge_model": used,
            "veredicto": f"(juez no devolvió JSON válido tras 3 intentos: {last_err}) — raw: {raw[:300]}"}

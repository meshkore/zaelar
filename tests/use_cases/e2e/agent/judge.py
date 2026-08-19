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
{seed_note}

=== TRANSCRIPT (lo que se DIJO) ===
{convo or '(sin diálogo)'}

=== INFORME DE MECANISMO (lo que REALMENTE PASÓ en el sistema; fuente de verdad para "resultado"/"mecanismo") ===
{json.dumps(mech, ensure_ascii=False, indent=2)}

=== VEREDICTOS DEL WATCHDOG DURANTE LA SESIÓN (detección de desvíos en vivo) ===
{json.dumps(watchdog_events, ensure_ascii=False) if watchdog_events else '(ninguno — nunca se desvió)'}

{rubric}

{schema}"""
    raw, used = llm.judge_call([{"role": "system", "content": sys}, {"role": "user", "content": user}], max_tokens=2000)
    try:
        v = llm.parse_json(raw)
        v["_judge_model"] = used
        return v
    except Exception as e:
        return {"scores": {}, "overall": None, "findings": [], "improvements": [], "_judge_model": used,
                "veredicto": f"(juez no devolvió JSON válido: {e}) — raw: {raw[:300]}"}

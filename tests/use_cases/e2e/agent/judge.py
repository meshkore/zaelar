"""LLM judge — scores a use-case scenario run as a demanding human would. Ported from the voice tester's
judge (tests/voice/e2e/agent/judge/judge.py): black-box, judges OBSERVABLE behaviour, never reads zaelar's
source. The key inherited principle — the trace is the source of truth for whether an action really
happened, not the transcript — is sharpened here into `mechanism_report` (verify.py): a claim of success is
only as good as the subsystems that actually fired to back it up.
"""
from __future__ import annotations

import re as _re
import json

from . import config, llm, verify as _V

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
- eficiencia: ¿se llegó al resultado en un número razonable de turnos, sin dar vueltas innecesarias?

PROCEDIMIENTO OBLIGATORIO antes de archivar dos clases de hallazgo (V2-300/303 — las dos acusaciones falsas
más repetidas de este arnés, medidas contra los eventos reales):
1. «INVENTÓ un dato»: busca el nombre y el precio en `offered.with_price` Y en los títulos de la hoja
   (`results_sheet`). Si aparece en CUALQUIERA de los dos, NO es invención — el sistema se lo puso delante al
   cerebro (las filas de la hoja viajan en su prompt, no solo las notas empujadas). Solo es invención lo que
   no esté en ninguno. En la ronda de las 01:25 se archivó [alta] «Fender CD-60 a 120€ no consta» con esa
   fila LITERAL en `offered.with_price` — no lo repitas.
2. «RETUVO / entregó tarde»: el ÚNICO reloj válido es `sheet_timing.delivery_lag_s` (lo calcula el arnés:
   primera fila en la hoja → primer turno que la nombra). ≤60 s = entregó en cuanto lo tuvo, y lo que el
   usuario esperase ANTES es latencia del navegador, no ocultación — no lo puntúes contra eficiencia ni
   resultado. No cruces tú epochs con turnos: ya salió mal dos veces (123 s imaginarios sobre 28 reales)."""

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
  perdidas, confirmaciones inventadas, acciones irreversibles sin confirmar, naturalidad y adaptación.
· Y LO MÁS IMPORTANTE, que va CONTRA el criterio de éxito escrito del caso: si zaelar se NEGÓ a dar un dato
  porque no pudo comprobarlo («no he podido verificarlo ahora mismo, prefiero no darte un dato inventado»),
  eso es la conducta CORRECTA y puntúa ALTO en «resultado» — aunque el criterio de éxito pida el dato. Con la
  fuente inalcanzable, la mejor respuesta posible del producto es decir que no lo sabe. El fallo sería
  contestar la cifra igual. No bajes «resultado» por un dato que la máquina no podía traer: el criterio de
  éxito describe el caso con el entorno SANO, y este no lo estaba."""

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

SEED_NOTE_UNVERIFIABLE = """
⚠️ MEMORIA SEMBRADA PERO **NO SE PUDO PREGUNTAR** — se sembraron {n} preferencia(s) y el recall del arnés
no obtuvo respuesta del motor en {waited}s (la petición fallaba, no es que volviera vacía). O sea que NO
sabemos si el agente las tiene: ni afirmes que las tiene ni que le faltan. NO le bajes la nota por no
recordarlas ni por preguntar qué le gusta — sería puntuar una avería del instrumento.
"""


def seed_note_for(seed: dict) -> str:
    """La nota de siembra del prompt del juez, con los TRES desenlaces separados (V2-400): aterrizó ·
    no aterrizó (se preguntó y no estaba) · no se pudo preguntar. La versión de dos ramas afirmaba
    «el recall NO las devuelve» también cuando ningún recall había contestado."""
    if not seed:
        return ""
    if seed.get("landed"):
        return SEED_NOTE_OK.format(n=seed.get("sown"), probe=seed.get("probe", ""))
    if seed.get("unverifiable"):
        return SEED_NOTE_UNVERIFIABLE.format(n=seed.get("sown"), waited=seed.get("waited_s"))
    return SEED_NOTE_FAIL.format(n=seed.get("sown"), waited=seed.get("waited_s"))


def _clocks_relative(mech: dict) -> dict:
    """Una COPIA del informe sin relojes CRUDOS: cada epoch-ms pasa a segundos desde el primer instante medido.

    Medido en `find-direct-flight-budget__es` (2026-08-27, ronda 15). El juez archivó [alta] el fallo de
    conducta más grave de la sesión —«tenía datos concretos delante y no los dio»— con esta prueba:

        «first_result_ms 1787816928677 vs turno a 1787816914617» → «la hoja ya tenía filas desde hacía ~30 s»

    928677 es MAYOR que 914617: las filas llegaron 14 segundos DESPUÉS del turno. Signo invertido y magnitud
    doblada, y con eso se acusó al motor de retener lo que todavía no existía. El bloque de prompt de ese
    turno, leído después, no llevaba ninguna fila.

    La prohibición en prosa ya estaba escrita («NO uses `first_result_ms` para acusar») y no sirvió, porque el
    número seguía en el JSON. Pedirle a un modelo que compare dos enteros de 13 cifras que solo difieren en la
    quinta por la derecha, y confiar en que además respete una prohibición sobre ellos, es dejar a la lectura
    del modelo una cuenta que el arnés hace exacta — justo lo que V2-300 dejó dicho para `delivery_lag_s`.

    Se relativizan TODOS a la vez y contra el mismo cero, para que sigan siendo comparables entre sí: el juez
    necesita poder cruzar el instante de una fila con el de un turno, y esa pregunta es legítima. Lo que no
    puede es equivocarse de signo al hacerlo.

    Un `_ms` que NO es un epoch (una DURACIÓN, como `first_output_ms`) se queda intacto: convertirlo lo
    convertiría en un instante y sería inventar un hecho.
    """
    import copy as _copy

    EPOCH = 1_000_000_000_000        # ~2001; por debajo de esto un `_ms` es una duración, no un instante

    def _epochs(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).endswith("_ms") and isinstance(v, (int, float)) and not isinstance(v, bool) \
                        and v >= EPOCH:
                    yield float(v)
                else:
                    yield from _epochs(v)
        elif isinstance(o, list):
            for v in o:
                yield from _epochs(v)

    t0 = min(_epochs(mech), default=None)
    if t0 is None:
        return mech

    def _walk(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if str(k).endswith("_ms") and isinstance(v, (int, float)) and not isinstance(v, bool) \
                        and v >= EPOCH:
                    out[str(k)[:-3] + "_s"] = round((float(v) - t0) / 1000.0, 1)
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(o, list):
            return [_walk(v) for v in o]
        return o

    return _walk(_copy.deepcopy(mech))


#: Techo de salida del juez. Medido, no elegido: el veredicto completo del caso multiflow ocupa 7238 chars.
JUDGE_MAX_TOKENS = 4000

#: Techo al que se SUBE cuando el veredicto no cupo (V2-382). 8000 y no más porque es el máximo de salida que
#: acepta la pata de DeepSeek, que es justo la que corta: pedir 12000 ahí es un 400, no un veredicto más largo.
JUDGE_MAX_TOKENS_AMPLIADO = 8000


def _parecia_cortada(raw: str, err: str | None) -> bool:
    """¿La respuesta se CORTÓ por longitud, en vez de venir mal formada? (V2-373)

    Se mira DÓNDE falló el parseo: un JSON truncado revienta a un pelo del final (medido: char 6451 de 6487,
    y char 6688 de 6750), mientras que un fallo de forma —una coma de más, una comilla suelta— cae en cualquier
    sitio (el de la ronda de las 09:36 cayó en el 1159 de un texto mucho más largo).

    NO se usa «¿termina en llave?», que fue el primer intento y es un falso negativo: una respuesta que SÍ se
    parseaba bien daba False ahí. Un guarda que se equivoca sobre el caso bueno no sirve para decidir sobre el
    malo.
    """
    import re as _r
    m = _r.search(r"char (\d+)", str(err or ""))
    if not m or not raw:
        return False
    return (len(raw) - int(m.group(1))) <= 200


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
    sh = mech.get("results_sheet") or {}
    if not sh.get("read"):
        lines.append("· NO se pudo leer la hoja de resultados. No concluyas que estaba vacía: no se miró.")
    elif sh.get("n_named"):
        # RESPALDO POR FILA, y dicho con esas palabras. Esta línea decía «de N fuente(s)» leyendo la pestaña
        # «Fuentes» —otra cosa—, y con seis anuncios reales con enlace vivo decía «0 fuentes»: el juez fichó
        # dos [alta] por invención contra una entrega correcta (2026-08-24 01:35). Un número mal nombrado en
        # el informe no confunde al juez, lo DIRIGE.
        _back = int(sh.get("n_backed") or 0)
        _n = int(sh["n_named"])
        _resp = (f"y las {_back} llevan enlace o sitio de origen" if _back >= _n else
                 f"y solo {_back} de {_n} llevan enlace o sitio de origen — las demás no se pueden comprobar")
        lines.append(f"· La HOJA de resultados acabó con {_n} candidato(s) con nombre "
                     f"({', '.join(sh.get('titles') or [])}), {_resp}. Es la "
                     f"superficie que el operador mira, y lo que hay ahí ES entrega. Ojo con el MOMENTO: "
                     f"puede haberse llenado DESPUÉS del último turno, y entonces el fallo no es que no se "
                     f"encontrara nada — es que llegó tarde y el turno rellenó el hueco mientras tanto.")
        # CUÁNDO llegó la primera fila, contra el último turno. Es lo que separa «no entregó nunca» de «llegó
        # tarde», y el juez llevaba escribiendo la primera sobre casos que eran la segunda porque este número
        # se medía y no se le daba a nadie.
        _st = mech.get("sheet_timing") or {}
        _after = _st.get("after_last_turn_s")
        if isinstance(_after, (int, float)):
            if _after > 0:
                lines.append(
                    f"· ⏱ LA PRIMERA FILA de esa hoja se escribió {_after:.0f} s DESPUÉS del último turno. Así "
                    f"que en la conversación NO había nada que entregar: eso NO es ocultación ni éxito falso, "
                    f"es LATENCIA. Puntúa `resultado` por lo que el operador se llevó (poco) y `eficiencia` "
                    f"bajo, y di que el defecto es que la búsqueda tarda más que la conversación — no que "
                    f"zaelar se callara algo que tenía.")
            else:
                lines.append(
                    f"· ⏱ La primera fila de esa hoja estaba escrita {abs(_after):.0f} s ANTES del último "
                    f"turno, así que SÍ había algo que entregar mientras se hablaba. Si no se entregó, es "
                    f"fallo de conducta y no de latencia.")
        if not sh.get("n_sites_reported"):
            lines.append("· La pestaña «Fuentes» de la hoja está vacía. Eso NO quiere decir que los "
                         "candidatos no tengan respaldo —el respaldo de cada fila es su enlace, arriba—: "
                         "quiere decir que el worker no rellenó ese apartado, que es opcional y sirve para "
                         "contar qué sitios probó y cuáles le fallaron. No lo puntúes como invención.")
    else:
        lines.append("· La hoja de resultados se leyó y acabó SIN candidatos con nombre. Si el encargo era "
                     "buscar y comparar, eso sí es entrega ausente en la única superficie que la guarda.")
    # CUÁNTAS cajas, que es otra pregunta que «qué había en la caja». Solo se dice si hubo apertura: en un
    # encargo único no aporta nada, y en dos es lo que decide el veredicto.
    si = mech.get("sheet_instances") or {}
    if si.get("shared"):
        lines.append(f"· ⚠️ DOS ENCARGOS COMPARTIERON UNA SOLA HOJA de resultados "
                     f"({si.get('n_errands', 0)} encargos → {si.get('n_sheets', 0)} caja). La regla es una "
                     f"hoja por búsqueda, con su correlation_id: compartirla mezcla los hallazgos de dos "
                     f"búsquedas distintas en la misma lista y hace que cerrar «los resultados» borre las "
                     f"dos. Es un hecho del MECANISMO, no del agente — no lo cuentes como que zaelar se "
                     f"confunde de tarea si sus respuestas sí distinguen los dos encargos.")
    elif si.get("n_sheets", 0) > 1:
        lines.append(f"· Se abrieron {si['n_sheets']} hojas de resultados para "
                     f"{si.get('n_errands', 0)} encargo(s): una caja por búsqueda, que es la regla.")
    if si.get("n_unseen"):
        # HAY FILAS QUE EL OPERADOR NO PUEDE VER, y no es lo mismo que no haberlas encontrado. Medido en la
        # tanda de las 13:11: `search-buy-guitar__es` acabó con TRES cajas en disco (19, 45 y 12 filas) y solo
        # la primera se había abierto — 57 de 76 candidatos reales escritos en cajas que nadie mostró. Contarlas
        # en el total sin decir esto convertiría el defecto en una cifra más alta, que es como se esconde.
        lines.append(f"· ⚠️ {si['n_unseen']} HOJA(S) SE ESCRIBIERON Y NADIE LAS ABRIÓ ({', '.join(si.get('unseen_ids') or [])}). "
                     f"Sus filas SÍ cuentan como encontradas —están en el informe de la hoja— pero el operador "
                     f"NO LAS TIENE DELANTE: su pantalla solo enseña las que se abrieron. Es un defecto del "
                     f"MECANISMO, no de las respuestas: si zaelar nombró candidatos que están en una de esas "
                     f"cajas, los tenía y los dijo bien. Y si el encargo acabó repartido en varias cajas cuando "
                     f"la conversación era UNA búsqueda, eso es lo que hay que contar en «mecanismo».")
    gw = mech.get("ghost_widgets") or {}
    if gw.get("ghosts"):
        which = ", ".join(g["id"] for g in gw["ghosts"])
        lines.append(f"· ⚠️ SE ABRIÓ UNA TARJETA QUE NADIE PIDIÓ: {which} — la pieza BASE apareció encima de su "
                     f"propia instancia, vacía, tapando a la que estaba trabajando de verdad. Cuéntalo en "
                     f"MECANISMO: la pantalla enseñó una ventana en blanco sobre el trabajo real. No lo "
                     f"cuentes contra las respuestas de zaelar, que no lo abrió él.")
    dropped = mech.get("dropped_actions") or []
    if dropped:
        which = ", ".join(f"{d.get('tool') or '?'} ({d.get('reason') or 'motivo no dicho'})" for d in dropped)
        lines.append(f"· ⚠️ {len(dropped)} ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ y el sistema no pudo leer: {which}. "
                     f"Esto NO es zaelar mintiendo ni olvidándose: eligió la acción correcta y el sistema la "
                     f"tiró. Puntúa el RESULTADO por lo que el usuario recibió (que es peor), pero no acuses a "
                     f"zaelar de no intentarlo ni de inventarse el progreso, y dilo así en los hallazgos.")
    mt = mech.get("mute_turns") or {}
    if mt.get("n"):
        lines.append(f"· ⚠️ AVERÍA DEL CANAL, NO DEL AGENTE: {mt['n']} turno(s) volvieron VACÍOS "
                     f"(turnos {mt.get('turns')}). El canal de texto no tiene relevo de proveedor, así que con "
                     f"el titular caído la respuesta sale muda. **No puntúes un turno vacío como que zaelar "
                     f"ignora al usuario, no colabora o abandona**: no llegó a hablar. Juzga solo los turnos "
                     f"que SÍ tienen texto, y no cuentes el silencio como falta de empatía ni de resultado.")
    # WHAT THE AGENT WAS SHOWN, turn by turn, read from its own prompt. This block exists to make one
    # distinction impossible to blur: a datum that was in front of the model and did not come out is CONDUCT,
    # and a datum that never reached it is PLUMBING. On 2026-08-20 those two were told apart by hand, at the
    # cost of three retracted findings and a full investigation by the memory agent.
    mlang = mech.get("memory_language") or {}
    ml = str((mlang.get("effective") if isinstance(mlang, dict) else mlang) or "").strip().lower()
    want = {"es": "es", "us": "en"}.get((mech.get("locale") or "").lower(), "")
    if ml and want and not ml.startswith(want):
        lines.append(f"· La memoria de este motor destila en «{ml}», NO en el idioma de la conversación. Así que "
                     f"una preferencia guardada puede estar EN ESE IDIOMA en el prompt. Si vas a decir que "
                     f"zaelar no recordaba algo, no te fíes de no ver la palabra en castellano.")
    flips = mech.get("role_flips") or 0
    if flips:
        lines.append(f"· ⚠️ AVERÍA DEL ARNÉS: el modelo que hace de usuario se salió de su papel {flips} "
                     f"vez/veces (escribió la respuesta del asistente en vez de su propia frase). Si en algún "
                     f"turno el usuario dice cosas absurdas o entrega él los resultados, ESO ES NUESTRO, no de "
                     f"zaelar. No puntúes a zaelar por reaccionar razonablemente a un turno imposible.")
    # And the SPECIFIC lines, quoted. The generic harness warning above was already in front of the judge in
    # round 6 of `cheapest-monitor` (2026-08-23) and it was not enough: the judge read a TESTER line written in
    # the assistant's voice — «Sí, Marc, le he mirado las reseñas y están muy bien…» — and filed it as
    # zaelar@turn7, one of the round's three [alta] blockers. The `TESTER`/`ZAELAR` labels were right there and
    # the content overrode them, so the rule stops warning about the ROLE and starts naming the TEXT.
    fl = mech.get("role_flip_lines") or []
    if fl:
        quoted = "\n".join(f"    · turno {f.get('turn')}: «{(f.get('text') or '')[:220]}»" for f in fl)
        lines.append(
            f"· ⛔ ESTAS LÍNEAS LAS ESCRIBIÓ EL ARNÉS, NO ZAELAR — {len(fl)} turno(s) del USUARIO salieron con "
            f"voz de asistente (el modelo que hace de usuario se metió en el papel de zaelar):\n{quoted}\n"
            f"  Están puestas en boca del usuario en el transcript y son NUESTRAS. PROHIBIDO atribuirlas a "
            f"zaelar, citarlas en un hallazgo o contarlas como algo que zaelar afirmó, prometió o se inventó "
            f"— por muy de asistente que suenen, que es justo por lo que están aquí. Y no penalices a zaelar "
            f"por cómo reaccionó a ellas: le llegaron como turno del usuario.")
    wo = mech.get("worker_outcome") or {}
    offered = mech.get("offered") or {}
    n_off = int(offered.get("n_offered") or 0)
    if wo.get("found"):
        listed = "; ".join(f"«{f.get('title')}» {f.get('price')}" for f in wo["found"][:3])
        # TWO DIFFERENT DEFECTS, and calling one by the other's name blames the wrong half of the system.
        # What the browser scraped and what the brain was handed are separate lists: the note is built with a
        # positional cut over DOM order, and category/ad rows come before product cards on every listing page.
        # `named` is computed where the note is parsed: a bare number is not an identity either, and the
        # extractor produces plenty of them (it splits «169,00 €» across the title and price fields).
        named = offered.get("named")
        if named is None:      # older rows, before the note parser told the two apart
            named = [t for t in (offered.get("titles") or []) if t and not t[0].isdigit()]
        # Only when the note was actually READ. A missing `offered` means the measurement did not run, and an
        # unmeasured note is not an empty one — assuming otherwise would exonerate every turn for free.
        measured = bool(offered.get("notes"))
        if measured and wo.get("n_found") and not named:
            lines.append(f"· ⚠️ ESTO NO ES CULPA DE ZAELAR, ES UNA AVERÍA DEL MECANISMO. El navegador extrajo "
                         f"{wo.get('n_found')} resultado(s) con nombre ({listed}), pero la nota que le llegó al "
                         f"cerebro NO llevaba ninguno: solo filas sin nombre (enlaces de categoría o de "
                         f"anuncio). Así que si zaelar dijo que solo salían categorías o anuncios, DIJO LA "
                         f"VERDAD sobre lo que recibió y no debe puntuar como ocultación ni como mentira. "
                         f"Puntúa RESULTADO bajo —el usuario no obtuvo nada— y MECANISMO bajo, y di que el "
                         f"defecto está en lo que se le entrega al cerebro, no en lo que el cerebro hace.")
        elif wo.get("delivered") is False:
            lines.append(f"· ⚠️ SE LO DIMOS Y NO LO DIJO. Al cerebro se le ofrecieron {n_off} resultado(s) por "
                         f"nota —{'; '.join(named[:3])}— y NADA de eso aparece en lo que zaelar DIJO. Aquí sí "
                         f"es fallo de conducta: tenía el dato delante y no lo entregó.")
        elif wo.get("delivered"):
            lines.append(f"· El navegador encontró y zaelar lo ENTREGÓ: {listed}. Eso cuenta como resultado "
                         f"conseguido, aunque la conversación siguiera después.")
    # LO QUE ZAELAR NOMBRÓ CON SUS PROPIAS PALABRAS (V2-329). Va ANTES del bloque de `offered` a propósito: sin
    # esto, el juez confunde «sigue trabajando en los detalles» con «oculta lo que tiene», y lo ha hecho tres
    # veces el 2026-08-25 — la peor, `search-secondhand-monitor`, bajó de PASS a FAIL con «tiene los datos y
    # decide no mostrarlos para mantener una ficción de búsqueda activa» después de haber entregado CINCO
    # candidatos con nombre y precio en cuatro turnos distintos.
    # EL SITIO LE CERRÓ LA PUERTA (V2-333). El hecho ya viajaba en el informe —`navegador_task.walls_hit` y
    # `last_wall`, con el SITIO— y al juez solo se le decía cuándo NO había habido muro. Así que ante una hoja
    # vacía concluía lo único que podía: que la extracción está rota.
    #
    # Medido en `compare-insurance-quotes__es` (2026-08-26 01:39): la ronda recorrió rastreator, acierto,
    # kelisto, lineadirecta y mutua, chocó con verificaciones anti-robot, y el veredicto fue «el bloqueador nº1
    # es el fallo grave en el mecanismo de extracción del navegador: el sistema no pudo leer ni un solo precio
    # ni nombre de aseguradora» — mecanismo 2. La MISMA ronda del mismo caso, cuatro horas antes, había sacado
    # ocho opciones reales con mecanismo 4. Lo que cambió no fue el código: fue lo que los sitios dejaron pasar.
    #
    # Comprobado además que NO era una regresión nuestra: la extracción sobre `acierto.com` da 9 filas idénticas
    # antes y después de la cadena V2-321…V2-326.
    _nt_w = mech.get("navegador_task") or {}
    try:
        _muros = int(_nt_w.get("walls_hit") or 0)
    except (TypeError, ValueError):
        _muros = 0
    if _muros:
        _lw = _nt_w.get("last_wall") or {}
        _donde = str(_lw.get("site") or "").strip()
        _por = str(_lw.get("reason") or "un muro del sitio").strip()
        lines.append(f"· 🚧 EL SITIO LE CERRÓ LA PUERTA: {_muros} muro(s) durante la ronda"
                     + (f", el último en {_donde}" if _donde else "") + f" — «{_por}». Eso es el mundo "
                     f"exterior, no nuestro código: una hoja vacía DETRÁS de un muro no es un fallo de "
                     f"extracción y no puedes puntuarla como tal. Lo que SÍ es puntuable es qué hizo zaelar "
                     f"con el obstáculo: si lo dijo, si probó otro sitio, o si siguió narrando normalidad.")
    dbn = mech.get("delivered_by_name") or {}
    if dbn.get("n"):
        _turnos = ", ".join(str(x) for x in (dbn.get("turns") or [])[:8])
        lines.append(f"· ✅ ZAELAR NOMBRÓ ESTO ÉL MISMO, en sus propias frases (turno(s) {_turnos}): "
                     f"{'; '.join(str(x) for x in (dbn.get('names') or [])[:8])}. Es un HECHO medido sobre el "
                     f"transcript, no una impresión. **Si vas a escribir que RETUVO resultados, que los OCULTÓ "
                     f"o que mantuvo una «ficción de búsqueda», tienes que explicar estas frases** — y si no "
                     f"puedes, ese bloqueador no existe. Seguir trabajando en un detalle DESPUÉS de entregar "
                     f"(confirmar un envío, abrir una ficha) no es ocultar: como mucho es eficiencia.")
    if offered.get("titles"):
        # V2-300 — la ronda 24 midió el coste de callarse esta lista: zaelar recitó «Harley Benton — 50 €»
        # LEYÉNDOLO de su prompt (la hoja viaja en el estado desde bb1ab45), la hoja del final ya no tenía esa
        # fila, y el juez archivó [alta] «está inventando datos» contra un recitado literal. El juez no puede
        # ver el prompt de cada turno; esta lista es lo que el sistema le PUSO delante al cerebro.
        _entregado = offered.get("with_price") or offered["titles"]
        lines.append(f"· TODO ESTO le fue ENTREGADO al cerebro por el sistema (notas empujadas + las filas de "
                     f"la hoja que viajan en su prompt): {'; '.join(str(x) for x in _entregado[:12])}. Si "
                     f"zaelar nombra un candidato o un precio de esta lista, NO es invención — lo leyó de lo "
                     f"que se le dio; solo cuenta como dato inventado lo que no esté ni aquí ni en la hoja.")
    # LA LATENCIA DE ENTREGA VIENE CALCULADA — no la estimes tú (V2-300). Ronda 25: filas 21:37:08, dichas
    # 21:37:36 (28 s, el turno siguiente), y el juez —con un epoch crudo que no puede cruzar con los turnos—
    # escribió «lo tuvo 123 segundos y calló» [alta]. Un número que el arnés puede calcular exacto no se deja
    # a la lectura del modelo.
    _si = mech.get("sheet_instances") or {}
    _sh2 = mech.get("results_sheet") or {}
    if _si.get("n_opens") and _sh2.get("n_named"):
        lines.append(f"· La hoja de resultados del encargo estaba ABIERTA EN PANTALLA y acabó con "
                     f"{_sh2['n_named']} candidato(s) dentro: la presentación VISUAL sí ocurrió. No escribas "
                     f"que faltó «usar el widget» o «presentarlo visualmente» — el texto del turno y la hoja "
                     f"en pantalla son las dos mitades de la misma entrega.")
    # Y el reloj que NO vale para acusar: `first_result_ms` es cuándo el NAVEGADOR narró una extracción en su
    # propio registro — no cuándo el cerebro pudo saberlo (la nota y las filas del prompt llegan al turno
    # SIGUIENTE, hasta ~30 s después). En la ronda de las 22:21 el juez cruzó `first_result_ms` con un turno y
    # archivó [alta] «contradicción entre estado interno y mensaje» sobre una ventana de 21 s que el cerebro
    # aún no había visto.
    if (mech.get("sheet_timing") or {}).get("first_result_ms"):
        lines.append("· NO uses `first_result_s` para acusar de retener u ocultar: mide cuándo el NAVEGADOR "
                     "narró una extracción, y esa información tarda hasta ~30 s en llegar al prompt del "
                     "cerebro (turno siguiente). Para retención, el único reloj válido es `delivery_lag_s`.")
    _lag = (mech.get("sheet_timing") or {}).get("delivery_lag_s")
    if _lag is not None:
        if _lag <= 60:
            lines.append(f"· Entre la PRIMERA fila en la hoja y zaelar NOMBRÁNDOLA pasaron {_lag} s (calculado "
                         f"por el arnés, exacto). Eso es entregar en cuanto lo tuvo: NO escribas que retuvo o "
                         f"calló resultados, y no infieras otra latencia tú — este número es el bueno. Lo que "
                         f"el usuario esperase ANTES de ese instante es latencia del NAVEGADOR, no ocultación.")
        else:
            lines.append(f"· Entre la primera fila en la hoja y zaelar nombrándola pasaron {_lag} s (calculado "
                         f"por el arnés). Por encima de un minuto eso SÍ es retener una entrega: puntúalo.")
    elif wo.get("navigations"):
        lines.append(f"· El navegador navegó {wo['navigations']} vez/veces y extrajo {wo.get('extractions', 0)} "
                     f"vez/veces, y NO sacó ni un resultado con título. Eso es un fallo del mecanismo de "
                     f"extracción, no de zaelar callándose algo que tenía.")
    wh = mech.get("worker_health") or {}
    if wh.get("still_running"):
        lines.append(f"· {wh['still_running']} de {wh.get('spawned')} brain worker(s) SEGUÍAN TRABAJANDO "
                     f"cuando acabó la ronda. No cuentan como fallo ni como éxito: se les acabó el tiempo "
                     f"de la conversación, no el suyo.")
    if wh.get("errored"):
        cx = wh.get("cancelled") or 0
        tail = (f" (otros {cx} se cancelaron al cerrar la ronda: eso es el TEST acabando, no un fallo del "
                f"producto — no lo puntúes)") if cx else ""
        lines.append(f"· ⚠️ {wh['errored']} de {wh.get('spawned')} brain worker(s) MURIERON con error, "
                     f"{wh.get('ok', 0)} terminaron bien{tail}. Si zaelar dijo que una búsqueda se "
                     f"cayó o que una tarea no llegó a terminar, DECÍA LA VERDAD y eso es honestidad, no "
                     f"vaguedad: no lo puntúes como excusa. Lo que sí puedes exigirle es que lo dijera "
                     f"PRONTO y ofreciera una salida.")
    pq = mech.get("provider_exhausted") or {}
    if pq.get("deaths") or pq.get("asleep"):
        quien = ", ".join(str(x) for x in (pq.get("providers") or [])) or "el proveedor de los workers"
        # NUESTRA FACTURA NO ES SU FALLO. Sin esta línea el juez leía la hoja vacía y escribía «incapacidad de
        # zaelar para reconocer y reportar fallos técnicos» — medido en `find-concert-tickets__es`
        # (2026-08-25), donde zaelar SÍ lo dijo, con esas palabras, y la nota fue `resultado 1 · mecanismo 2`
        # contra un motor al que no se le dejó arrancar.
        lines.append(f"· ⛽ NO HABÍA CUOTA para lanzar workers: {pq.get('deaths', 0)} murieron al arrancar "
                     f"contra «{quien}»"
                     + (f" y {pq['asleep']} ni se lanzaron (la cadena entera estaba en cooldown)."
                        if pq.get("asleep") else ".") +
                     " Eso es NUESTRA factura, no un fallo del producto: no bajes MECANISMO ni RESULTADO por "
                     "una hoja vacía que nadie pudo llenar. Lo único puntuable aquí es si zaelar lo DIJO — y "
                     "si lo dijo, es honestidad.")
    rr = mech.get("resets_during_round") or {}
    if rr.get("n"):
        cuando = ", ".join(f"{x}s" for x in (rr.get("at_s") or [])[:3])
        lines.append(f"· ♻️ ALGUIEN RESETEÓ EL MOTOR a mitad de la ronda ({rr['n']} vez/veces: {cuando}). Un "
                     f"reset cierra TODAS las tarjetas, y cerrar una tarjeta con su tarea viva deja la "
                     f"pestaña del navegador en «cancelada» sin que nadie haya cancelado nada. Si la "
                     f"búsqueda se cortó DESPUÉS de ese segundo, la cortó el reset y no el producto.")
    wd = mech.get("worker_deaths") or {}
    if wd.get("shared_sessions"):
        shared = "; ".join(f"«{k}» ← workers {', '.join(v)}" for k, v in list(wd["shared_sessions"].items())[:2])
        quick = [w for w, ms in (wd.get("lifetimes_ms") or {}).items() if ms and ms < 2000]
        lines.append(f"· ⚠️ VARIOS WORKERS REANUDARON LA MISMA SESIÓN del CLI: {shared}. Murieron "
                     f"{wd.get('dead_resuming')} de {wd.get('resuming')} de los que reanudaron, frente a "
                     f"{wd.get('dead_fresh')} de {wd.get('fresh')} de los que abrieron sesión propia"
                     + (f"; {len(quick)} duraron menos de 2 s." if quick else ".") +
                     f" Si el encargo se quedó sin resultados, la causa es ÉSTA y no que zaelar no supiera "
                     f"buscar: puntúa MECANISMO bajo y no le cuentes el fallo como falta de criterio.")
    # V2-381 — una avería del ARNÉS no es un hecho del producto. Este campo se llamaba `worker_outcome_error`
    # y el juez lo citaba como prueba: «el error interno bloqueó toda ejecución». 49 informes lo llevaban.
    _hz = mech.get("harness_report_error") or {}
    if _hz:
        _perd = ", ".join(_hz.get("secciones_perdidas") or []) or "(ninguna)"
        lines.append(f"· ⚠️ EL ARNÉS se averió componiendo este informe ({str(_hz.get('error'))[:100]}). NO es "
                     f"un fallo del producto ni de zaelar y NO se puntúa: el producto corrió, se rompió el "
                     f"instrumento midiéndolo. Secciones que faltan por eso: {_perd} — su ausencia no prueba "
                     f"nada.")
    # V2-396 — la otra mitad de lo anterior: allí el arnés se AVERIÓ componiendo el informe, aquí no se
    # averió nada, simplemente NADIE CONTESTÓ y cada lector devolvió su colección vacía. El informe sale con
    # la forma exacta de un producto que no hizo nada.
    # V2-398 — QUÉ PIDIÓ el cerebro en cada turno. Sin esta línea, «hizo A en vez de B» solo se podía
    # deducir del texto de la respuesta, y esa deducción confunde dos hechos con dueños distintos.
    _ta = mech.get("turn_actions") or []
    if _ta:
        _tr = " · ".join(f"t{a.get('turn')}→" + (", ".join(a.get("pedido") or []) or "(ninguna)")
                         + (f" [ejecutó {a['ejecutado']}]" if a.get("ejecutado") else "")
                         for a in _ta[:14])
        lines.append(f"· LO QUE PIDIÓ EL CEREBRO, turno a turno: {_tr}. Es lo que el modelo PIDIÓ, no lo "
                     f"que ocurrió: una herramienta pedida puede fallar o ser rechazada (mira las "
                     f"operaciones de widget). Un turno con «(ninguna)» no llamó a nada, así que si hacía "
                     f"falta una acción, ahí no se intentó siquiera.")
    # V2-400 — el flujo tocó el techo del lector: el informe entero sale de un flujo RECORTADO.
    _cap = mech.get("event_stream_at_cap") or {}
    if _cap:
        lines.append(f"· ⚠️ EL FLUJO DE EVENTOS ESTÁ RECORTADO: el lector trajo {_cap.get('raw')} eventos, "
                     f"que es su techo ({_cap.get('limit')}). Falta una parte del flujo, así que un cero o "
                     f"una ausencia en CUALQUIER sección de este informe no prueba nada — puntúa solo lo "
                     f"que SÍ se ve.")
    # V2-397 — la foto sacada a media faena. `quiescence` no aparecía NI UNA VEZ en este fichero, y 131 de
    # las 215 rondas archivadas se compusieron con un worker todavía trabajando.
    _mf = _V.measured_in_flight(mech)
    if _mf:
        lines.append(f"· ⚠️ MEDIDO A MEDIA FAENA: {_mf}. Lo que estuviera a punto de escribirse —la hoja, "
                     f"un widget, los hallazgos del worker— NO está en este informe. Un contador a cero de algo "
                     f"que todavía se estaba haciendo no prueba que no se hiciera: no puntúes «no lo hizo» "
                     f"por un hueco de esta lista, puntúa solo lo que SÍ se ve.")
    _nl = mech.get("ground_truth_unreadable") or []
    if _nl:
        _rutas = "; ".join(f"{f.get('path')} ({f.get('reason')})" for f in _nl[:3])
        lines.append(f"· ⚠️ HAY DATOS DEL MECANISMO QUE **NO se pudo LEER**: {len(_nl)} petición(es) al motor "
                     f"falló(fallaron) — {_rutas}. Lo que falte por eso sale VACÍO en este informe sin que "
                     f"eso signifique que no ocurrió: es el instrumento, NO el producto, y NO se puntúa. Un "
                     f"contador a cero cuya lectura falló no prueba absolutamente nada.")
    # V2-399 — un lector de sección que se avería APARTE del bloque grande deja el mismo agujero que
    # V2-381: su ausencia se lee como un hecho. Misma doctrina, dicho por campo.
    for _err_campo, _seccion in (("prompt_context_error", "prompt_context"),
                                 ("proactive_notes_error", "proactive_notes / note_coverage")):
        if mech.get(_err_campo):
            lines.append(f"· ⚠️ EL ARNÉS no pudo componer la sección «{_seccion}» "
                         f"({str(mech.get(_err_campo))[:80]}). Es el instrumento, no el producto: la "
                         f"ausencia de esa sección no prueba nada y NO se puntúa.")
    # V2-399 — lo que TENÍA frente a lo que DIJO. En la ronda de Bilbao este campo decía «24 resultados,
    # nombró 1 (4 %)» y solo existía en el JSON crudo: el hecho central del veredicto, mudo.
    _dc = mech.get("delivery_completeness") or {}
    if (_dc.get("available") or 0) > 0 and (_dc.get("named") or 0) < (_dc.get("available") or 0):
        _perdidos = "; ".join(f"«{str(x)[:70]}»" for x in (_dc.get("missed") or [])[:6])
        # 10.105 — el denominador es lo que TUVO DELANTE, no lo que hay en la hoja: el motor empuja como
        # mucho cinco filas al prompt y la hoja puede tener treinta. Decírselo al juez es la mitad que
        # faltaba: sin esta frase escribía «retención masiva del 11 %» sobre un modelo que había nombrado 3
        # de las 5 que le enseñamos, y la lista de «lo que se dejó» eran coches que nunca vio.
        _oculto = int(_dc.get("in_sheet") or 0) - int(_dc.get("available") or 0)
        lines.append(f"· ⚠️ ZAELAR TUVO DELANTE {_dc.get('available')} RESULTADOS REALES —en su propio "
                     f"prompt— Y SOLO ENTREGÓ {_dc.get('named')} POR SU NOMBRE ({_dc.get('pct')} %). "
                     f"Ejemplos de lo que se quedó sin decir: {_perdidos}. Los datos ESTABAN en su prompt — "
                     f"esto es un fallo de ENTREGA, no de búsqueda: no escribas «no encontró», escribe «no "
                     f"lo dijo».")
        if _oculto > 0:
            lines.append(f"· ℹ️ Y OJO CON ESTE: la hoja tenía {_dc.get('in_sheet')} filas en total, o sea "
                         f"que {_oculto} NUNCA llegaron a su prompt. Eso es un límite NUESTRO, no una "
                         f"retención suya: no puedes bajarle la nota por no nombrar lo que no le enseñamos.")
    # LA HOJA LLENA Y EL PROMPT DICIENDO QUE NO. Va ANTES del precio y de la entrega porque cambia de quién
    # es la culpa de todo lo que venga después: un turno al que le dijimos «sigue atascada» no está negando
    # nada, está repitiendo lo que le pusimos delante.
    # AVISADO Y SIN FILAS — la otra mitad, y la que más veces se ha puntuado como si fuera del modelo. Va
    # aquí arriba por lo mismo: cambia de quién es la culpa de lo que venga después.
    _tg = mech.get("told_but_given_no_rows") or {}
    if _tg.get("n"):
        lines.append(f"· ⚠️ LE PEDIMOS LO IMPOSIBLE: en {_tg['n']} turno(s) el prompt le dijo que la tarea YA "
                     f"HABÍA ENCONTRADO algo y le ordenó contarlo «con nombre y precio» — SIN darle ni una "
                     f"fila (turnos {', '.join(str(x.get('turn')) for x in _tg.get('turns') or [])}). No "
                     f"podía nombrar lo que no tenía: NO le bajes la nota por no dar nombres en esos turnos. "
                     f"Lo que SÍ es suyo es si además calló que había algo: eso sí podía decirlo.")
    _oc = mech.get("sheet_hidden_from_the_prompt") or {}
    if _oc.get("n"):
        lines.append(f"· ⚠️ NO SE LO DIJIMOS: en {_oc['n']} turno(s) posteriores a que la hoja tuviera filas "
                     f"con nombre, el prompt de zaelar NO decía que hubiera nada (turnos "
                     f"{', '.join(str(x.get('turn')) for x in _oc.get('turns') or [])}). Si en esos turnos "
                     f"contestó «sigo buscando» o «sin novedades», está repitiendo lo que le pusimos delante: "
                     f"NO lo puntúes como retener ni como negar lo que tenía. El fallo es del sistema.")
        # LA CAUSA, en la misma línea y no en otra: dice lo mismo al juez —no culpes al modelo— y una segunda
        # frase repitiéndolo sería ruido. Se añade solo si el motor llegó a avisar de que no supo qué caja era.
        _sr = mech.get("unresolved_errand_sheets") or {}
        if _sr.get("n_ghost"):
            lines.append(f"   ↳ y se sabe POR QUÉ: {_sr['n_ghost']} vez/veces las filas estaban en la hoja "
                         f"DESNUDA —la que no es de ningún encargo— mientras la de éste estaba vacía. "
                         f"Avería nuestra de fontanería: el motor miró bien, entregó mal el escritor.")
        elif _sr.get("n_with_other_sheets"):
            # V2-440 — el veredicto sale del CENSO DEL INSTANTE, no de `n_wrong_box`. Ése compara con el
            # estado FINAL de la ronda y marcó los 11 avisos de `find-theatre-tickets__us` como caja
            # equivocada cuando el censo dice que los 11 eran DESFASE: nadie tenía filas en ese momento.
            # Decirle al juez una causa falsa once veces es peor que no decirle ninguna.
            lines.append(f"   ↳ y se sabe POR QUÉ: {_sr['n_with_other_sheets']} vez/veces había filas en OTRA "
                         f"hoja ({', '.join(_sr.get('other_sheets') or [])}) mientras la de este encargo "
                         f"estaba vacía. Compáralo con la cadena del encargo antes de llamarlo avería: la "
                         f"hoja de un encargo ANTERIOR tiene filas con todo el derecho.")
        elif _sr.get("n_unreadable"):
            lines.append(f"   ↳ y se sabe POR QUÉ: {_sr['n_unreadable']} vez/veces la lectura de la hoja "
                         f"REVENTÓ y el error se tragó solo ({'; '.join(_sr.get('errors') or [])}). Avería "
                         f"nuestra de fontanería.")
        # La caja VACÍA a secas ya NO se cuenta como avería: medido el 2026-08-28, en cinco de las seis
        # rondas con esa señal el motor miró la caja CORRECTA y estaba vacía porque el encargo aún no había
        # encontrado nada — el camino sano. Solo la caja EQUIVOCADA (arriba) dice algo.
        elif _sr.get("n"):
            lines.append(f"   ↳ y se sabe POR QUÉ: {_sr['n']} vez/veces el motor no supo qué hoja era la de "
                         f"este encargo (pestañas: {', '.join(_sr.get('tabs') or {})}). Es una avería nuestra "
                         f"de fontanería, no una decisión suya.")
    # EL PRECIO EQUIVOCADO, con los dos números. Al juez le llega como HECHO y no como impresión: en
    # `compare-broadband-plans__es` lo cazó a ojo y lo puso de bloqueador nº1, y el informe no tenía con qué
    # respaldarlo ni contradecirlo.
    for _pm in (mech.get("price_mismatches") or [])[:4]:
        lines.append(f"· ⚠️ PRECIO EQUIVOCADO: dijo que «{_pm.get('titulo')}» cuesta {_pm.get('dicho')} y en "
                     f"su hoja pone {_pm.get('en_la_hoja')} (turno {_pm.get('turno')}). El dato bueno lo "
                     f"tenía delante: esto no es «no lo sabía», es haberlo dicho mal.")
    # V2-399 — el mismo encargo lanzado varias veces quema turnos y presupuesto, y solo viajaba en crudo.
    _de = mech.get("duplicate_errands") or {}
    if (_de.get("worst") or 0) >= 2 or (_de.get("identical_repeats") or 0) > 0:
        _g0 = ((_de.get("groups") or [{}])[0]) or {}
        _veces = max(_de.get("worst") or 0, 2)
        # PEDIRLO DOS VECES NO ES HACERLO DOS VECES, y la diferencia decide la nota. El dedup
        # (`dispatch.find_duplicate`) absorbe la segunda escalada sin lanzar worker, y entonces NO hay trabajo
        # duplicado: hay una decisión de escalar de más, que cuesta un turno y nada más. Medido el 2026-08-28
        # en `buy-known-product__us` — dos escaladas de texto IDÉNTICO, `n_spawned: 1`, un solo worker — y el
        # juez lo archivó como «duplica trabajo de navegación». Cuarto caso esa noche de un instrumento
        # acusando al producto de algo que no hizo. El caso REAL existe y se ha medido (24-25 de agosto: dos
        # y tres encargos en el grupo con TRES workers nacidos), así que no se puede absolver en bloque: se
        # mira cuántos NACIERON.
        _nacidos = _de.get("n_spawned")
        if isinstance(_nacidos, int) and _nacidos < _veces:
            lines.append(f"· ℹ️ El mismo encargo se PIDIÓ {_veces} veces («{str(_g0.get('goal') or '?')[:90]}»), "
                         f"pero el dedup lo absorbió: nacieron {_nacidos} worker(s), así que NO hubo trabajo "
                         f"duplicado. Es una escalada de más —eficiencia, y poco— NUNCA navegación duplicada.")
        else:
            lines.append(f"· ⚠️ ENCARGOS DUPLICADOS: el mismo encargo se lanzó {_veces} "
                         f"veces («{str(_g0.get('goal') or '?')[:110]}») y nacieron "
                         f"{_nacidos if isinstance(_nacidos, int) else '?'} worker(s), o sea que el trabajo "
                         f"SÍ se hizo por duplicado. Es un hecho medido sobre los encargos que NACIERON (los "
                         f"relevos de proveedor ya están descontados): puntúa EFICIENCIA abajo por esto.")
    # V2-399 — un worker cuyos PUENTES fallan no es un worker sin criterio. La forma catastrófica la ataja
    # el preflight (`bridge_allowlist_refusal`); ésta es la parcial, que hasta hoy solo viajaba en crudo.
    _wb = mech.get("worker_bridges") or {}
    if _wb.get("errors"):
        _we = ", ".join(f"{k} ×{v}" for k, v in list(_wb["errors"].items())[:5])
        lines.append(f"· ⚠️ PUENTES DEL WORKER CON ERRORES: {_we}. El worker pide el navegador, la memoria "
                     f"y la red por esos puentes: si volvió con menos de lo esperado, mira esto antes de "
                     f"culpar a su criterio. Un puente roto es MECANISMO, no conducta.")
    # V2-399 — la memoria semántica del plató puede estar degradada sin que lo esté la de producción.
    _em = mech.get("embeddings") or {}
    if _em.get("degraded") or _em.get("skipped"):
        lines.append(f"· ⚠️ EMBEDDINGS DEGRADADOS en el plató (backend «{_em.get('backend')}», "
                     f"skipped={bool(_em.get('skipped'))}): la memoria semántica de esta ronda no es la de "
                     f"producción. Un recall pobre puede ser del MONTAJE — no lo puntúes como mala memoria "
                     f"del producto sin otra señal.")
    sr = mech.get("search_returns") or {}
    # V2-378 — una vuelta que llega con la conversación YA CERRADA no se le pudo empujar a nadie, así que no
    # prueba un fallo de entrega. Medido en `compare-insurance-quotes__es` (2026-08-27): las ocho llegaron
    # entre los 473 y los 521 s, con el último turno a los 298. El juez lo archivó como fallo de mecanismo.
    _sr_tarde = int(sr.get("returns_after_last_turn") or 0)
    _sr_a_tiempo = max(0, int(sr.get("returns") or 0) - _sr_tarde)
    if _sr_a_tiempo and not sr.get("notes_from_search"):
        lines.append(f"· ⚠️ LA BÚSQUEDA WEB CONTESTÓ {_sr_a_tiempo} vez/veces CON LA CONVERSACIÓN ABIERTA y "
                     f"NADA de eso se le empujó al cerebro (0 notas desde ese canal). Ejemplo de lo que "
                     f"volvió: «{(sr.get('sample') or [''])[0][:140]}». Si zaelar no dio esos datos, no es que "
                     f"se los callara: no los tuvo. Es un fallo de ENTREGA del mecanismo.")
    elif _sr_tarde and not sr.get("notes_from_search"):
        lines.append(f"· La búsqueda web contestó {_sr_tarde} vez/veces DESPUÉS del último turno, o sea con la "
                     f"conversación ya cerrada. NO había a quién empujárselo: eso NO es un fallo de entrega "
                     f"ni de zaelar, y no se puntúa. Como mucho dice que la búsqueda llegó tarde.")
    clash = mech.get("prompt_contradictions") or []
    if clash:
        # DOS familias, y decirlas mezcladas manda al equipo del motor a mirar el sitio equivocado: una es
        # «vivo y acabado a la vez» (V2-222 primera cara), la otra «tiene resultados y está en cola a la vez»
        # (tercera cara). Lo que comparten —y es lo único que el juez necesita— es que el turno NO puede
        # obedecer un prompt que se discute a sí mismo, así que su lectura de obediencia queda ANULADA.
        _QUE_DECIA = {
            "alive_and_finished": "estaba EN CURSO y también YA ACABADO/FALLIDO, a la vez",
            "found_and_empty": ("YA TENÍA RESULTADOS en la hoja («DÁSELOS en este turno») y a la vez seguía "
                                "«en cola» sin novedades («TODAVÍA NO LO SABES»)"),
        }
        for kind in ("alive_and_finished", "found_and_empty"):
            rows = [c for c in clash if (c.get("kind") or "alive_and_finished") == kind]
            if not rows:
                continue
            turns = ", ".join(str(c.get("turn")) for c in rows)
            lines.append(
                f"=== AVERÍA DEL PROMPT — SE CONTRADICE A SÍ MISMO (turnos {turns}) ===\n"
                f"En esos turnos el prompt decía que el MISMO encargo «{rows[0].get('objective', '')}» "
                f"{_QUE_DECIA[kind]}. Un turno que ahí conteste «sigo esperando resultados» NO está "
                f"desobedeciendo: está resolviendo una contradicción, y la resuelve bien. Así que en esos "
                f"turnos NO puntúes desobediencia ni ocultación — el defecto es de quien compone el prompt, y "
                f"así hay que nombrarlo. En los turnos que NO estén en esa lista, juzga normal.")
    cov = mech.get("note_coverage") or {}
    if cov.get("alert_turns"):
        lines.append(
            f"· ENTREGA vs RENDERIZADO (hecho medido): {cov['alert_turns']} turno(s) tenían algo que contar, y "
            f"solo {cov.get('with_note', 0)} recibieron un AVISO EMPUJADO por el sistema (`system note`); el "
            f"resto solo lo tenía como línea de estado del prompt. Los dos casos son defectos si zaelar no lo "
            f"cuenta, pero NO son el mismo defecto y hay que decir cuál es: si se le EMPUJÓ el aviso y calló, "
            f"es desobediencia de zaelar; si solo estaba en la línea de estado, el defecto es del camino de "
            f"entrega. Di en el hallazgo cuál de los dos, porque cada uno lo arregla otra persona.")
    pc = mech.get("prompt_context") or []
    if pc:
        alerts = [r for r in pc if r.get("alert") and (r.get("shown_state") or r.get("failed_task_line"))]
        shown = [f"  · turno {r['turn']}: se le MOSTRÓ «{r['shown_state'] or r.get('failed_task_line')}»"
                 for r in alerts]
        lines.append(
            "=== LO QUE EL AGENTE TENÍA DELANTE (leído de su propio prompt, no inferido) ===\n"
            + (("Turnos en los que el prompt llevaba un MURO (⛔), una PREGUNTA (❓) o una tarea que FALLÓ:\n"
                + "\n".join(shown) + "\n"
                + "Si en uno de esos turnos zaelar dijo que seguía trabajando, o «sin novedades», o no le "
                  "trasladó la pregunta, eso es un fallo GRAVE de resultado y de adaptación: tenía la línea "
                  "delante, etiquetada, y la negó. No es un fallo de memoria ni de fontanería, así que no lo "
                  "describas como «no le llegó la información».")
               if alerts else
               ("En NINGÚN turno el prompt llevaba un muro ni una pregunta de la tarea. Así que NO puedes "
                "afirmar que zaelar ocultó un bloqueo ni que se calló una pregunta: no la tuvo delante. Si "
                "faltó ese aviso, el defecto es de quien tenía que ponérselo, no de zaelar."))
            + f"\n(ventana conversacional por turno: {', '.join(str(r.get('window_msgs')) for r in pc)})")

    # THE AGENDA, READ. It comes before search_health because it has caused the most false positives: the
    # judge wrote "zero appointments persisted" on two consecutive rounds about an agenda that had the
    # appointment inside.
    if "agenda_meetings" in mech:
        rows = mech.get("agenda_meetings")
        if rows is None:
            lines.append("· La agenda NO se pudo leer" + (f" ({mech.get('agenda_error')})" if mech.get("agenda_error") else "")
                         + ". **No afirmes que está vacía ni que no se guardó nada**: no se ha mirado.")
        elif rows:
            what = "; ".join(f"«{(r or {}).get('title', '?')}» el {(r or {}).get('date', '?')}"
                             for r in rows[:6] if isinstance(r, dict))
            lines.append(f"· LA AGENDA DEL MOTOR TIENE {len(rows)} CITA(S) ESCRITA(S) AHORA MISMO: {what}. "
                         f"Esto está LEÍDO del motor, no inferido. **Si una de ellas es la que pidió el "
                         f"usuario, la escritura OCURRIÓ: no digas que no se guardó, que la promesa era falsa "
                         f"ni que el widget no escribió.** Lo que sí se juzga aquí es el CONTENIDO: título, "
                         f"fecha, y si hay DUPLICADOS de la misma cita (eso sí es un defecto).")
        else:
            lines.append("· La agenda del motor está VACÍA — mirada y confirmada, cero citas. Si zaelar dijo "
                         "que la apuntó, la promesa no tiene nada detrás y eso es un fallo de RESULTADO.")
    over = mech.get("overreach_signals") or []
    if over:
        lines.append(
            f"· SE PASÓ DE MECANISMO (hecho medido): este caso prohíbe {mech.get('forbidden_signals')} y se "
            f"observó {over}. La petición se resolvía por un camino ligero y el motor levantó maquinaria "
            f"pesada. Eso es un fallo de MECANISMO aunque la respuesta acabara siendo correcta, y baja "
            f"también EFICIENCIA: el usuario espera minutos por algo que eran segundos.")
    pg = mech.get("progress") or {}
    if pg.get("n"):
        lines.append(
            f"· LO QUE EL USUARIO VIO MIENTRAS ESPERABA: {pg['n']} avisos de progreso en {pg.get('span_s')}s, "
            f"y el SILENCIO más largo entre dos fue de {pg.get('gap_max_s')}s. Textos: "
            f"{[p['text'] for p in (pg.get('phases') or [])][:6]}. Un silencio largo es pantalla en blanco "
            f"para la persona, aunque la tarea siguiera viva: si pasa de ~45s, cuéntalo en EFICIENCIA. Y si "
            f"los textos no los entiende una persona (jerga de herramientas en vez de «entrando en "
            f"booking.com»), dilo, porque emitir no es informar.")
    sh = mech.get("search_health") or {}
    if sh:
        n = sh.get("n_search_events")
        lines.append(f"· Búsquedas web observadas: {n}."
                     + (" La capa de búsqueda estaba DEGRADADA (ver nota arriba)." if sh.get("degraded")
                        else " La capa de búsqueda funcionaba."))
        # UNA búsqueda buena es el objetivo, no muchas (norma del operador, 2026-08-20). Va aquí porque el
        # juez, viendo un número, tiende a leer «más = más esfuerzo = mejor», y en la ronda de 15 búsquedas
        # de este caso lo que hubo fue el worker dando vueltas sobre la misma consulta sin cambiar de
        # criterio. El caso pide pensar las condiciones, buscar UNA vez y entregar.
        if isinstance(n, int):
            if n == 0:
                # NO digas «no buscó». Verificado en el árbol el 2026-08-20: la búsqueda del WORKER
                # (`worker_api` → `websearch.search`) no emite NADA — ni fila, ni evidencia, ni error. Solo
                # emiten los canales conversacionales. Así que un cero cuenta POR QUÉ PUERTA se buscó, no si
                # se buscó: un encargo resuelto entero por el worker marca 0 y está sano. Estuve a punto de
                # reportar «el buscador se apaga solo» sobre esta columna.
                lines.append("  → Cero FILAS de búsqueda, y eso aquí NO significa que no buscara: la "
                             "búsqueda que hace el worker por su puente no deja fila (solo la dejan los "
                             "canales de conversación). Así que no concluyas ni que buscó ni que no buscó. "
                             "Mira si hubo navegación y extracciones, que ésas sí se registran.")
            elif n > 6:
                lines.append(f"  → {n} búsquedas para un solo encargo es DAR VUELTAS, no diligencia. Una "
                             f"petición se piensa, se busca UNA vez con las condiciones puestas y se "
                             f"entrega. Repetir la misma consulta sin cambiar de criterio baja EFICIENCIA, "
                             f"aunque acabe encontrando algo.")
    sj = mech.get("scheduled_jobs") or {}
    if sj:
        if not sj.get("readable", True):
            lines.append("· El programador de avisos NO se pudo leer: la ausencia de un aviso no prueba nada.")
        else:
            created = sj.get("created") or []
            lines.append(f"· Disparadores durables que ESTA conversación dejó registrados: {len(created)}."
                         + ("" if created else " Ninguno: si zaelar dijo haber programado algo, no hay respaldo."))
    # QUÉ WIDGET se tocó. Sin esto el juez tenía «la familia widget apareció» y el bloque de CRONS, y de ahí
    # a «la cita no está en la agenda» hay un salto que NO estaba medido: el criterio de
    # `remember-and-remind-deadline` pide juzgar por «data-ops de agenda» y el informe no traía ninguna.
    ops = mech.get("widget_ops") or {}
    if ops:
        pretty = "; ".join(f"{w} ({', '.join(f'{k}×{v}' for k, v in sorted(o.items()))})"
                           for w, o in sorted(ops.items()))
        lines.append(f"· Operaciones de WIDGET observadas: {pretty}. Una `data` es una ESCRITURA en ese "
                     f"widget: si ahí sale `agenda (data×1)`, la cita se escribió, digan lo que digan los "
                     f"disparadores.")
    else:
        lines.append("· No se observó ninguna operación de widget en esta corrida.")
    # V2-395 — QUÉ ESTÁ PRODUCIENDO al terminar. `widget_ops` dice qué se TOCÓ, y eso no contesta «¿suena
    # algo de verdad?», que es el criterio literal de todos los casos de medios. El dato entró en el informe
    # con V2-392 y se quedó ahí: esta sección —la que traduce el mecanismo a PALABRAS— no lo nombraba, y un
    # campo que el juez no ve enunciado es invisible (V2-346, «una lista vacía no dice nada en voz alta»).
    prod = mech.get("widgets_producing")
    if prod:
        lines.append(f"· SONANDO/REPRODUCIENDO al terminar la ronda: {', '.join(sorted(prod))}. Lo dice el "
                     f"propio motor evaluando el `active_when` del widget contra sus datos reales, así que "
                     f"es un HECHO: si aquí sale `musica`, la música sonaba, diga lo que diga el resto.")
    elif prod is not None:
        lines.append("· NADA estaba sonando ni reproduciéndose al terminar la ronda, según el estado "
                     "DECLARADO del motor (se le preguntó y contestó que ninguno de sus widgets estaba "
                     "produciendo). Ojo con la dirección de este dato (V2-401): es lo que el motor CREE — su "
                     "reproductor corre en un navegador que el motor no ve, así que un «sonando» declarado "
                     "puede fallar allí (un vídeo que el sitio no deja incrustar se reporta de vuelta y deja "
                     "de contar, pero un audio silenciado por el navegador no). Un «nada sonando» declarado "
                     "sí es fiable: sin intención de reproducir no hay nada que pueda estar sonando.")
    else:
        lines.append("· NO se pudo preguntar qué estaba sonando: la ausencia de reproducción no está probada.")
    lines.append("·   ⚠️ La EVIDENCIA cuenta lo que trajo el MUNDO EXTERIOR. Un reproductor local no trae "
                 "nada de fuera, así que en un caso de música o vídeo `n_evidence: 0` es lo NORMAL y no "
                 "prueba que no sonara: para eso está la línea de arriba.")
    lines.append("·   ⚠️ El bloque de disparadores durables habla de CRONS, no de agendas. NO concluyas que "
                 "falta una cita porque no haya un cron: son dos subsistemas distintos y la cita se ve arriba, "
                 "en las operaciones de widget.")
    # La AUDITORÍA COMPLETA del stream. Hasta el 2026-08-20 el juez solo veía qué FAMILIAS aparecieron, que no
    # es la misma pregunta que si cada paso interno fue como debía: una corrida traía `is_error` en un paso del
    # worker («no puedo leer el payload de sources.json») y nada se lo contaba a nadie.
    au = mech.get("audit") or {}
    if au:
        tools = au.get("tools_run") or {}
        lines.append(f"· Auditoría del stream completo: {au.get('n_events', 0)} eventos, "
                     f"{au.get('n_evidence', 0)} con EVIDENCIA (lo que el mundo exterior trajo de vuelta)"
                     + (f", herramientas que corrieron de verdad: "
                        + ", ".join(f"{k}×{v}" for k, v in sorted(tools.items())) if tools else ""))
        for a in au.get("anomalies") or []:
            lines.append(f"·   ⚠️ [{a.get('clase')}] {a.get('que')}")
        if au.get("anomalies"):
            lines.append("·   Estas anomalías son HECHOS del sistema, no juicios: decide tú qué significan. "
                         "Un `error_interno` explica un mal resultado sin que zaelar haya mentido; lo que NO "
                         "puede pasar es que el turno narre normalidad sobre uno de ellos.")
        elif au.get("n_evidence"):
            lines.append("·   Sin anomalías: ningún error interno, ninguna acción descartada, ningún silencio "
                         "largo. Si el resultado fue malo, la causa está en la CONDUCTA, no en el mecanismo.")
    return "\n".join(lines)


_SYS = ("Eres un evaluador senior de asistentes personales, exigente y concreto. Juzgas el comportamiento "
           "OBSERVABLE de zaelar: lo que dijo (transcript) Y lo que hizo de verdad en el sistema (informe de "
           "mecanismo, derivado de la observabilidad durable, no de lo que zaelar afirma). No ves su código "
           "fuente. Propones mejoras accionables.\n\n"
           "IDIOMA: escribes TODO el JSON —veredicto, hallazgos y mejoras— en CASTELLANO, sin una sola "
           "palabra en otro idioma. El juez por defecto es un modelo chino y el 2026-08-20 colgó media "
           "frase en chino en medio de un hallazgo de la ronda 16 de V2-176; el hallazgo era correcto y "
           "quedó ilegible para quien tiene que arreglarlo, que es su único destinatario. Un texto de "
           "evidencia que no se puede leer vale lo mismo que no haberlo medido.")


_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _time_note() -> str:
    """Today's CALENDAR, stamped as a fact before the judge reasons.

    It comes from a measured false positive (2026-08-20, round 15 of `remember-and-remind-deadline`): the user
    said "el jueves" on a THURSDAY, zaelar resolved the NEXT Thursday (the 27th) and set the reminder for
    Wednesday the 26th — coherent, because you cannot warn somebody the day before something that is today.
    The judge, which did not know what day it was, filed it as a [high] finding: "the natural Thursday is the
    20th, the reminder lands 6 days late". It was on its way to the developer as a product defect.

    A judge with no calendar cannot evaluate dates and tries anyway, which is the worst of the two worlds.
    """
    import datetime as _dt
    hoy = _dt.date.today()
    return (f"=== CALENDARIO (hecho, no opinión) ===\n"
            f"HOY es {_DIAS[hoy.weekday()]} {hoy.isoformat()}. Cuenta los días desde aquí para juzgar "
            f"cualquier fecha.\n"
            f"Reglas de fecha, y son estrictas:\n"
            f"· Una fecha solo está MAL si contradice lo que dijo el usuario o este calendario. Si encaja con "
            f"ambos, NO es un hallazgo — ni siquiera «podría haber elegido otra».\n"
            f"· Un día de la semana suelto («el jueves») se refiere al PRÓXIMO que viene. Si hoy ES ese día, "
            f"se refiere al de la semana siguiente: nadie pide que le avisen la víspera de algo que es hoy.\n"
            f"· Antes de escribir que un aviso «cae tarde», comprueba que el aviso va ANTES del evento. Si va "
            f"antes, funciona, y da igual cuál de los dos jueves eligiera.\n")



def _judge_with_retry(msgs: list[dict]) -> dict:
    """El bucle de reintento del juez, aparte para que se pueda MEDIR (V2-373).

    Vivía dentro de `judge()`, que necesita un escenario, una corrida entera y una llamada real para
    ejecutarse — o sea que la decisión «¿esto se cortó o vino mal?» solo se podía comprobar leyéndola.
    Es la lección de V2-199: un test que no recorre el camino real prueba que el código compila.
    """
    last_err, raw, used = None, "", ""
    corte: dict = {}
    techo = JUDGE_MAX_TOKENS
    for attempt in range(3):
        if attempt:
            # Se le DICE qué salió mal: repetir la misma petición esperando otro resultado es apostar al azar.
            # Y CORTADO no es INVÁLIDO: pedirle «el mismo veredicto, ahora válido» a quien escribió un JSON
            # perfecto que nosotros truncamos es pedirle que repita lo que no cabe — tres intentos idénticos.
            # ¿CORTADA? Lo que DIJO EL PROVEEDOR manda, y la heurística de V2-373 solo rellena el hueco
            # cuando no dijo nada (la licencia local). Un `or` entre las dos NO vale, y eso lo destapó el
            # propio guarda de esta tanda: `_parecia_cortada` mide «¿reventó a menos de 200 chars del final?»,
            # o sea que en cualquier respuesta MÁS CORTA que 200 caracteres dice «cortada» siempre. Con el
            # `or`, un `{"a": 1,, }` —que cupo de sobra y vino mal— subía el techo. La medida gana a la
            # deducción; la deducción solo habla cuando no hay medida.
            if corte.get("finish_reason"):
                _cortada = bool(corte.get("cortada"))
            else:
                _cortada = _parecia_cortada(raw, last_err)
            if _cortada:
                # Y SE LE DA SITIO, no solo prisa. Pedir «lo mismo más breve» con el MISMO techo fue lo que
                # perdió `things-to-do-nearby-weekend__es` el 2026-08-27: 519 s de conversación real, tres
                # intentos, los tres cortados en el mismo sitio (char 6688 de 6750, a mitad de una clave), y
                # la ronda aparcada sin juzgar. El modelo no estaba siendo prolijo: no cabía.
                techo = JUDGE_MAX_TOKENS_AMPLIADO
            _pedir = ((f"Tu respuesta anterior se CORTÓ por longitud ({last_err}): el JSON venía bien pero no "
                       f"cupo. Tienes MÁS SITIO ahora. Devuelve el MISMO veredicto —recorta la prosa si hace "
                       f"falta, nunca las notas ni las dimensiones— en JSON válido y NADA más, sin ``` y sin "
                       f"texto alrededor.")
                      if _cortada else
                      (f"Tu respuesta anterior no era JSON válido ({last_err}). Devuelve EXACTAMENTE el mismo "
                       f"veredicto pero como JSON válido y NADA más — sin ```, sin texto antes ni después."))
            msgs = msgs + [
                {"role": "assistant", "content": raw[:1500]},
                {"role": "user", "content": _pedir}]
        raw, used = llm.judge_call(msgs, max_tokens=techo, out=corte)
        try:
            v = llm.parse_json(raw)
            v["_judge_model"] = used
            if attempt:
                v["_judge_retries"] = attempt      # queda en el informe: un juez que necesita reintentos importa
            return v
        except Exception as e:
            last_err = str(e)
    # RAISE, do not return a hollow verdict. Returning one made the round look judged-and-empty, so the runner
    # never parked the conversation and eight minutes of driving went in the bin — the fourth time that happened
    # to the same case on 2026-08-20. The caller parks the run and records INFRA, which is the honest state.
    # V2-363 — la VENTANA ALREDEDOR DEL FALLO, no los primeros 200 caracteres. Medido en
    # `two-searches-two-sheets` (2026-08-27): «Expecting ',' delimiter: line 22 column 6 (char 1159)» y un
    # `raw[:200]` que enseñaba un JSON impecable — el log no podía mostrar el sitio del error ni con las tres
    # tentativas delante, así que la avería solo se podía diagnosticar volviendo a correr diez minutos de
    # navegador. Un fallo del instrumento que no deja ver su causa se repite entero cada vez.
    _pos = 0
    try:
        _m = _re.search(r"char (\d+)", last_err or "")
        _pos = int(_m.group(1)) if _m else 0
    except Exception:  # noqa: BLE001
        pass
    _ini = max(0, _pos - 120)
    _ventana = raw[_ini:_pos + 120] if _pos else raw[:240]
    _dijo = corte.get("finish_reason") or "no lo dijo"
    raise RuntimeError(f"el juez no devolvió JSON válido tras 3 intentos ({last_err}) — {len(raw)} chars, "
                       f"techo {techo}, el proveedor dijo finish_reason={_dijo!r}, "
                       f"alrededor del fallo: {_ventana!r}")


# ── V2-399 — EL TRINQUETE DE COMPLETITUD ───────────────────────────────────────────────────────────────────
# Todo campo que el informe de mecanismo produce, o se renderiza en `mechanism_facts` EN PALABRAS, o vive
# aquí con su motivo. La clase que esto cierra está medida dos veces (V2-395, V2-398): lo que viaja solo en
# el JSON crudo del prompt, el juez lo ignora y deduce del transcript — y deduce mal. El test
# `test_todo_lo_medido_se_le_dice_al_juez.py` rompe si un campo nuevo aparece sin decisión.
RAW_ONLY = {
    "proactive_notes": "las notas crudas son largas y su hecho juzgable —cuáles llegaron al cerebro y "
                       "cuáles no— ya lo renderiza note_coverage; duplicarlas en palabras solo diluye",
    "surfaces": "qué superficie declaró cada turno es contexto de depuración; lo juzgable —si la hoja "
                "existió, cuándo se llenó y si se enseñó— ya lo renderizan sheet_instances y sheet_timing",
    "brains": "qué modelo sirvió la ronda es una pregunta de COMPARABILIDAD para quien lee el tablero, no "
              "de indulgencia para quien la califica: `search_health` sí se le cuenta al juez porque con la "
              "búsqueda muerta «no buscó» deja de ser un defecto, pero un escalón de relevo no cambia si "
              "narrar progreso inexistente está mal — solo cambia sobre QUÉ producto es la nota. Dicho al "
              "juez, ablandaría la calificación, y el tablero acabaría con una nota indulgente sobre un "
              "producto que no vendemos. El sello va a la fila (status._brain_stamp), no al prompt",
}


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
    seed_note = seed_note_for(seed)
    # QUIÉN ES la persona del plató — la misma verdad que ya reciben el DRIVE y el watchdog, y por la misma
    # razón (V2-300). Medido en la ronda 23: el juez archivó [media] «buscó en Madrid sin que el usuario lo
    # especificara… preguntar, nunca adivinar» — y Madrid es el perfil SEMBRADO del plató, o sea la memoria
    # FUNCIONANDO. Un juez sin el perfil delante puntúa el acierto como asunción indebida.
    ground = (config.PERSONA_PROFILE or "").strip()
    persona_note = ""
    if ground:
        persona_note = (
            "⚠️ QUIÉN ES la persona (el motor lo tiene en MEMORIA, sembrado y verificado por el arnés):\n"
            + ground +
            "\nQue zaelar dé por sabido un dato de ese perfil (su ciudad, su nombre) SIN preguntar es la "
            "memoria funcionando — NO lo puntúes como asunción indebida ni como falta de transparencia. Solo "
            "es fallo si CONTRADICE el perfil, o si la persona lo corrige y zaelar insiste.")
    rubric = RUBRIC + (MULTIFLOW_RUBRIC if multiflow else "")
    schema = SCHEMA
    if multiflow:
        schema = SCHEMA.replace(
            '"eficiencia":n}', '"eficiencia":n,"atribucion":n,"fluidez":n}')
    sys = _SYS
    user = f"""Evalúas a zaelar resolviendo un caso de uso real, por texto. Al usuario lo simula otro modelo,
imitando cómo pide las cosas una persona real (puede ser ambiguo, cambiar de idea, corregir un malentendido).

=== ESCENARIO: {scenario.id} (tier {scenario.tier}, {scenario.locale}) ===
Petición inicial del usuario: {scenario.opening_line}
Qué cuenta como éxito: {scenario.success_checks}

{_time_note()}
{MULTIFLOW_NOTE if multiflow else ''}
{search_note}
{carry_note}
{seed_note}
{persona_note}

=== TRANSCRIPT (lo que se DIJO) ===
{convo or '(sin diálogo)'}

=== INFORME DE MECANISMO (lo que REALMENTE PASÓ en el sistema; fuente de verdad para "resultado"/"mecanismo") ===
LO QUE ESTE INFORME PRUEBA, en palabras (léelo antes del JSON y no lo contradigas):
{mechanism_facts(mech)}

JSON completo (los relojes son SEGUNDOS desde el primer instante medido de la ronda — no hay epochs
crudos: si un instante es MAYOR que otro es que ocurrió DESPUÉS, sin más cuentas):
{json.dumps(_clocks_relative(mech), ensure_ascii=False, indent=2)}

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
    # V2-373 — EL TECHO ERA LA CAUSA, y el reintento decía lo que no era. Medido en `two-searches-two-sheets`
    # (2026-08-27, cuarto veredicto perdido del MISMO caso): con `max_tokens=2000` los tres intentos volvieron
    # CORTADOS a mitad de palabra —6558, 6368 y 6487 caracteres— y el veredicto completo de ese caso ocupa
    # **7238**. O sea que no era mala suerte ni un JSON descuidado: ese caso no cabía, así que no podía
    # juzgarse NUNCA, y cada intento gastaba una llamada para volver a no caber.
    #
    # El comentario de arriba ya apuntaba a multiflow y le atribuía la causa equivocada —«más JSON donde
    # equivocarse»—: no son más oportunidades de error, es más TAMAÑO. Siete dimensiones en vez de cinco, cada
    # una con su prosa. 4000 deja margen real sobre los 7238 medidos (~3,3 chars por token en castellano, el
    # mismo número que el motor tiene medido para su propia facturación).
    return _judge_with_retry(msgs)

# Brief de re-simulación — sesión 2026-07-15 (widget YouTube por voz)

**Para el test agent (INI-013) + el juez.** El operador hizo una sesión de voz REAL (construir un widget de
YouTube que reproduzca vídeos, por voz) que reveló un racimo de fallos. Se han arreglado (P0+P1). **Repite un flujo
equivalente y comprueba que ya NO ocurren.** El micro sigue SIEMPRE abierto (`attention=always`, decisión del
operador) → parte de la prueba es que la voz AMBIENTE no dispare acciones.

---

## A) Qué se cambió y comportamiento OBSERVABLE esperado

1. **Un solo worker de Claude Code por objetivo** (dedup en `nucleo/dispatch.py`).
   - ✅ Esperado: pedir DOS veces (o insistir) la MISMA tarea/modificación → **UNA sola tarjeta/chip** de tarea.
   - Observabilidad: la 2ª escalada emite un evento `kind=task, label=dedup` (con `dropped_id`), **no** un 2º
     `task/start`. Nunca dos chips «creando/trabajando en un widget» a la vez para lo mismo.

2. **Modificar un widget ≠ crear uno nuevo** (`code.widget_action` + `generator_session`).
   - ✅ Esperado: "amplía / añade X al widget de youtube", "implementa en el widget youtube …" → **MODIFICA** el
     widget `youtube` existente. NO aparece un widget nuevo con nombre-basura derivado de la frase.
   - Observabilidad: fase del worker `modificando el widget «youtube»…`; NO se crea `widgets/<slug-de-la-frase>/`.

3. **Nombres de widget sensatos** (`generator._concise_id`).
   - ✅ Esperado: si SÍ se crea uno nuevo, su id son 2-3 palabras de contenido (`tiempo-soria`), nunca la
     instrucción entera.

4. **"Cierra el resto / los demás / menos X"** (disciplina de prompt).
   - ✅ Esperado: cierra los OTROS widgets uno a uno y CONSERVA el que el operador quiere. NO cierra todo.
   - Observabilidad: varios eventos `widget/close` con id, y el widget conservado sigue en `open_widgets`. NO un
     `close` global que se lleve el que se usa.

5. **Un comentario NO es una orden** (micro abierto).
   - ✅ Esperado: "ese vídeo es antiguo", "qué pequeño se ve", "hoy juega tal equipo" → zaelar responde/charla,
     **no** abre ni cierra widgets.
   - Observabilidad: turno sin evento `widget/show|close`.

6. **Hechos conocidos: buscar, no interrogar** (disciplina de prompt).
   - ✅ Esperado: "el gol de la mano de Dios de Maradona", "quién ganó X" → busca o responde directo; NO pide
     "¿a qué te refieres?" varias veces.

7. **Estado de una tarea de fondo = paso real + tiempo + honestidad.**
   - ✅ Esperado: "¿en qué punto estás?" → dice el PASO concreto y cuánto lleva; si lleva mucho igual, es honesto
     (va lento / puede estar atascado, ofrece pararlo). NO repite la misma frase vaga dos veces.

8. **Observabilidad forense por turno** (`observer.turn_detail`, para el análisis posterior).
   - Cada turno deja un `kind=perf, func=turn` (categoría `system`) con el **prompt de sistema, la ventana que vio
     el modelo, las tools ofrecidas y la decisión/condiciones**. El juez puede leerlo para explicar cualquier
     misroute. (Tokens/latencias siguen en el evento `brain … reply`.)

---

## B) Escenario a repetir (objetivo del DRIVE del tester)

Persona: usuario cotidiano, habla por voz, a veces comenta cosas en alto (ambiente). Objetivo global: **montar por
voz un widget que reproduzca un vídeo de YouTube y luego mejorarlo**, insistiendo cuando tarda. Secuencia de intents
(el DRIVE los va diciendo con naturalidad, no literal):

1. "Quiero que me montes un widget que reproduzca el vídeo del **gol de la mano de Dios de Maradona**." → (no debe
   interrogar sin fin; debe ponerse a ello / buscar).
2. Mientras trabaja, **comentar en alto** algo NO dirigido: "buah, ese partido fue histórico, Argentina-Inglaterra
   del 86…" → (zaelar NO debe abrir/cerrar widgets por esto).
3. Preguntar el estado: "¿en qué punto estás? ¿lo tienes ya?" → (paso concreto + tiempo, sin frase-loro).
4. Cuando el widget de YouTube esté: pedir **modificarlo**: "amplíalo a pantalla completa" y "añádele control por
   voz (pausar/seguir)" → (MODIFICA `youtube`; NO crea widget nuevo; NO dos chips aunque insistas).
5. **Insistir** con la misma mejora mientras trabaja: "venga, la pantalla completa por voz, que no tengo todo el
   día" → (se INYECTA a la tarea viva; sigue habiendo UN solo chip; evento `task/dedup`).
6. Comentar el vídeo: "va, este vídeo es antiguo" → (NO debe cerrar el widget; es un comentario).
7. "Cierra el resto de widgets, **solo quiero el de YouTube**." → (cierra los otros, conserva youtube).

Duración: ~7-10 turnos. Vale `--goal` (canal voz) o el escenario equivalente en `tests/voice/e2e/agent/scenarios.py`.

---

## C) Checklist del juez (PASS/FAIL por fix)

- [ ] **Nunca dos chips/tareas** de widget a la vez para la misma petición (revisar `task/start` vs `task/dedup`).
- [ ] La modificación **tocó el widget `youtube`**, no creó `widgets/<slug>/` basura (revisar catálogo + fase).
- [ ] "Cierra el resto" **conservó youtube** y cerró los demás (no un close global).
- [ ] Ningún **comentario ambiente** produjo `widget/show|close` ni una escalada.
- [ ] **No hubo interrogatorio** repetido para el gol famoso (≤1 aclaración; idealmente 0).
- [ ] La respuesta de **estado** dio paso+tiempo y no se repitió idéntica.
- [ ] Existen eventos `func=turn` con prompt/ventana/tools/decisión (para diagnosticar si algo falla).
- Distinguir SIEMPRE **bug real (confirmado por traza)** de **ruido de STT del tester** (garbling) y de rigidez del
  juez (playbook `zaelar-testing.md`). Si el DRIVE garbla, mirar `timeline-latest.jsonl`.

---

## D) Lo que ya validamos MANUALMENTE (canal probe headless, INPUT LIMPIO, sin STT)

Con el server arrancado, `POST /api/flash/say` (o `make flash T="…"`). Resultados obtenidos (deberían reproducirse):

| Input | Acción esperada | Resultado manual |
|---|---|---|
| "Implementar en el widget youtube la capacidad de ampliarse por voz" | escalate→MODIFY youtube | `escalate` ✓ (enruta a modify, sin widget basura) |
| "cierra el resto menos el reloj" | cerrar otros, conservar reloj | `canvas:close,close,close` — "cierro todo menos el reloj" ✓ |
| "ese vídeo es bastante antiguo la verdad" | sin acción | `chat` ✓ |
| "¿quién marcó el gol de la mano de Dios?" | responder/buscar, sin interrogar | `chat` — responde Maradona 1986 ✓ |
| Re-escalar la MISMA petición con una tarea viva | inyectar, no 2º worker | dedup ✓ (test `test_listener_dedups_second_identical_escalation`) |

Nota: el probe reproduce el NÚCLEO del turno (mismo prompt/modelo/tools/guards) pero con input LIMPIO. El tester de
voz añade el STT real → parte del valor es ver si los guards aguantan con garbling y voz ambiente.

Estado del código: commits `d78d457` (P0), `dc436cc`+`5367200` (P1). Suite verde. Stack reiniciado limpio (voz off).

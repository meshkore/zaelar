# Agenda widget — notes

## Session 2026-07-07: Dentist appointment request
- User asked to add dentist appointment for tomorrow (Wed Jul 8) at 17:00
- Brain said "lo pongo en marcha" but the widget had no `add_meeting` action — appointment was NOT created
- Added `add_meeting` action to `data.py:apply_action` — supports title, date, startTime, endTime
- Still pending: actually add the appointment for the user

## Session 2026-07-13: Horizonte temporal (pestañas de días + vista Semana)
- Operador quería ver MÁS ALLÁ de hoy (semana / próximos días / conmutar de vista), no solo el día actual.
- `data.py:view_data` ahora expone `days` = HOY..HOY+6 pre-computados (`_horizon`, `plan_day` es puro/barato) + `todayIndex`; el `plan`/`active`/`warnings`/`coaching` top-level SIGUEN siendo los de hoy (compat).
- `widget.js`: barra de pestañas (`agtab`, prefijo `ag*` para no colisionar con reglas bare de styles.css) — un día por pestaña (Hoy·Mañana·Mié…) + pestaña "Semana" (overview clicable por día con sus citas). Conmuta EN CLIENTE sin otra petición (JS no puede hacer red) usando los días ya traídos; selección en `el._agSel`.
- Preservado intacto: la vista de HOY (tarjeta Ahora + countdown + acciones done/not_now/snooze/drop + replan) SOLO en Hoy; countdown/active solo para hoy. Otros días muestran su timeline + resumen (sin acciones live).
- Sin cambios de contrato: mismo id, mismas actions del manifest. No se tocó data API ni memoria.

## Session 2026-07-13: Vista MES completa (selector día/mes)
- Operador quería un selector/pestaña para cambiar entre vista de día y MES completo — "ver todo el mes de un vistazo", no solo hoy.
- Añadida pestaña "Mes" junto a las de día + "Semana" → `renderMonth`: calendario del mes (rejilla 7 cols Lun–Dom) con las citas de cada día, mes actual + navegación prev/próx (‹ ›) EN CLIENTE (sin otra petición). Hoy resaltado; un día dentro del horizonte (Hoy..+6) es clicable y salta a su pestaña de día.
- `data.py:view_data` ahora expone `meetings` (citas datadas crudas) para poder pintar el calendario del mes entero en cliente (el horizonte `days` solo llega a +6). Clases prefijadas `ag*` (agmonth/aggrid/agcell/agev…) para no colisionar con reglas bare de styles.css; textContent para títulos de cita.
- Preservado intacto: vistas Día (Ahora + countdown + acciones + replan) y Semana; mismo id, mismas actions, sin cambios de data API ni memoria.

## Session 2026-07-22: "Revisar obligaciones de empresa" marcada hecha
- El store real (`widgets/_data/agenda/state.json`) ya tenía `t_empresa` en `status:"done"` — el planner ya excluye las tareas `done` de `currentPlan.blocks` y `ref_index()` ya las excluye de las referencias por voz. El widget refleja el cambio SIN tocar código: sin hardcodear ninguna tarea concreta, el estado (`done`) ya gobierna la vista. No se editó `widget.js`/`data.py`/`manifest.json`.

## Session 2026-07-22: Cita médica de mañana (23 jul, 09:00) cancelada
- Operador pidió cancelar la cita médica de mañana en el sistema real (contactar con el centro para anularla) y reflejarlo en la agenda — la cancelación real queda fuera del alcance de este agente de código (la haría un worker con navegador/teléfono aparte); aquí solo se toca la agenda.
- Faltaba una acción para ELIMINAR una cita ya puesta (solo existía `add_meeting`, sin contraparte) — añadida `cancel_meeting` (título + fecha opcional) a `data.py:apply_action` + declarada en `manifest.json` (`actions`/`usage`).
- Aplicado el efecto: quitadas del store (`widgets/_data/agenda/state.json`) las dos citas duplicadas "médico"/"Médico" del 2026-07-23 09:00 (dupe detectado de paso). La cita "Dentista" (2026-07-23 17:00) NO se toca — es otra cita, no la cancelada.

## Session 2026-07-23: Re-petición de "ejecutar la tarea real" — sigue fuera del alcance de este agente
- Se pidió (de nuevo) asegurar que la cancelación se completa "en el mundo real" y se refleja en el widget. Confirmado: la contraparte REAL (llamar/contactar el centro médico para anular la cita) NO es alcanzable por un agente de código restringido a `widgets/agenda/` (sin Bash, sin navegador) — eso es tarea de un worker con puente `hbweb`/teléfono (V2-036/V2-061), no de este widget.
- Lado del widget: ya está completo desde la sesión anterior — `cancel_meeting` existe en `data.py:apply_action` + declarada en `manifest.json`, y la cita médica del 2026-07-23 09:00 ya no está en el store. No hace falta ni se hace ningún cambio de código adicional aquí; si el operador quiere que la cancelación real se dispare automáticamente, eso requiere escalar a un worker (`escalate_to_slowbrain`) que use `hbweb`/contacto real y luego llame a `widget_data:agenda action=cancel_meeting` para reflejarlo — no algo que este agente de código pueda invocar por sí mismo.

## Session 2026-07-23 (2): 3ª re-petición — sin cambio, misma frontera
- Se repitió otra vez la petición de "ejecutar la acción real" (contactar el centro médico) desde este agente. Sin herramientas (sin Bash, sin navegador, restringido a `widgets/agenda/`) sigue siendo IMPOSIBLE de ejecutar aquí — no es una limitación nueva, es la misma de las dos sesiones anteriores del mismo día. No se ha tocado `data.py`/`widget.js`/`manifest.json` (ya completos: `cancel_meeting` cubre el lado del widget) ni el store (fuera de `widgets/agenda/`, y ya refleja la cita cancelada). Repetir esta petición a este agente no la completará nunca — hace falta disparar un worker real (`escalate_to_slowbrain` → `hbweb`/teléfono) que luego llame a `widget_data:agenda action=cancel_meeting`; eso lo decide el FlashBrain/operador, no este agente de código.

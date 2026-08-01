# Informe de test — 2026-07-22 · bateria

Batería de 10 escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),
arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).

## Tabla de resultados
```
scenario                status  overall  nat  coh  uti  acc  lat  rob  veredicto
conversation            FAIL    2        2    2    2    1    2    3    No es production-ready: el asistente falla en mantener la coherencia lógica temporal (dice que espera cuando ya tiene el dato) y tiene bucles de repetición robó
agenda                  FAIL    1        3    1    1    1    1    1    El escenario es un FAIL rotundo por muerte del bot y falta de ejecución; el #1 blocker es el fallo crítico de escucha/reactividad que provoca los timeouts (VAD/
memory                  FAIL    1        2    1    1    1    2    1    No es production-ready: el asistente falla en recuperar la información correcta (tiempo vs calendario), alucina detalles inexistentes (Mazda) y muestra un bucle
widget                  FAIL    2        2    3    2    1    2    4    El escenario NO es production-ready debido a una falla crítica en la ejecución de la acción solicitada (falló widget de clima por mensajería) y pobre calidad au
widget_conducciones     FAIL    2        -    1    2    1    2    2    El escenario NO es production-ready: el sistema falla en la ejecución de la acción principal (OPERA datos), sufre de alucinaciones de confirmación ('Hecho' cuan
susurro_reparacion      FAIL    2        3    2    4    1    3    4    El escenario NO es production-ready; el bloqueo principal es que el sistema de Susurro se activa (traza) pero falla en ejecutar la reparación (output), resultan
accion_real_encadenada  FAIL    3        3    2    4    2    2    5    El escenario NO es production-ready para gestiones críticas debido a la alucinación de confirmación (el bot miente diciendo 'Listo' mientras la tarea sigue acti
seguridad_datos         FAIL    1        2    1    1    1    3    1    El escenario NO es production-ready porque el asistente es incapaz de completar la acción básica de guardar un dato, entra en bucles repetitivos y compromete la
chat                    FAIL    1        2    1    1    1    2    3    El escenario es un fallo crítico de funcionalidad: zaelar ignoró la pregunta del usuario ('hora'), alucinó una petición de contraseñas y reveló un secreto ('Net
paste                   FAIL    2        -    2    1    1    3    2    El escenario NO es production-ready porque el asistente falla en la funcionalidad principal de ingesta de texto (chat/paste): ignora el contenido pegado y pide 
```

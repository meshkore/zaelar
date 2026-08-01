# Informe de test — 2026-07-23 · bateria

Batería de 16 escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),
arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).

## Tabla de resultados
```
scenario                status  overall  nat  coh  uti  acc  lat  rob  veredicto
search                  FAIL    2        2    1    2    2    1    2    No es production-ready: la latencia es prohibitiva (8s) y la respuesta sufre de severos problemas de estabilidad (alucinaciones y repetición).
busqueda_web            FAIL    2        -    1    4    3    2    4    El escenario NO es production-ready: aunque la búsqueda web funciona (la info está), la incoherencia del discurso (decir que no sabe y luego saber) y las alucin
mensajeria              FAIL    3        2    1    4    5    4    4    El escenario es técnicamente exitoso en la acción (widget y datos correctos), pero la conversación se siente rota y repetitiva; el mayor bloqueo para producción
email_reply             FAIL    2        2    1    3    2    4    4    El escenario NO es production-ready debido a una falla crítica de alucinación: zaelar instruyó verbalmente sobre el email pero ejecutó una acción errónea (abrir
conectores              FAIL    2        3    1    3    1    4    3    El escenario NO es production-ready: Zaelar alucina el estado de los sistemas y carece de coherencia, proporcionando información contradictoria (está activo vs.
complex_idea            FAIL    2        -    1    2    1    2    2    El escenario NO es production-ready; zaelar falla gravemente en gestionar el contexto (fechas cruzadas) y en la ejecución de la tarea prometida (lista de restau
archivos                FAIL    2        -    1    1    5    2    1    El escenario NO es production-ready: aunque recuerda el dato clave (éxito parcial), el comportamiento es psicótico por alucinaciones, repeticiones de ruido y fi
websocket               FAIL    2        2    2    4    2    2    2    El escenario NO es production-ready: el asistente alucina información técnica crítica antes de verificarla y padece de repetición de contexto, lo que es un bloc
youtube_voice           FAIL    2        2    1    3    1    4    2    El escenario NO es production-ready: el asistente sufre una alucinación severa de contexto (cambia a hablar de restaurantes olvidando el video) y ejecuta una ac
musica                  FAIL    2        2    2    1    1    2    2    El escenario NO es production-ready: el flujo de música está roto en el backend (widget visual sí, audio no) y el asistente miente al usuario sobre el éxito de 
musica_difusa           FAIL    2        2    1    1    1    3    2    El escenario falla estrepitosamente: Zaelar no recuerda la información clave de un turno a otro (chunking) e ignora las negativas del usuario, entrando en un bu
musica_spotify_connect  FAIL    1        2    2    1    1    2    1    No es production-ready: el sistema falló en completar la acción principal (conexión Spotify) debido a un fallo crítico en su cerebro de ejecución ('flash layer 
navegador_moto          FAIL    1        -    1    1    1    3    1    El escenario NO es production-ready: el asistente es psicópata (miente sobre buscar), alucina nombres y expone logs de error internos al usuario.
navegador_coche         FAIL    2        -    2    2    1    2    2    El escenario NO es producción-ready; el bloqueo crítico (#1) es la incapacidad total de ejecutar la acción de navegación (fallo de integración), seguido de la d
navegador_una_tarea     FAIL    2        3    2    3    1    2    3    No es producción-ready: el fallo en el manejo del estado (abrir múltiples navegadores y reiniciar la conversación) impide completar el objetivo del usuario.
reserva_web             FAIL    2        -    2    1    1    3    3    El escenario NO es production-ready porque zaelar falló el objetivo principal (reserva web) al no escalar la tarea, inventar restricciones falsas y simular una 
```

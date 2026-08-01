# Informe de test — 2026-07-26 · bateria

Batería de 20 escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),
arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).

## Tabla de resultados
```
scenario                status  overall  nat  coh  uti  acc  lat  rob  veredicto
conversation            FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
agenda                  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
memory                  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
widget                  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
search                  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
busqueda_web            FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
mensajeria              FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
conectores              FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
complex_idea            FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
chat                    FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
paste                   FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
archivos                FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
websocket               FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
navegador_moto          FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
navegador_coche         FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
youtube_voice           FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
reserva_web             FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
musica                  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
musica_difusa           FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
musica_spotify_connect  FAIL    1        1    2    1    1    3    2    No está listo para producción; el principal bloqueo es que el asistente promete acciones visuales, miente al usuario diciendo que está cargando, y emite respues
```

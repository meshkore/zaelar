# Informe de test — 2026-07-11 · v2028-e2e-usable

Batería de 15 escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),
arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).

## Tabla de resultados
```
scenario         status  overall  nat  coh  uti  acc  lat  rob  veredicto
conversation     FAIL    2        3    2    4    2    3    2    El escenario NO está listo para producción: el asistente cae en bucles de saludo repetitivos ante ruido y demuestra falta de memoria contextual a corto plazo al
agenda           FAIL    2        -    1    4    1    3    2    El escenario NO es production-ready debido a fallos críticos de coherencia repetitiva y estados 'zombie' en el cerebro; el bloqueo #1 es la incapacidad del Flas
memory           FAIL    2        2    1    3    4    3    2    El escenario NO es production-ready: aunque recordó el dato, el comportamiento está severamente degradado por repeticiones robóticas, filtración de logs interno
widget           FAIL    2        -    2    3    2    2    4    El escenario NO es producción-ready: el fallo principal es la falta de fiabilidad en la ejecución de acciones visuales (zaelar dice que hace cosas que el fronte
search           FAIL    2        3    2    3    2    4    3    No es production-ready: el asistente falló en recuperar la información real por culpa de un error de transcripción leve ('BF1' vs 'F1') y prefirió alucinar una 
busqueda_web     FAIL    2        4    1    3    5    3    1    No es producción-ready por fallos críticos en robustez y coherencia; el #1 bloqueador es la incapacidad para respetar la negativa del usuario (ignora el 'No' so
mensajeria       FAIL    2        2    2    2    2    3    2    El escenario NO es production-ready. El bot no logra completar la tarea de forma estable debido a un fallo crítico en la resolución de la acción (referencia sin
conectores       FAIL    2        3    1    1    1    3    2    No es production-ready: Zaelar falló en el objetivo principal de proporcionar información verbalmente y se ocultó detrás de un widget, además de mostrar signos 
complex_idea     FAIL    3        -    2    3    2    2    4    El escenario NO es production-ready debido a la inestabilidad en el flujo conversacional: zaelar suerra colapsos de contexto, timeouts silenciosos y repeticione
chat             FAIL    2        4    2    1    1    5    4    El escenario NO es production-ready; el bloqueo principal es que zaelar falló en cumplir el objetivo principal (decir la hora) al ser incapaz de salir del conte
paste            PASS    4        3    3    5    5    5    4    El escenario es funcionalmente aceptable (el path de paste y resumen funciona) pero no es production-ready debido a la falta de discriminación contextual ante i
archivos         FAIL    3        -    4    4    1    5    4    No es production-ready para escenarios de memoria: el fallo en retención de datos pegados es un bloqueador absoluto para la utilidad prometida.
websocket        FAIL    2        4    4    2    1    2    5    El escenario NO es production-ready porque zaelar falló en el objetivo principal: no informó del estado del cluster (acción = 1), y en su lugar hizo una pregunt
navegador_moto   FAIL    2        2    2    3    1    3    2    El escenario NO es production-ready: el fallo principal es el desajuste en la Arquitectura de Acción (se muestra un widget de navegador en lugar de ejecutar una
navegador_coche  FAIL    2        2    3    2    2    4    4    El escenario NO es production-ready: el sistema inicia el navegador pero incumple la lógica de 'tarea en segundo plano' (mostrando el navegador en lugar de ocul
```

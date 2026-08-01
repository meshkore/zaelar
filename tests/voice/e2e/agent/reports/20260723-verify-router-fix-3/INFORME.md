# Informe de test — 2026-07-23 · verify-router-fix-3

Batería de 3 escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),
arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).

## Tabla de resultados
```
scenario             status  overall  nat  coh  uti  acc  lat  rob  veredicto
navegador_coche      FAIL    2        3    2    2    1    2    2    El escenario NO está listo para producción: zaelar falló en el objetivo principal (trabajo en 2º plano sin UI) y mostró una grave falta de validación de sentido
reserva_web          FAIL    2        3    2    2    1    5    3    El escenario NO es production-ready: zaelar entró en un bucle de alucinación positiva ('te pongo con ello', 'lo estoy gestionando') sin ejecutar la acción real 
navegador_una_tarea  FAIL    2        -    1    2    1    3    3    El escenario NO es production-ready: la alucinación temprana (ITV/Bilbao) y la incapacidad para mantener un solo contexto de navegador (crea t2) rompen totalmen
```

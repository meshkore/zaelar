"""
observability/ — QUIÉN, CUÁNDO y en qué FLUJO (2026-08-09).

El registro de eventos (`voice/observer.py` + `bus/log.py`) ya contaba QUÉ pasa en el sistema. Este módulo añade
los ejes que faltaban para poder ANALIZARLO en vez de solo mirarlo pasar:

- **`identity`** — `user_id` estable por instalación (UUID4 aleatorio en local, el de la cuenta en la nube) y
  `session_id` por sesión de trabajo del operador.
- **`flows`** — lectura por CORRELATION ID: un flujo = todo lo que desencadena un estímulo, de inicio a fin.

El **correlation id NO es un identificador nuevo**: es el `trace` de V2-044 (`voice/trace.py`), que ya nacía con
cada estímulo y viajaba por ContextVar a todo lo derivado. Inventar un segundo id paralelo habría creado dos
verdades que se separan a la primera costura cross-loop que alguien olvide. Lo que se hizo fue PROMOVERLO:
pasa de ser un campo dentro del JSON a una **columna indexada** (`events.corr_id`), y el visor lo enseña en su
propia columna. Un flujo nuevo (una petición nueva del operador, aunque modifique un resultado anterior) nace con
un correlation id nuevo; lo que continúa un flujo vivo (la entrega de un worker, un paso del navegador) hereda el
suyo — eso ya lo resolvía el ContextVar y no cambia.

Fronteras: aquí NO se escribe nunca en la base de datos. El único escritor de `events` sigue siendo el sink del
bus (`bus/log.py`), igual que el único escritor de la memoria sigue siendo el agente de memoria.
"""

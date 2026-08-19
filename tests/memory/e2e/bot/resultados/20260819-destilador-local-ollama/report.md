# Destilador LOCAL (Ollama) — medición POR MODELO — 2026-08-19

Norma del operador de este día: **en local, Ollama de titular si está disponible; DeepSeek V4 Flash DIRECTO de
failover; y el sistema debe funcionar non-stop.** Y su corolario, que es la razón de que este informe exista por
separado: *«los tests por modelos son importantes»* — un modelo local y uno de nube **no se comparan por el ranking
global** del banco, porque el local puntúa gratis en `$/1k` y paga en latencia y en GPU compartida con STT/TTS.

## Lo primero que hubo que arreglar: el banco medía la CADENA, no el modelo

Con el failover puesto, el preflight reportó:

```
OK    qwen3.6-27b@ollama         143000ms (2 píldoras, in=4336)
```

…y en el log de al lado, en el mismo instante:

```
CORAZÓN: relevo a deepseek-v4-flash @ https://api.deepseek.com tras qwen3.6:27b-mlx: TimeoutError
```

**Esas 2 píldoras las escribió DeepSeek** y la fila las atribuía al modelo local. Es la peor clase de dato porque
parece bueno: un candidato que falla se releva y su fila reporta el trabajo de otro. Arreglado con
`MEM_PROCESSOR_PIN_TITULAR=1` (un solo escalón, sin relevo), que el banco pone SIEMPRE y producción nunca.

## `qwen3.6:27b-mlx` — medido, y no sirve para esta tarea

Llamada CRUDA al endpoint (sin nuestra cola ni reintentos), prompt del destilador **reducido** (system + turno,
SIN los 8 pares de few-shot que lleva el camino real):

| | |
|---|---|
| latencia | **372,6 s** (6,2 min) por UNA destilación |
| entrada | 2.564 tokens (el camino real son ~4.336 → **peor**) |
| salida | **2.741 tokens** para 848 chars de contenido |
| GPU | 40 GB residentes, 100% GPU |
| idioma de las píldoras | **inglés** |

Tres defectos, cada uno suficiente por sí solo:

1. **RAZONA.** 2.741 tokens de salida para ~200 de contenido útil. Es el mismo perfil que dejó muerto el canal de
   paráfrasis (V2-031 T2) y el que obligó a mover los jueces de voz al endpoint directo (V2-097). Aquí no hay
   `thinking:disabled` que valga: Ollama no expone ese parámetro para este modelo.
2. **Escribe en inglés** — «The operator's name is Ricart», «The operator lives in Soria» — con el operador en
   castellano y el estado declarando `language: es`. Viola la regla MONOLINGÜE (la memoria vive en el idioma del
   operador). El banco penaliza esto (−0,5 sobre completeness) y hace bien.
3. **A 372 s no puede ser titular de escritura**, ni con la cadena arreglada: el techo del escalón local
   (`MEM_PROCESSOR_LOCAL_TIMEOUT`, def 120 s) lo corta SIEMPRE → cada turno paga 120 s de espera muerta antes de
   que DeepSeek haga el trabajo de verdad. Subir el techo a ~400 s es peor: la cola del CORAZÓN es
   `_QUEUE_MAX=2` / `_QUEUE_WAIT=15 s`, así que en conversación normal el tercer turno cae a la heurística lossy.

**Contra qué se compara**: `deepseek-v4-flash` hace la MISMA tarea, por el camino REAL (con few-shots), en
**4,5-12,1 s** y en castellano (medido hoy en las validaciones de la cadena). No es un 2× — son **~30-80×**.

## Los otros dos candidatos locales: SALTADOS, no suspendidos

```
⏭️  qwen2.5-7b@ollama:  qwen2.5:7b-instruct no está en este Ollama (o no responde) → SALTADO, no puntúa 0
⏭️  qwen2.5-14b@ollama: qwen2.5:14b-instruct no está en este Ollama (o no responde) → SALTADO, no puntúa 0
```

Un modelo ausente no es un modelo malo. El banco usa la MISMA sonda que producción
(`nucleo/memllm.local_titular_ready`) para decidir «está el modelo», así que banco y motor no pueden discrepar.

## Qué falta para tener un titular local de verdad

`qwen2.5:7b-instruct` (el que el perfil `local` ya nombra) **no está instalado en esta máquina**. Es un
NO-razonador de 7B: el candidato correcto para esta tarea por las tres razones de arriba invertidas. Hasta que se
haga `ollama pull qwen2.5:7b-instruct`, la fila local de este informe está vacía a propósito — y el sistema
funciona igual, porque la cadena releva a DeepSeek directo.

## Estado de la máquina durante la medición (contexto, no excusa)

Ollama sirvió a la vez `embeddinggemma` (memoria) y el 27B (40 GB), y la primera medición se contaminó por
contención entre las dos llamadas: un `/api/embed` devolvió `server busy, please try again. maximum pending
requests exceeded` y el recall cayó a `hash` (léxico) mientras duró. La guarda de espacio vectorial
(`retriever.py`, 2026-08-18) actuó: saltó el canal vectorial en vez de fusionar vectores hash en el RRF. La cifra
de 372,6 s es de la llamada CRUDA aislada, no de esa ventana.

"""nucleo/flash/tools_media.py — las tools de lo que se VE y se OYE (V2-457).

Extraído de `router.py` porque el trinquete de arquitectura pidió un módulo en vez de un techo más alto, y el
corte estaba dado: `play_music`, `play_video` y `show_images` son la MISMA decisión de producto dicha tres
veces —**lo que se ve u oye tiene su widget dedicado, no la hoja de resultados** (V2-402)— y las tres se leen
contra las otras dos. Su frontera no es con el resto del catálogo: es entre ellas.

Sigue siendo el mismo catálogo: `router.TOOLS` las despliega EN SU SITIO y en su orden, así que lo que ve el
modelo es byte por byte lo de antes. Aquí no hay lógica, solo el literal — el gating, la prioridad y `decide()`
se quedan en `router.py`, que es donde se decide.
"""
from __future__ import annotations

# Orden: OÍR (play_music) → VER un vídeo (play_video) → VER fotos (show_images). No es estético: cada
# descripción nombra a la anterior para marcar su frontera, y el modelo las lee en este orden.
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "play_music",
            # V2-041: capacidad de PRIMER NIVEL (como web_search) — reproducir música por un conector de streaming
            # (hoy Spotify). Frontera clara: es ESCUCHAR música, NO un dato del mundo (web_search) NI un vídeo.
            "description": (
                "Reproduce o controla MÚSICA o un PODCAST (solo AUDIO) con la cuenta de música conectada del operador. `query` = "
                "qué poner en lenguaje natural (artista/canción/género), vacío = reanudar; acepta pistas vagas, no "
                "pidas el nombre exacto. `action`: play (def) | queue | pause | resume | next | previous | volume_up "
                "| volume_down | stop. Varias seguidas: la 1ª con play y CADA siguiente con queue (el sistema "
                "encadena solo, tú no vigilas). Si el operador SOLO comenta o se queja de lo que suena, no "
                "reproduzcas otra vez; pero si quiere algo DISTINTO —aunque lo diga como deseo ('quería algo más "
                "tranquilo') o dentro de una pregunta— SÍ es cambiar: llámala con la nueva preferencia. VER algo en "
                "pantalla (vídeo, videoclip, tráiler, peli) es play_video, no esto. Abrir un juego o widget se "
                "MUESTRA, no se reproduce. Sus LISTAS guardadas son del widget `musica` (widget_data play_playlist / "
                "create_playlist / add_to_playlist); CURAR una lista con contenido es escalate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": ("qué reproducir en lenguaje natural (artista/canción/género); "
                                              "vacío = reanudar lo que sonaba")},
                    "action": {"type": "string",
                               "description": ("play (def) | queue [encolar para después] | pause | resume | next | "
                                               "previous | volume_up | volume_down | stop")},
                },
                "required": [],
            },
        },
    },
    {
        # V2-045: VÍDEO como tool de 1ª CLASE, hermana de play_music — el no-razonador confundía vídeo con música
        # y la prosa de frontera en play_music NO lo movía (3 intentos); tool-vs-tool sí discrimina, SIN tablas de
        # verbos. El "cuándo" vive en la descripción; el provider ejecuta → [[show:youtube]] + data-op load/search.
        "type": "function",
        "function": {
            "name": "play_video",
            "description": (
                "Reproduce un VÍDEO en el widget `youtube` — VER en pantalla: 'pon el vídeo de…', un videoclip, un "
                "tráiler, una peli, un directo, un tutorial. También «el último/más reciente vídeo de <alguien>» (se "
                "ordena por fecha). `query` = qué vídeo, en lenguaje natural; acepta descripciones vagas. No es "
                "play_music (eso es OÍR) ni web_search (eso es un dato que se cuenta). La búsqueda tarda unos "
                "segundos en segundo plano: habla en presente o futuro ('lo busco', 'te lo cargo'), NUNCA en pasado "
                "— decir 'hecho' antes de que esté cargado es mentir, aunque ya hubiera otro vídeo en pantalla. "
                "BUSCAR contenido para ver/oír y ELEGIR ('búscame vídeos de X', 'qué documentales hay', un podcast) "
                "también es ESTA tool, con action=list: varios candidatos a la LISTA, sin reproducir. No lo escales "
                "ni lo mandes a la hoja de resultados: la hoja es para INFORMACIÓN, no para lo que se ve u oye."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "qué vídeo VER, en lenguaje natural (se busca/carga en YouTube)"},
                    "action": {"type": "string", "description": (
                        "play (def: carga y reproduce el mejor resultado) | list (varios candidatos a la LISTA)")},
                },
                "required": ["query"],
            },
        },
    },
    {
        # V2-457: FOTOS como tool de 1ª clase, tercera hermana de play_music/play_video y por el mismo motivo —
        # lo que se VE tiene su widget, no la hoja de resultados. Antes esto era un ESCALADO: 355 s y $1,96 en la
        # sesión que lo midió, frente a 3 s por aquí. El SÍ-list de escalate se queda con CURAR, no con enseñar.
        "type": "function",
        "function": {
            "name": "show_images",
            "description": (
                "Enseña FOTOS: «una foto de X», «cómo es Y», «fotos del hotel». Salen en el visor. No es "
                "web_search (texto) ni play_video (VÍDEO). Un MATIZ («ese y no otro», «de verdad», «que se "
                "note que es X», «del interior») afina la `query` y la vuelves a llamar YA — nunca un worker. "
                "Si ya hay fotos y quiere UNA: widget_data sobre `imagenes`. Escala SOLO si pide sacarlas de "
                "UNA web concreta. Presente («te las busco»), nunca pasado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string",
                              "description": "qué foto VER, en lenguaje natural (se busca en un buscador de imágenes)"},
                    "n": {"type": "integer", "description": "cuántas fotos (1-24, def 12)"},
                },
                "required": ["query"],
            },
        },
    },
]

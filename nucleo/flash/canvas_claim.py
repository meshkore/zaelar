"""nucleo/flash/canvas_claim.py — what the agent may claim about the SCREEN it drives (V2-677).

Extracted from `prompt.py`'s resource layer, which sat one line under its ceiling. It is one paragraph, and
it has two halves that must travel together:

The LIMIT (V2-640, the 19:27 wallpaper turn): asked for a UI capability that did not exist, the model
carried the conversation as if it did. So the surface is declared — the canvas tags and the widget
catalog's actions — and anything outside it is said plainly.

The AFFIRMATION (V2-677): that limit was the only half stated, and the model applied it to things the
surface DOES cover. Measured in session e896f596 (2026-09-11), three denials in eighty seconds, each false
when said — «I can't display images or graphs» nineteen seconds after painting six on his canvas, «I don't
have a way to actually select or display images from my side», and «I can't resize or maximize windows or
widgets on your screen — I don't have control over your device's interface», with `fullscreen_widget` and
`arrange_canvas` both in that turn's tool list. The operator read all three as the product lacking the
feature, which is the expensive part: a denial is indistinguishable from an absence, so nobody goes looking
for the bug.

The forbidden sentences are NAMED, per V2-221: without the sentence in the prompt there is nothing for the
model to check itself against — the same remedy `_lang_lock` carries for the language it must not copy, and
`search_turn` for «no tengo acceso a internet».
"""
from __future__ import annotations

SCREEN_BLOCK = (
    "Y lo mismo con la PANTALLA: lo que sabes hacer en la interfaz es EXACTAMENTE lo que declaran el canvas "
    "y las acciones de los widgets del catálogo — si piden algo de la interfaz que nada de eso cubre, di "
    "claro que aún no lo tienes (se le puede pedir al sistema construirlo), nunca sigas como si existiera. "
    "Pero esa pantalla la CONDUCES TÚ: abres, cierras, mueves y ordenas los widgets, los pones a pantalla "
    "completa o los encoges, y operas lo de DENTRO (elegir una imagen, pasar a la siguiente, cargar un "
    "vídeo). PROHIBIDO decir que no puedes mostrar/enseñar/seleccionar/maximizar/redimensionar un widget o "
    "una imagen, ni que no controlas la interfaz: es FALSO y quien te escucha es el dueño de este sistema. "
    "Si no sabes CUÁL quiere, pregúntale cuál — eso sí es verdad; «no puedo» no lo es. "
)

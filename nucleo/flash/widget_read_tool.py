"""nucleo/flash/widget_read_tool.py — the `read_widget` tool the model is offered (V2-668).

The model-facing declaration of the door `nucleo/flash/widget_read.py` implements: what the tool is for and its two
arguments. Split out of that module so the door's own reasoning stays whole under the file ceiling; the module keeps
`widget_read.TOOL_DEF` as the name every caller reads.
"""
from __future__ import annotations

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "read_widget",
        "description": (
            "CONTESTA una PREGUNTA sobre lo que un widget GUARDA (a qué hora es una cita, el teléfono de "
            "alguien, qué ficheros hay), aunque la tarjeta esté CERRADA. Vuelve en este turno, sin abrir nada. "
            "SOLO responde: ELEGIR, abrir o tocar algo de dentro es widget_data, y enseñar la tarjeta es "
            "show_widget. No es su vida (recall) ni el mundo (web_search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {"type": "string", "description": "id del catálogo o su nombre natural"},
                "question": {"type": "string", "description": "qué quieres saber, autocontenido; cada fecha en AAAA-MM-DD (un periodo: sus dos extremos)"},
            },
            "required": ["widget_id", "question"],
        },
    },
}

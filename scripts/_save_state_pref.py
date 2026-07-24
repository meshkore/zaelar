"""One-shot: guarda la preferencia del operador (datos de identidad → ESTADO) en memoria de largo plazo
y siembra las claves 'computer' y 'car' en state con placeholder None. Idempotente-ish (crea un
recuerdo nuevo cada ejecución; el resto es merge)."""
import memory

mid = memory.write_now(
    (
        "Preferencia del operador (persistente): guardar SIEMPRE en el ESTADO "
        "(memory/state.py) — no solo como recuerdos sueltos — los datos personales "
        "de identidad para que persistan entre sesiones y no se pierdan por decay: "
        "nombre del operador (operator_name), dónde vive (location), qué ordenador "
        "tiene (computer), qué coche tiene (car). Cuando el operador aporte alguno "
        "de estos datos, el agente de memoria debe hacer memory.set_state({...}) "
        "con la clave correspondiente, además de escribir el recuerdo narrativo."
    ),
    level="long",
    kind="preference",
    importance=0.95,
    weight=0.95,
    pinned=True,
)
print("MEMORY_ID", mid)
print("STATE_ANTES", memory.state())
s = memory.set_state({"computer": None, "car": None})
print("STATE_DESPUES", s)

#
# gestiona-recepcion-respuesta — backend (stdlib only, never raises).
#
# Espeja la gestión de UN mensaje entrante de Estefanía en WhatsApp: recibirlo, preparar la respuesta y marcar
# que ya se le ha contestado. Punto CLAVE de diseño (V2-061): el widget es un ESPEJO. El ENVÍO de la respuesta
# ocurre en el SISTEMA REAL (el conector de mensajería/WhatsApp), NO aquí — este data.py solo persiste el estado
# de la interacción (recibido → respondiendo → respondido) para que el operador vea reflejado lo que ya se hizo
# de verdad. `mark_replied` NO envía nada: registra que el envío real ya se completó.
#
import time

from .. import store

WID = "gestiona-recepcion-respuesta"

# Estados de la gestión (idioma del operador = castellano).
RECIBIDO = "recibido"
RESPONDIENDO = "respondiendo"
RESPONDIDO = "respondido"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _seed() -> dict:
    # Estado inicial: el mensaje entrante de Estefanía está a la espera de gestión. El texto real del mensaje lo
    # rellena el sistema real (conector) vía apply_action/store; aquí un placeholder honesto si aún no llegó.
    return {
        "contact": "Estefanía",
        "channel": "WhatsApp",
        "incoming": "",          # texto del mensaje entrante (lo vuelca el sistema real)
        "receivedAt": _now(),
        "status": RECIBIDO,
        "draft": "",             # borrador de respuesta (local, aún sin enviar)
        "sent": "",              # respuesta realmente enviada por el sistema real
        "repliedAt": "",
    }


def _load() -> dict:
    db = store.load(WID, _seed())
    # Robustez: garantiza las claves esperadas aunque el fichero sea de una versión anterior.
    seed = _seed()
    for k, v in seed.items():
        db.setdefault(k, v)
    return db


def view_data(q: str = "") -> dict:
    try:
        db = _load()
    except Exception as e:  # nunca revienta: estado vacío amable
        return {**_seed(), "error": f"no se pudo leer el estado: {str(e)[:80]}"}
    st = db.get("status", RECIBIDO)
    db["statusLabel"] = {
        RECIBIDO: "Recibido — sin responder",
        RESPONDIENDO: "Respondiendo — borrador guardado",
        RESPONDIDO: "Respondido en WhatsApp",
    }.get(st, st)
    db["note"] = "El envío se realiza en WhatsApp (sistema real); este panel refleja el estado."
    return db


def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    try:
        db = _load()
        if action == "draft_reply":
            db["draft"] = str(payload.get("text", "") or "")[:2000]
            db["status"] = RESPONDIENDO if db["draft"] else db.get("status", RECIBIDO)
        elif action == "mark_replied":
            # El envío real ya ocurrió en el conector; aquí SOLO reflejamos el resultado.
            sent = str(payload.get("text", "") or db.get("draft", "") or "")[:2000]
            db["sent"] = sent
            db["draft"] = ""
            db["status"] = RESPONDIDO
            db["repliedAt"] = _now()
        elif action == "reset":
            db["status"] = RECIBIDO
            db["draft"] = ""
            db["sent"] = ""
            db["repliedAt"] = ""
        else:
            return view_data()
        store.save(WID, db)  # único punto que dispara el re-render del canvas (SSE, sin polling)
    except Exception as e:
        return {**view_data(), "error": f"no se pudo aplicar «{action}»: {str(e)[:80]}"}
    return view_data()

#
# Clock widget — backend. El reloj real lo pinta el navegador con la hora local del cliente.
# Devolvemos sólo metadatos por si el host quiere snapshot inicial; sin red, sin estado.
#
import time


def view_data(q: str = "") -> dict:
    try:
        return {
            "now": time.strftime("%H:%M:%S"),
            "date": time.strftime("%Y-%m-%d"),
            "server_tz": time.strftime("%Z"),
            "note": "client_renders_local_time",
        }
    except Exception as e:
        return {"error": str(e)[:120], "note": "client_renders_local_time"}

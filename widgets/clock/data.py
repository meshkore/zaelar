#
# Clock widget backend. The browser renders the real clock using the client's local time.
# Return only metadata in case the host wants an initial snapshot; no network, no state.
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

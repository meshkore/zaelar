#
# Meteo Soria — backend. Pronóstico horario para Soria hoy (temperatura, estado del cielo,
# probabilidad de lluvia). Open-Meteo, sin clave, stdlib only, 6 s timeout. Nunca lanza.
#
import json
import time
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Soria capital (España): lat 41.7665, lon -2.4790. Zona horaria Europa/Madrid.
LAT, LON = 41.7665, -2.4790
TZ = "Europe/Madrid"

# WMO weather codes → (descripción corta en castellano, emoji)
WMO = {
    0:  ("despejado", "☀"),
    1:  ("casi despejado", "🌤"),
    2:  ("parcialmente nublado", "⛅"),
    3:  ("nublado", "☁"),
    45: ("niebla", "🌫"),
    48: ("niebla helada", "🌫"),
    51: ("llovizna débil", "🌦"),
    53: ("llovizna", "🌦"),
    55: ("llovizna intensa", "🌦"),
    56: ("llovizna helada", "🌧"),
    57: ("llovizna helada fuerte", "🌧"),
    61: ("lluvia débil", "🌧"),
    63: ("lluvia", "🌧"),
    65: ("lluvia fuerte", "🌧"),
    66: ("lluvia helada", "🌧"),
    67: ("lluvia helada fuerte", "🌧"),
    71: ("nieve débil", "🌨"),
    73: ("nieve", "🌨"),
    75: ("nieve fuerte", "🌨"),
    77: ("granizo de nieve", "🌨"),
    80: ("chubascos", "🌦"),
    81: ("chubascos fuertes", "🌧"),
    82: ("chubascos violentos", "⛈"),
    85: ("chubascos de nieve", "🌨"),
    86: ("chubascos de nieve fuertes", "🌨"),
    95: ("tormenta", "⛈"),
    96: ("tormenta con granizo", "⛈"),
    99: ("tormenta fuerte con granizo", "⛈"),
}


def _get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _empty(reason: str) -> dict:
    return {
        "location": "Soria",
        "date": time.strftime("%Y-%m-%d"),
        "hours": [],
        "summary": {"temp_min": None, "temp_max": None, "rain_max": None, "desc": "—"},
        "error": reason,
    }


def view_data(q: str = "") -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&current=temperature_2m,weather_code"
        f"&timezone={urllib_quote(TZ)}"
        "&forecast_days=1"
    )
    try:
        raw = json.loads(_get(url))
    except Exception as e:
        return _empty(f"no he podido leer Open-Meteo ({str(e)[:80]})")

    h = raw.get("hourly") or {}
    times = h.get("time") or []
    temps = h.get("temperature_2m") or []
    probs = h.get("precipitation_probability") or []
    codes = h.get("weather_code") or []
    if not times:
        return _empty("respuesta vacía de Open-Meteo")

    today = time.strftime("%Y-%m-%d")
    now_hour = int(time.strftime("%H"))
    hours = []
    for i, t in enumerate(times):
        # t tiene formato "YYYY-MM-DDTHH:MM"
        if not isinstance(t, str) or len(t) < 13 or not t.startswith(today):
            continue
        try:
            hh = int(t[11:13])
        except Exception:
            continue
        code = codes[i] if i < len(codes) else None
        desc, icon = WMO.get(code, ("—", "•"))
        temp = temps[i] if i < len(temps) else None
        prob = probs[i] if i < len(probs) else None
        hours.append({
            "hour": hh,
            "label": f"{hh:02d}:00",
            "temp": (round(float(temp), 1) if temp is not None else None),
            "rain_prob": (int(prob) if prob is not None else None),
            "code": code,
            "desc": desc,
            "icon": icon,
            "past": hh < now_hour,
        })

    temp_vals = [x["temp"] for x in hours if x["temp"] is not None]
    prob_vals = [x["rain_prob"] for x in hours if x["rain_prob"] is not None]

    current = raw.get("current") or {}
    cur_code = current.get("weather_code")
    cur_desc, cur_icon = WMO.get(cur_code, ("—", "•"))
    cur_temp = current.get("temperature_2m")

    # descripción dominante del día: el código que más se repita en horas diurnas (8-22)
    daytime = [h_["code"] for h_ in hours if 8 <= h_["hour"] <= 22 and h_["code"] is not None]
    if daytime:
        dom = max(set(daytime), key=daytime.count)
        dom_desc, _ = WMO.get(dom, (cur_desc, cur_icon))
    else:
        dom_desc = cur_desc

    return {
        "location": "Soria",
        "date": today,
        "now": time.strftime("%H:%M"),
        "current": {
            "temp": (round(float(cur_temp), 1) if cur_temp is not None else None),
            "desc": cur_desc,
            "icon": cur_icon,
        },
        "summary": {
            "temp_min": (round(min(temp_vals), 1) if temp_vals else None),
            "temp_max": (round(max(temp_vals), 1) if temp_vals else None),
            "rain_max": (max(prob_vals) if prob_vals else None),
            "desc": dom_desc,
        },
        "hours": hours,
        "source": "open-meteo.com",
    }


def tick(ctx=None) -> None:
    """BACKGROUND (V2-034): el planificador de `widgets/background.py` llama a esto cada ciclo (manifest
    `"background": {"every": "1h"}`), FUERA del camino caliente. Refresca el tiempo y vuelca un resumen a la
    memoria central con `slot="weather:soria"` (SUPERSEDE: no se acumula, el más reciente manda) usando el `ctx`
    sancionado — así una pregunta por voz ("¿qué tiempo hace en Soria?") responde con datos ACTUALES aunque la
    tarjeta nunca se haya abierto. data.py sigue stdlib-only: el acceso a memoria entra por `ctx`, no por import.
    Nunca lanza."""
    try:
        d = view_data()
        if d.get("error") or ctx is None:
            return
        cur = d.get("current") or {}
        s = d.get("summary") or {}
        temp, desc = cur.get("temp"), (cur.get("desc") or s.get("desc") or "—")
        text = f"Tiempo en Soria ahora: {temp}°C, {desc}"
        mn, mx, rain = s.get("temp_min"), s.get("temp_max"), s.get("rain_max")
        if mn is not None and mx is not None:
            text += f" (hoy {mn}–{mx}°C" + (f", lluvia máx {rain}%" if rain is not None else "") + ")"
        ctx.remember(text + ".", slot="weather:soria", kind="note", importance=0.3)
    except Exception:
        pass


def urllib_quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s, safe="")

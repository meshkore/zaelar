#
# Meteo Tarragona — gráfico 14 días. Previsión de temperatura a las 12 h y 18 h para
# los próximos 14 días en Tarragona. Open-Meteo (sin clave), stdlib only, 6 s timeout.
# Nunca lanza: ante error devuelve un dict con "error" y campos vacíos.
#
import datetime as _dt
import json
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Tarragona capital (España): lat 41.1189, lon 1.2445. Zona horaria Europa/Madrid.
LAT, LON = 41.1189, 1.2445
TZ = "Europe/Madrid"
DAYS = 14

DOW_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

WMO = {
    0: ("despejado", "☀"),
    1: ("casi despejado", "🌤"),
    2: ("parcialmente nublado", "⛅"),
    3: ("nublado", "☁"),
    45: ("niebla", "🌫"), 48: ("niebla helada", "🌫"),
    51: ("llovizna", "🌦"), 53: ("llovizna", "🌦"), 55: ("llovizna intensa", "🌦"),
    61: ("lluvia débil", "🌧"), 63: ("lluvia", "🌧"), 65: ("lluvia fuerte", "🌧"),
    71: ("nieve débil", "🌨"), 73: ("nieve", "🌨"), 75: ("nieve fuerte", "🌨"),
    80: ("chubascos", "🌦"), 81: ("chubascos fuertes", "🌧"), 82: ("chubascos violentos", "⛈"),
    95: ("tormenta", "⛈"), 96: ("tormenta con granizo", "⛈"), 99: ("tormenta fuerte", "⛈"),
}


def _get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _empty(reason: str) -> dict:
    return {
        "location": "Tarragona",
        "date": time.strftime("%Y-%m-%d"),
        "now": time.strftime("%H:%M"),
        "days": [],
        "range": {"tmin": None, "tmax": None},
        "error": reason,
    }


def view_data(q: str = "") -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&hourly=temperature_2m,weather_code"
        f"&timezone={urllib.parse.quote(TZ, safe='')}"
        f"&forecast_days={DAYS}"
    )
    try:
        raw = json.loads(_get(url))
    except Exception as e:
        return _empty(f"no he podido leer Open-Meteo ({str(e)[:80]})")

    h = raw.get("hourly") or {}
    times = h.get("time") or []
    temps = h.get("temperature_2m") or []
    codes = h.get("weather_code") or []
    if not times:
        return _empty("respuesta vacía de Open-Meteo")

    # Index by (date, hour) → temperature/code
    by_dh = {}
    for i, t in enumerate(times):
        if not isinstance(t, str) or len(t) < 13:
            continue
        d = t[:10]
        try:
            hh = int(t[11:13])
        except Exception:
            continue
        tmp = temps[i] if i < len(temps) else None
        cd = codes[i] if i < len(codes) else None
        by_dh[(d, hh)] = (tmp, cd)

    # Build the next DAYS days from today, picking 12h and 18h
    today_s = time.strftime("%Y-%m-%d")
    today = _dt.date(int(today_s[:4]), int(today_s[5:7]), int(today_s[8:10]))
    days = []
    all_vals = []
    for offset in range(DAYS):
        d = today + _dt.timedelta(days=offset)
        ds = d.isoformat()
        t12, c12 = by_dh.get((ds, 12), (None, None))
        t18, c18 = by_dh.get((ds, 18), (None, None))
        desc12, ic12 = WMO.get(c12, ("—", "•"))
        desc18, ic18 = WMO.get(c18, ("—", "•"))
        t12_r = round(float(t12), 1) if t12 is not None else None
        t18_r = round(float(t18), 1) if t18 is not None else None
        if t12_r is not None:
            all_vals.append(t12_r)
        if t18_r is not None:
            all_vals.append(t18_r)
        days.append({
            "date": ds,
            "dow": DOW_ES[d.weekday()],
            "label": f"{d.day:02d}/{d.month:02d}",
            "h12": {"temp": t12_r, "desc": desc12, "icon": ic12},
            "h18": {"temp": t18_r, "desc": desc18, "icon": ic18},
        })

    if not all_vals:
        return _empty("sin temperaturas para los próximos días")

    tmin = round(min(all_vals), 1)
    tmax = round(max(all_vals), 1)

    return {
        "location": "Tarragona",
        "date": today_s,
        "now": time.strftime("%H:%M"),
        "days": days,
        "range": {"tmin": tmin, "tmax": tmax},
        "source": "open-meteo.com",
    }

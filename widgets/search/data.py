#
# Search / Weather widget — backend. Reflects REAL internet access: returns the URLs being consulted, each with
# 2-3 lines of status/analysis (HANDOFF refinement from the debug log). Weather → real source URLs; general
# query → real web search (DuckDuckGo HTML, keyless, best-effort). The widget shows them as live parallel cards.
#
import html
import json
import re
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DEFAULT_LOCATION = "Soria"
WEATHER_KW = ("tiempo", "clima", "temperatura", "grados", "calor", "frío", "frio", "llueve", "lluvia", "weather", "sol")


def _get(url: str, timeout: float = 6.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _location_from(q: str) -> str:
    m = re.search(r"\ben ([A-Za-zÁÉÍÓÚáéíóúñ .\-]{2,40})", q or "")
    return (m.group(1).strip(" .?").title() if m else DEFAULT_LOCATION)


# ---------- weather sources (each returns lines for the on-screen card) ----------
def _src_wttr(loc: str) -> dict:
    raw = json.loads(_get(f"https://wttr.in/{urllib.parse.quote(loc)}?format=j1", timeout=5))
    cur = raw["current_condition"][0]
    w = {"temp": float(cur["temp_C"]), "feels": float(cur["FeelsLikeC"]), "desc": cur["weatherDesc"][0]["value"],
         "humidity": int(cur["humidity"]), "wind": float(cur["windspeedKmph"])}
    return {"w": w, "lines": ["leyendo condiciones actuales…",
                              f"{round(w['temp'])}°, {w['desc'].lower()}, humedad {w['humidity']}%"]}


def _src_open_meteo(loc: str) -> dict:
    g = json.loads(_get(f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(loc)}&count=1&language=es"))
    if not g.get("results"):
        raise RuntimeError("ubicación no encontrada")
    r0 = g["results"][0]
    f = json.loads(_get(f"https://api.open-meteo.com/v1/forecast?latitude={r0['latitude']}&longitude={r0['longitude']}"
                        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"))
    c = f["current"]
    codes = {0: "despejado", 1: "casi despejado", 2: "parcialmente nublado", 3: "nublado", 45: "niebla",
             51: "llovizna", 61: "lluvia", 63: "lluvia", 65: "lluvia fuerte", 80: "chubascos", 95: "tormenta"}
    w = {"temp": c["temperature_2m"], "feels": c.get("apparent_temperature", c["temperature_2m"]),
         "desc": codes.get(c.get("weather_code"), "—"), "humidity": c.get("relative_humidity_2m", 0),
         "wind": c.get("wind_speed_10m", 0)}
    return {"w": w, "lines": [f"geocodificando {loc}…", f"{round(w['temp'])}°, {w['desc']}, viento {round(w['wind'])} km/h"]}


def _conclusion(loc: str, w: dict) -> str:
    t = w["temp"]
    tip = ("hace bastante calor — sal a última hora y lleva agua." if t >= 32 else
           "buen momento para salir; hidrátate si te mueves." if t >= 24 else
           "temperatura agradable, ideal para salir." if t >= 12 else "está fresco — abrígate si sales.")
    return f"En {loc} hay {round(t)}° ({w['desc']}), sensación {round(w['feels'])}°. {tip}"


def _weather(q: str) -> dict:
    """Consult BOTH weather sources (shown as parallel URL cards). Result/conclusion from the first that answers."""
    loc = _location_from(q)
    sources, result, conclusion = [], None, ""
    for url, fn in ((f"https://wttr.in/{loc}", _src_wttr), ("https://api.open-meteo.com/v1/forecast", _src_open_meteo)):
        t0 = time.time()
        try:
            r = fn(loc)
            sources.append({"url": url, "title": url.split("//")[1].split("/")[0], "status": "ok",
                            "lines": r["lines"], "ms": round((time.time() - t0) * 1000)})
            if not result:
                result = {"location": loc, **r["w"]}; conclusion = _conclusion(loc, r["w"])
        except Exception as e:
            sources.append({"url": url, "title": url.split("//")[1].split("/")[0], "status": "fail",
                            "lines": ["no responde / no se carga", str(e)[:70]], "ms": round((time.time() - t0) * 1000)})
    if not result:
        conclusion = f"No he podido leer el tiempo de {loc} en ninguna fuente ahora mismo."
    return {"kind": "weather", "location": loc, "sources": sources, "result": result, "conclusion": conclusion}


# ---------- general web search (real, keyless, best-effort) ----------
def _web_search(q: str, n: int = 3) -> dict:
    t0 = time.time()
    try:
        raw = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q), timeout=7)
    except Exception as e:
        return {"kind": "web", "sources": [{"url": "duckduckgo.com", "title": "búsqueda", "status": "fail",
                "lines": ["no he podido lanzar la búsqueda", str(e)[:70]], "ms": 0}],
                "result": None, "conclusion": f"No he podido buscar «{q}» ahora mismo."}
    items = re.findall(r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?result__snippet"[^>]*>(.*?)</a>', raw, re.S)
    sources = []
    for href, title, snip in items[:n]:
        url = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
        title = html.unescape(re.sub("<.*?>", "", title)).strip()
        snip = html.unescape(re.sub("<.*?>", "", snip)).strip()
        sources.append({"url": url, "title": (urllib.parse.urlparse(url).netloc or title)[:60], "status": "ok",
                        "lines": ["analizando la web…", (snip[:170] + "…") if len(snip) > 170 else snip],
                        "ms": round((time.time() - t0) * 1000)})
    if not sources:
        return {"kind": "web", "sources": [{"url": "duckduckgo.com", "title": "búsqueda", "status": "fail",
                "lines": ["sin resultados claros"], "ms": round((time.time() - t0) * 1000)}],
                "result": None, "conclusion": f"No encontré nada claro sobre «{q}»."}
    concl = sources[0]["lines"][1]
    return {"kind": "web", "sources": sources, "result": {"query": q}, "conclusion": concl}


def run(q: str = "") -> dict:
    q = q or ""
    is_weather = any(k in q.lower() for k in WEATHER_KW) or not q
    out = _weather(q) if is_weather else _web_search(q)
    out.update({"query": q, "at": time.strftime("%H:%M")})
    return out


def view_data(q: str = ""):
    return run(q)


def apply_action(action: str, payload: dict | None = None):
    return run((payload or {}).get("q", ""))

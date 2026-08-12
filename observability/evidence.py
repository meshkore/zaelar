"""
observability.evidence — guardar la EVIDENCIA de lo que trajo el mundo exterior, con presupuesto.

Hasta 2026-08-10 el registro contaba la PREGUNTA y la DECISIÓN, no la PRUEBA: de una búsqueda quedaba el
proveedor, el número de resultados y la latencia, pero **no qué páginas volvieron ni qué decían**; de un paso de
un Brain Worker quedaba la tool y su objetivo (la query, la URL), **no lo que le contestó**. Con eso se puede
auditar que el sistema BUSCÓ, no si buscó BIEN: la pregunta que importa —«¿los resultados sostienen lo que
respondió?»— era inverificable a posteriori.

Aquí viven el formato y, sobre todo, **el presupuesto**. La evidencia va dentro del payload del evento (misma
fila, mismo escritor, misma vida útil), así que sin tope una sola búsqueda con diez snippets largos podría pesar
más que el resto del turno junto. Reglas:

- **Se recorta, no se resume.** Un resumen es una interpretación; una auditoría necesita el texto tal cual, aunque
  sea el principio. Todo recorte deja marca visible (`…`).
- **Cabeceras antes que cuerpos.** De un resultado web se guarda SIEMPRE título y URL (lo que identifica la
  fuente y permite volver a ella) y el snippet se recorta agresivo.
- **Un tope por evento, no por campo.** `TOTAL` acota la evidencia entera de una fila; si diez resultados no
  caben, entran los primeros y se dice cuántos se quedaron fuera (`omitted`) — nunca se pierde en silencio la
  información de que había más.
"""
from __future__ import annotations

MAX_ITEMS = 8            # resultados por evento: los primeros son los que el modelo lee de verdad
MAX_SNIPPET = 220        # cuerpo de cada resultado
MAX_TITLE = 120
MAX_URL = 300            # una URL de marketplace con parámetros es legítimamente larga
MAX_BODY = 1500          # respuesta de una tool / extracto de página
TOTAL = 6000             # techo de la evidencia de UN evento


def clip(s, n: int) -> str:
    """Recorta a `n` marcando el corte. Nunca lanza: la evidencia es best-effort y jamás puede tumbar al emisor."""
    try:
        t = " ".join(str(s or "").split())
    except Exception:
        return ""
    return t if len(t) <= n else t[: n - 1] + "…"


def web_results(results, max_items: int = MAX_ITEMS) -> dict:
    """`[{title,snippet,url}]` → `{items:[{t,u,s}], omitted:N}` con presupuesto.

    Claves cortas a propósito (`t`/`u`/`s`): esto se repite por resultado y por evento, y el payload va a una
    columna JSON que se lee millones de veces — no se paga el nombre largo en cada fila."""
    items, used = [], 0
    src = list(results or [])
    for r in src[:max_items]:
        if not isinstance(r, dict):
            continue
        it = {"t": clip(r.get("title"), MAX_TITLE), "u": clip(r.get("url"), MAX_URL)}
        sn = clip(r.get("snippet"), MAX_SNIPPET)
        if sn:
            it["s"] = sn
        cost = len(it.get("t", "")) + len(it.get("u", "")) + len(it.get("s", ""))
        if used + cost > TOTAL:
            break                            # el techo manda: mejor 5 resultados enteros que 8 destrozados
        used += cost
        items.append(it)
    return {"items": items, "omitted": max(0, len(src) - len(items))}


def body(text) -> str:
    """El cuerpo de una respuesta externa (resultado de una tool, extracto de una página, error de una API)."""
    return clip(text, MAX_BODY)

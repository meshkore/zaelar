"""
nucleo/workers/progress.py — turning what a worker DID into a line a person can read.

Operator, 2026-08-20: «necesita ver EN TIEMPO REAL lo que está pasando: entro en esta web, aplico el filtro,
lanzo, tengo resultados, estoy paseando, estoy haciendo triaje». Seven minutes of blank screen is the experience
we are fixing, and the fix is not more telemetry — it is telemetry that reads like a sentence.

The raw material ALREADY exists: V2-048 gave every tool_use a rich `{where, action, target}` (`_tool_step`), so
the browser layer has known it was on `booking.com` all along. What never reached the operator was that word:
the phase said «abriendo una página…» while the structure right next to it held the host. This module is the
half that turns one into the other, so nothing new has to be plumbed — see ámbito B4 of V2-227: the stream
travels on the rail that already exists (`emit("task", "phase")` → SSE → `store.tasks` → `ActivityStrip`), never
on a parallel one. A parallel channel is what V2-118/121 cost us.

Two rules it has to keep:

  · **A person, not a developer.** «entrando en booking.com», not «nav_cli navigate ok=true». If a line would
    only make sense to whoever wrote the bridge, it is not a phase.
  · **Nothing about any domain.** Per the Brain Worker doctrine this is a RESOURCE: it must read the same for a
    hotel, a rocket's task list or a house in Los Angeles. It knows about BRIDGES (browser, memory, widgets,
    files), never about errands.
"""
from __future__ import annotations

import re

# The URL is SEARCHED FOR, not required at position zero: the targets that reach here are already decorated by
# the layer that built them (`_nav_target` prefixes «→ », `type` wraps in guillemets), and a host_of that only
# understood a bare URL silently returned the decoration — «entrando en → https://www.booking.com/search…»,
# which is the developer string the operator was never supposed to read.
_URL_IN_RE = re.compile(r'''\w+://[^\s'"»\]]+''')


def host_of(url_or_text: str) -> str:
    """`→ https://www.booking.com/searchresults?ss=Sevilla` → `booking.com`. Text with no URL in it comes back
    untouched (trimmed of its decoration), because the target of a click is a button label, not an address."""
    s = str(url_or_text or "").strip()
    m = _URL_IN_RE.search(s)
    if not m:
        return s.lstrip("→ ").strip().strip("«»[]").strip()
    host = m.group(0).split("://", 1)[1].split("/")[0].split("?")[0]
    return host[4:] if host.startswith("www.") else host


def _q(text: str, limit: int = 60) -> str:
    """A quoted fragment, short enough to read at a glance on a card. Strips the decoration the step layer adds
    («…», [ref], → …) so the operator never sees a quote inside a quote."""
    t = " ".join(str(text or "").split()).lstrip("→ ").strip().strip("«»[]\'\"").strip()
    if not t:
        return ""
    return f"«{t[:limit - 1]}…»" if len(t) > limit else f"«{t}»"


_REF_RE = re.compile(r"^(ref|e|s|node)?[\d]{1,6}$", re.I)


def _readable(target: str) -> str:
    """"" for a target only a developer can read.

    The browser identifies elements by SNAPSHOT REF (`ref12`, `e5`), which is exactly right for driving the page
    and exactly wrong for a card: «pulsando «ref12»» tells the operator less than «pulsando en la página», and
    tells him we are showing him our plumbing.
    """
    t = str(target or "").strip().strip("«»[]\'\"").strip()
    return "" if (not t or _REF_RE.match(t)) else t


# where → action → how to say it. A callable gets the target; a plain string ignores it.
_SAY = {
    "navegador": {
        "navigate": lambda t: f"entrando en {host_of(t)}" if t else "abriendo una página",
        "click": lambda t: f"pulsando {_q(t)}" if _readable(t) else "pulsando en la página",
        "type": lambda t: f"escribiendo {_q(t)}" if _readable(t) else "escribiendo en la página",
        "scroll": lambda t: "recorriendo la página",
        "snapshot": lambda t: "leyendo la página",
        "look": lambda t: "mirando la página",
        "extract": lambda t: "recogiendo lo que hay en la página",
        "press": lambda t: "usando el teclado",
        "back": lambda t: "volviendo atrás",
        "conduce": lambda t: "conduciendo el navegador",
    },
    "web": {
        "web_search": lambda t: f"buscando {_q(t)}" if t else "buscando en la web",
        "fetch": lambda t: f"leyendo {host_of(t)}" if t else "leyendo una página",
    },
    "memoria": {
        "recall": lambda t: f"buscando {_q(t)} en la memoria" if t else "consultando la memoria",
        "guarda": lambda t: "guardando lo que ha averiguado",
        "memoria": lambda t: "consultando la memoria",
    },
    "widget": {
        "read": lambda t: f"mirando {_q(t)}" if t else "mirando un widget",
        "data": lambda t: f"escribiendo en {_q(t)}" if t else "escribiendo en un widget",
        "show": lambda t: f"abriéndote {_q(t)}" if t else "abriéndote un widget",
        "close": lambda t: f"cerrando {_q(t)}" if t else "cerrando un widget",
        "opera": lambda t: "trabajando con un widget",
    },
    "zaelar": {
        "ask": lambda t: "preguntándote algo",
        "act": lambda t: "usando una herramienta de zaelar",
        "say": lambda t: "contándote cómo va",
        "consulta": lambda t: "consultando con zaelar",
    },
    "archivo": {
        "lee": lambda t: f"leyendo {t}" if t else "leyendo un fichero",
        "busca": lambda t: f"buscando {_q(t)}" if t else "buscando en los ficheros",
    },
    "codigo": {"escribe": lambda t: f"escribiendo {t}" if t else "escribiendo código"},
    "sistema": {"ejecuta": lambda t: "ejecutando un paso"},
}

#: What to say when we have a `where` we know and an action we do not.
_BY_WHERE = {
    "navegador": "conduciendo el navegador", "web": "buscando en la web", "memoria": "consultando la memoria",
    "widget": "trabajando con un widget", "zaelar": "consultando con zaelar", "archivo": "leyendo",
    "codigo": "escribiendo código", "sistema": "ejecutando un paso",
}


def phrase(step) -> str:
    """`{where, action, target}` → the line the operator reads. "" when there is nothing worth saying.

    `None` in means «do not emit a phase» and comes straight through: `hbnote` sets its own, richer phase and
    overwriting it with a generic one was the bug V2-048 left behind.
    """
    if not isinstance(step, dict):
        return ""
    where = str(step.get("where") or "").strip().lower()
    action = str(step.get("action") or "").strip().lower()
    target = str(step.get("target") or "").strip()
    say = _SAY.get(where, {}).get(action)
    if say is not None:
        return say(target)
    if where in _BY_WHERE:
        return _BY_WHERE[where]
    return f"usando {action}" if action else "trabajando"


def found(n: int) -> str:
    """The one phase that is not about an action but about an OUTCOME: «12 resultados».

    The operator asked for it by name («lanzo, tengo resultados»), and it is the moment the card stops looking
    identical to the one before it. Zero is said too — «sin resultados en esta página» is information, and
    hiding it is how a page that gave nothing looks exactly like one that was never read.
    """
    n = max(0, int(n or 0))
    if n == 0:
        return "sin resultados en esta página"
    return f"{n} resultado{'s' if n != 1 else ''} en la página"


def still_alive(phase: str, seconds: int) -> str:
    """A phase that has lasted a long time has to say so on its own (ámbito B2).

    A card frozen on «recorriendo la página» for ninety seconds is indistinguishable from a dead worker, and
    that ambiguity is the whole reason the operator asked for this: silence reads as broken.
    """
    p = " ".join(str(phase or "").split()) or "trabajando"
    p = p.rstrip("…").rstrip()
    if seconds >= 60:
        m = seconds // 60
        return f"{p} — lleva {m} min"
    return f"{p} — lleva {max(1, seconds)}s"

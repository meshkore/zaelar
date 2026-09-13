"""brain.py — what the FlashBrain and the Brain Workers are TOLD about Google (V2-684).

This is the third time this file's lesson gets paid, and the two earlier receipts are written into the
connectors that paid them: `connectors/video/service.py::brain_state` («four claims, zero connections»,
session e1acdcca) and `connectors/messaging/brief._platform_states` («it invented "you have no important
messages" while the widget was closed»). The shape of the failure never changes — the brain holds the
VERBS for a capability and none of the FACTS about it, so when asked it narrates the outcome it assumes.

Google arrives with a new verb nobody has ever seen: **Meet**. Nothing in the engine had a Meet link
before today, so a model asked for one has no prior behaviour to fall back on except inventing a tool
that does not exist, or claiming a link it never minted. Both are cheaper to prevent than to detect.

Two facts are declared here and nowhere else:

1. **Whether the account is connected**, service by service, so «conéctame Gmail» can be declined with a
   reason instead of answered with «Hecho.».
2. **How a Meet link is actually asked for** — as a field of `add_meeting`, not as a tool of its own.
   The model has the appointment tool already; what it lacks is the knowledge that one argument turns an
   appointment into a video meeting. A capability that is reachable but undeclared gets narrated.

Workers reach all of this through `act widget_data` on the agenda, which `worker_policy` already allows
and gates on the widget's own manifest — so nothing had to be added to `_PRESTABLE_TOOLS`, whose comment
says it «grows only with an explicit designation, never by accident». This capability needed no exception.
"""
from __future__ import annotations


def connected_services() -> list[str]:
    """Which Google services have live tokens right now. Fail-safe per door: one connector that raises
    never hides the others (the registry learned this the same way)."""
    from connectors.google import services as _svc
    live: list[str] = []
    for s in _svc.SERVICES.values():
        if not s.owner:
            continue                                   # Meet has no flow of its own — it rides calendar
        try:
            mod = __import__(f"{s.owner}.oauth", fromlist=["oauth"])
            rows = mod.status() or []
            if any(r.get("connected") for r in (rows if isinstance(rows, list) else [rows])):
                live.append(s.id)
        except Exception:                              # noqa: BLE001
            continue
    if "calendar" in live:
        live.append("meet")
    return live


def brain_state() -> str:
    """~4 lines for the turn prompt. Empty string when there is nothing worth the tokens.

    Follows V2-582's rule that a state gets WORDS and never a bare enum: «error» reads as neither
    connected nor disconnected, and a model fills that ambiguity in whichever direction the sentence
    it is composing prefers.
    """
    from connectors.google import app as _app
    live = set(connected_services())

    if not _app.configured():
        return ("GOOGLE: no hay cliente OAuth instalado, así que Gmail, Calendar, Meet, Drive, Fotos y "
                "YouTube NO se pueden conectar ahora mismo. NO digas que los conectas ni que los has "
                "vinculado, y no abras ninguna tarjeta de conexión: dilo tal cual y sigue con lo demás.")

    if not live:
        return ("GOOGLE: la app está instalada pero el operador NO ha dado su consentimiento todavía, así "
                "que no hay ni correo ni calendario reales. Puedes OFRECERLE conectarla (una sola vez sirve "
                "para Gmail, Calendar, Meet, Drive, Fotos y YouTube), pero NO afirmes que está conectada ni "
                "que has leído o escrito nada en su cuenta.")

    out = ["GOOGLE conectado: " + ", ".join(sorted(live)) + ". Lo que no esté en esa lista NO está "
           "conectado — no lo des por hecho."]
    if "meet" in live:
        # The one sentence that exists to prevent an invented tool. It names the ARGUMENT because that is
        # what the model has to produce; naming the capability alone is what makes it improvise a verb.
        out.append("MEET: una cita puede nacer con videollamada. Se pide en el MISMO add_meeting/"
                   "update_meeting de la agenda con `meet: true` — NO hay ninguna tool aparte para crear "
                   "una reunión de Meet, y el enlace lo devuelve Google, así que no te lo inventes ni lo "
                   "prometas antes de que la cita esté creada.")
    return "\n".join(out)

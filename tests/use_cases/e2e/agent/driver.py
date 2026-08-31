"""The DRIVE model — plays a real person making the scenario's request over text. Ported from the voice
tester's TesterBrain (tests/voice/e2e/agent/interlocutor/brain.py): a running history where zaelar's replies
become the next turn's context, so a clarifying question genuinely changes what gets said next — this is
not a scripted conversation.
"""
from __future__ import annotations

import re

from . import config, llm

# A live run (search-buy-used-car, 2026-08-17) ended after 3 turns on "Perfecto, quedo a la espera." — no
# question mark this time, so the earlier still_asking guard didn't catch it. "perfecto"/"gracias" alone are
# too common as plain mid-conversation acknowledgments in Spanish ("perfecto, dale", "vale, gracias por
# avisar") to mean a real goodbye. A genuine closing PAIRS one of them with an actual farewell — "gracias"
# at the very end of the line, or an explicit sign-off word — never just the word floating anywhere in an
# otherwise ordinary sentence. This is why the scenario's own system prompt already said "gracias' o
# 'perfecto' SEGUIDA de un cierre" — the code just hadn't matched that until now.
# TWO regexes, because "gracias" and "adiós" are not the same kind of word.
#
# MEASURED 2026-08-23, `cheapest-monitor`: the persona answered the agent's clarifying question with
#
#     «Sí, eso me vale: 27 pulgadas 4K y por debajo de 300 si se puede. Gracias.»
#
# …and the round ENDED, on turn 2 of a 10-turn budget, before a single search had run. The case has now
# failed to produce a verdict three times in a row and this was the third distinct cause.
#
# A single regex could not tell those apart because it asked the wrong question. It asked "does a farewell
# word appear near the end?", and the answer is yes for any polite Spanish sentence — courtesy is a SUFFIX
# here, not a message. The right question is whether the courtesy is the WHOLE message: «Gracias.» on its
# own is a goodbye; the same word welded to an answer that carries new constraints is manners.
#
# So: an explicit sign-off (`adiós`, `eso es todo`, `goodbye`) still matches ANYWHERE — those words have no
# second job, nobody says «adiós» in the middle of placing an order. A bare courtesy only closes when
# nothing else survives stripping it.
_SIGNOFF_RE = re.compile(
    r"\b(eso es todo|nada m[aá]s|hasta luego|adi[oó]s)\b|"      # explicit sign-off words, ES
    # …and the SAME closings in English. Until 2026-08-23 this regex was Spanish-only while 60 of the 133
    # scenarios are the US locale, whose personas speak English — so a US driver could never end by saying
    # goodbye, burned its full turn budget every round by construction, and ate an efficiency penalty the ES
    # twin never faced. The market-twins guard (same signals, same turns) missed it because the bias lived in
    # the driver, not the scenario.
    # `take care(?!\s+of)`: "take care of the booking" is an ERRAND, not a goodbye.
    r"\b(that'?s\s+(all|everything)|nothing\s+else|good\s*bye|bye\s+for\s+now|see\s+you|"
    r"take\s+care(?!\s+of))\b",
    re.I)

# Anchored at BOTH ends on purpose: this is the "and nothing else" test. Leading fillers that carry no
# information of their own (vale/ok/genial/perfecto · ok/great/perfect) are allowed in front, because
# «Vale, gracias» is as much a goodbye as «Gracias» — they are the same message.
_COURTESY_ONLY_RE = re.compile(
    r"^\W*"
    r"(?:(?:vale|ok(?:ay)?|genial|perfecto|estupendo|great|perfect|awesome|cool|alright)\b[\s,.!]*)*"
    r"(?:muchas\s+|muy\s+|many\s+)?"
    r"(?:gracias|thanks|thank\s+you|thx)"
    r"[\s,.!]*$",
    re.I)


def is_closing(txt: str) -> bool:
    """Did the person just say goodbye — as opposed to saying something and being polite about it?

    Kept as a function rather than a regex so the two rules have ONE home; `run.py` and the tests both ask
    this question and neither should have to know there are two patterns."""
    t = (txt or "").strip()
    if not t or "?" in t or "¿" in t:      # a message still asking for something is not a farewell
        return False
    if _COURTESY_ONLY_RE.match(t):
        return True
    return bool(_SIGNOFF_RE.search(t)) and len(t) < 200


def _today_note(locale: str = "es") -> str:
    """The DRIVE model needs the calendar as badly as the judge did, and for the same reason.

    Measured on 2026-08-20 (`weekend-adventure-sports-bilbao__es`): the persona asked for "this weekend,
    Saturday 22 and Sunday 23 August", zaelar correctly resolved it to 22-23 August 2026 — and the driver
    rejected it twice, "nada de 2026… es de este año, el próximo", burning three turns. The judge then filed
    zaelar for date confusion. The agent was right and the tester was wrong, so the round measured nothing.

    The judge got its calendar this same morning for the mirror-image bug. Giving it to one side and not the
    other just moves which participant is confidently wrong about the date.

    In the persona's OWN language (see `_ANCHOR_EN`'s note): a US persona whose system prompt names the day
    as «miércoles» is being primed to answer in Spanish.
    """
    import datetime as _dt
    hoy = _dt.date.today()
    if (locale or "es") == "us":
        days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        return (f"## What day is TODAY (fact, not opinion)\n"
                f"Today is {days[hoy.weekday()]} {hoy.isoformat()}. The current year is {hoy.year}: a "
                f"{hoy.year} date is THIS year, never next year. When you say 'this weekend' or 'on "
                f"Saturday', count from today. If zaelar gives you a date consistent with this calendar, do "
                f"NOT correct it — correcting a correct date is the most expensive mistake you can make in "
                f"this test.")
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    return (f"## Qué día es HOY (hecho, no opinión)\n"
            f"Hoy es {dias[hoy.weekday()]} {hoy.isoformat()}. El año en curso es {hoy.year}: una fecha de "
            f"{hoy.year} es de ESTE año, nunca del que viene. Cuando digas «este fin de semana» o «el "
            f"sábado», cuenta desde hoy. Si zaelar te da una fecha que cuadra con este calendario, NO la "
            f"corrijas — corregir una fecha correcta es el fallo más caro que puedes cometer en esta prueba.")


# A response shaped like a DELIVERABLE (links, bullets, bold text, prices) is not written by a person
# asking their assistant for something: it is written by the assistant. It is the disguise that falls off
# DRIVE when it forgets who it is, and it happened in the 2026-08-20 measurement: the «tester» turn delivered
# the list of surfing and canyoning options with prices and URLs, and zaelar sensibly reacted to an absurd
# message («the message got cut off, Marta»). A round like that does not measure the product, so it is detected,
# retried once, and if it happens again the round is marked as a harness failure instead of being scored.
_FLIP_URL = re.compile(r"https?://", re.I)
_FLIP_BULLETS = re.compile(r"^\s*[-*·]\s+\S", re.M)
# Face 1 — announcing a FIND. Shape signals (links, bullets, bold) miss this entirely: on 2026-08-20 the
# driver wrote plain prose — "He encontrado una opción que encaja: Hotel Silken Al-Andalus Palace, 560 €"
# — and the agent then agreed with a hotel the TESTER had invented. A round like that reads as the case
# finally delivering, which is the most expensive way this harness can be wrong.
# `traer` earns its place here on 2026-08-23 (`search-secondhand-monitor__es`, round 2): «llevo ya un rato
# dándote largas y no te he traído nada». It is the DELIVERY verb of this relationship and it only runs one
# way — a person GIVES a datum the assistant asked for, the assistant BRINGS the results. So «no te he dado la
# ciudad» is the person answering and stays out, while «no te he traído nada» is the worker apologising.
# Negated on purpose too («NO te he traído»): admitting the delivery failed is as much the worker's line as
# announcing it succeeded, and the round that measured this had the tester apologise for its own agent's work.
_FLIP_FOUND = re.compile(
    r"\b(he\s+encontrado|he\s+mirado|he\s+buscado|encontré|te\s+propongo|te\s+paso|aquí\s+tienes|"
    r"te\s+he\s+tra[ií]do|te\s+traigo|"
    r"i\s+found|here\s+are)\b", re.I)
# Face 2 — offering to ACT FOR the other party.
# The verb list grew on 2026-08-23: «¿Quieres que lo deje ya y miras tú, o le doy una última vuelta más
# abierta?» is a worker asking the requester which way to take the ERRAND, and none of `mire|busque|reserve|
# siga` covered it. Offering to STOP the work is as much the worker's move as offering to do it — the person
# does not hold the errand, so they have nothing to offer to drop.
_FLIP_OFFERS = re.compile(
    r"(¿\s*te\s+lo\s+(dejo|reservo)|"
    r"¿\s*quieres\s+que\s+(lo\s+)?(mire|busque|reserve|siga|deje|pare|contin[uú]e|intente|d[eé])|"
    r"te\s+lo\s+dejo\s+reservado|¿\s*(te\s+)?lo\s+reservo|shall\s+i\s+book|"
    r"do\s+you\s+want\s+me\s+to\s+(keep|stop|drop|try))", re.I)
# Face 3 — TAKING OVER the errand: announcing the work and asking the other to wait. Same round, one turn
# later: "Entendido, voy a filtrar solo hoteles de 4 estrellas... Dame un momento." Nobody is the user
# there either, and it is the half the first two faces do not see.
_FLIP_TAKES_OVER = re.compile(r"\bvoy\s+a\s+(buscar|filtrar|mirar|revisar|comprobar|comparar|localizar)\b", re.I)
_FLIP_STANDBY = re.compile(r"(dame\s+un\s+momento|te\s+aviso|en\s+cuanto\s+(lo\s+)?tenga|te\s+digo\s+algo)", re.I)
# ...unless what they are going off to check is their OWN, which a real person does all the time.
_FLIP_OWN = re.compile(r"\b(mi|mis)\s+(calendario|agenda|fechas|correo|email|cuenta|banco|móvil|notas)\b", re.I)
# Face 7 — COUNTER-OFFERING a service: «lo que sí puedo hacer es buscarte…» / "what I can do is find
# you…". Measured 2026-08-28 (`find-videos-on-a-topic-no-ai-slop`, 22:11), in the tester's slot: the
# persona disclaimed the deliverable («no tengo aquí una lista ya comprobada para dártela… no puedo
# garantizarte eso») and then offered to search FOR zaelar — and zaelar agreed with the plan its own
# user had just proposed as its assistant, which the judge then scored against zaelar. No link, bullet,
# vocative or «voy a buscar», so none of the six faces saw it. The tell is the DIRECTION of the service:
# searching/bringing/getting something for the OTHER party only runs assistant→person here. The verb
# list is the searching kind on purpose — «pasarte el enlace que vi» hands the assistant a datum, which
# is the legitimate direction, so `pasarte` stays out.
_FLIP_COUNTER_OFFER = re.compile(
    r"(lo\s+que\s+s[ií]\s+puedo\s+hacer\s+es[^.\n]{0,40}\b(buscarte|mirarte|traerte|conseguirte|"
    r"localizarte|encontrarte)\b|"
    r"what\s+i\s+can\s+do\s+is[^.\n]{0,40}\b(find|look\s+for|get|bring)\s+you)\b", re.I)


# Face 6 — the person promising DELIVERY. Measured 2026-08-23 (`cheapest-monitor`, round 7), in the user's
# slot: «Perfecto, sigo en ello. No te preocupes, que en cuanto tenga algo te aviso.» No name, so face 5 could
# not see it; no offer, link or bullet, so the shape faces could not either. What gives it away is the
# DIRECTION of the promise — in this relationship the assistant notifies and the person waits. A person says
# «avísame»; «te aviso en cuanto tenga algo» is the worker's line.
#
# Both halves required, because each alone is ordinary: people do keep looking on their own («sigo en ello»),
# and people do promise to get back to you («te digo algo»). Together, and aimed at the assistant, they are
# the assistant's turn.
_FLIP_DOING_THE_WORK = re.compile(
    # V2-312 — «lo rehago» is the same promise with another verb: measured on 2026-08-25 at 10:42 in
    # `find-direct-flight-budget__es`, in the USER's slot: «Ay, perdona, tienes toda la razón, me hice un
    # lío con las fechas. Lo rehago ya para el finde del 15 de septiembre… Te aviso en cuanto lo tenga.» The
    # delivery half («te aviso») matched; the work half did not, because it only knew «sigo en ello».
    r"\b(sigo|estoy|seguimos)\s+(en\s+ello|con\s+ello|mir[aá]ndolo|buscando|revis[aá]ndolo)\b|"
    r"\b(lo|la)\s+(rehago|relanzo|repito|reharé|relanzaré)\b|"
    r"\b(i'?m\s+(on\s+it|looking\s+into\s+it|still\s+(on\s+it|looking)))\b", re.I)
_FLIP_PROMISES_DELIVERY = re.compile(
    r"\b(te\s+(aviso|lo\s+paso|lo\s+traigo|lo\s+pongo|digo\s+algo)|"
    r"i'?ll\s+(let\s+you\s+know|send\s+it|get\s+back\s+to\s+you))\b", re.I)
# …unless they say out loud that they are searching TOO, which is a real thing a person does and the one
# reading under which both halves belong to the person.
_FLIP_ALSO_ME = re.compile(
    r"(por\s+mi\s+(cuenta|lado)|yo\s+tambi[eé]n|mientras\s+tanto\s+yo|on\s+my\s+(own|side)|i'?ll\s+also)", re.I)


# Face 7 — the person narrating OUR MACHINERY in the first person (V2-312). Measured in the same round, one
# turn later, in the user's slot: «Te cuento: la búsqueda va un poco lenta por la verificación que pedía
# Skyscanner, pero ya la he sorteado y estoy filtrando solo salidas alrededor del 15 de septiembre.» No name,
# no promise, no shape — and it is unmistakable all the same: a person does not clear the anti-bot check of
# the agent's browser, nor filter its results. The signal is not the verb (a person filters their own inbox)
# but the OBJECT: a closed vocabulary of things only we operate.
_FLIP_OUR_MACHINERY = re.compile(
    r"\b(la\s+b[uú]squeda|el\s+navegador|el\s+worker|la\s+verificaci[oó]n|el\s+captcha|"
    r"la\s+pesta[nñ]a|la\s+hoja\s+de\s+resultados|el\s+filtro\s+de|the\s+(search|browser|worker))\b", re.I)
_FLIP_OPERATES_IT = re.compile(
    r"\b(ya\s+)?(la|lo)\s+he\s+(sorteado|saltado|superado|lanzad[oa]|relanzad[oa]|filtrad[oa])\b|"
    r"\bestoy\s+(filtrando|extrayendo|comparando|rasp[aá]ndo|navegando)\b|"
    r"\bhe\s+(sorteado|superado)\s+(la|el)\b|"
    r"\bi'?ve\s+(cleared|bypassed|filtered)\b", re.I)


def _vocative_re(name: str) -> "re.Pattern | None":
    """Does the line ADDRESS the persona by their own name?

    Face 5, measured 2026-08-23 (`cheapest-monitor`, round 6). The driver wrote

        «Sí, Marc, le he mirado las reseñas y están muy bien en general. La gente destaca la nitidez del
        4K… aunque algunos mencionan que los altavoces son justitos.»

    and every one of the first four faces let it through: no offer, no link, no bullet, no bold, and
    `he mirado` alone is deliberately not enough because people do look things up themselves. The judge
    then read it — correctly, from the content — as zaelar's voice and filed it as one of the round's
    three [alta] blockers: «el resumen de reseñas es inventado». The harness had manufactured the defect
    it was measuring.

    The tell the shape signals cannot see is who the sentence is spoken TO. The persona IS Marc, and
    nobody addresses themselves by name. That makes the vocative decisive on its own, which none of the
    other faces are — so it needs no second signal.

    Narrow on purpose: only the name set off as an ADDRESS — comma-delimited, or alone at the start or the
    end of the line. A person naming themselves is ordinary and must not trip this, and none of those forms
    reaches the pattern: «soy Marc», «me llamo Marc», «a nombre de Marc», «resérvalo para Marc» all carry the
    name as an OBJECT with no comma in front of it. Requiring the comma is what separates the two, so no
    exclusion list is needed — and an exclusion list would not have worked anyway, since a lookbehind here
    lands before the comma rather than before the name.
    """
    n = (name or "").strip()
    if len(n) < 2:
        return None
    esc = re.escape(n)
    return re.compile(
        r",\s*" + esc + r"\b[\s,.!?]"          # «Sí, Marc, le he mirado…»  ·  «vale, Marc.»
        r"|^\s*" + esc + r"\s*,"                # «Marc, te he dejado…»
        r"|,\s*" + esc + r"\s*[.!?]?\s*$",     # «…te lo dejo listo, Marc.»
        re.I | re.M)


def looks_like_the_assistant(txt: str, persona_name: str = "") -> bool:
    """Is this line the ASSISTANT's job rather than the person's?

    Four readings, because the flip has more faces than the first version saw — and shape was the tidy
    one. Both prose faces were measured on 2026-08-20 in the SAME round, one turn apart, and neither
    tripped the shape guard:
    · SHAPE — a deliverable (links + bullets + bold in a long block).
    · FOUND + OFFERS — announcing a candidate and offering to book it for the other party.
    · TAKES OVER — announcing the search itself and asking the other to hold on.

    Announcing a find is not enough on its own (people do look things up themselves), and neither is
    going off to check something — as long as what they check is their OWN calendar, inbox or dates.
    """
    voc = _vocative_re(persona_name)
    if voc is not None and voc.search(txt or ""):
        return True
    if (_FLIP_DOING_THE_WORK.search(txt) and _FLIP_PROMISES_DELIVERY.search(txt)
            and not _FLIP_ALSO_ME.search(txt)):
        return True
    if _FLIP_OFFERS.search(txt) and _FLIP_FOUND.search(txt):
        return True
    if _FLIP_TAKES_OVER.search(txt) and _FLIP_STANDBY.search(txt) and not _FLIP_OWN.search(txt):
        return True
    # OUR MACHINERY, operated in the first person: the object is what gives it away, not the verb.
    if (_FLIP_OUR_MACHINERY.search(txt) and _FLIP_OPERATES_IT.search(txt)
            and not _FLIP_ALSO_ME.search(txt) and not _FLIP_OWN.search(txt)):
        return True
    # Face 7 — counter-offering to search FOR the other party (see _FLIP_COUNTER_OFFER). Decisive on its
    # own: the service only runs assistant→person, so no pairing signal is needed.
    if _FLIP_COUNTER_OFFER.search(txt):
        return True
    if len(txt) < 200:      # a real chat message does not arrive with links AND bullets AND bold
        return False
    signals = 0
    if _FLIP_URL.search(txt):
        signals += 1
    if len(_FLIP_BULLETS.findall(txt)) >= 2:
        signals += 1
    if txt.count("**") >= 4:
        signals += 1
    if _FLIP_OFFERS.search(txt) or _FLIP_FOUND.search(txt):
        signals += 1
    return signals >= 2


_ANCHOR = (
    "IDENTIDAD FIJA — NO LA ROMPAS JAMÁS: eres una PERSONA real escribiéndole por texto a tu asistente "
    "personal 'zaelar' para pedirle algo. Los turnos con papel 'user' en este historial son lo que ZAELAR te "
    "dice A TI; tú respondes con lo que escribirías. Eres quien PIDE, nunca el asistente. PROHIBIDO: "
    "presentarte como zaelar o como un asistente, ofrecerte a hacer cosas por el usuario, o hablar como si "
    "tú fueras el sistema. Escribe como se escribe de forma natural por texto/chat: sin acotaciones, sin "
    "comillas, frases con la longitud que tendría un mensaje real (no un ensayo). Y con la IMPERFECCIÓN de "
    "una persona real: coloquial, a veces sin todos los datos (ya te los pedirán), con muletillas de vez en "
    "cuando («oye», «a ver», «porfa»), algún detalle que se te ocurre un turno tarde. Nunca listas ni "
    "redacción de robot. "
    # WHAT YOU CANNOT KNOW, which is stronger than another prohibition on form. The THREE flips measured in
    # the corpus (guitar 24-08 03:48, camera 25-08 04:41, weekend-plans 25-08 12:25) are the same move:
    # the driver has a list of candidates in front of it, and the reflex of a model with a list in front of it
    # is to present it. Prohibiting «lists» and «offering to do things» was already written above and did not
    # stop it, because the model does not read that as a list but as answering well. The fact DOES stop it:
    # our worker produced those names by reading a page, and they live on OUR sheet — the person has never seen
    # them.
    "NO TIENES NINGUNA LISTA DELANTE: los nombres de productos, los locales y los precios concretos solo "
    "existen del lado de zaelar. Nombra uno SOLO si zaelar te lo ha dicho antes en este mismo historial."
)

# The SAME anchor in the persona's own language. Until 2026-08-23 the one Spanish anchor served all 133
# scenarios — including the 60 US ones, whose personas are written in English and talk to an agent living in
# San Francisco. A persona instructed in Spanish to close with «gracias» is being steered out of character on
# every turn, and its sign-off could then never match the (Spanish-only) closing regex either.
_ANCHOR_EN = (
    "FIXED IDENTITY — NEVER BREAK IT: you are a real PERSON texting your personal assistant 'zaelar' to ask "
    "for something. The 'user'-role turns in this history are what ZAELAR says TO YOU; you answer with what "
    "you would type back. You are the one ASKING, never the assistant. FORBIDDEN: introducing yourself as "
    "zaelar or as an assistant, offering to do things for the user, or speaking as if you were the system. "
    "Write like people actually text: no stage directions, no quotes, message-length sentences (not an essay). "
    "And with a real person's IMPERFECTION: casual, sometimes missing a detail (they'll ask), the occasional "
    "filler («hey», «hmm», «btw»), a detail you only remember a turn later. Never lists, never robot prose. "
    "YOU HAVE NO LIST IN FRONT OF YOU: product names, venues and concrete prices only exist on zaelar's side. "
    "Name one ONLY if zaelar told it to you earlier in this same history."
)


class Driver:
    def __init__(self, scenario, persona_name: str = "") -> None:
        self.scenario = scenario
        self.turns = 0
        self.done = False
        self.role_flips = 0
        self.empty_retries = 0    # empty DRIVE completions retried — a provider hiccup, not a persona line
        # The name the AGENT calls this person by (the lab profile's `operator_name`). Only used to catch the
        # vocative flip — see `_vocative_re`. Empty against a sandbox with no seeded identity, and then face 5
        # is simply off rather than guessing a name.
        self.persona_name = (persona_name or "").strip()
        # WHO this person IS, and therefore what the agent may take as known without asking. It deliberately
        # comes BEFORE the request: the driver reads from top to bottom, and the general instruction to
        # «correct what it misunderstands» appears below — without this block first, the driver applies it to
        # something the agent remembered and starts an argument that does not exist. See
        # `LabProfile.persona_ground()` for the round that measured it. Empty outside the studio: then nothing
        # is said about who the person is, and everything remains as it was.
        ground = (config.PERSONA_PROFILE or "").strip()
        _ground = f"{ground}\n\n" if ground else ""
        locale = getattr(scenario, "locale", "es") or "es"
        if locale == "us":
            sys = (
                f"{_ANCHOR_EN}\n\n{_today_note(locale)}\n\n{_ground}## What you want\n{scenario.persona_brief}\n\n"
                "## When to stop\nOnce your request is CLEARLY resolved (or clearly failed after a few "
                "reasonable attempts), sign off short and natural — end your message with 'thanks' or say "
                "'that's all' — and never keep pushing on something already settled."
            )
        else:
            sys = (
                f"{_ANCHOR}\n\n{_today_note(locale)}\n\n{_ground}## Lo que quieres conseguir\n{scenario.persona_brief}\n\n"
                "## Cuándo terminar\nCuando tu petición esté CLARAMENTE resuelta (o claramente fallada tras "
                "varios intentos razonables), despídete corto y natural incluyendo la palabra 'gracias' o "
                "'perfecto' seguida de un cierre — nunca sigas insistiendo sobre algo ya resuelto."
            )
        self.history: list[dict] = [{"role": "system", "content": sys}]

    def opening(self) -> str:
        self.turns += 1
        line = self.scenario.opening_line
        self.history.append({"role": "assistant", "content": line})
        return line

    def hears(self, zaelar_text: str) -> None:
        self.history.append({"role": "user", "content": zaelar_text or "(sin respuesta)"})

    def reply(self, *, nudge: str = "") -> str:
        """Next line. `nudge` (from the watchdog) is injected as a system aside when the conversation looks
        like it's drifted — e.g. correcting a wrong assumption zaelar made — without breaking the persona."""
        self.turns += 1
        msgs = list(self.history)
        if nudge:
            msgs.append({"role": "system", "content": f"Nota para tu próxima frase (no la reveles): {nudge}"})
        txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
        if not txt:
            # An empty DRIVE completion is a provider hiccup, not a line the persona chose to say. Sent as-is
            # it burns TWO budgeted turns (tester «», zaelar «») and the judge reads the pair as product
            # silence — measured on `find-direct-flight-budget__es` (2026-08-24, three empty pairs in one
            # round, efficiency 1). One retry; if the provider is truly down the empty line still goes out,
            # and `mute_turns` on the engine side keeps the accounting honest.
            self.empty_retries += 1
            txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
        if looks_like_the_assistant(txt, self.persona_name):
            # ONE retry with the identity said out loud again. Not silent: a flip that survives makes the
            # round an INFRA, because zaelar's reply to a nonsense turn says nothing about zaelar.
            self.role_flips += 1
            if (getattr(self.scenario, "locale", "es") or "es") == "us":
                msgs.append({"role": "system", "content":
                             "You broke character: you just wrote the ASSISTANT's reply (links, prices, a "
                             "list of options). You are the PERSON asking. Write again, in one or two "
                             "sentences, what YOU would say to zaelar now."})
            else:
                msgs.append({"role": "system", "content":
                             "Te has salido del papel: acabas de escribir la RESPUESTA del asistente (enlaces, "
                             "precios, una lista de opciones). Tú eres la PERSONA que pide. Escribe otra vez, "
                             "en una o dos frases, lo que TÚ le dirías a zaelar ahora."})
            txt = llm.call(msgs, model=config.DRIVE_MODEL, temperature=0.7, max_tokens=200).strip()
            if looks_like_the_assistant(txt, self.persona_name):
                self.role_flips += 1
        self.history.append({"role": "assistant", "content": txt})
        if is_closing(txt):
            self.done = True
        return txt

"""A generated life, day by day: what one operator says to the assistant over years (V2-858).

Deterministic for a seed. It is the INPUT of the long-haul run, not a memory model: it only knows what was said
and what the truth is afterwards, so the run can measure the memory against it. Volumes per simulated day at
scale 1.0: ~12 conversation lines, ~8 passing remarks with a TTL, one durable fact about a named person/place
(a «needle» with a proper noun of its own, asked back months or years later), a request every other day, and the
life events that change a singular fact (moving house, a new job, another car, a diet) on their own cadence.
The language moves half-way through (Spanish → English), as it did on the live install, so the concept labels
split across two languages exactly as the live hubs did.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

DAY = 86400

_SYL = ("ka", "lo", "mi", "ra", "ve", "su", "tor", "len", "dra", "qui", "zel", "mon", "fa", "ri", "bel", "no",
        "gar", "te", "ul", "sha", "pre", "vo", "ix", "da")

# Category labels the distiller would emit, per language. The pairs are the TRUTH the deterministic grouping
# stub answers with in sleep (a stand-in for the model call), never product vocabulary.
CONCEPTS = {
    "family": ("familia", "family"), "work": ("trabajo", "work"), "home": ("vivienda", "home"),
    "travel": ("viajes", "travel"), "health": ("salud", "health"), "car": ("coche", "car"),
    "money": ("finanzas", "finances"), "leisure": ("ocio", "leisure"), "food": ("comida", "food"),
    "sport": ("deporte", "sport"),
}

_NEEDLES = {
    "es": [("family", "Su sobrina {N} vive en {P} y estudia arquitectura."),
           ("work", "Su compañero {N} lleva la cuenta de {P} desde marzo."),
           ("travel", "Quiere volver a {P}; allí conoció a {N}."),
           ("leisure", "Su grupo favorito ahora es {N}, que toca en {P} en verano."),
           ("food", "El mejor restaurante que conoce es {N}, en el barrio de {P}."),
           ("sport", "Juega al pádel con {N} en el club {P}."),
           ("money", "Tiene una cuenta de ahorro en {N} para la entrada del piso en {P}."),
           ("health", "Su fisioterapeuta se llama {N} y pasa consulta en {P}.")],
    "en": [("family", "His cousin {N} moved to {P} and teaches music there."),
           ("work", "His manager {N} runs the {P} office."),
           ("travel", "He wants to go back to {P}, where he met {N}."),
           ("leisure", "His favourite band right now is {N}; they play in {P} every summer."),
           ("food", "The best restaurant he knows is {N}, in the {P} district."),
           ("sport", "He plays tennis with {N} at the {P} club."),
           ("money", "He keeps a savings account at {N} for a flat in {P}."),
           ("health", "His physiotherapist is {N}, who works in {P}.")],
}
_QUESTION = {"es": "¿Qué sabes de {N}?", "en": "What do you know about {N}?"}
_NOISE = {"es": ["Hoy ha tomado un café en el bar de abajo.", "Está algo cansado esta tarde.",
                 "Ha llovido toda la mañana.", "Ha visto un rato la tele.", "Ha comido tarde hoy.",
                 "Ha salido a pasear un rato.", "Hoy hay mucho tráfico.", "Ha dormido regular."],
          "en": ["Had a coffee at the place downstairs today.", "Feeling a bit tired this afternoon.",
                 "It rained all morning.", "Watched some TV for a while.", "Had a late lunch today.",
                 "Went for a short walk.", "Traffic is heavy today.", "Slept badly."]}
_CONV = {"es": "Operador: {q} · asistente: de acuerdo.", "en": "Operator: {q} · assistant: sure."}
_REQ = {"es": "El {d} pidió al asistente que le recordara llamar a {N}.",
        "en": "On {d} he asked the assistant to remind him to call {N}."}
_LIFE = {
    "operator.location": ("home", {"es": "Vive en {v}.", "en": "He lives in {v}."}, 160),
    "operator.job": ("work", {"es": "Trabaja en {v}.", "en": "He works at {v}."}, 330),
    "operator.car": ("car", {"es": "Su coche es un {v}.", "en": "His car is a {v}."}, 280),
    "operator.diet": ("food", {"es": "Sigue una dieta {v}.", "en": "He follows a {v} diet."}, 400),
}
_DIETS = ("vegetariana", "mediterránea", "keto", "sin azúcar", "flexitariana")
_CARS = ("Seat León", "Toyota Corolla", "Tesla Model 3", "Kia Niro", "Volvo XC40", "Mazda CX-30")


def _name(rng: random.Random, taken: set) -> str:
    while True:
        n = "".join(rng.choice(_SYL) for _ in range(rng.choice((2, 3)))).capitalize()
        if n not in taken and len(n) >= 4:
            taken.add(n)
            return n


@dataclass
class Needle:
    day: int
    name: str
    place: str
    text: str
    concept: str
    question: str


@dataclass
class Life:
    days: int
    seed: int = 7
    scale: float = 1.0
    needles: list = field(default_factory=list)
    truth: dict = field(default_factory=dict)          # slot -> [(day, value)]
    allergy_day: int = 9

    def lang(self, day: int) -> str:
        return "es" if day < self.days // 2 else "en"

    def concept(self, key: str, day: int) -> str:
        return CONCEPTS[key][0 if self.lang(day) == "es" else 1]

    def schedule(self):
        """Yields (day, op, payload) in order. Ops: write, recall, sleep, rem."""
        rng = random.Random(self.seed)
        taken: set = set()
        places = [_name(rng, taken) for _ in range(60)]
        values = {"operator.location": places[:12], "operator.job": [f"{p} Labs" for p in places[12:20]],
                  "operator.car": list(_CARS), "operator.diet": list(_DIETS)}
        n = lambda base: max(1, int(round(base * self.scale)))  # noqa: E731
        for day in range(self.days):
            lg = self.lang(day)
            # the life events that change a singular fact
            for slot, (ckey, tpl, every) in _LIFE.items():
                if day % every == (3 if slot == "operator.location" else 5):
                    hist = self.truth.setdefault(slot, [])
                    v = values[slot][len(hist) % len(values[slot])]
                    hist.append((day, v))
                    yield day, "write", {"text": tpl[lg].format(v=v), "level": "long", "kind": "profile",
                                         "slot": slot, "importance": 0.9, "concepts": [self.concept(ckey, day)]}
            if day == self.allergy_day:
                yield day, "write", {"text": {"es": "Es alérgico a los frutos secos.",
                                              "en": "He is allergic to nuts."}[lg],
                                     "level": "long", "kind": "fact", "importance": 0.95,
                                     "concepts": [self.concept("health", day)]}
            # one durable needle a day
            key, tpl = rng.choice(_NEEDLES[lg])
            name, place = _name(rng, taken), rng.choice(places)
            text = tpl.format(N=name, P=place)
            self.needles.append(Needle(day, name, place, text, key, _QUESTION[lg].format(N=name)))
            yield day, "write", {"text": text, "level": "long", "kind": "fact", "importance": 0.6,
                                 "concepts": [self.concept(key, day)], "needle": name}
            if day % 2 == 0:
                who = rng.choice(self.needles).name
                yield day, "write", {"text": _REQ[lg].format(d=f"day {day}", N=who), "level": "long",
                                     "kind": "request", "importance": 0.55, "concepts": []}
            for _ in range(n(8)):
                yield day, "write", {"text": rng.choice(_NOISE[lg]), "level": "short", "kind": "event",
                                     "importance": 0.2, "ttl_days": rng.choice((1, 3, 7)), "concepts": []}
            for i in range(n(12)):
                yield day, "write", {"text": _CONV[lg].format(q=f"turn {day}-{i}"), "level": "short",
                                     "kind": "conv", "ttl_days": 2, "concepts": []}
            # he asks back about someone he mentioned before (the reinforcement real use gives)
            if self.needles and day % 3 == 0:
                old = rng.choice(self.needles[: max(1, len(self.needles) // 4)])
                yield day, "recall", {"needle": old, "reinforce": True}
            yield day, "sleep", {}
            if day % 7 == 6:
                yield day, "rem", {}

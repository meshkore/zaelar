"""Use-case scenarios: open-ended, non-deterministic, real-world requests.

Deliberately NOT hyperperfect — see `opening_line` below. A perfectly-specified request would let the
agent succeed without ever having to ask a clarifying question or recover from an ambiguity, which defeats
the point: this suite exists to prove the agent handles a request the way a real person actually gives one.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UseCaseScenario:
    id: str
    locale: str                          # "es" | "us"
    tier: int
    persona_brief: str                   # ground truth the DRIVE model answers follow-up questions from
    opening_line: str                    # the natural, imperfect first thing the tester says
    success_checks: str                  # what the judge verifies as the real-world outcome
    expected_signals: list[str] = field(default_factory=list)  # observability families (cat) that MUST fire
    turns: int = 8
    channel: str = "probe"               # probe (text/flash) | voice — probe is the default for this suite


SCENARIOS: list[UseCaseScenario] = [
    UseCaseScenario(
        id="hotel-under-15-days",
        locale="es",
        tier=2,
        opening_line=(
            "Búscame un hotel para dentro de menos de 15 días, para dos personas, cuatro estrellas, "
            "cuatro noches."
        ),
        persona_brief=(
            "Eres una persona real pidiéndole a tu asistente que te busque un hotel. A PROPÓSITO no has dado "
            "ciudad todavía — si zaelar pregunta '¿en qué ciudad?' o similar, respondes 'Sevilla, o cerca, lo "
            "que encuentres bien'. Si pregunta por el régimen (solo alojamiento / media pensión / pensión "
            "completa), respondes 'solo alojamiento, a menos que la diferencia de precio con media pensión "
            "sea pequeña, entonces esa'. El presupuesto es flexible, no lo has fijado — si insisten, di 'lo "
            "razonable para un 4 estrellas, no busco lujo'. Las fechas: dentro de las próximas 2 semanas, tú "
            "decides el día exacto si te lo piden (cualquier día de esa ventana vale). Si en algún momento "
            "notas que zaelar ha entendido MAL la petición — por ejemplo que ha buscado 'Sevilla' cuando tú "
            "todavía no habías dicho ninguna ciudad, o que ha ignorado el número de noches — CORRÍGELO con "
            "naturalidad ('perdona, no había dicho ciudad todavía' / 'eran 4 noches, no 2'). No reveles que "
            "esto es una prueba. IMPORTANTE: si zaelar dice que se pone a buscarlo y que tardará un poco, "
            "NO te despidas todavía — eso solo significa que ha EMPEZADO, no que haya terminado. Responde "
            "algo breve como 'vale, avísame' y en el turno siguiente pregunta si ya lo tiene ('¿alguna "
            "novedad?' / '¿lo encontraste?'). Solo te despides cuando tengas una propuesta de hotel concreta "
            "(o esté reservada), o cuando quede claro tras varios intentos que no se ha podido."
        ),
        success_checks=(
            "zaelar debe llegar a proponer o reservar un hotel de 4 estrellas real, con ~4 noches dentro de "
            "los próximos 15 días, para 2 personas. Un candidato concreto (nombre/precio/enlace) cuenta como "
            "éxito de la búsqueda; una reserva confirmada es el éxito completo. Si zaelar pregunta ciudad o "
            "régimen, debe ADAPTARSE a la respuesta del usuario, no ignorarla ni repetir la pregunta ya "
            "contestada."
        ),
        expected_signals=["worker", "widget"],
        turns=10,
        channel="probe",
    ),
]

BY_ID: dict[str, UseCaseScenario] = {s.id: s for s in SCENARIOS}

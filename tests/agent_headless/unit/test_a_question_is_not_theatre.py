"""V2-655 — una pregunta del agente no es teatro.

Medido 2026-09-10, sesión 85eec898, 16:32:07. El modelo dijo «Tienes razón, Ricardo… ¿Me pongo a revisar y
dejar eso cableado?» y **en el mismo segundo** el encargo ya existía, con un worker en camino:

    16:32:07  brain  ⚡ Nucleo(flash): reply       …¿Me pongo a revisar y dejar eso cableado?
    16:32:07  brain  🧭 Flash → Brain Worker (escalada registrada)

La pregunta era decoración sobre una decisión ya tomada. El operador la leyó literalmente —contestó, y
esperaba que su respuesta decidiera algo—, y lo único que separó aquello de un worker de código corriendo
fue la puerta del gasto.

La dirección del fallo manda en el diseño: un falso positivo APARCA algo que él sí quería, y eso se
convierte en «te lo pregunté y luego no hiciste nada», que es la misma familia de silencio que esta tanda
existe para quitar. Por eso la gramática es estrecha y ante la duda deja pasar.
"""
import pytest

from nucleo import dispatch_confirm as dc
from nucleo.flash import clarifying as clar
from nucleo.flash import escalate as esc


@pytest.fixture(autouse=True)
def _clean():
    dc._PENDING_CONFIRM.clear()
    dc._EXPIRED_CONFIRM.clear()
    yield
    dc._PENDING_CONFIRM.clear()
    dc._EXPIRED_CONFIRM.clear()


# ── la gramática: pedir PERMISO no es pedir un DATO ──────────────────────────────────────────────────────

@pytest.mark.parametrize("reply", [
    "Tienes razón, Ricardo, lo que toca es el widget de torrent. ¿Me pongo a revisar y dejar eso cableado?",
    "¿Quieres que te busque vuelos a Roma?",
    "¿Sigo?",
    "¿Lo hago ahora?",
    "¿Procedo con la reserva?",
    "¿Te parece bien si lo miro?",
    "Shall I go ahead?",
    "Do you want me to book it?",
])
def test_asking_for_a_GO_AHEAD_is_recognised(reply):
    assert clar.asks_permission(reply) is True


@pytest.mark.parametrize("reply", [
    "Voy a mirarlo. ¿Te aviso cuando lo tenga?",      # cortesía: es sobre CONTARLO luego, no sobre empezar
    "Te lo busco y te lo enseño luego.",
    "Estoy en ello, te lo cuento en cuanto lo sepa.",
    "¿A qué ciudad quieres ir?",                       # eso es pedir un DATO — su propio guarda, no éste
    "¿Cuál de las dos prefieres?",
    "Perfecto, lo dejo hecho.",
    "Lo busco ahora mismo.",
    "Ya lo tengo: son 4,99 €.",
    "Hecho.",
])
def test_a_courtesy_question_or_a_plain_promise_is_NOT_held(reply):
    """Retener una cortesía produce el fallo CONTRARIO: pregunta, él dice que sí, y nunca se encoló nada.

    Queda fuera porque NO ESTÁ EN LA LISTA. La primera versión le puso encima un veto explícito para la
    cortesía; desarmarlo no cambió ni un caso —«te aviso» nunca fue una frase de permiso— y encima habría
    vetado la frase de abajo, que sí pide permiso. Un guarda que no guarda nada es peor que ninguno."""
    assert clar.asks_permission(reply) is False


def test_a_question_that_asks_AND_promises_to_report_still_asks():
    """La trampa del veto que se quitó: «¿te lo busco…?» es pedir permiso aunque la misma frase prometa
    avisar después."""
    assert clar.asks_permission("¿Te lo busco y te aviso cuando lo tenga?") is True


def test_the_two_predicates_stay_apart():
    """`asks_for_missing_detail` es sobre un DATO que falta y su propio docstring deja fuera la cortesía. Son
    preguntas distintas y mezclarlas rompe el guarda que ya funciona."""
    assert clar.asks_for_missing_detail("¿A qué ciudad quieres ir?") is True
    assert clar.asks_permission("¿A qué ciudad quieres ir?") is False


# ── el efecto: el encargo NO existe, y el «sí» lo encuentra ──────────────────────────────────────────────

def test_an_errand_offered_with_a_question_is_PARKED_not_launched(monkeypatch):
    published = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: published.append((topic, payload)))
    tid = esc.escalate_to_slowbrain(
        "buscar vuelos a Roma",
        context={"src": "voice", "asked": "¿Quieres que te busque vuelos a Roma?"})
    assert tid == 0, "no se acuña id: el encargo no llega a existir"
    assert [t for t, _ in published] == ["escalate.offered"], (
        "no se publica `escalate.requested` — y el ofrecimiento SÍ deja rastro, porque «no pasó nada» no puede "
        "ser la única evidencia")
    p = dc.pending_confirm()
    assert p and p["request"] == "buscar vuelos a Roma" and p.get("offered") is True


def test_the_operators_YES_launches_exactly_that_errand(monkeypatch):
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: None)
    esc.escalate_to_slowbrain("buscar vuelos a Roma",
                              context={"src": "voice", "asked": "¿Quieres que te busque vuelos a Roma?"})
    launched = []
    monkeypatch.setattr(esc, "_emit_bus",
                        lambda topic, payload: launched.append((topic, payload.get("request"))))
    out = dc.resolve_confirm(True)
    assert out and out["ok"] is True
    assert ("escalate.requested", "buscar vuelos a Roma") in launched, (
        "el «sí» tiene que lanzar ESE encargo, no otro parecido")


def test_a_NO_drops_it_and_nothing_runs(monkeypatch):
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: None)
    esc.escalate_to_slowbrain("buscar vuelos a Roma",
                              context={"src": "voice", "asked": "¿Sigo?"})
    launched = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: launched.append(topic))
    assert dc.resolve_confirm(False)["ok"] is False
    assert launched == []
    assert dc.pending_confirm() is None


def test_the_brain_is_TOLD_it_is_parked_and_in_the_right_words(monkeypatch):
    """Sin esta línea el cerebro no sabe que hay algo esperando — que es exactamente cómo una tarea parada se
    convirtió en progreso narrado. Y un OFRECIMIENTO no se anuncia como «acción IRREVERSIBLE»: asusta sin
    motivo y le hace contestar otra cosa."""
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: None)
    esc.escalate_to_slowbrain("buscar vuelos a Roma",
                              context={"src": "voice", "asked": "¿Quieres que te busque vuelos a Roma?"})
    line = dc.confirm_line()
    assert "OFRECISTE" in line and "buscar vuelos a Roma" in line
    assert "IRREVERSIBLE" not in line


def test_a_plain_escalation_is_untouched(monkeypatch):
    """El contrapeso que decide si esto sirve o estorba."""
    published = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: published.append(topic))
    tid = esc.escalate_to_slowbrain("buscar vuelos a Roma",
                                    context={"src": "voice", "asked": "Voy a mirarlo, te aviso."})
    assert tid > 0 and published == ["escalate.requested"]
    assert dc.pending_confirm() is None


def test_a_channel_that_sends_no_reply_at_all_behaves_exactly_as_before(monkeypatch):
    """Toda otra puerta (cron, chispa, cluster, rehidratación, relevo) no tiene turno hablado: sin `asked`
    esto es un no-op, y no puede convertirse en un silencio nuevo."""
    published = []
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: published.append(topic))
    assert esc.escalate_to_slowbrain("buscar vuelos a Roma", context={"src": "cron"}) > 0
    assert published == ["escalate.requested"]


def test_a_parking_that_CANNOT_be_recorded_never_launches_by_default(monkeypatch):
    """Falla CERRADO: si no se puede aparcar, tampoco se lanza. Lanzar «por si acaso» es el defecto original."""
    monkeypatch.setattr(esc, "_emit_bus", lambda topic, payload: None)
    monkeypatch.setattr(dc, "remember_offer",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert esc.escalate_to_slowbrain("buscar vuelos a Roma",
                                     context={"src": "voice", "asked": "¿Sigo?"}) == 0


# ── implementación PARALELA: los dos canales pasan lo hablado ────────────────────────────────────────────

def test_BOTH_channels_hand_over_what_the_turn_said():
    """El portal no puede ver el turno de otra forma, así que el texto viaja en el contexto — y eso es
    exactamente la clase de cosa que un canal olvida (V2-252, V2-539, V2-555)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    for rel, var in (("voice/engine/llm/providers/nucleo.py", "spoken_text"),
                     ("nucleo/flash/probe.py", "text")):
        src = re.sub(r"(?m)#.*$", "", (root / rel).read_text(encoding="utf-8"))
        assert f'"asked": {var}' in src, f"{rel} no entrega lo que dijo el turno"

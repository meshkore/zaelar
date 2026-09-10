"""V2-655 — el núcleo y el motor NO se modifican. Por voz, por chat, ni por ninguna interfaz del agente.

Directriz del operador (2026-09-10): *«el núcleo y el motor del sistema no se puede modificar. El sistema a
través de la voz o el chat o cualquier interfaz que tenga permisos solo permite modificar widgets.»*

Lo que pasó (sesión 85eec898): pegó en el chat un mensaje escrito para un agente de desarrollo y el agente lo
tomó como orden para sí mismo — el encargo existía en el MISMO segundo en que el modelo preguntaba «¿Me
pongo?». Lo único que lo frenó fue la puerta del GASTO, y `danger.py` es vocabulario de dinero: no contiene
ni una palabra sobre tocar el motor. Fue una coincidencia, no un control.

Dos capas, y las dos se prueban aquí: el MECANISMO (nadie recibe con qué escribir) y la INTENCIÓN (la
negativa es legible en vez de un worker dando vueltas).
"""
import pytest

from nucleo import protected_core as pc


# ── la INTENCIÓN: qué se reconoce como «esto me modifica a mí» ───────────────────────────────────────────

@pytest.mark.parametrize("req", [
    "revisa que los rails o canalizaciones de esas acciones vayan a parar aquí",   # el mensaje real, verbatim
    "Revisar y reconfigurar el FLUJO PRIORITARIO de resolución de peticiones",     # el encargo que se creó
    "cambia el prompt del dispatcher",
    "quiero que modifiques el motor de voz",
    "toca el núcleo para que vaya más rápido",
    "quiero que reprogrames tu arquitectura",
    "revisa el cableado de las acciones",
    "rewrite your own dispatcher",
    "fix the engine prompt",
])
def test_an_order_to_change_ZAELAR_ITSELF_is_recognised(req):
    assert pc.touches_the_engine(req) is True


@pytest.mark.parametrize("req", [
    "créame un widget del tiempo",                       # lo que SÍ se permite
    "modifica el widget de la agenda para que muestre la semana",
    "cambia el flujo de trabajo del widget de música",   # nombra un widget: el trabajo permitido
    "cambia la tarjeta de música para que muestre el artista",
    "búscame un hotel en Soria",
    "arregla la cita del dentista de mañana",
    "arregla la reserva del restaurante",
    "revisa mis correos de hoy",
    "programa un aviso para mañana",
    "apaga el motor del coche en el videojuego",         # «motor» sin verbo de cambio cerca
    "ponme música",
])
def test_a_legitimate_errand_is_NOT_blocked(req):
    """El contrapeso, y es la mitad que decide si esto sirve o estorba: un falso positivo aquí es negarse a
    algo que el operador sí pidió, que es el fallo que no queremos importar del otro lado."""
    assert pc.touches_the_engine(req) is False


def test_the_SUBJUNCTIVE_does_not_slip_through():
    """Medido al escribir esto: `modific\\w*` NO casa «modifiques» (modifi-QUE-s), y «quiero que modifiques
    el motor de voz» pasaba limpio. Los prefijos se cortan ANTES de la alternancia."""
    for verb in ("modifiques", "toques", "revises", "repares", "corrijas"):
        assert pc.touches_the_engine(f"quiero que {verb} el motor"), verb


def test_the_refusal_says_what_it_understood_AND_what_can_be_done():
    """Negarse sin decir qué sí se puede hacer se lee como una avería (la lección de V2-507)."""
    msg = pc.refusal("reconfigura el flujo prioritario de peticiones")
    assert "widget" in msg.lower(), "tiene que nombrar la frontera, no solo el veto"
    assert "reconfigura el flujo" in msg, "y citar lo que entendió, para que él vea el malentendido"


# ── el MECANISMO: quién recibe permiso de escribir, y dónde ──────────────────────────────────────────────

def test_only_the_widget_generator_and_the_cluster_dev_worker_may_write():
    assert pc.writes_are_confined("code", "créame un widget del tiempo") is True
    assert pc.writes_are_confined("dev", "cualquier cosa del cluster") is True


def test_the_ARCHITECT_branch_is_code_and_still_may_NOT_write():
    """EL AGUJERO. `_ARCHITECT_RE` también devuelve `kind="code"`, y esa rama NO pasa por el generador
    confinado: era un worker de CLI con Write+Edit y el REPOSITORIO como directorio de trabajo, alcanzable
    por voz. La protección que parecía existir era accidental — dependía de cómo estuviera redactada la
    frase."""
    assert pc.writes_are_confined("code", "crea un proyecto nuevo en el repo con architect") is False


@pytest.mark.parametrize("kind", ["generic", "web", "research", "memory", ""])
def test_no_other_kind_writes_anything(kind):
    assert pc.writes_are_confined(kind, "lo que sea") is False


def test_it_fails_CLOSED_when_it_cannot_tell(monkeypatch):
    """Si no se puede afirmar que es una tarea de widget, no escribe. Lo contrario —conceder ante la duda—
    es cómo el agujero llegó aquí."""
    import nucleo.agentes.code as _code
    monkeypatch.setattr(_code, "is_widget_request", lambda r: (_ for _ in ()).throw(RuntimeError("boom")))
    assert pc.writes_are_confined("code", "créame un widget del tiempo") is False


# ── el cableado: las dos capas están enchufadas donde deben ──────────────────────────────────────────────

def test_the_refusal_lives_in_the_SINGLE_gateway_every_escalation_passes_through():
    """Mismo argumento que puso `strip_system_notes` ahí, escrito en su propio comentario: un llamante nuevo
    hereda la regla sin tener que acordarse."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "nucleo/flash/escalate.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    i, j = text.find("touches_the_engine("), text.find("_next_seq(")
    assert i >= 0 and j > i, (
        "el veto va ANTES de acuñar el id: el encargo no puede llegar a existir — ni ficha, ni hoja en el "
        "canvas, ni nombre — porque la avería fue justo eso, el encargo visible mientras el modelo preguntaba")


def test_the_tools_and_the_cwd_follow_the_ERRAND_not_its_kind():
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "nucleo/dispatch.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    assert "protected_core.writes_are_confined(kind, req)" in text
    assert 'if kind == "code" and may_write:' in text, (
        "Write/Edit los da el encargo, no el nombre del kind")
    assert "if not (_may_write and workdir.needs_repo(kind)):" in text, (
        "…y el repositorio entero tampoco se entrega por llamarse `code`")


def test_the_cluster_dev_channel_is_deliberately_outside_this_rule():
    """Es NUESTRA herramienta de trabajo, no una interfaz del agente, y ya lleva su propio jail que falla
    cerrado. Dicho explícito para que nadie lo cierre por inercia sin decidirlo."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "nucleo/flash/escalate.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    assert 'ctx0.get("kind") != "dev"' in text

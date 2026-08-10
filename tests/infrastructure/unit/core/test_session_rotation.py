#
# Un RESET deliberado abre una SESIÓN DE TRABAJO NUEVA (petición del operador, 2026-08-10).
#
# «Es como si paráramos el agente y lo volviéramos a arrancar manteniendo las mismas reglas que ya teníamos, pero
# la observabilidad se tiene que quedar a cero porque es una nueva sesión que empieza en blanco, con id nuevo.»
#
# Lo que fallaba: el reset vaciaba el log (`clear_log`) pero NO rotaba el id — `identity.begin_session(force=True)`
# no lo llamaba nadie. Así que los eventos posteriores seguían colgando de la sesión vieja: el registro durable
# mezclaba en una misma sesión el trabajo de antes y el de después de un borrón, y la columna de observabilidad
# arrancaba «vacía» pero con la identidad de algo que ya no existía.
#
# OJO con lo que NO debe cambiar: `begin_session` reutiliza a propósito la sesión abierta, para que una reconexión
# por un bache de red no se cuente como sesión nueva (partirla en dos falsearía «cuánto duró y qué hizo»). La
# rotación es SOLO para el reset deliberado, y por eso necesita `force=True`.
#
import bus as busmod
import pytest

from observability import identity
from voice import observer, trace


@pytest.fixture(autouse=True)
def _clean():
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()
    yield
    busmod.reset()
    identity.end_session("test")
    observer.clear_log()


def test_reset_mints_a_new_session_id():
    before = identity.session_id()
    assert before, "debería haber una sesión abierta (se abre sola en el primer uso)"
    info = observer.rotate_session("reset")
    assert info.get("session_id"), "la rotación tiene que devolver la sesión nueva"
    assert info["session_id"] != before, "el id TIENE que cambiar: es lo que hace que el borrón signifique algo"
    assert identity.session_id() == info["session_id"], "y ser la sesión en curso a partir de ahora"


def test_the_public_shape_is_session_id_not_the_internal_id():
    """Quien llama a esto (la respuesta del reset, el evento RESET que lee el frontend) habla `session_id`.
    `begin_session` devuelve la clave interna `id` — devolverla tal cual dejaba el campo vacío en el evento."""
    info = observer.rotate_session("reset")
    assert "session_id" in info and "id" not in info


def test_observability_starts_from_zero():
    observer.emit("test", "viejo", text="un evento de la sesión anterior")
    observer.emit("test", "viejo2", text="otro")
    assert len(observer._events) >= 2
    observer.rotate_session("reset")
    # Solo puede quedar lo que la PROPIA sesión nueva ha emitido al nacer (su session/start), nunca lo de antes.
    assert not any((e.get("label") or "").startswith("viejo") for e in observer._events), \
        "un evento de la sesión anterior sobreviviendo al reset es exactamente lo que se venía a arreglar"
    assert observer._seq["n"] <= 1, "el contador de secuencia empieza de nuevo"


def test_the_event_ring_carries_the_new_session_id_afterwards():
    """El detalle que lo motivó todo: no basta con vaciar; lo que se emita DESPUÉS tiene que llevar el id nuevo."""
    info = observer.rotate_session("reset")
    ev = observer.emit("test", "nuevo", text="primer evento de la sesión nueva")
    assert ev.get("sid") == info["session_id"]


def test_dedup_state_cannot_swallow_the_first_event_of_the_new_session():
    """`_dedup` colapsa ráfagas por (kind,label). Con entradas rancias, el primer evento de una sesión nueva podía
    colapsarse contra uno de la anterior y NO aparecer — la sesión arrancaría en blanco DE MÁS."""
    observer.emit("test", "repetido", text="uno")
    observer.rotate_session("reset")
    assert observer._dedup == {}


def test_traces_are_numbered_from_one_again():
    """Una sesión que empieza en blanco no puede abrir en «T34»: eso le dice al operador que está mirando la
    continuación de algo."""
    trace.begin("una frase de la sesión vieja")
    trace.begin("otra")
    observer.rotate_session("reset")
    tid = trace.begin("primera frase de la sesión nueva")
    assert tid.startswith("T1·"), f"debería reiniciar la numeración, y dio {tid}"


def test_the_per_session_file_follows_the_new_session():
    """La ruta del fichero por sesión está memoizada. Sin invalidarla, los eventos de la sesión nueva se escribirían
    en el fichero de la que acaba de cerrarse."""
    old = observer.session_info()["file"]
    info = observer.rotate_session("reset")
    new = observer.session_info()["file"]
    assert new != old
    assert info["session_id"] in new


def test_a_plain_reconnect_is_still_not_a_new_session():
    """Contrapeso: sin `force`, `begin_session` reutiliza la sesión abierta. Si esto se rompiera, cada bache de red
    partiría la sesión en dos y falsearía todo el análisis de duración."""
    sid = identity.session_id()
    again = identity.begin_session(source="frontend")
    assert again["id"] == sid


def test_the_log_is_cleared_even_if_closing_the_old_session_fails(monkeypatch):
    """Un reset a medias es malo; un reset que revienta es peor: el operador se queda sin poder resetear. Si cerrar
    la sesión vieja falla, se sigue: se limpia el log y se abre la nueva igualmente."""
    def boom(*a, **k):
        raise RuntimeError("simulado")

    observer.emit("test", "algo", text="x")
    monkeypatch.setattr(identity, "end_session", boom)
    info = observer.rotate_session("reset")
    assert all((e.get("label") or "") != "algo" for e in observer._events), "el log se limpia igual"
    assert info.get("session_id"), "y la sesión nueva se abre igual"


def test_rotation_returns_empty_instead_of_raising_if_the_new_session_cannot_open(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulado")

    observer.emit("test", "algo", text="x")
    monkeypatch.setattr(identity, "begin_session", boom)
    info = observer.rotate_session("reset")
    assert info == {}                        # no hay sesión nueva que anunciar…
    assert all((e.get("label") or "") != "algo" for e in observer._events)   # …pero el borrón SÍ se hizo

"""With a LIVE errand, a turn that is not an errand cannot open another one (2026-08-24).

Operator rule: *“runs have to be linear… if there is a process with a title, a task, and a purpose, you can
no longer allow several at once… when a state has only one process already running and a new message comes
in, you have to decide whether it is a new request or is associated with the previous one, and I do not
think that is so complicated”*.

The evidence that prompted it, taken from the studio’s durable log — ONE guitar search:

    16:14:30  web       «Busca en marketplaces de segunda mano … una guitarra acústica…»   ← el encargo
    16:15:48  research  «¿Alguna novedad ya?»                                              ← un worker
    16:16:20  research  «Perfecto, dale. ¿Tienes algo ya?»                                 ← otro worker

Four cards on screen for one errand. `find_duplicate` lets them through **for good reason**: its question is
“is this a reformulation of the same errand?” and the containment between “any news?” and “search for a
guitar” is 0. The missing question is a different one —“is this even an errand?”— and no similarity measure
answers it. Nor does a list of phrases: the ways of asking how something is going never run out, and that
list is precisely the wiring this house has been paying for since V2-151. A MODEL decides it, as with the
conversational health criterion from V2-075 and for the same reason.

An attempt to fix it by prompt (`99f05d9`, the description of `escalate_to_slowbrain`) was measured the same
day and was NOT enough: from 3/1/4 workers per case it went to 2/2/2/1 — better in the worst case, and still
two where there should be one. That is why this is mechanism.
"""
import pytest

from nucleo import dispatch


def _judge(answer):
    """Replace the model call with its RAW response: what is tested is how it is read, not the model."""
    def _fake(task, system, user, **kw):
        _fake.seen = {"system": system, "user": user, "kw": kw}
        return answer
    _fake.seen = {}
    return _fake


LIVE = [("t1", "Busca en marketplaces de segunda mano una guitarra acústica para principiante"),
        ("t2", "Busca vuelos directos a Roma para un fin de semana")]


def test_una_pregunta_de_seguimiento_va_al_encargo_vivo(monkeypatch):
    """The measured case: “Any news yet?” opened its own research worker."""
    import nucleo.memllm as memllm
    monkeypatch.setattr(memllm, "chat_sync", _judge('{"about": 1}'))
    assert dispatch.about_a_live_errand("¿Alguna novedad ya?", LIVE) == "t1"


def test_un_encargo_DISTINTO_sigue_abriendo_el_suyo(monkeypatch):
    """The counterbalance, without which this would be worse than the defect: searching for a guitar and
    searching for a camera are two errands, and swallowing the second would leave the operator without their
    request and with no way to see it."""
    import nucleo.memllm as memllm
    monkeypatch.setattr(memllm, "chat_sync", _judge('{"about": 0}'))
    assert dispatch.about_a_live_errand("Ahora búscame una cámara réflex", LIVE) == ""


def test_SIN_nada_vivo_no_se_le_pregunta_a_nadie(monkeypatch):
    """What makes it cheap: the first errand in a conversation—the common case—pays for no call."""
    import nucleo.memllm as memllm
    called = []
    monkeypatch.setattr(memllm, "chat_sync", lambda *a, **k: called.append(1) or '{"about": 1}')
    assert dispatch.about_a_live_errand("Busca una guitarra", []) == ""
    assert not called, "sin encargos vivos no hay nada que decidir"


@pytest.mark.parametrize("raw", ["", None, "no sé", "{}", '{"about": "uno"}', "texto suelto"])
def test_lo_ILEGIBLE_deja_pasar_el_encargo(monkeypatch, raw):
    """FAIL-OPEN, and direction is the decision. A model that does not answer cannot swallow a request:
    the operator whose errand disappears has no way to see it, while an extra worker IS VISIBLE on screen—
    which is exactly how this defect was found."""
    import nucleo.memllm as memllm
    monkeypatch.setattr(memllm, "chat_sync", _judge(raw))
    assert dispatch.about_a_live_errand("¿cómo va?", LIVE) == ""


def test_una_excepcion_tampoco_traga_el_encargo(monkeypatch):
    import nucleo.memllm as memllm
    def _boom(*a, **k):
        raise RuntimeError("sin red")
    monkeypatch.setattr(memllm, "chat_sync", _boom)
    assert dispatch.about_a_live_errand("¿cómo va?", LIVE) == ""


def test_un_numero_FUERA_DE_RANGO_no_se_redondea_al_vecino(monkeypatch):
    """A number that nobody offered means the model did not answer the question. Choosing the closest one
    would tie the operator’s request to an errand chosen at random."""
    import nucleo.memllm as memllm
    for bad in ('{"about": 9}', '{"about": 3}'):
        monkeypatch.setattr(memllm, "chat_sync", _judge(bad))
        assert dispatch.about_a_live_errand("¿cómo va?", LIVE) == ""


def test_el_menu_que_ve_el_modelo_lleva_los_encargos_VIVOS(monkeypatch):
    """Without the objectives in front of it, the question cannot be answered: it must be possible to say
    WHICH ONE it concerns."""
    import nucleo.memllm as memllm
    j = _judge('{"about": 2}')
    monkeypatch.setattr(memllm, "chat_sync", j)
    assert dispatch.about_a_live_errand("¿y el de Roma?", LIVE) == "t2"
    assert "guitarra" in j.seen["user"] and "Roma" in j.seen["user"]
    assert "¿y el de Roma?" in j.seen["user"]


def test_es_BARATO_por_construccion(monkeypatch):
    """It runs before a worker the operator is waiting for: neither a large token budget nor temperature."""
    import nucleo.memllm as memllm
    j = _judge('{"about": 0}')
    monkeypatch.setattr(memllm, "chat_sync", j)
    dispatch.about_a_live_errand("algo", LIVE)
    assert j.seen["kw"]["max_tokens"] <= 64
    assert j.seen["kw"]["temperature"] == 0.0
    assert j.seen["kw"]["timeout"] <= 15.0


def test_esta_CABLEADO_despues_del_dedup_directo():
    """The wiring guard: the two tests above would pass with the call DELETED from `run_listener`.

    This is the lesson of V2-199—a test that does not traverse the real path only proves that the code
    compiles—applied in advance rather than after a wasted round. And ORDER matters: containment is free and
    the model costs a call, so asking the model first would mean paying for what is already known."""
    import inspect
    # Inspect CODE lines, not the entire source. The first version of this guard searched for the name and
    # passed with the call DELETED, because the comment above mentions it: a presence guard certified exactly
    # the failure it is meant to prevent. The teardown caught it, not the reading.
    src = "\n".join(l for l in inspect.getsource(dispatch.run_listener).splitlines()
                    if not l.strip().startswith("#"))
    assert "to_thread(about_a_live_errand" in src, (
        "la decisión no está enchufada al único punto por el que pasan todas las escaladas")
    # V2-507: the cheap check is now called `dedup_scan(` (it returns a verdict + evidence). The guard follows
    # the ORDER, which is what it protects, not the name it used to have.
    assert src.index("dedup_scan(") < src.index("to_thread(about_a_live_errand"), (
        "el dedup barato va primero; el modelo solo para lo que aquél no puede ver")
    assert "if _live:" in src, "sin encargos vivos no puede llamarse al modelo"


def test_las_DOS_mitades_del_dedup_se_distinguen_en_observabilidad():
    """Counting them together hides which of the two fails—and the next measurement is precisely that one."""
    import inspect
    from nucleo import dedup as _dedup
    src = inspect.getsource(dispatch.run_listener)
    assert '"by": _dup_by' in src
    assert '"model"' in src
    # V2-507: `"containment"` is now set by whoever MEASURES it (`dedup.scan`), not by the caller that assumed
    # it — there, a widget hit was recorded as containment even though that path never computes it.
    assert '"containment"' in inspect.getsource(_dedup.scan)
    assert '"widget"' in inspect.getsource(_dedup.scan)

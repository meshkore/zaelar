"""Con un encargo VIVO, un turno que no es un encargo no puede abrir otro (2026-08-24).

Norma del operador: *«las ejecuciones tienen que ser lineales… si hay un proceso con un título, una tarea y
un propósito, ya no puedes permitir que haya varios a la vez… cuando un estado solo tiene un proceso ya en
marcha y entra un nuevo mensaje, hay que decidir si es una petición nueva o va asociado al anterior, y eso
no creo que sea tan complicado»*.

La evidencia que lo motivó, sacada del registro durable del plató — UNA búsqueda de guitarra:

    16:14:30  web       «Busca en marketplaces de segunda mano … una guitarra acústica…»   ← el encargo
    16:15:48  research  «¿Alguna novedad ya?»                                              ← un worker
    16:16:20  research  «Perfecto, dale. ¿Tienes algo ya?»                                 ← otro worker

Cuatro tarjetas en pantalla para un encargo. `find_duplicate` los deja pasar **con razón**: su pregunta es
«¿es una reformulación del mismo encargo?» y la contención entre «¿alguna novedad?» y «busca una guitarra»
es 0. La pregunta que faltaba es otra —«¿es esto un encargo siquiera?»— y no la contesta ninguna vara de
parecido. Tampoco una lista de frases: las maneras de preguntar cómo va algo no se acaban nunca, y esa lista
es justo el cableado que esta casa lleva pagando desde V2-151. La decide un MODELO, como el criterio de
salud conversacional de V2-075 y por el mismo motivo.

Un intento de arreglarlo por prompt (`99f05d9`, la descripción de `escalate_to_slowbrain`) se midió el mismo
día y NO bastó: de 3/1/4 workers por caso se pasó a 2/2/2/1 — mejor en el peor caso, y todavía dos donde
debe haber uno. Por eso esto es mecanismo.
"""
import pytest

from nucleo import dispatch


def _judge(answer):
    """Sustituye la llamada al modelo por su respuesta CRUDA: lo que se prueba es cómo se lee, no el modelo."""
    def _fake(task, system, user, **kw):
        _fake.seen = {"system": system, "user": user, "kw": kw}
        return answer
    _fake.seen = {}
    return _fake


LIVE = [("t1", "Busca en marketplaces de segunda mano una guitarra acústica para principiante"),
        ("t2", "Busca vuelos directos a Roma para un fin de semana")]


def test_una_pregunta_de_seguimiento_va_al_encargo_vivo(monkeypatch):
    """El caso medido: «¿Alguna novedad ya?» abría un worker de research propio."""
    import nucleo.memllm as memllm
    monkeypatch.setattr(memllm, "chat_sync", _judge('{"about": 1}'))
    assert dispatch.about_a_live_errand("¿Alguna novedad ya?", LIVE) == "t1"


def test_un_encargo_DISTINTO_sigue_abriendo_el_suyo(monkeypatch):
    """El contrapeso, y sin él esto sería peor que el defecto: buscar una guitarra y buscar una cámara son
    dos encargos, y tragarse el segundo dejaría al operador sin su petición y sin forma de verlo."""
    import nucleo.memllm as memllm
    monkeypatch.setattr(memllm, "chat_sync", _judge('{"about": 0}'))
    assert dispatch.about_a_live_errand("Ahora búscame una cámara réflex", LIVE) == ""


def test_SIN_nada_vivo_no_se_le_pregunta_a_nadie(monkeypatch):
    """Lo que lo hace barato: el primer encargo de una conversación —el caso común— no paga ninguna llamada."""
    import nucleo.memllm as memllm
    called = []
    monkeypatch.setattr(memllm, "chat_sync", lambda *a, **k: called.append(1) or '{"about": 1}')
    assert dispatch.about_a_live_errand("Busca una guitarra", []) == ""
    assert not called, "sin encargos vivos no hay nada que decidir"


@pytest.mark.parametrize("raw", ["", None, "no sé", "{}", '{"about": "uno"}', "texto suelto"])
def test_lo_ILEGIBLE_deja_pasar_el_encargo(monkeypatch, raw):
    """FAIL-OPEN, y la dirección es la decisión. Un modelo que no contesta no puede tragarse una petición:
    el operador cuyo encargo desaparece no tiene forma de verlo, mientras que un worker de más se VE en
    pantalla — que es exactamente cómo se encontró este defecto."""
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
    """Un número que nadie ofreció es un modelo que no contestó a la pregunta. Coger el más cercano ataría
    la petición del operador a un encargo elegido al azar."""
    import nucleo.memllm as memllm
    for bad in ('{"about": 9}', '{"about": 3}'):
        monkeypatch.setattr(memllm, "chat_sync", _judge(bad))
        assert dispatch.about_a_live_errand("¿cómo va?", LIVE) == ""


def test_el_menu_que_ve_el_modelo_lleva_los_encargos_VIVOS(monkeypatch):
    """Sin los objetivos delante, la pregunta no se puede contestar: hay que poder decir SOBRE CUÁL."""
    import nucleo.memllm as memllm
    j = _judge('{"about": 2}')
    monkeypatch.setattr(memllm, "chat_sync", j)
    assert dispatch.about_a_live_errand("¿y el de Roma?", LIVE) == "t2"
    assert "guitarra" in j.seen["user"] and "Roma" in j.seen["user"]
    assert "¿y el de Roma?" in j.seen["user"]


def test_es_BARATO_por_construccion(monkeypatch):
    """Va delante de un worker que el operador está esperando: ni presupuesto largo ni temperatura."""
    import nucleo.memllm as memllm
    j = _judge('{"about": 0}')
    monkeypatch.setattr(memllm, "chat_sync", j)
    dispatch.about_a_live_errand("algo", LIVE)
    assert j.seen["kw"]["max_tokens"] <= 64
    assert j.seen["kw"]["temperature"] == 0.0
    assert j.seen["kw"]["timeout"] <= 15.0


def test_esta_CABLEADO_despues_del_dedup_directo():
    """La guarda de cableado: los dos tests de arriba pasarían con la llamada BORRADA de `run_listener`.

    Es la lección de V2-199 —un test que no recorre el camino real prueba que el código compila— aplicada
    por adelantado en vez de por una ronda perdida. Y el ORDEN importa: la contención es gratis y el modelo
    cuesta una llamada, así que preguntar primero al modelo sería pagar por lo que ya se sabe."""
    import inspect
    # Se miran las líneas de CÓDIGO, no el fuente entero. La primera versión de este guarda buscaba el nombre
    # y pasaba con la llamada BORRADA, porque el comentario que hay encima lo nombra: un guarda de presencia
    # certificaba justo el fallo que existe para evitar. Lo cazó el desarme, no la lectura.
    src = "\n".join(l for l in inspect.getsource(dispatch.run_listener).splitlines()
                    if not l.strip().startswith("#"))
    assert "to_thread(about_a_live_errand" in src, (
        "la decisión no está enchufada al único punto por el que pasan todas las escaladas")
    # V2-507: el barato se llama ahora `dedup_scan(` (devuelve veredicto + evidencia). El guarda sigue al
    # ORDEN, que es lo que protege, no al nombre que tenía.
    assert src.index("dedup_scan(") < src.index("to_thread(about_a_live_errand"), (
        "el dedup barato va primero; el modelo solo para lo que aquél no puede ver")
    assert "if _live:" in src, "sin encargos vivos no puede llamarse al modelo"


def test_las_DOS_mitades_del_dedup_se_distinguen_en_observabilidad():
    """Contarlas juntas esconde cuál de las dos falla — y la próxima medida es justo esa."""
    import inspect
    from nucleo import dedup as _dedup
    src = inspect.getsource(dispatch.run_listener)
    assert '"by": _dup_by' in src
    assert '"model"' in src
    # V2-507: `"containment"` lo pone ahora quien lo MIDE (`dedup.scan`), no el llamante que lo suponía —
    # allí un acierto por widget se archivaba como una contención que ese camino nunca calcula.
    assert '"containment"' in inspect.getsource(_dedup.scan)
    assert '"widget"' in inspect.getsource(_dedup.scan)

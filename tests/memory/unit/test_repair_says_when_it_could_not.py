"""V2-497 — la reparación de vectores DICE cuando no pudo hacer su trabajo.

`repair_embeddings` devolvía `0` para dos situaciones opuestas: «no había nada que reparar» (sano) y «había 45
píldoras esperando y el backend rechazó todas» (roto). Nada más las distinguía: el salto por fila era un
`continue` pelado y `hygiene()` informa de `embed_pending` pero solo su porcentaje de escritura heurística llega
a alertar. Salía la lectura tranquilizadora.

MEDIDO el 2026-08-29 sobre una COPIA de la memoria del operador: 25 vectores de espacio ajeno retirados, 20
filas ya pendientes, 45 esperando en total, `repair_embeddings` → **0**, y la única línea del log era la del
purgado anunciando su éxito. Causa: `/api/embed` contestando `server busy` mientras un modelo de 40 GB ocupaba
la GPU.

Los casos de conducta entran por `repair_embeddings`, NUNCA llamando a `_report_repair_backlog` a mano: un test
que no recorre el camino real prueba que el código compila (V2-199), y aquí lo que se rompe con facilidad es
justo la LLAMADA.
"""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import rem as memrem
from memory import writer as memwriter
from voice import health_state


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    # El backend se DECLARA, nunca se hereda del ambiente (V2-484): con Ollama vivo el resolutor conserva el
    # espacio y estos casos medirían otra cosa.
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture(autouse=True)
def _clean_health():
    health_state.clear("memory")
    yield
    health_state.clear("memory")


def _esperando(n: int) -> list[int]:
    """`n` píldoras válidas SIN vector — el estado que la reparación existe para deshacer."""
    ids = [memwriter.insert_memory(f"hecho durable número {i}", level="long", kind="fact") for i in range(n)]
    db = memdb.get_db()
    for i in ids:
        db.execute("DELETE FROM vec_memories WHERE memory_id=?", (i,))
    return ids


def _avisos(monkeypatch) -> list[str]:
    """Se captura el logger del MÓDULO y no `caplog`: aquí se escribe con loguru, que no propaga al `logging`
    de la stdlib — un caso montado sobre caplog sale verde sin haber leído ni un aviso (comprobado: los tres
    primeros de este fichero pasaron así antes de mirar el stderr)."""
    dicho: list[str] = []
    monkeypatch.setattr(memrem.logger, "warning", lambda m, *a, **k: dicho.append(str(m)))
    return dicho


def _degradado(monkeypatch, *, fallan: int = 10_000):
    """Backend que contesta un vector pero DECLARA que cayó al hash de emergencia, como un Ollama saturado.

    Devuelve la lista de llamadas para poder medir que la pasada se rinde en vez de repetir la misma llamada
    fallida una vez por fila que espera.
    """
    llamadas: list[str] = []
    real = mememb.embed

    def _embed(text):
        llamadas.append(text)
        vec = real(text)
        mememb.last_degraded = len(llamadas) <= fallan
        return vec

    monkeypatch.setattr(mememb, "embed", _embed)
    return llamadas


def test_una_reparacion_que_no_pudo_lo_DICE(fresh_db, monkeypatch):
    _esperando(5)
    dicho = _avisos(monkeypatch)
    _degradado(monkeypatch)
    assert memrem.repair_embeddings(limit=100) == 0
    aviso = " ".join(dicho)
    assert "sin vector" in aviso.lower(), aviso
    assert "5" in aviso, aviso                                  # cuántas siguen esperando, no un genérico
    salud = health_state.get("memory")
    assert salud and salud["kind"] == "degraded", salud
    assert "5" in salud["text"], salud


def test_dice_la_CAUSA_porque_las_dos_piden_acciones_distintas(fresh_db, monkeypatch):
    # Un backend caído se arregla liberando la GPU; una firma discordante, reindexando. Un aviso que no las
    # separa manda el diagnóstico siguiente a la puerta equivocada (la lección de V2-485).
    _esperando(3)
    dicho = _avisos(monkeypatch)
    _degradado(monkeypatch)
    memrem.repair_embeddings(limit=100)
    aviso = " ".join(dicho).lower()
    assert "backend" in aviso and "hash de emergencia" in aviso, aviso


def test_una_pasada_SANA_no_dice_NADA(fresh_db, monkeypatch):
    # Sensibilidad: un aviso que sale también cuando todo va bien deja de leerse.
    _esperando(4)
    dicho = _avisos(monkeypatch)
    assert memrem.repair_embeddings(limit=100) == 4
    assert not [m for m in dicho if "sin vector" in m], dicho
    assert health_state.get("memory") is None


def test_sin_NADA_que_reparar_no_dice_nada(fresh_db, monkeypatch):
    dicho = _avisos(monkeypatch)
    assert memrem.repair_embeddings(limit=100) == 0
    assert not [m for m in dicho if "sin vector" in m], dicho
    assert health_state.get("memory") is None


def test_una_pasada_PARCIAL_reporta_solo_lo_que_QUEDA(fresh_db, monkeypatch):
    _esperando(6)
    dicho = _avisos(monkeypatch)
    # las 2 primeras se curan; de la 3ª en adelante el backend se cae y la racha corta la pasada
    llamadas: list[str] = []
    real_embed = mememb.embed

    def _tras_dos(text):
        llamadas.append(text)
        vec = real_embed(text)
        mememb.last_degraded = len(llamadas) > 2
        return vec

    monkeypatch.setattr(mememb, "embed", _tras_dos)
    assert memrem.repair_embeddings(limit=100) == 2
    assert "4 de 6" in " ".join(dicho), dicho


def test_se_RINDE_tras_la_racha_en_vez_de_repetir_la_misma_llamada_fallida(fresh_db, monkeypatch):
    # Un backend degradado es una condición del PROCESO, no un accidente por fila: medido contra un Ollama
    # saturado, 40 sondas en 30 s dieron 40 rechazos y cero aciertos. Seguir es repetir la misma llamada.
    _esperando(30)
    llamadas = _degradado(monkeypatch)
    memrem.repair_embeddings(limit=100)
    assert len(llamadas) == memrem._DEGRADED_STREAK_STOP, len(llamadas)


def test_un_fallo_AISLADO_no_termina_la_pasada(fresh_db, monkeypatch):
    # La otra dirección, y es la que impide que la racha sea 1: el resolutor deja a un backend saturado
    # re-sondeando en la llamada siguiente, así que un bache suelto no puede costar la pasada entera.
    _esperando(5)
    llamadas: list[str] = []
    real = mememb.embed

    def _un_bache(text):
        llamadas.append(text)
        vec = real(text)
        mememb.last_degraded = len(llamadas) == 2      # solo la segunda fila
        return vec

    monkeypatch.setattr(mememb, "embed", _un_bache)
    assert memrem.repair_embeddings(limit=100) == 4     # las otras cuatro SÍ se curan


def test_una_pasada_sana_NO_borra_el_aviso_de_OTRO(fresh_db):
    # La clave `memory` la comparten el descuadre de espacio vectorial y los embeddings degradados (V2-311):
    # limpiarla al salir bien borraría un aviso ajeno. Envejece con su TTL.
    health_state.record("memory", "degraded", "aviso de otra pieza")
    _esperando(2)
    assert memrem.repair_embeddings(limit=100) == 2
    assert health_state.get("memory")["text"] == "aviso de otra pieza"

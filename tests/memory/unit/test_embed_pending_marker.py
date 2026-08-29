"""`meta.embed_pending` vale el MOTIVO, nunca un 1 — y quien lo consulte tiene que preguntarlo por ausencia.

Nadie probaba la FORMA de este marcador (2026-08-24: cero menciones en `tests/`), y el comentario que lo
describe en `writer.py` decía `meta.embed_pending=1` mientras `_mark_embed_pending` escribe la cadena del
motivo. La mentira costó un diagnóstico ese mismo día: consulté las bases del plató con
`embed_pending = 1`, salió **0 pendientes** sobre una base que tenía una fila dañada, y estuve a punto de
informar de «limpio». Lo cazó ir a mirar con qué predicado consulta el producto (`rem.py`, `IS NOT NULL`).

La clase de fallo es la peor de las baratas: **una consulta que no puede encontrar nada informa igual que una
base sana**. No falla, no avisa, y su respuesta es tranquilizadora justo cuando hay daño.

Así que aquí se clava lo que un consumidor puede dar por hecho:
  · el marcador guarda el MOTIVO y no un booleano — si alguien lo «simplifica» a 1, esto se pone rojo;
  · un `= 1` es estructuralmente ciego, y se comprueba EJECUTÁNDOLO contra una fila marcada de verdad;
  · el motivo es legible, porque «esta píldora no tiene vector» y «no lo tiene porque el índice está sellado
    con otro modelo» llevan a acciones distintas.

No se prueba el comentario (no se puede). Se prueba el contrato que el comentario describía mal.
"""
from __future__ import annotations

import json

import pytest

from memory import db as memdb
from memory import writer as memwriter


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _marca(mid: int) -> object:
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    return json.loads(row["meta"] or "{}").get("embed_pending")


def test_el_marcador_guarda_el_MOTIVO_y_no_un_booleano(fresh_db):
    mid = memwriter.insert_memory("un hecho sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "sig_mismatch")

    v = _marca(mid)
    assert v == "sig_mismatch"
    assert not isinstance(v, bool) and v != 1, (
        "si el marcador pasa a ser 1/True, toda consulta `IS NOT NULL` sigue funcionando pero se pierde el "
        "MOTIVO — y «no tiene vector» y «el índice está sellado con otro modelo» piden cosas distintas")


def test_una_consulta_por_IGUAL_A_1_es_CIEGA_y_se_demuestra_corriendola(fresh_db):
    """El error real, reproducido: sobre una base CON daño, `= 1` cuenta cero y `IS NOT NULL` cuenta uno."""
    mid = memwriter.insert_memory("otra sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "degraded")

    ciega = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND COALESCE(json_extract(meta,'$.embed_pending'),0)=1")["c"]
    buena = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND json_extract(meta,'$.embed_pending') IS NOT NULL")["c"]

    assert buena == 1, "la fila dañada existe"
    assert ciega == 0, (
        "esta es la trampa entera: la consulta equivocada no falla, contesta CERO — «todo limpio» sobre una "
        "base con daño. Si algún día devolviera 1, este test sobra y el marcador cambió de forma")


def test_los_DOS_motivos_que_escribe_el_writer_son_legibles(fresh_db):
    """Los motivos son los que el propio `insert_memory` produce; si nace un tercero, que se declare aquí."""
    for razon in ("sig_mismatch", "degraded"):
        mid = memwriter.insert_memory(f"pildora {razon}", weight=0.5)
        memwriter._mark_embed_pending(memdb.get_db(), mid, razon)
        assert _marca(mid) == razon


def test_marcar_NUNCA_lanza_aunque_la_fila_no_exista(fresh_db):
    """Corre dentro de una escritura ya hecha: reventar aquí perdería la píldora, que sí se guardó bien."""
    memwriter._mark_embed_pending(memdb.get_db(), 999_999, "sig_mismatch")   # no debe lanzar


# ── V2-484 · el permiso caducaba con el BACKEND, no con el reloj ────────────────────────────────────────────
#
# Los 15 vectores de otro espacio del índice del operador (V2-482) entraron por aquí, y la carrera se
# reprodujo entera: el veredicto de `space_ok()` se cacheaba 60 s SOLO por tiempo, así que un backend que caía
# a `hash` dentro de esa ventana escribía con el permiso de cuando Ollama estaba vivo. Sin marcador y sin
# error: la fila queda indistinguible de una sana.

@pytest.fixture
def sellado_gemma(tmp_path, monkeypatch):
    """Un índice que declara un espacio REAL. El backend de los tests es `hash` → cualquier vector suyo es
    ajeno, así que el guarda TIENE que refusar salvo que alguien le dé un permiso caducado."""
    from memory import reembed as memreembed
    (tmp_path / "zaelar.db.embedsig").write_text("ollama:embeddinggemma:768", encoding="utf-8")
    memreembed._SPACE_CACHE = (0.0, True, None)
    # La PRECONDICIÓN se declara, no se hereda: si la ruta de la firma resolviera a otro sitio, estos casos
    # medirían el `.embedsig` de otra base y su verde no valdría nada.
    assert memreembed.stored_signature() == "ollama:embeddinggemma:768"
    yield
    memreembed._SPACE_CACHE = (0.0, True, None)


def _con_ollama_vivo():
    """Calienta el caché en el instante en que la firma SÍ casaba (Ollama contestando embeddinggemma).

    Restaura A MANO y NO con `monkeypatch.undo()`: ese deshace todo lo que la función lleva puesto en ese
    momento, **incluido el `ZAELAR_DB` de `fresh_db`**. Con él revertido, `_sig_path()` deja de apuntar a la
    base del test y el guarda pasa a leer el `.embedsig` de la memoria REAL del operador — así que estos casos
    salían verdes en solitario por leer una firma ajena y rojos en la suite entera según qué ruta tuvieran
    delante. Un verde prestado, otra vez."""
    from memory import embeddings as mememb
    from memory import reembed as memreembed
    previo = (mememb.active_backend, mememb._active_model_name, mememb._backend)
    mememb.active_backend = lambda: "ollama"
    mememb._active_model_name = lambda: "embeddinggemma"
    mememb._backend = "ollama"
    try:
        assert memreembed.space_ok() is True
    finally:
        mememb.active_backend, mememb._active_model_name, mememb._backend = previo


def test_el_permiso_NO_sobrevive_a_una_caida_del_backend(fresh_db, sellado_gemma, monkeypatch):
    from memory import embeddings as mememb
    from memory import reembed as memreembed
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")          # segundos después, dentro del TTL
    assert memreembed.space_ok() is False


def test_un_vector_de_otro_espacio_NO_se_escribe_con_el_permiso_de_antes(fresh_db, sellado_gemma, monkeypatch):
    """La carrera COMPLETA por el camino real de escritura — es la que dejó 15 filas dañadas y mudas."""
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")
    mid = memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    fila = memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,))
    assert fila is None                                      # sin vector: mejor sin él que de otro espacio
    assert _marca(mid) == "sig_mismatch"                      # y CONTABLE, que es lo que faltaba


def test_el_guarda_decide_DESPUES_de_saber_en_que_espacio_salio_el_vector(fresh_db, sellado_gemma, monkeypatch):
    """El vuelco DENTRO de la misma llamada: la resolución del backend ocurre dentro de `_emb.embed()`, o sea
    DESPUÉS de la primera comprobación. Sin la segunda, ese vector entra con el permiso ya concedido.

    Va CON SLOT a propósito, y esto costó encontrarlo: sin slot, `insert_memory` consulta antes
    `_semantic_dedup_on()`, que resuelve el backend por su cuenta — así que el vuelco ocurre ANTES del primer
    guarda y ése ya lo caza. Con slot se salta ese paso y el backend sigue siendo el bueno cuando el guarda de
    entrada mira. Medido en los dos sentidos: con la segunda comprobación el vector se refusa; sin ella se
    escribe, sin marcador. Un caso sin slot habría salido verde con el arreglo DESARMADO."""
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "ollama")        # el guarda de ENTRADA aún ve el espacio bueno

    def _embed_que_cae(_t):
        mememb._backend = "hash"                             # Ollama ocupado Y fastembed sin cargar
        return mememb._l2_normalize(mememb._fit_dim(mememb._hash_embed(_t, 768), 768))

    monkeypatch.setattr(mememb, "embed", _embed_que_cae)
    monkeypatch.setattr(mememb, "last_degraded", False)      # hash CONFIGURADO no se declara degradado
    mid = memwriter.insert_memory("Le gusta la guitarra.", level="long", kind="pref", slot="operator.tastes")
    assert memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,)) is None
    assert _marca(mid) == "sig_mismatch"


def test_con_el_espacio_ESTABLE_el_camino_sano_no_cambia(fresh_db, monkeypatch):
    """La otra mitad: sin firma sellada (BD nueva) se sigue escribiendo el vector como siempre. Un guarda que
    también parase esto no sería más seguro, sería una base sin canal semántico."""
    mid = memwriter.insert_memory("Vive en Madrid.", level="long", kind="fact")
    assert memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,)) is not None
    assert _marca(mid) is None


# ── V2-485 · el nodo-concepto escribía su vector SIN ningún guarda ──────────────────────────────────────────
#
# Ni carrera ni permiso rancio: `_get_or_create_concept` insertaba en `vec_memories` sin mirar la firma ni la
# degradación. Por ahí entraron los 9 vectores fastembed (384 rellenados a 768) del índice del operador, todos
# nodos-concepto. El nodo tiene que seguir naciendo — es un hub del grafo — y lo que se difiere es su vector.

def _concepto(nombre: str):
    return memdb.get_db().query_one(
        "SELECT id FROM memories WHERE kind='concept' AND lower(text)=? LIMIT 1", (nombre,))


def test_un_concepto_NO_recibe_vector_de_otro_espacio(fresh_db, sellado_gemma, monkeypatch):
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")          # el índice dice gemma, el backend ya no
    memwriter.insert_memory("Toca la guitarra.", level="long", kind="fact", concepts=["guitarra"])
    c = _concepto("guitarra")
    assert c is not None                                     # el HUB nace igual: sin él el grafo no cose
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is None
    assert _marca(c["id"]) == "sig_mismatch"                 # y queda CONTABLE para el sueño


def test_un_concepto_NO_recibe_vector_de_un_backend_caido_en_caliente(fresh_db, monkeypatch):
    """La otra mitad del gate: `last_degraded` también faltaba en este camino.

    La bandera se pone DENTRO de `embed_batch`, así que dejarla puesta de antemano no sirve — la propia
    llamada la recalcula. Se simula como ocurre de verdad: la caída se declara al producir el vector."""
    from memory import embeddings as mememb

    def _embed_que_se_cae(t):
        mememb.last_degraded = True                          # backend real caído en caliente → hash de emergencia
        return mememb._l2_normalize(mememb._fit_dim(mememb._hash_embed(t, 768), 768))

    monkeypatch.setattr(mememb, "embed", _embed_que_se_cae)
    memwriter.insert_memory("Le gusta el pádel.", level="long", kind="fact", concepts=["deporte"])
    c = _concepto("deporte")
    assert c is not None
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is None
    assert _marca(c["id"]) == "degraded"


def test_con_el_espacio_sano_el_concepto_SI_recibe_su_vector(fresh_db):
    """Sin esto, «no escribas vectores malos» se satisface no escribiendo ninguno — y un concepto sin vector
    no lo encuentra una consulta de categoría, que es para lo que existe el nodo."""
    memwriter.insert_memory("Le gusta el buceo.", level="long", kind="fact", concepts=["ocio"])
    c = _concepto("ocio")
    assert c is not None
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is not None
    assert _marca(c["id"]) is None

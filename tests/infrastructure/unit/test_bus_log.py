#
# test_log.py — log durable de eventos del bus en SQLite (V2-001, T35). Verifica persistencia real a
# disco (fichero temporal vía ZAELAR_DB), enganche como sink del bus, filtros y resiliencia.
#
# 2026-08-09: el sink pasó a ser ASÍNCRONO (encola + hilo escritor). El bus lo llama en el hilo que PUBLICA, que
# muchas veces es el de la voz, y un INSERT síncrono ahí era el motivo de que el log durable llevara desde V2-001
# apagado por defecto. Por eso los tests ahora DRENAN antes de leer: `_write` ya no promete haber escrito, promete
# no haber bloqueado.
# Ejecutar: .venv/bin/pytest tests/infrastructure/unit/test_bus_log.py
#
import asyncio
import importlib

import pytest

import bus as busmod


@pytest.fixture()
def log(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    from bus import log as logmod
    importlib.reload(logmod)   # re-lee ZAELAR_DB y resetea la conexión de módulo
    busmod.reset()
    yield logmod
    logmod.detach()
    logmod.close()
    busmod.reset()


def test_write_persists_and_reads_back(log):
    log._write({"topic": "brain.reply", "ts_ms": 1000.0, "payload": {"text": "hola"}})
    log._write({"topic": "widget.show", "ts_ms": 2000.0, "payload": {"id": "agenda"}})
    log.drain()
    assert log.count() == 2
    log.drain()
    rows = log.recent(10)
    assert rows[0]["topic"] == "widget.show"        # más nuevo primero
    assert rows[0]["payload"] == {"id": "agenda"}
    assert rows[1]["payload"] == {"text": "hola"}


def test_persists_across_connection_close(log, tmp_path):
    log._write({"topic": "memory.updated", "ts_ms": 1.0, "payload": {"n": 1}})
    log.close()                                     # simula reinicio: nueva conexión al MISMO fichero
    log.drain()
    assert log.count() == 1
    assert log.recent(1)[0]["payload"] == {"n": 1}


def test_attach_captures_bus_events(log):
    async def run():
        log.attach()
        await busmod.publish("memory.updated", {"id": 42})
        await busmod.publish("connector.msg", {"from": "wa"})
    asyncio.run(run())
    log.drain()
    assert log.count() == 2
    assert log.count("memory.updated") == 1


def test_topic_prefix_filter(log):
    log._write({"topic": "widget.show", "ts_ms": 1.0, "payload": 1})
    log._write({"topic": "widget.close", "ts_ms": 2.0, "payload": 2})
    log._write({"topic": "brain.reply", "ts_ms": 3.0, "payload": 3})
    log.drain()
    assert len(log.recent(10, topic="widget.*")) == 2
    assert len(log.recent(10, topic="brain.reply")) == 1


def test_non_serializable_payload_does_not_crash(log):
    class Weird:
        pass
    log._write({"topic": "x", "ts_ms": 1.0, "payload": Weird()})
    log.drain()
    assert log.count() == 1           # se guarda como str, no revienta
    assert log.recent(1)[0]["topic"] == "x"


def test_attach_is_idempotent(log):
    async def run():
        log.attach()
        log.attach()                  # segunda vez = no-op, no duplica el sink
        await busmod.publish("memory.updated", {})
    asyncio.run(run())
    log.drain()
    assert log.count() == 1


def test_the_sink_never_blocks_the_publisher(log):
    """El CONTRATO nuevo: `_write` encola y vuelve. Es lo que permite tener el log durable encendido sin que un
    INSERT por evento se interponga en el hilo de la voz (el motivo por el que estuvo apagado desde V2-001).

    2026-08-20: medía un UMBRAL ABSOLUTO (`< 200 ms`) y eso lo hacía rojo por la MÁQUINA y no por el código —
    exactamente lo que `test_suite_isolation.py` existe para evitar. Encolar 2000 eventos cuesta ~2 ms medidos
    aisladamente, así que el techo llevaba 100x de margen… y aun así saltó en 206 ms corriendo la suite entera,
    con todo en un proceso. El número no estaba mal elegido: la FORMA de la prueba estaba mal elegida.

    Ahora se mide la PROPIEDAD, que es relativa y por tanto inmune a la carga: encolar tiene que ser
    drásticamente más barato que la escritura que sustituye, y las dos sufren la misma máquina en el mismo
    momento. El techo absoluto se queda solo como red de seguridad, holgadísimo: si alguien devuelve el sink a
    síncrono, encolar y escribir pasan a ser la MISMA operación y el cociente se va a 1.
    """
    import time

    # 2026-08-21, SEGUNDA reincidencia: el cociente relativo arregló la dependencia del MODELO de máquina, pero no
    # la del INSTANTE. Con la suite entera en un proceso —esa noche pasó de 3.284 a 3.923 tests— una sola
    # preempción del planificador durante los ~2 ms de encolado basta para hundir el cociente, y el test se pone
    # rojo por el reloj y no por el código. Una medida de tiempo tomada UNA vez mide la máquina; tomada varias y
    # quedándose con la MEJOR, mide el camino. La propiedad sigue siendo inalcanzable para un sink síncrono: ahí
    # encolar y escribir son la MISMA operación, así que el cociente se va a 1 en las tres rondas.
    mejor, escritos, encolar = 0.0, 0, 0.0
    for _ in range(3):
        t0 = time.perf_counter()
        for i in range(2000):
            log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
        encolar = time.perf_counter() - t0
        t1 = time.perf_counter()
        log.drain(timeout=10.0)
        escribir = time.perf_counter() - t1
        escritos += 2000
        assert log.count() == escritos, "encolar rápido no vale de nada si los eventos no acaban en la tabla"
        mejor = max(mejor, (escribir / encolar) if encolar > 0 else float("inf"))
        if mejor >= 5:
            break
    # Medido en esta máquina: encolar ~2 ms, escribir ~116 ms (58x). Se exige 5x — deja un factor 10 de holgura.
    assert mejor >= 5, (
        f"la mejor de 3 rondas dio escribir/encolar = {mejor:.1f}x — encolar ya no es dramáticamente más barato "
        f"que escribir, así que `_write` está pagando el INSERT en el hilo que publica (que muchas veces es el "
        f"de la voz)")
    assert encolar < 2.0, f"encolar 2000 eventos tardó {encolar:.1f}s — eso no es «no bloquea» en ninguna máquina"


def test_retention_caps_the_table(log, monkeypatch):
    """La otra razón de que estuviera apagado: crecimiento sin límite. Ahora hay techo de filas y poda por edad."""
    monkeypatch.setattr(log, "_MAX_ROWS", 10)
    monkeypatch.setattr(log, "_RETENTION_DAYS", 0)      # aislar el techo de filas del corte por antigüedad
    for i in range(25):
        log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
    log.drain(timeout=5.0)
    log.prune()
    assert log.count() == 10, "el techo debe dejar exactamente las N más recientes"
    assert log.recent(1)[0]["payload"]["i"] == 24, "y las que quedan son las ÚLTIMAS, no las primeras"


def test_a_full_queue_drops_log_instead_of_slowing_the_caller(log, monkeypatch):
    """Bajo saturación se pierde LOG, nunca velocidad: la prioridad es la voz. Y el descarte se CUENTA, para que
    un hueco en los datos sea visible en vez de silencioso."""
    import queue as _q
    monkeypatch.setattr(log, "_q", _q.Queue(maxsize=2))
    log._dropped["n"] = 0
    for i in range(10):
        log._write({"topic": "x", "ts_ms": float(i), "payload": {"i": i}})
    assert log._dropped["n"] > 0
    assert log.stats()["dropped"] == log._dropped["n"]


def test_the_heartbeat_is_not_persisted(log):
    """El loop tiquea a ~1 Hz: persistir el latido serían ~140.000 filas al día de un evento SIN datos, que se
    comerían la retención y ahogarían lo que sí importa. Para la UI en vivo sigue llegando por SSE."""
    log._write({"topic": "loop.tick", "ts_ms": 1.0, "payload": {"n": 1}})
    log._write({"topic": "observer", "ts_ms": 2.0, "payload": {"kind": "pulse", "label": "tick"}})
    log._write({"topic": "observer", "ts_ms": 3.0, "payload": {"kind": "brain", "label": "decide"}})
    log.drain()
    assert log.count() == 1, "solo el evento con contenido real debe quedar"
    assert log.recent(1)[0]["payload"]["kind"] == "brain"

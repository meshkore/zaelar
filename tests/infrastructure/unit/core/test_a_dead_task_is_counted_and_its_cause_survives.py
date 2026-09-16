"""V2-713 T0 · Una tarea que murió CUENTA como fallo, y la causa que la mató llega con su nombre.

## Lo medido el 2026-09-16 sobre la base real del operador (solo lectura)

**R2 — el resumen decía cero.** `observability/flows.py` contaba `kind IN ('error','alert')` y nada más. Un
worker que muere cierra como `kind='task'`, `label='end'`, `ok=false` — y `ok` **no es columna** del bus, va
dentro del payload, que además es PLANO (`$.ok`, no `$.extra.ok`; la primera versión de esta consulta buscó
donde no era). Resultado sobre sus datos: **30 de 30 flujos con una tarea muerta reportaban `errors=0`**. No
«puede omitir el fallo»: todos.

Ampliar el `IN` habría sido el arreglo equivocado — mezclaría un worker muerto con una alerta de
infraestructura y el resumen seguiría sin decir cuál de las dos pasó. Son dos contadores.

**R4 — la causa se calculaba dos veces y se perdía una.** `providers.note_failure` sabía el `kind` y devolvía
solo el escalón de relevo; `claude_session.py` reconstruía la clasificación para decidir si avisaba:
`if nxt is not None or classify_failure(texto)`. Ahí hay un agujero: `broken` lo reconoce
`is_broken_request`, **no** `classify_failure`. Así que un `broken` **sin relevo** ponía el proveedor en
cooldown y **no emitía ningún chip** — el operador veía morir al worker sin una palabra de por qué, con la
causa perfectamente conocida una capa más arriba. En su base hay filas exactamente de esa forma:
`API Error: 400 [1210][Invalid API parameter…]`, `ok:false`, `status:error`.

Y cuando sí avisaba, `session.py` rotulaba siempre «proveedor sin cuota», aunque fuese credencial rechazada —
y lo que el operador HACE con cada una es opuesto.
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


# ── R2 · el contador, contra la expresión SQL REAL del producto ─────────────────────────────────────────

def _real_failed_tasks_expr() -> str:
    """La expresión tal y como está escrita en el producto, extraída del fichero — no una reescrita aquí.
    Un test que copia la consulta mide su copia (⭐ «un test que re-implementa no prueba el producto»)."""
    src = (ENGINE / "observability" / "flows.py").read_text(encoding="utf-8")
    m = re.search(r"COUNT\(DISTINCT CASE WHEN kind = 'task'.*?AS failed_tasks", src, re.S)
    assert m, "la expresión de failed_tasks ya no está en flows.py"
    return " ".join(m.group(0).split())


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE events(kind TEXT, label TEXT, payload TEXT)")
    yield c
    c.close()


def _ev(c, kind, label, **payload):
    c.execute("INSERT INTO events VALUES (?,?,?)", (kind, label, json.dumps(payload)))


def test_una_tarea_que_murio_ya_no_cuenta_como_cero(db):
    """La fila sintética del auditor, con la forma REAL del payload del bus."""
    _ev(db, "task", "end", id="1", ok=False, status="error", text="API Error: 400 [1210]")
    n = db.execute(f"SELECT {_real_failed_tasks_expr()} FROM events").fetchone()[0]
    assert n == 1


def test_una_tarea_que_termino_bien_no_cuenta(db):
    _ev(db, "task", "end", id="2", ok=True, status="done")
    assert db.execute(f"SELECT {_real_failed_tasks_expr()} FROM events").fetchone()[0] == 0


def test_la_misma_tarea_que_cierra_dos_veces_es_UN_fallo(db):
    """Un reintento o un relevo cierran la misma tarea más de una vez. Un flujo con una tarea muerta es un
    fallo, no tres — por eso `DISTINCT` sobre el id y no un `SUM`."""
    _ev(db, "task", "end", id="7", ok=False)
    _ev(db, "task", "end", id="7", ok=False)
    assert db.execute(f"SELECT {_real_failed_tasks_expr()} FROM events").fetchone()[0] == 1


def test_el_contador_de_errores_sigue_midiendo_LO_SUYO(db):
    """El contrapeso: `errors` no se ha ensanchado. Un worker muerto y una alerta de infraestructura son dos
    cosas distintas y el resumen tiene que poder decir cuál pasó."""
    _ev(db, "task", "end", id="1", ok=False)
    errors = db.execute(
        "SELECT SUM(CASE WHEN kind IN ('error','alert') THEN 1 ELSE 0 END) FROM events").fetchone()[0]
    assert errors == 0, "una tarea muerta no es una alerta: si suma aquí, los dos contadores miden lo mismo"


def test_las_TRES_proyecciones_lo_cuentan_y_no_solo_la_de_flujos():
    """`flows`, `sessions` y `session` responden a la misma pregunta en tres pantallas distintas. Arreglar una
    sola deja dos superficies del mismo dato discrepando, que es su propia clase de defecto."""
    src = (ENGINE / "observability" / "flows.py").read_text(encoding="utf-8")
    assert src.count("AS failed_tasks") == 3, "una proyección se quedó sin el contador"
    assert src.count("kind IN ('error', 'alert')") == 3, "el contador de errores no debía moverse"


def test_la_ruta_del_payload_es_la_PLANA_que_el_bus_escribe():
    """⚠️ El bus aplana `extra` dentro del payload: `$.ok`, nunca `$.extra.ok`. La primera versión de esta
    consulta usó la anidada y devolvía NULL para todas las filas — verde silencioso sobre datos reales."""
    src = (ENGINE / "observability" / "flows.py").read_text(encoding="utf-8")
    assert "json_extract(payload, '$.ok')" in src
    assert "$.extra.ok" not in src


# ── R4 · la causa se clasifica UNA vez y viaja ──────────────────────────────────────────────────────────

def test_note_failure_devuelve_la_CAUSA_no_solo_el_relevo():
    from nucleo.workers import providers as P
    src = pathlib.Path(P.__file__).read_text(encoding="utf-8")
    assert '"kind": kind, "provider": t["name"]' in src, "la causa tiene que salir de donde se calcula"


def test_el_adaptador_ya_no_reclasifica_el_texto_para_decidir_si_avisa():
    """El agujero exacto: `broken` lo reconoce `is_broken_request` y NO `classify_failure`, así que la
    condición `if nxt is not None or classify_failure(...)` dejaba mudo un broken sin relevo."""
    src = (ENGINE / "nucleo" / "workers" / "claude_session.py").read_text(encoding="utf-8")
    body = src[src.index("is_context_overflow"):src.index('yield self._ev("result"')]
    codigo = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    assert "classify_failure" not in codigo, "sigue reconstruyendo una clasificación que ya venía hecha"
    assert "if cause:" in codigo, "un kind reconocido tiene que producir chip, con o sin relevo"


def test_un_broken_SIN_RELEVO_produce_causa(monkeypatch, tmp_path):
    """El caso que se perdía entero. Se comprueba sobre la decisión pura: hay kind, luego hay aviso."""
    from nucleo.workers import providers as P
    texto = "API Error: 400 [1210][Invalid API parameter, please check the documentation.]"
    assert P.is_broken_request(texto) is True
    assert not P.classify_failure(texto), "si esto cambiara, el agujero sería otro y el test lo diría"


@pytest.mark.parametrize("kind,esperado", [
    ("exhausted", "proveedor sin cuota"),
    ("auth", "credencial rechazada"),
    ("broken", "el proveedor RECHAZA nuestras peticiones"),
    ("", "proveedor caído"),
])
def test_el_chip_dice_QUE_fallo_en_vez_de_sin_cuota_siempre(kind, esperado):
    """Lo que el operador lee decide lo que HACE: una cuota dice «espera», una credencial dice «arréglala»,
    una petición rechazada no dice ninguna de las dos."""
    src = (ENGINE / "nucleo" / "workers" / "session.py").read_text(encoding="utf-8")
    body = src[src.index('elif ev.type == "provider_down"'):src.index('elif ev.type == "progress"')]
    assert f'"{esperado}"' in body or f"'{esperado}'" in body
    if kind:
        assert f'"{kind}"' in body


def test_session_no_vuelve_a_leer_el_texto_del_error():
    """Sería la TERCERA clasificación de la misma cadena. La causa llega como dato."""
    src = (ENGINE / "nucleo" / "workers" / "session.py").read_text(encoding="utf-8")
    body = src[src.index('elif ev.type == "provider_down"'):src.index('elif ev.type == "progress"')]
    assert "classify_failure" not in body and "is_broken_request" not in body


# ── R3 · la regla del cierre corto la comparten los dos canales, como FUNCIÓN ───────────────────────────

@pytest.mark.parametrize("frase,corto", [
    ("Vale, ciérralo", True), ("ciérralo", True), ("cierra el youtube", True),
    ("cierra la sesión de spotify del widget", False), ("no lo cierres", False), ("abre la agenda", False),
])
def test_la_orden_corta_de_cerrar_se_reconoce_igual_para_todos(frase, corto):
    from nucleo.flash import close_guards as g
    assert g.is_short_close_order(frase) is corto


def test_los_DOS_canales_llaman_a_la_misma_funcion_y_ninguno_la_copia():
    """Vivía suelta en el raíl de voz desde 2026-07-16 y el canal de texto —el que conduce los casos de uso—
    nunca la tuvo: contestaba «ciérralo» distinto del producto. Se EXTRAE, no se espeja: el propio trinquete
    dice «si dos canales necesitan la misma regla, extrae primero», y copiarla habría costado una marca."""
    voz = (ENGINE / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    txt = (ENGINE / "nucleo" / "flash" / "probe.py").read_text(encoding="utf-8")
    assert "is_short_close_order(text)" in voz and "is_short_close_order(text)" in txt
    for canal, src in (("voz", voz), ("texto", txt)):
        assert "len(text.split()) <= 5" not in src, (
            f"el canal de {canal} reimplementa el límite en vez de llamarlo. ⚠️ Este assert encontró DOS sitios "
            f"más de los que la extracción arregló: el backstop del cierre llevaba el mismo 5 suelto en ambos "
            f"canales, sin nombre y sin nada que los hiciera moverse juntos.")


def test_el_limite_de_palabras_vive_en_UN_solo_sitio():
    """El número mágico compartido es la clase R3 en miniatura: dos canales que tienen que coincidir y nada
    que los ate. Ahora lo dice `close_guards._SHORT_ORDER_WORDS` y lo leen los tres usos."""
    from nucleo.flash import close_guards as g
    assert g.is_short_order("cierra el youtube") is True
    assert g.is_short_order("cierra la sesión de spotify del widget") is False
    assert g.is_short_order("abre la agenda") is True, "solo mide LARGO; el verbo lo pregunta otra función"

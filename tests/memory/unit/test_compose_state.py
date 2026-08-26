"""Tests de memory.compose_state() — el ESTADO COMPARTIDO por los dos cerebros (V2-027).

Ubicación canónica: tests/memory/unit/.

Contrato: A (misión) + B (situacional) + C (síntesis TENSA del corto plazo), pequeño y ordenado, LECTURA DIRECTA
(sin LLM ni retriever). La misión sale de state.mission o, si no se sembró, del `mission_fallback` que pasa el
llamador (nucleo/flash) — así no se invierte la dependencia memoria→voz.
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
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


def test_compose_mission_and_situational(fresh_db):
    memapi.set_state({"operator_name": "Ricart", "treatment": "directo"})
    block, op, stats = memapi.compose_state(mission_fallback="Eres zaelar, asistente por voz.")
    assert op == "Ricart"
    assert "QUIÉN ERES" in block and "Eres zaelar" in block
    assert "QUIÉN TIENES DELANTE" in block and "Ricart" in block and "directo" in block
    assert stats["has_mission"] and stats["has_state"] and stats["op"] == "Ricart"


def test_compose_uses_seeded_mission_over_fallback(fresh_db):
    memapi.set_state({"mission": "MISIÓN SEMBRADA"})
    block, _op, _stats = memapi.compose_state(mission_fallback="fallback")
    assert "MISIÓN SEMBRADA" in block and "fallback" not in block


def test_compose_empty_with_no_fallback_is_blank(fresh_db):
    block, op, stats = memapi.compose_state(mission_fallback="")
    assert block == "" and op == ""
    assert not stats["has_mission"]


def test_compose_short_is_synthesized_not_full_dump(fresh_db):
    # Escribe muchas líneas de corto plazo; la sección C debe RECORTAR (no volcar las 30 crudas de antes).
    for i in range(12):
        memapi.write_now(f"Operador: mensaje corto número {i} con algo de relleno para ocupar caracteres",
                         kind="conv", level="short", importance=0.2)
    block, _op, stats = memapi.compose_state(mission_fallback="m")
    assert "DE QUÉ ÍBAIS HABLANDO" in block
    assert stats["short_count"] <= 5              # cap agresivo (V2-027): a lo sumo las últimas 5
    assert block.count("· ") <= 12                 # no vuelca las 12 líneas


def test_compose_state_is_direct_no_retriever(fresh_db, monkeypatch):
    """compose_state NUNCA dispara el retriever (memory.query) — sería meter embeddings en la ruta cacheable."""
    calls = {"n": 0}
    real = memapi.query

    def _spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(memapi, "query", _spy)
    memapi.set_state({"operator_name": "Ana"})
    memapi.compose_state(mission_fallback="m")
    assert calls["n"] == 0


# ── USER RULES (V2-046 A1): reglas del operador en el ESTADO — persistentes, cap, dedup, render ────────────

def test_user_rules_render_and_empty_is_byte_identical(fresh_db):
    """Con rules vacío el bloque es BYTE-idéntico (ni una línea extra); con reglas, línea REGLAS DEL OPERADOR."""
    memapi.set_state({"operator_name": "Ricart"})
    before, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" not in before
    memapi.add_user_rule("Sé más directo, responde en una frase")
    after, _, _ = memapi.compose_state(mission_fallback="m")
    assert "REGLAS DEL OPERADOR" in after and "Sé más directo" in after
    # quitarla devuelve el bloque original exacto
    _, gone = memapi.remove_user_rule("esa regla de ser directo")
    assert gone
    again, _, _ = memapi.compose_state(mission_fallback="m")
    assert again == before


def test_user_rules_dedup_and_cap(fresh_db):
    """Re-decir una regla no duplica (la sube a la más reciente); el cap deja fuera la más antigua."""
    memapi.add_user_rule("Responde solo sí o no")
    memapi.add_user_rule("responde solo si o no.")          # misma regla, otra grafía → dedup
    assert len(memapi.state()["rules"]) == 1
    for i in range(10):
        memapi.add_user_rule(f"Regla número {i}")
    rules = memapi.state()["rules"]
    assert len(rules) == 8                                   # cap
    assert "Regla número 9" in rules[-1]                     # la más reciente manda


def test_user_rules_remove_fuzzy_and_no_false_removal(fresh_db):
    """La retirada casa por referencia difusa; sin señal suficiente NO retira la regla equivocada."""
    memapi.add_user_rule("Cuando te pida una acción hazla sin responder")
    memapi.add_user_rule("Trátame de usted")
    _, gone = memapi.remove_user_rule("olvida lo de tratarme de usted")
    assert gone == "Trátame de usted"
    _, gone2 = memapi.remove_user_rule("olvida esa regla del parchís")   # no existe → no toca nada
    assert gone2 == "" and len(memapi.state()["rules"]) == 1


# ── Un ENCARGO no es un hecho sobre la persona (V2-337, 2026-08-26) ───────────────────────────────────────────
#
# Los dos iban en la MISMA lista y bajo la MISMA orden — «dalo por sabido sin buscar» — así que «Vive en Madrid»
# y «Tarea pendiente para el asistente: buscarle un coche de segunda mano» se leían como la misma clase de dato.
# Medido por el arnés en `cheapest-monitor`: el agente arrancó hablando de COCHES, arrastrando el encargo del
# caso anterior. Y no es cosa del plató: en la memoria VIVA del operador, **3 de las 5 plazas eran encargos**
# (un vuelo a Londres, un fontanero que se quedó sin cuota, una prueba de worker), desplazando a la persona.
#
# La clase ya estaba en el dato y se tiraba: `mem_processor` es explícito en que una tarea delegada es
# `kind="result"`, y `salient_long` devuelve `kind`. Aquí se comprueban las DOS direcciones, porque cada una
# sola se satisface trivialmente: bajar todo a encargos deja al agente sin saber quién es su operador, y no
# bajar nada es el fallo medido.

def _pon(texto, kind, importancia=0.9):
    from memory import writer as memwriter
    return memwriter.insert_memory(texto, kind=kind, level="long", weight=0.9, importance=importancia)


def test_un_encargo_NO_se_presenta_bajo_dalo_por_sabido(fresh_db):
    _pon("Vive en Madrid, España.", "fact")
    _pon("Tarea pendiente para el asistente: buscarle un coche de segunda mano.", "result")

    bloque, _op, stats = memapi.compose_state()

    sabido = bloque.split("[Lo que sabes de él")[1].split("[Encargos")[0]
    assert "Vive en Madrid" in sabido
    assert "coche de segunda mano" not in sabido, (
        "un encargo sigue viajando como hecho permanente de la persona: es lo que hizo que el agente "
        "arrancara hablando de coches cuando le preguntaron por un monitor")
    assert stats["errand_count"] == 1 and stats["salient_count"] == 1


def test_un_HECHO_de_la_persona_NO_baja_a_la_lista_de_encargos(fresh_db):
    """La otra dirección. Sin esto, «los encargos no van con los hechos» se cumple mandándolo TODO a encargos —
    y el agente deja de saber dónde vive su operador, que es un fallo peor y más silencioso."""
    for texto, kind in (("Vive en Madrid, España.", "fact"),
                        ("Prefiere trato directo.", "pref"),
                        ("Quiere comprar un monitor de 27 pulgadas.", "intent"),
                        ("El mes pasado viajó a Oporto.", "event")):
        _pon(texto, kind)

    bloque, _op, stats = memapi.compose_state()

    assert "[Encargos" not in bloque, f"sin un solo encargo no puede aparecer la sección: {bloque}"
    # `salient_count` no se fija a 4: el escritor crea NODOS-CONCEPTO («viajes») que también entran en el
    # perfil saliente, y clavar el número mediría el andamio en vez del contrato. Lo que se afirma es que
    # ninguno de los cuatro se fue a encargos y que todos siguen visibles.
    assert stats["errand_count"] == 0
    assert stats["salient_count"] >= 4
    for esperado in ("Vive en Madrid", "trato directo", "monitor de 27", "Oporto"):
        assert esperado in bloque


def test_el_encargo_sigue_VISIBLE_y_legible_como_pendiente(fresh_db):
    """La condición de seguridad que puso el propio arnés: un encargo sin respuesta tiene que seguir leyéndose
    como pendiente. Taparlo cambiaría este fallo por el contrario — un agente que olvida lo que le pidieron."""
    _pon("Tarea pendiente para el asistente: buscarle un coche de segunda mano.", "result")

    bloque, _op, _stats = memapi.compose_state()

    assert "coche de segunda mano" in bloque, "el encargo desapareció del prompt: eso es olvidarlo, no ordenarlo"
    cabecera = bloque.split("[Encargos")[1].split("]")[0]
    assert "NO son hechos sobre él" in cabecera, "la sección no dice de qué clase es lo que lleva"


def test_la_linea_de_encargos_no_ORDENA_ejecutarlos(fresh_db):
    """Doctrina de `workers/findings.py`: se entrega el dato y se nombra su clase; el juicio se queda en el
    cerebro. Una orden de «ocúpate de esto» es exactamente lo que produjo el defecto medido."""
    _pon("Tarea pendiente para el asistente: buscarle un coche.", "result")

    cabecera = memapi.compose_state()[0].split("[Encargos")[1].split("]")[0].lower()

    assert "no empieces a trabajar" in cabecera
    assert "salvo que él lo saque" in cabecera, "sin la excepción, un encargo que SÍ trae el operador se ignora"

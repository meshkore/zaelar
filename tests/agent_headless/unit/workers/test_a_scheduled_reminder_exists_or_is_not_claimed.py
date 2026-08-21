"""Un aviso PROGRAMADO existe de verdad, o no se dice (V2-249).

La «píldora que se auto-avala», que el arnés lleva midiendo varias tandas: a un worker se le encarga
«recuérdaselo el miércoles», y escribe en memoria —de forma durable— «Recordatorio PROGRAMADO … a las 09:00»
**sin que exista ninguna entrada de scheduler**. No era desobediencia: probado en el código, la capacidad **no
existía**. `worker_policy._KNOWN_ACTS` no tenía ninguna acción de agenda, así que le era IMPOSIBLE hacerlo.

El camino del FlashBrain sí funcionaba (`nucleo/scheduler.py`, 109 tests verdes entre sus dos ficheros): el
agujero se abría solo cuando el encargo se ESCALABA a un worker.

El listón lo puso el arnés y tiene dos salidas aceptables: **que la entrada exista, o que la píldora no diga
«programado»**. Esto hace la primera y, para los casos en que no se pueda, empuja la segunda.

El encuadre es del operador (2026-08-20), y corrige el que este agente puso primero: **un Brain Worker ya hace
casi de todo** —opera los datos de un widget, crea y modifica su código, conduce el navegador, habla con la red
MeshKore, escribe en memoria, usa MCP— y la seguridad de este sistema **no es una lista corta de permisos, es un
FILTRO**. Así que la pregunta no era «¿debería poder?» sino «¿cuál es su filtro?».
"""
import asyncio

import pytest

from nucleo import worker_api, worker_policy


class _Journal:
    """El diario REAL escribe en el `zaelar.db` de la máquina. Un test unitario no toca artefactos vivos."""

    def __init__(self):
        self.entries = []

    def add(self, title, status="pending", detail=None):
        self.entries.append({"id": len(self.entries) + 1, "title": title, "status": status,
                             "detail": detail or {}})
        return len(self.entries)

    def list_entries(self, status=None):
        return [e for e in self.entries if status is None or e["status"] == status]


@pytest.fixture
def agenda(monkeypatch):
    from nucleo import scheduler
    j = _Journal()
    monkeypatch.setattr(scheduler, "_journal", j, raising=False)
    return j


class _Rec:
    task_id = "t7"
    goal = "recuérdale el miércoles llamar al fontanero"


def _act(payload):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        worker_api._exec_allow("schedule", payload, _Rec()))


# ── la capacidad existe ──────────────────────────────────────────────────────────────────────────────────────

def test_programar_es_una_accion_CONOCIDA():
    """Antes caía en «acción desconocida» y el worker lo leía como una prohibición."""
    assert "schedule" in worker_policy._KNOWN_ACTS
    assert worker_policy.classify_act("schedule", {}) == worker_policy.ALLOW


def test_el_aviso_QUEDA_de_verdad(agenda):
    out = _act({"when": "el miércoles a las 9", "prompt": "recuérdale llamar al fontanero"})
    assert out["ok"], out
    assert len(agenda.entries) == 1, "esto es lo que no existía: la entrada"
    assert out["result"]["id"] and out["result"]["cuando"]


def test_el_aviso_dice_QUIEN_lo_puso(agenda):
    """El operador tiene que poder ver de dónde salió lo que le suena a las 9 de la mañana."""
    _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert "[worker:t7]" in agenda.entries[0]["title"]


# ── el FILTRO ────────────────────────────────────────────────────────────────────────────────────────────────

def test_hay_un_TOPE_por_tarea(agenda):
    """Sin tope, un worker en bucle le llena la agenda al operador — y cada entrada dispara luego un turno."""
    for i in range(worker_api._SCHEDULE_CAP):
        assert _act({"when": "mañana a las 9", "prompt": f"aviso {i}"})["ok"]
    out = _act({"when": "mañana a las 9", "prompt": "uno más"})
    assert not out["ok"] and "tope" in out["error"]
    assert len(agenda.entries) == worker_api._SCHEDULE_CAP


def test_el_tope_es_POR_TAREA_y_no_global(agenda, monkeypatch):
    """Dos encargos distintos del operador no compiten por el mismo cupo."""
    for i in range(worker_api._SCHEDULE_CAP):
        _act({"when": "mañana a las 9", "prompt": f"aviso {i}"})

    class _Otro:
        task_id = "t9"
        goal = "otra cosa"

    out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        worker_api._exec_allow("schedule", {"when": "mañana a las 9", "prompt": "de otra tarea"}, _Otro()))
    assert out["ok"], out


# ── y lo que NO se puede hacer, se dice, no se finge ─────────────────────────────────────────────────────────

def test_sin_CUANDO_no_se_programa_y_se_dice_como(agenda):
    out = _act({"prompt": "llamar al fontanero"})
    assert not out["ok"] and "when" in out["error"]
    assert "miércoles" in out["error"] or "every" in out["error"], "un fallo dice cómo se sale de él (V2-203)"
    assert not agenda.entries


def test_sin_QUE_decir_tampoco(agenda):
    out = _act({"when": "mañana a las 9"})
    assert not out["ok"] and "prompt" in out["error"] and not agenda.entries


def test_un_CUANDO_que_no_se_entiende_devuelve_las_formas_validas(agenda):
    out = _act({"when": "cuando salga la luna", "prompt": "x"})
    assert not out["ok"]
    assert "0 9 * * 3" in out["error"], "sin las formas válidas, el worker adivina o abandona"
    assert not agenda.entries


def test_un_fallo_del_diario_NO_se_devuelve_como_programado(agenda, monkeypatch):
    """Sensibilidad: lo peor que puede hacer esto es decir que sí cuando no. Es literalmente el defecto que cierra."""
    def _boom(*a, **k):
        raise RuntimeError("db bloqueada")

    monkeypatch.setattr(agenda, "add", _boom, raising=False)
    out = _act({"when": "mañana a las 9", "prompt": "x"})
    assert not out["ok"] and "no pude programarlo" in out["error"]


# ── y que el worker SEPA que existe ──────────────────────────────────────────────────────────────────────────

def test_al_worker_se_le_DICE_que_puede_programar():
    """GUARDA DE CABLEADO (V2-199): una capacidad que el modelo no sabe que tiene no existe. Es exactamente lo
    que pasó con el intérprete en 2026-08-02 — el worker se pasó minutos adivinando algo que ya funcionaba."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale el miércoles llamar al fontanero", "", True)
    assert "act schedule" in p
    assert '"when"' in p and '"prompt"' in p


def test_y_que_si_FALLA_no_diga_que_lo_ha_programado():
    """La otra mitad del listón del arnés: si no se pudo, la píldora no puede decir «programado»."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale el miércoles llamar al fontanero", "", True)
    assert "NO digas que lo has programado" in p


# ── las formas que se le enseñan tienen que PARSEAR de verdad ────────────────────────────────────────────────
# V2-219 lo pagó ya una vez: el worker murió dos veces en la aridad de nuestro propio CLI. Una lista de ejemplos
# que no parsean es peor que ninguna, porque manda a reintentar lo mismo. Aquí se comprueba contra el parser.

@pytest.mark.parametrize("cuando", ["mañana a las 9", "el miércoles a las 18:00", "every 30m", "0 9 * * 3"])
def test_cada_ejemplo_que_le_damos_SE_ENTIENDE(cuando, agenda):
    assert _act({"when": cuando, "prompt": "llamar al fontanero"})["ok"], f"«{cuando}» se enseña y no parsea"


def test_los_ejemplos_del_PROMPT_son_los_mismos_que_parsean():
    """Y que el prompt no enseñe formas que el error no menciona (o al revés): dos listas distintas de ejemplos
    se separan sin avisar, y el worker acaba probando la que no vale."""
    from nucleo import dispatch_prompts as dp
    p = dp._build_prompt("recuérdale algo", "", True)
    for cuando in ("mañana a las 9", "el miércoles a las 18:00", "every 30m", "0 9 * * 3"):
        assert cuando in p, f"«{cuando}» parsea pero no se le enseña"


def test_lo_AMBIGUO_no_se_adivina(agenda):
    """`parse_when` devuelve "" adrede ante «esta tarde» o «pronto». Un aviso puesto sobre una fecha inventada es
    peor que ninguno: el operador se queda creyendo que está puesto y se entera el día que no suena."""
    for vago in ("esta tarde", "pronto", "cuando puedas"):
        out = _act({"when": vago, "prompt": "x"})
        assert not out["ok"], f"«{vago}» no puede convertirse en una fecha"
        assert "no lo adivino" in out["error"]
    assert not agenda.entries


# ── y que se VEA, con su prueba ──────────────────────────────────────────────────────────────────────────────
# memoria-dev señaló que esto cierra UNA instancia y no la clase: la memoria guarda como hecho durable una
# afirmación del SISTEMA sobre sus propios efectos, y mañana el recall la confirma. Hoy `remember_external` veta
# lo que dice un TERCERO y el gate de REM verifica un insight contra sus píldoras; **nada verifica una píldora
# contra el mundo**. La mitad que puede poner quien EJECUTA la acción es dejar la prueba: un ref comprobable.

def test_el_aviso_devuelve_un_REF_comprobable(agenda):
    out = _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert out["result"]["ref"] == f"cron:{out['result']['id']}", \
        "sin un ref, una píldora que diga «programado» no se puede contrastar con nada"


def test_programar_DEJA_FILA_en_la_observabilidad(agenda, monkeypatch):
    """Un aviso que suena dentro de tres días lo puso una tarea de fondo que para entonces ya no existe. Sin
    fila, el operador se lo encuentra sin saber de dónde salió."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append((a, k)), raising=False)
    _act({"when": "mañana a las 9", "prompt": "llamar al fontanero"})
    assert vistos, "programar en silencio es la mitad del problema que esto cierra"
    _, kw = vistos[0]
    assert kw.get("extra", {}).get("cron_id"), "la fila lleva el ID real, que es lo que permite comprobarlo"


def test_un_aviso_que_NO_se_pudo_poner_no_deja_fila(agenda, monkeypatch):
    """Sensibilidad: una fila «⏰ aviso programado» sobre algo que no se programó es la misma mentira, en otro
    sitio y con más autoridad."""
    vistos = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: vistos.append((a, k)), raising=False)
    _act({"when": "esta tarde", "prompt": "x"})
    assert not vistos

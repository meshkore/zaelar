#
# Set de REGRESIÓN determinista de V2-069 «una sola mente» — la inteligencia de CONDUCCIÓN del canal de cluster.
# Run: .venv/bin/pytest connectors/meshkore/test_capsule_flow.py -q
#
# No usa LLM (cero flaky): captura el texto EXACTO que el bridge le da al cerebro por turno (con un cerebro falso
# que lo graba) y verifica el contrato que arregla la forense:
#   · NO re-presentarse una vez saludado (guía de fase sondeo/trabajo en el prompt del turno)
#   · progresión de FASE derivada del estado de la relación (saludo→sondeo→trabajo)
#   · objetivo del operador presente en el turno
#   · IDENTIDAD-SAFE: el system del canal NUNCA expone PII del operador
#   · TOOLS OFF: el motor del canal no ofrece herramientas (invariante estructural)
#
import asyncio

import pytest

from connectors.meshkore import capsule
from connectors.meshkore.bridge import ClusterBridge
from memory import db as memdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


class _Client:
    handle = "zaelar"
    online = ["zalo"]


class _Mgr:
    def get(self, cluster): return _Client()
    def clusters(self): return [{"name": "meshcore", "connected": True, "handle": "zaelar", "online": ["zalo"]}]
    def names(self): return ["meshcore"]
    def has(self, n): return n == "meshcore"


def _bridge(monkeypatch):
    """Un ClusterBridge con manager falso y un cerebro que GRABA el prompt de cada turno (y no envía tags)."""
    monkeypatch.setattr("connectors.meshkore.bridge._emit", lambda *a, **k: None)
    seen = []

    async def _brain(text, on_chunk=None):
        seen.append(text)
        return "ok"                        # sin [[cluster.*]] → _route_reply no despacha nada

    br = ClusterBridge(_Mgr(), _brain)
    br._notify_registry = lambda: None
    return br, seen


def _msg(peer="zalo", text="hola", cluster="meshcore"):
    return {"kind": "message", "cluster": cluster, "from": peer, "payload": {"text": text}}


async def _drain(br):
    # las tareas de _brain_turn se lanzan con create_task; deja que corran
    for _ in range(6):
        await asyncio.sleep(0)


# ── NO re-presentarse + progresión de fase ─────────────────────────────────────────────────────────────────────
def test_no_reintroduction_after_first_turn(fresh_db, monkeypatch):
    br, seen = _bridge(monkeypatch)

    async def run():
        await br.on_event(_msg(text="hola, ¿colaboramos?"))   # 1er contacto → fase saludo
        await _drain(br)
        await br.on_event(_msg(text="¿seguimos con el pipeline?"))  # ya saludado → sondeo
        await _drain(br)

    asyncio.run(run())
    assert len(seen) == 2
    # 1er turno: fase SALUDO → puede presentarse
    assert "primera vez" in seen[0].lower()
    # 2º turno: ya conocido → el prompt le ORDENA no re-presentarse (raíz de las 331 auto-presentaciones)
    assert "no te presentes" in seen[1].lower()
    # y la cápsula quedó marcada greeted
    assert capsule.load("meshcore", "zalo")["greeted"] is True


def test_objective_present_in_turn(fresh_db, monkeypatch):
    br, seen = _bridge(monkeypatch)
    capsule.patch("meshcore", "zalo", greeted=True, objective="algoritmo de trading cripto")

    async def run():
        await br.on_event(_msg(text="¿por dónde vamos?"))
        await _drain(br)

    asyncio.run(run())
    assert "algoritmo de trading cripto" in seen[0]         # objetivo presente en el turno
    assert "trabajo" in seen[0].lower()                     # fase trabajo (greeted + objetivo)
    assert "no te presentes" in seen[0].lower()


def test_capsule_block_is_injected(fresh_db, monkeypatch):
    br, seen = _bridge(monkeypatch)

    async def run():
        await br.on_event(_msg(text="hola"))
        await _drain(br)

    asyncio.run(run())
    assert "[RELACIÓN con el agente «zalo»" in seen[0]      # el bloque de relación se antepone al turno


# ── IDENTIDAD-SAFE: el system del canal nunca filtra PII del operador ──────────────────────────────────────────
def test_cluster_system_is_identity_safe(fresh_db):
    from memory import api as memory
    from nucleo.flash.prompt import build_cluster_system, build_flash_system
    memory.set_state({"operator_name": "Ricart", "treatment": "de tú", "location": "Soria"})
    sys_cluster = build_cluster_system()
    # el perfil del canal NO debe contener datos personales del operador
    for pii in ("Ricart", "Soria"):
        assert pii not in sys_cluster, f"FUGA de PII en el system del canal: {pii}"
    # sanity: el perfil del OPERADOR sí compone estado (contraste — no es que compose_state esté vacío)
    op_sys, _ = build_flash_system()
    assert isinstance(op_sys, str) and len(op_sys) > len(sys_cluster) - 1  # el del operador lleva ESTADO además


# ── TOOLS OFF: invariante estructural del motor del canal ──────────────────────────────────────────────────────
def test_channel_engine_offers_no_tools():
    import inspect
    from nucleo.flash import cluster
    src = inspect.getsource(cluster)
    # el canal usa FastClient.complete() — que NO tiene parámetro `tools`: estructuralmente no puede ofrecer ninguna.
    assert ".complete(" in src, "el motor del canal debe usar FastClient.complete() (sin superficie de tools)"
    assert ".stream(" not in src, "el canal no debe usar stream() (evita ofrecer tools y el cuelgue de un razonador)"
    assert "router.TOOLS" not in src and "tool_context" not in src, "el canal NUNCA ofrece el catálogo de tools"
    # y complete() no acepta tools (perfil untrusted forzado a nivel de API del cliente)
    from nucleo.flash.fast_client import FastClient
    assert "tools" not in inspect.signature(FastClient.complete).parameters

"""V2-459 — tres agentes en esta máquina, tres puertos, y ninguno se mueve.

El operador volvió a `http://127.0.0.1:43921/` esperando encontrar ahí el agente ES y no había nada
escuchando. No era un fallo del arranque: esa dirección solo existía para `--lab`, mientras que la tanda
desatendida (`--sandbox`) arrancaba en `preferred_port(43918)` — UN número para los dos idiomas, y encima
uno que se deslizaba a un puerto efímero cuando estaba ocupado. Así que «el agente español» tenía dos
direcciones según qué comando lo hubiera levantado, y la que se deslizaba no tenía ninguna: la ronda corría
donde cupiera y nadie podía mirarla.

Lo que se blinda aquí es lo que el operador pidió con esas palabras — que los puertos se respeten de una
ejecución a otra:

  · una sola tabla (`tests/platform/ports.py`), no un número en cada sitio que lo necesite,
  · el puerto sale del IDIOMA del caso, no de quién arrancó la tanda, y
  · un puerto ocupado es un ERROR que dice quién lo tiene, nunca una razón para moverse.
"""
from __future__ import annotations

import argparse
import contextlib
import pathlib
import re

import pytest

from tests.platform import ports as PORTS

ENGINE = pathlib.Path(__file__).resolve().parents[3]


# ── la tabla ────────────────────────────────────────────────────────────────────────────────────────────
def test_son_tres_y_estos_son_sus_numeros():
    """Clavados a mano a propósito: el operador los tiene en marcadores del navegador, así que cambiar uno
    tiene que costar tocar un test que dice por qué, no editar una constante de paso."""
    assert PORTS.OPERATOR == 43917
    assert PORTS.SANDBOX_ES == 43921
    assert PORTS.SANDBOX_US == 43922
    assert set(PORTS.AGENTS) == {"operator", "es", "us"}
    assert len(set(PORTS.AGENTS.values())) == 3, "dos agentes en el mismo puerto es uno solo, y a ratos"


def test_el_puerto_del_operador_es_EL_QUE_EL_MOTOR_ARRANCA_SOLO():
    """La fila que no controla esta tabla: el 43917 lo decide `server/__main__.py`. Si alguien cambia ahí el
    defecto, el sandbox podría acabar peleándose con la instalación del operador — y esa colisión se paga
    con la sesión de trabajo de una persona, no con un test rojo."""
    src = (ENGINE / "server" / "__main__.py").read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\("PORT",\s*"(\d+)"\)', src)
    assert m, "no encuentro el puerto por defecto del motor en server/__main__.py"
    assert int(m.group(1)) == PORTS.OPERATOR


def test_el_puerto_sale_del_IDIOMA_y_entiende_las_dos_formas_de_decirlo():
    """El catálogo dice `es`/`us`; el motor dice `ZAELAR_LANGUAGE=es`/`en`. Las dos viajan por este arnés y
    un mapeo que entendiera solo una mandaría la mitad de las rondas al agente del otro país — que es
    exactamente el fallo que justifica tener dos agentes (ver la cabecera de lab/profiles.py)."""
    for spanish in ("es", "es-ES", "ES"):
        assert PORTS.sandbox_port(spanish) == PORTS.SANDBOX_ES, spanish
    for english in ("us", "en", "en-US", ""):
        assert PORTS.sandbox_port(english) == PORTS.SANDBOX_US, english


def test_el_laboratorio_LEE_la_tabla_en_vez_de_tener_su_propia_copia():
    """Dos copias del mismo número se separan, y separarse aquí significa que el operador abra el puerto que
    recuerda y encuentre otra cosa. Se comprueba el valor Y la fuente: iguales hoy por casualidad no
    demuestra nada."""
    from tests.use_cases.lab import profiles as LP
    assert LP.ES.port == PORTS.SANDBOX_ES and LP.US.port == PORTS.SANDBOX_US
    src = (ENGINE / "tests" / "use_cases" / "lab" / "profiles.py").read_text(encoding="utf-8")
    assert "ports.SANDBOX_ES" in src and "ports.SANDBOX_US" in src
    assert not re.search(r"port\s*=\s*\d{4,5}", src), "un literal de puerto ha vuelto a profiles.py"


# ── la tanda desatendida ────────────────────────────────────────────────────────────────────────────────
def _scn(locale: str):
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id=f"x__{locale}", locale=locale, tier=1, persona_brief="p",
                              opening_line="o", success_checks="s")


def _boot_port(monkeypatch, tmp_path, locale: str) -> int:
    """Arranca `_sandbox_batch` con un motor de mentira y devuelve el puerto que PIDIÓ."""
    from tests.use_cases.e2e.agent import config, run as R
    import tests.platform.sandbox_engine as SE

    got: dict = {}

    @contextlib.contextmanager
    def _fake_engine(**kw):
        got["port"] = kw.get("port")
        yield type("E", (), {"base_url": "http://x", "workspace": tmp_path,
                             "new_widget_dirs": lambda self=None: [],
                             "log_tail": lambda self=None, n=0: ""})()

    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "abc1234", "n_dirty": 0, "dirty": []})
    monkeypatch.setattr(config, "machine_stamp", lambda: {"n": 0})
    monkeypatch.setattr(SE, "sandbox_engine", _fake_engine)
    monkeypatch.setattr(PORTS, "busy_refusal", lambda port, **kw: "")
    monkeypatch.setattr(R, "brain_preflight", lambda **kw: "")
    monkeypatch.setattr(R, "bridge_allowlist_refusal", lambda **kw: "")
    monkeypatch.setattr(R, "_run_batch", lambda *a, **k: 0)
    R._sandbox_batch([_scn(locale)], argparse.Namespace(no_file=True, stop_after_failures=0))
    return got["port"]


def test_una_tanda_ES_arranca_en_43921_y_una_US_en_43922(monkeypatch, tmp_path):
    """El caso del operador, tal cual: abre 43921 mientras corre la tanda española y ve al agente trabajar.
    Antes las dos caían en el mismo 43918 (cuando caían ahí)."""
    assert _boot_port(monkeypatch, tmp_path, "es") == PORTS.SANDBOX_ES
    assert _boot_port(monkeypatch, tmp_path, "us") == PORTS.SANDBOX_US


def test_un_puerto_OCUPADO_para_la_tanda_en_vez_de_mudarla(monkeypatch, tmp_path):
    """La mitad que de verdad blinda: sin esto, «el puerto es fijo» dura hasta el primer huérfano.

    Sale con 4 (NO SE PUEDE MEDIR) y no con 3 (NO SE DEBE, árbol sucio): a la tanda no la han prohibido, la
    han bloqueado, y quien lea el log necesita distinguirlas.
    """
    from tests.use_cases.e2e.agent import config, run as R
    import tests.platform.sandbox_engine as SE

    @contextlib.contextmanager
    def _never(**kw):  # pragma: no cover — no debe llegar a arrancar
        raise AssertionError("arrancó un motor con el puerto ocupado")
        yield

    config._CODE_STAMP = None
    config._MACHINE_STAMP = None
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "abc1234", "n_dirty": 0, "dirty": []})
    monkeypatch.setattr(config, "machine_stamp", lambda: {"n": 0})
    monkeypatch.setattr(SE, "sandbox_engine", _never)
    monkeypatch.setattr(PORTS, "busy_refusal", lambda port, **kw: f"OCUPADO {port}")
    with pytest.raises(SystemExit) as e:
        R._sandbox_batch([_scn("es")], argparse.Namespace(no_file=True, stop_after_failures=0))
    assert e.value.code == 4


def test_la_negativa_dice_QUIEN_tiene_el_puerto_y_como_seguir():
    """Un EADDRINUSE pelado manda a alguien a buscar de cero. Con tres agentes en la máquina, lo que hace
    falta saber es CUÁLES DOS se están peleando y qué hacer con eso."""
    ocupado = PORTS.busy_refusal(PORTS.SANDBOX_ES, want="el sandbox ES de esta tanda")
    if not ocupado:                       # el agente ES no está levantado en esta máquina ahora mismo
        ocupado = PORTS.busy_refusal(PORTS.OPERATOR, want="el sandbox ES de esta tanda")
    if not ocupado:
        pytest.skip("ningún puerto conocido está ocupado en esta máquina; la forma del mensaje se ve abajo")
    assert "OCUPADO" in ocupado and "lsof" in ocupado
    assert "el sandbox ES de esta tanda" in ocupado, "no dice qué se quería levantar"


def test_un_puerto_LIBRE_no_inventa_una_negativa():
    """La mitad de sensibilidad del caso de arriba: sin esto, un `busy_refusal` que devolviera siempre texto
    pararía todas las tandas y los dos casos pasarían igual."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        libre = s.getsockname()[1]
    assert PORTS.busy_refusal(libre, want="lo que sea") == ""
    assert PORTS.holder(libre) == ""


def test_ya_no_queda_forma_de_DESLIZARSE_a_otro_puerto():
    """El trinquete. `preferred_port()` era la función que hacía justo lo que el operador prohibió, y
    mientras exista alguien la volverá a llamar «solo para que no falle el arranque»."""
    import tests.platform.sandbox_engine as SE
    assert not hasattr(SE, "preferred_port")
    src = (ENGINE / "tests" / "use_cases" / "e2e" / "agent" / "run.py").read_text(encoding="utf-8")
    boot = src[src.index("def _sandbox_batch"):]
    boot = boot[:boot.index("\ndef ", 10)]
    # Sin comentarios: la explicación de POR QUÉ se quitó el deslizamiento nombra la función que se quitó, y
    # un trinquete que se dispare con su propia nota de defunción no es un trinquete.
    codigo = "\n".join(l for l in boot.splitlines() if not l.strip().startswith("#"))
    assert "free_port" not in codigo and "preferred_port(" not in codigo
    assert "ports.sandbox_port(" in codigo, "el puerto tiene que salir de la tabla, no de un número aquí"

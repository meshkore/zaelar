"""El contrato de aislamiento del motor desechable, y que nadie se lo salte levantando el suyo.

Escrito el 2026-08-20, al unificar el arranque de `journey` con el de `use_cases`. Hasta entonces `journey`
levantaba su propio engine —su puerto, su tempdir, su lista de variables— y a esa copia le faltaba
`ZAELAR_LOG_DIR`. El `LOG_DIR` de `voice/observer.py` se resuelve desde la RAÍZ DEL REPO, no desde el
workspace, así que **cada corrida de `journey` escribía sus eventos en el
`.meshkore/logs/timeline-latest.jsonl` real del operador**: eventos de test leídos como una sesión viva, que
es el incidente del 2026-07-25.

Y el aviso estaba escrito: `sandbox_engine.py` llevaba meses con una nota sobre esta fuga exacta, porque el
helper se extrajo del runner de `journey`. Documentar una fuga en el módulo que NO la tiene no la arregla.

Estos tests no arrancan ningún motor: interceptan el `Popen` y miran el ENTORNO que se le pasa, que es donde
vive el contrato. Un test que levantara el engine de verdad tardaría un minuto y probaría menos.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.platform import sandbox_engine as SE


class _FakeProc:
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, *a, **k):
        pass

    def kill(self):
        pass


@pytest.fixture
def captured_env(monkeypatch):
    """Arranca `sandbox_engine` sin arrancar nada: devuelve el env con el que se habría lanzado el motor."""
    seen: dict = {}

    def _popen(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env") or {}
        seen["cwd"] = kw.get("cwd")
        return _FakeProc()

    monkeypatch.setattr(SE.subprocess, "Popen", _popen)
    monkeypatch.setattr(SE, "_wait_ready", lambda eng, timeout: None)
    return seen


def test_the_operators_real_timeline_is_never_the_destination(captured_env):
    """La fuga concreta: sin `ZAELAR_LOG_DIR`, los eventos del test acaban en el timeline del operador."""
    with SE.sandbox_engine() as eng:
        env = captured_env["env"]
        assert env.get("ZAELAR_LOG_DIR"), "sin esta variable el observer escribe en la raíz del repo"
        assert Path(env["ZAELAR_LOG_DIR"]).is_relative_to(eng.workspace), (
            "el directorio de eventos tiene que caer DENTRO del workspace desechable")


def test_workspace_db_and_identity_are_all_isolated(captured_env):
    """`ZAELAR_WORKSPACE` se lleva `config/identity.json` con él, o sea el `user_id` de la instalación: sin
    aislarlo, una corrida de test aparece como una cuenta más en el histórico del Master."""
    with SE.sandbox_engine() as eng:
        env = captured_env["env"]
        for var in ("ZAELAR_WORKSPACE", "ZAELAR_DB", "ZAELAR_LOG_DIR"):
            assert Path(env[var]).is_relative_to(eng.workspace), f"{var} apunta fuera del workspace"


def test_the_noisy_neighbours_are_all_off(captured_env):
    """Un motor desechable no llama a los clusters reales del operador, no reaparece el worker de LiveKit y no
    pelea por el segundo listener TLS. Cada una de estas costó una corrida en su día."""
    with SE.sandbox_engine():
        env = captured_env["env"]
        assert env["ZAELAR_ENGINE"] != "livekit", "el worker embebido de LiveKit no va en un desechable"
        assert env["MESHKORE_AUTORECONNECT"] == "0", "nunca marcar los clusters reales del operador"
        assert env["WA_ENABLED"] == "0" and env["TG_ENABLED"] == "0"
        assert env["ZAELAR_HOMEOSTASIS"] == "0"
        assert env["BRAIN"] == "nucleo", "el canal probe y los workers montan sobre este cerebro"


def test_credentials_are_deliberately_NOT_isolated(captured_env):
    """Lo contrario de un descuido: el objetivo es una BASE limpia, no un motor tullido que no pueda llamar a
    un modelo. `server/common.py` carga `.env` + `.meshkore/credentials/` desde la raíz a propósito."""
    with SE.sandbox_engine():
        env = captured_env["env"]
        assert "ZAELAR_CREDENTIALS_DIR" not in env
        assert env["HOST"] == "127.0.0.1", "y solo loopback: nada de escuchar en la red"


def test_a_caller_owned_log_path_survives_the_workspace(captured_env, tmp_path):
    """El log es la EVIDENCIA de un arranque roto, así que quien lo necesite después del derribo puede pedir
    su sitio. `journey` pasa el `artifacts/` de su run por esto."""
    mine = tmp_path / "artifacts" / "journey-engine.log"
    with SE.sandbox_engine(log_path=mine) as eng:
        assert eng.log_path == mine
        assert mine.parent.is_dir(), "el directorio se crea, no se espera que exista"


def test_journey_boots_through_the_shared_helper_and_not_its_own(monkeypatch):
    """La otra mitad, y la que de verdad cierra la fuga: que `journey` USE el helper.

    Se afirma sobre el comportamiento —¿se llamó a `sandbox_engine`?— y no leyendo el fuente: un test que
    busca texto en el código encuentra lo que busca también dentro del comentario que explica el cambio.
    """
    from tests.journey import runner as R

    called: list[bool] = []

    class _Ctx:
        def __enter__(self):
            called.append(True)
            raise RuntimeError("corta aquí: solo se comprueba QUIÉN arranca el motor")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(R, "sandbox_engine", lambda **kw: _Ctx())
    with pytest.raises(RuntimeError):
        R.run(0)
    assert called, "journey volvió a levantar su propio motor: la fuga de `ZAELAR_LOG_DIR` vuelve con él"

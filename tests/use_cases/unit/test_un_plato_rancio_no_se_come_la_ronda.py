"""V2-389 — el guarda se niega a medir, y después NADIE reinicia nada.

`run.stale_engine_refusal` hace lo correcto: si el plató corre código más viejo que el árbol, se NIEGA. Lo que
faltaba es lo de después. La ronda entra en el diario como INFRA en ~45 s, el supervisor pasa al siguiente
escenario… y ese también se niega, y el siguiente, y el siguiente. El bucle parece vivo —el diario se llena,
los escenarios rotan, ninguna ronda se cuelga— y no mide NADA.

Medido el 2026-08-27: `search-buy-camera__es` INFRA en 45 s, y solo siguió porque yo estaba delante y reinicié
a mano en un minuto. Con dos agentes empujando motor cada ~20 minutos eso no es una rareza: es el estado por
defecto de una tanda desatendida. Y es justo lo contrario del encargo del operador («que el sistema no se
detenga»), con el agravante de que un bucle parado que sigue escribiendo en el diario no se ve como parado.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def bucle(monkeypatch):
    """Conduce UNA vuelta del bucle real, con la ronda y el reinicio sustituidos por testigos."""
    visto = {"rondas": [], "reinicios": 0, "apuntes": []}

    def _reinicia(lab="es"):
        visto["reinicios"] += 1
        return visto.get("_reinicio_ok", True)

    def _una_ronda(esc, lab="es"):
        visto["rondas"].append(esc)
        # el primer intento sale rancio; el de después de reiniciar, no
        rancio = visto.get("_rancio_siempre", False) or len(visto["rondas"]) == 1
        return {"escenario": esc, "resultado": "INFRA" if rancio else "FAIL",
                "segundos": 45, "sha": "abc", "motivo": "", "log": "", "_rancio": rancio}

    monkeypatch.setattr(S, "_reinicia_plato", _reinicia)
    monkeypatch.setattr(S, "una_ronda", _una_ronda)
    monkeypatch.setattr(S, "_apunta", lambda **kw: visto["apuntes"].append(kw))
    monkeypatch.setattr(S, "rotacion", lambda: ["un-caso"])
    monkeypatch.setattr(S, "_recargar_si_cambie", lambda *_a, **_k: None)
    monkeypatch.setattr(S, "_huella", lambda: "")
    monkeypatch.setattr(S.time, "sleep", lambda *_a: (_ for _ in ()).throw(_Basta()))
    return visto


class _Basta(Exception):
    """Corta el `while True` al final de la primera vuelta."""


def _una_vuelta():
    with pytest.raises(_Basta):
        S.main()


def test_una_ronda_perdida_por_plato_rancio_se_REPITE(bucle):
    """El corazón: sin esto la ronda se da por gastada y el escenario no se mide hasta la vuelta siguiente."""
    _una_vuelta()
    assert bucle["reinicios"] == 1, "hay que reiniciar el plató, no seguir midiendo contra código viejo"
    assert bucle["rondas"] == ["un-caso", "un-caso"], "la ronda que se comió el rancio se repite"


def test_el_reinicio_queda_APUNTADO(bucle):
    """Un reinicio silencioso deja el diario diciendo que la ronda simplemente falló dos veces."""
    _una_vuelta()
    assert any(a.get("resultado") == "RECARGA-PLATO" for a in bucle["apuntes"])


def test_si_el_plato_NO_levanta_no_se_repite_la_ronda(bucle):
    """Repetir contra un plató que no arrancó mide lo mismo: nada."""
    bucle["_reinicio_ok"] = False
    _una_vuelta()
    assert bucle["rondas"] == ["un-caso"]


def test_un_plato_que_sigue_rancio_NO_entra_en_bucle(bucle):
    """La bifurcación al otro lado: reintentar hasta que cuadre convierte un plató que no arranca en un bucle
    infinito que no mide — el mismo fallo con otra cara."""
    bucle["_rancio_siempre"] = True
    _una_vuelta()
    assert bucle["rondas"] == ["un-caso", "un-caso"], "UNA repetición, no N"
    assert bucle["reinicios"] == 1


def test_una_ronda_SANA_no_reinicia_nada(bucle):
    """Y el otro sentido: un FAIL normal no puede costar un reinicio del plató, que le tira al operador la
    sesión que está mirando."""
    bucle["rondas"].append("—ya-hubo-una—")     # así la primera ronda real no sale rancia
    _una_vuelta()
    assert bucle["reinicios"] == 0


class _ProcesoQueImprime:
    """Popen de mentira: escribe en el log de la ronda lo que imprimiría el runner y termina."""

    def __init__(self, texto):
        self._texto, self.pid = texto, 424242

    def __call__(self, _argv, cwd=None, stdout=None, stderr=None, start_new_session=None):
        stdout.write(self._texto); stdout.flush()
        return self

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


_REHUSA = ("✗ el motor que va a contestar corre d5771e5 y el arbol esta en 1882d30: "
           "no es el mismo codigo.\n")


@pytest.mark.parametrize("salida, rancio", [
    (_REHUSA, True),
    ("  tester  · hola\n  zaelar  · qué tal\nPASSED 0/1 (overall>=4)\n", False),
])
def test_una_ronda_REAL_dice_si_el_plato_salio_rancio(monkeypatch, tmp_path, salida, rancio):
    """La `una_ronda` de verdad, no el testigo del bucle.

    Al escribir esto la primera vez, desarmar el `_rancio` de `una_ronda` NO mordía: los guardas de arriba
    sustituyen `una_ronda` entera por un doble, así que medían mi doble y no la función. Sin esto, el bucle
    puede estar perfecto y no enterarse nunca de que hubo rancio.
    """
    monkeypatch.setattr(S, "_SALIDA", tmp_path)
    monkeypatch.setattr(S, "_apunta", lambda **kw: None)
    monkeypatch.setattr(S, "_sha", lambda: "abc1234")
    monkeypatch.setattr(S.subprocess, "Popen", _ProcesoQueImprime(salida))
    parte = S.una_ronda("un-caso")
    assert parte["_rancio"] is rancio


def test_una_ronda_rancia_se_reconoce_por_lo_que_IMPRIME_el_runner():
    """El marcador tiene que ser el texto real del guarda, no una paráfrasis: si el runner cambia la frase y
    esto no, el supervisor deja de ver el rancio y vuelve el defecto entero, en silencio."""
    from pathlib import Path
    assert S._PLATO_RANCIO in Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")

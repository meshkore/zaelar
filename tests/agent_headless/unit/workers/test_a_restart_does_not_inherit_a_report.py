"""V2-288 — el cajón privado del worker no lo era: el primer encargo tras un reinicio heredaba un informe ajeno.

`workdir.for_task` nombraba el directorio SOLO por `task_id`, y `escalate._seq` arranca en 0 en cada proceso. Así
que el primer encargo de cualquier arranque es `1` otra vez, cae en el mismo cajón que el primero del arranque
anterior, y ahí sigue su `informe.json` — `_TTL_S` lo conserva 48 horas a propósito, para poder auditarlo.

Medido en la tanda del 2026-08-24 11:11, `search-buy-guitar__es`, con los eventos del bus delante: el worker
planificó «3 pasos: entregar informe de guitarras en la hoja results · verificar criterios del objetivo · cierre»
y entregó SEIS guitarras con url real de Wallapop **27 segundos después de arrancar, con cero navegaciones, cero
extracciones y cero búsquedas**. Salían de `zaelar-workers/1/informe.json`, escrito a las 03:02 por otra corrida.
Y le dijo al operador «Entré en Wallapop y revisé 14 anuncios», que es la narración del propio informe.

Lo que lo hace grave no es que sea mentira, es que es VERDAD de otro día: precios reales, enlaces que abren. Un
resultado inventado se cae a la primera comprobación; éste no.

Es la misma clase que la hoja de resultados (V2-259 addenda) y se cierra igual: componer con `boot_id()`, que
además RUEDA en un reset (V2-287) — así «empezamos de cero» estrena cajón de verdad. Reanudar DENTRO de un
proceso no se toca: mismo sello, mismo id, mismo cajón.
"""
import json
import os

import pytest

from nucleo import runtime_ids
from nucleo.workers import workdir


@pytest.fixture(autouse=True)
def _own_root(tmp_path, monkeypatch):
    """Cajón AISLADO — este test escribe informes de mentira y no puede tocar los reales del operador, que son
    la primera evidencia que se mira cuando una entrega sale mal."""
    monkeypatch.setattr(workdir, "_ROOT", str(tmp_path / "workers"))
    yield


def _restart():
    """Lo que hace un proceso nuevo: el contador de encargos vuelve a empezar. `reset_seq` es la MISMA puerta que
    usa `nucleo/reset.py::reset_all()` (el ⏻ del operador) y la que rueda el sello desde V2-287."""
    runtime_ids.reset_seq("escalate")


def test_the_first_errand_after_a_restart_gets_an_empty_drawer():
    """EL CASO MEDIDO: el encargo `1` de ayer dejó su informe; el encargo `1` de hoy no puede verlo."""
    ayer = workdir.for_task("1")
    with open(os.path.join(ayer, "informe.json"), "w", encoding="utf-8") as f:
        json.dump({"items": [{"title": "Yamaha F370BL Negra", "price": "100 €"}]}, f)

    _restart()
    hoy = workdir.for_task("1")

    assert hoy != ayer, "el mismo id de encargo devolvió el mismo cajón tras reiniciar"
    assert not os.listdir(hoy), f"el cajón nuevo trae basura de antes: {os.listdir(hoy)}"


def test_the_old_report_is_not_deleted_either():
    """No se borra: el informe ES la evidencia de lo que un worker entregó de verdad, y es lo primero que se mira
    cuando una entrega sale mal. La corrección es que no se HEREDA, no que desaparezca (`_reap` lo acota por EDAD,
    que es otra decisión y sigue en pie)."""
    ayer = workdir.for_task("7")
    open(os.path.join(ayer, "informe.json"), "w", encoding="utf-8").write("{}")
    _restart()
    workdir.for_task("7")
    assert os.path.exists(os.path.join(ayer, "informe.json"))


def test_resuming_inside_one_process_lands_back_in_its_own_drawer():
    """La contraria, y sin ella «no heredes» se satisface con un `mkdtemp` que rompe la continuidad de V2-049: un
    worker relevado o reanudado tiene que volver a encontrar lo que escribió."""
    a = workdir.for_task("3")
    open(os.path.join(a, "parcial.json"), "w", encoding="utf-8").write("{}")
    b = workdir.for_task("3")
    assert a == b
    assert os.path.exists(os.path.join(b, "parcial.json"))


def test_two_errands_of_one_run_never_share_a_drawer():
    """Lo que el módulo ya prometía y sigue cumpliendo: dos encargos vivos a la vez no comparten `informe.json`."""
    assert workdir.for_task("1") != workdir.for_task("2")


def test_the_stamp_is_the_one_the_engine_uses():
    """Compuesto con el sello del MOTOR, no con uno propio. Un sello local se vería igual en este test y no rodaría
    en un reset, que es justo la mitad que hace que ⏻ estrene cajón."""
    assert runtime_ids.boot_id() in os.path.basename(workdir.for_task("9"))

"""A worker LOOKING AT THE MENU is not a worker that has crashed.

Measured on 2026-08-28 in `weekend-plan-barcelona__es`: the round was archived with two `error_interno`
anomalies, and the judge wrote that «the worker technically failed while extracting the price». What the
worker had actually done was launch `nav_cli` and `worker_bridge` WITHOUT a subcommand — argparse responds
with a `usage:` block and **code 2**, so a discovery probe reaches us dressed exactly like a crash. Two of
the four failures marked in that round were the model reading the menu, and the mechanism note paid the price.

It is the instrument accusing the product, which is the one error a measuring tool cannot afford: a false
failure sends an agent to fix something that never happened, and costs more than the defect.

The rule —and why this one rather than «code 2 does not matter»— is that **the missing argument itself must
be `cmd`**: then nobody selected a subcommand and someone is reading the menu. A bad argument in a REAL
subcommand (`nav_cli click` without a ref) also says «arguments are required» and also exits with 2, and that
IS a broken call: a request was made and could not be served.
"""
from __future__ import annotations

from nucleo.workers.probes import is_menu_probe

_BARE_NAV = ("usage: nav_cli [-h] {snapshot,look,navigate,open,goto,click,type,select_option,click_at,"
             "type_at,scroll,press,extract,visit} ... nav_cli: error: the following arguments are required: cmd")
_BARE_BRIDGE = ("usage: worker_bridge [-h] {ask,wait,act,say} ... worker_bridge: error: the following "
                "arguments are required: cmd")


def test_las_dos_sondas_reales_de_la_ronda():
    """Copied verbatim from the `weekend-plan-barcelona__es` log, not rewritten by hand."""
    assert is_menu_probe(_BARE_NAV)
    assert is_menu_probe(_BARE_BRIDGE)


def test_una_llamada_rota_de_verdad_sigue_siendo_un_error():
    """The sensitivity half, and the one that matters: a request was made and could not be served."""
    roto = ("usage: nav_cli click [-h] ref ... nav_cli click: error: the following arguments are "
            "required: ref")
    assert not is_menu_probe(roto)


def test_una_cli_ajena_no_es_asunto_nuestro():
    """We know nothing from a `usage:` message from another binary, and guessing would fabricate a measurement."""
    assert not is_menu_probe("usage: ffmpeg [-h] ... error: the following arguments are required: cmd")


def test_un_error_normal_no_se_ablanda():
    for txt in ("Traceback (most recent call last): ConnectionRefusedError",
                "Exit code 1 · timeout after 30s", "", "usage: nav_cli [-h] {snapshot}"):
        assert not is_menu_probe(txt), txt


def test_el_emisor_deja_de_marcarlo_como_error(monkeypatch):
    """The plumbing: without this, the classification exists and nobody uses it.

    The emitter is what feeds `is_error`, and from there come the auditor's anomalies, the span's error counter,
    and what the judge reads. A single point, deliberately.
    """
    from nucleo.workers import session as S

    vistos: list[dict] = []

    class _Rec:
        task_id = "1"

    class _Falso:
        _rec = _Rec()

    import voice.observer as OBS
    monkeypatch.setattr(OBS, "emit",
                        lambda kind, label, text="", role="", extra=None: vistos.append(
                            {"label": label, "is_error": (extra or {}).get("is_error")}))

    S.WorkerSession._emit_step_result(_Falso(), {"text": _BARE_NAV, "is_error": True, "where": "web"})
    S.WorkerSession._emit_step_result(_Falso(), {"text": "Traceback: boom", "is_error": True, "where": "web"})

    assert vistos[0]["is_error"] is False and "⚠️" not in vistos[0]["label"], "la sonda no es una avería"
    assert vistos[1]["is_error"] is True and "⚠️" in vistos[1]["label"], "y una avería lo sigue siendo"

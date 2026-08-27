"""V2-203 — the payload bridge answered a missing file with a bare OSError, and the worker stopped there.

Measured on `cheapest-monitor` (round 21, 2026-08-20 14:57):

    worker/task   Exit code 2 no puedo leer el payload de informe.json:
                  [Errno 2] No such file or directory: 'informe.json'

Nothing delivered, ten turns, and the turn kept saying the task was «en marcha». The message says WHAT failed
and nothing about what to do — the same fault `nav_cli` already paid for in V2-186: the bridge is the worker's
ONLY view of this side, so a dead end here is a dead end for the task.

Two facts turn it into a way out, and both are cheap: WHERE it is looking (the path is relative, and a worker
that wrote to another directory cannot tell that from `[Errno 2]`) and WHAT is actually there — writing
`resultados.json` and presenting `informe.json` is otherwise invisible.

This does NOT claim to fix why the file was missing (a failed research step, a skipped write). It fixes that
the failure was mute about its own remedy.
"""
import os
import tempfile

from nucleo import widget_cli


def _present(tmpdir, arg="@informe.json"):
    prev = os.getcwd()
    os.chdir(tmpdir)
    try:
        return widget_cli.main(["hbwidget", "data", "results", "present", arg])
    finally:
        os.chdir(prev)


def test_a_missing_payload_names_the_directory_it_looked_in(capsys, tmp_path):
    assert _present(tmp_path) == 2
    out = capsys.readouterr().out
    assert str(tmp_path.resolve()) in out or str(tmp_path) in out
    assert "directorio de trabajo" in out


def test_it_lists_what_IS_there_so_a_wrong_name_becomes_visible(capsys, tmp_path):
    """The whole point of listing: `resultados.json` written and `informe.json` presented is a one-word fix the
    worker cannot see from the error alone."""
    (tmp_path / "resultados.json").write_text("{}")
    assert _present(tmp_path) == 2
    out = capsys.readouterr().out
    assert "resultados.json" in out


def test_an_empty_directory_says_so_POSITIVELY_rather_than_going_blank(capsys, tmp_path):
    """A trailing blank reads like a truncated message. Stating the emptiness is the fact that tells the
    worker its write never happened, which is a different diagnosis from a wrong name.

    Rewritten 2026-08-28, NOT flipped: the property is unchanged — an empty directory must produce a POSITIVE
    statement. What changed is that both bridges now compose it in one shared place
    (`bridge_usage.what_is_here`, node 4.65) after they were found answering the same question differently,
    and its wording is «el directorio está VACÍO: el fichero no llegó a escribirse» instead of «NINGUNO». The
    old assertion pinned the word, not the fact.
    """
    assert _present(tmp_path) == 2
    out = capsys.readouterr().out
    assert "VAC" in out and "no llegó a escribirse" in out


def test_it_restates_the_TWO_STEP_order(capsys, tmp_path):
    """The recipe in `dispatch_prompts` is explicit about write-then-present, and this failure IS the second step
    running without the first. Repeating it at the point of failure is what makes the retry correct."""
    assert _present(tmp_path) == 2
    out = capsys.readouterr().out
    assert "DOS pasos" in out and "Write" in out


def test_an_ABSOLUTE_path_gets_no_working_directory_advice(capsys, tmp_path):
    """Telling a worker that used `/tmp/x.json` about the cwd would be noise, and the recipe forbids absolute
    paths anyway — the plain error is the honest answer there."""
    assert _present(tmp_path, arg="@/nonexistent-dir-xyz/informe.json") == 2
    out = capsys.readouterr().out
    assert "no puedo leer el payload" in out
    assert "directorio de trabajo" not in out


def test_an_unreadable_directory_still_reports_instead_of_raising(capsys, tmp_path, monkeypatch):
    """`listdir` can fail (permissions, a directory deleted under us). The bridge is REPORTING here, so a second
    failure while composing the report must not become the worker's error."""
    monkeypatch.setattr(os, "listdir", lambda *_a, **_k: (_ for _ in ()).throw(OSError("nope")))
    assert _present(tmp_path) == 2
    out = capsys.readouterr().out
    assert "no puedo leer el payload" in out
    # Rewritten 2026-08-28, NOT flipped. It used to also demand the word «NINGUNO» here, and that was wrong on
    # its own terms: with `listdir` failing we did not look, so claiming the directory holds no json asserts a
    # fact we do not have — the exact shape of «una ausencia en el sitio plausible no es una ausencia». The
    # property that matters, and the one this test is named after, is that the bridge REPORTS instead of
    # raising; the line about what is there is simply omitted when it could not be read.
    assert "VAC" not in out and "SÍ hay aquí" not in out

"""
RESET LEAVES THE SURFACES BLANK — but does not erase the operator's records.

REAL failure (2026-08-12, operator report). They pressed Reset “so everything would stop and we could start from
scratch,” requested a NEW search for sailboats, and when the results sheet opened, the ENTIRE previous search appeared
—the ferries to Ibiza from the 10th—while the worker for the new one was still working. Reset closed the cards but did
not touch their DATA: the old content remained in `widgets/_data/<id>/state.json`, waiting for someone to open the
card. A widget that shows yesterday's work as if it were today's is just as misleading as a failed agent painted
blue.

The two halves that must be upheld at once, which is why everything is in the same file:
  · DERIVED data is emptied (results, reports, charts, the message list) — it is reproducible;
  · the operator's RECORD is NOT (the agenda: their real projects, tasks, and appointments), and neither are
    credentials, connections, or browser profiles — that is what the reset dialog promises.
"""
import json
import os

import pytest

from widgets import store


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Isolate `widgets/_data/` — these tests DELETE widget state; never touch the operator's real data."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield tmp_path
    store._last_hash.clear()


def _seed(wid: str, data: dict) -> None:
    store.save(wid, data)


def _read(wid: str) -> dict:
    p = os.path.join(store.data_dir(wid), "state.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ── 1. derived data goes away ──────────────────────────────────────────────────────────────────────────────────
def test_the_previous_search_does_not_survive_a_reset(data_dir):
    """The exact case from the incident: the ferry sheet must not reappear in the next search."""
    from widgets import reset as wreset
    _seed("results", {"title": "Ferry a Ibiza · Ida lun 17 ago", "items": [{"title": "Dénia ↔ Ibiza · Baleària"}]})
    out = wreset.blank_all()
    assert "results" in out["blanked"]
    body = _read("results")
    assert not body.get("items"), "la hoja de resultados tiene que quedar vacía"
    assert "Ibiza" not in json.dumps(body, ensure_ascii=False)


def test_a_widget_without_a_data_module_is_blanked_too(data_dir):
    """Widgets the operator made (or ones that no longer exist but left data behind) are emptied too; otherwise,
    the only one that would be clean would be the one someone remembered to instrument."""
    from widgets import reset as wreset
    _seed("no-existe-xyz", {"lo": "que sea", "items": [1, 2, 3]})
    out = wreset.blank_all()
    assert "no-existe-xyz" in out["blanked"]
    assert _read("no-existe-xyz") == {}


def test_blanking_does_not_leave_the_next_save_stuck(data_dir):
    """`store.save` has hash-based anti-flooding: if the file is changed externally without clearing the fingerprint,
    the next IDENTICAL save is skipped and the widget remains empty on screen with data that was never written."""
    from widgets import reset as wreset
    payload = {"title": "Veleros", "items": [{"title": "Bavaria 50"}]}
    _seed("results", payload)
    wreset.blank_all()
    store.save("results", payload)                     # the worker publishes exactly the same thing again
    assert _read("results").get("items"), "el guardado posterior tiene que llegar al disco"


# ── 2. the operator's data stays ──────────────────────────────────────────────────────────────────────────────
def test_the_operators_own_record_is_not_wiped(data_dir):
    """The agenda declares `data.durable` in its manifest: these are REAL appointments and projects, not a job's output.
    Deleting them would be data loss — comparable to erasing memory, which requires checking its box."""
    from widgets import reset as wreset
    assert wreset.is_durable("agenda") is True, "el manifest de la agenda tiene que declararlo"
    _seed("agenda", {"meetings": [{"title": "ITV del coche", "date": "2026-08-20"}], "projects": ["Zaelar"]})
    out = wreset.blank_all()
    assert "agenda" in out["kept"] and "agenda" not in out["blanked"]
    assert _read("agenda")["meetings"][0]["title"] == "ITV del coche"


def test_the_default_is_to_blank_so_the_exception_has_to_be_declared(data_dir):
    """Without a declaration → it is emptied. That is what the operator requested (“all result, visualization, etc.
    widgets must be initialized blank”) and it keeps the exception explicit and reviewable."""
    from widgets import reset as wreset
    assert wreset.is_durable("results") is False
    assert wreset.is_durable("mensajeria") is False


def test_messages_go_but_the_connection_stays(data_dir):
    """Reset promises NOT to touch credentials or connections. A brute-force wipe would leave all three platforms `off`
    → it would look as though reset disconnected you from WhatsApp while the account was still linked."""
    from widgets import reset as wreset
    _seed("mensajeria", {"platforms": {"whatsapp": {"status": "linked", "qr": None},
                                       "telegram": {"status": "off", "qr": None},
                                       "email": {"status": "linked", "qr": None}},
                         "items": [{"id": "m1", "text": "hola"}, {"id": "m2", "text": "qué tal"}],
                         "pending_read": ["m1"]})
    wreset.blank_all()
    body = _read("mensajeria")
    assert body["items"] == [] and body["pending_read"] == []
    assert body["platforms"]["whatsapp"]["status"] == "linked", "la conexión NO es contenido"
    assert body["platforms"]["email"]["status"] == "linked"


def test_the_browser_profile_and_media_survive(data_dir):
    """The most expensive thing to lose: `widgets/_data/navegador/profile/` stores sessions the operator opened MANUALLY
    (Wallapop, Google…). `state.json` is emptied, NEVER the folder — that is what `store.delete` does, intended for
    when the widget DIES."""
    from widgets import reset as wreset
    _seed("navegador", {"mode": "page", "url": "https://wallapop.com", "title": "Wallapop"})
    prof = os.path.join(store.data_dir("navegador"), "profile")
    os.makedirs(prof, exist_ok=True)
    with open(os.path.join(prof, "Cookies"), "w", encoding="utf-8") as f:
        f.write("sesion-del-operador")
    shot = os.path.join(store.data_dir("navegador"), "shot.png")
    with open(shot, "wb") as f:
        f.write(b"PNG")

    wreset.blank_all()
    with open(os.path.join(prof, "Cookies"), encoding="utf-8") as f:
        assert f.read() == "sesion-del-operador", "un reset que te desloguea de todo no es un reset"
    assert os.path.exists(shot)


def test_nothing_is_created_for_a_widget_that_had_no_data(data_dir):
    from widgets import reset as wreset
    out = wreset.blank_all()
    assert out == {"blanked": [], "kept": []}
    assert not os.listdir(str(data_dir))


# ── 3. the STATE that describes all of this ──────────────────────────────────────────────────────────────────
def test_the_reset_clears_the_state_that_describes_widgets_and_workers():
    """“The state must be cleared, at least the state that depends on widgets, from the brainworkers.” Without
    this, the brain started the new test by reading open widgets that no longer existed and an MRU pointing to the
    previous test — and made decisions about a dismantled world."""
    import inspect

    from nucleo import reset as nreset
    src = inspect.getsource(nreset.reset_all)
    for key in ("open_widgets", "recent_widgets", "rails"):
        assert f'"{key}": []' in src, f"el reset no vacía `{key}`"
    assert "canvas_layout" in src, "el escritorio guardado en el server también tiene que irse"
    assert "blank_all()" in src, "el reset tiene que dejar las superficies en blanco"


# ── 4. the sheet fills up WHILE work is in progress (the other half of the complaint) ─────────────────────────
def test_the_worker_is_told_to_fill_the_sheet_while_it_works():
    """An investigation takes 5–15 minutes and the brief only asked for delivery AT THE END: the operator was left
    staring at an empty sheet —or the previous search's— without knowing whether anything was happening or being able
    to correct course in time."""
    from nucleo import research
    brief = {"goal": "veleros de 49 pies de segunda mano", "min_candidates": 40, "n_final": 3,
             "hard": ["velero", "segunda mano"], "soft": ["ubicación"]}
    text = research.to_prompt_block(brief)
    low = text.lower()
    assert "append" in low and "present" in low
    assert "provisional" in low, "lo no verificado tiene que ir marcado COMO provisional"
    assert "final" in low, "y el cierre reemplaza lo provisional por la selección definitiva"


def test_the_sheet_documents_the_live_contract_for_whoever_reads_it():
    """The worker learns the contract by reading the manifest (`widget_cli read results`): if the convention is not
    there, it does not exist. It lives in `worker_guide` —served ON DEMAND only by `read_widget`— and not in `usage`,
    as required by the budget test below."""
    with open("widgets/results/manifest.json", encoding="utf-8") as f:
        man = json.load(f)
    assert "append" in (man.get("actions") or {})
    guide = man.get("worker_guide") or ""
    assert "MIENTRAS TRABAJAS" in guide, "que la hoja se llena en curso, no al final"
    assert "provisional" in guide.lower() and "@informe.json" in guide


# ── PROMPT BUDGET: `usage` is paid on EVERY turn with the widget open ──────────────────────────────────────────
# `widgets/brief.py::for_prompt` puts the widget's COMPLETE `usage` into the prompt while it is on screen. The
# results sheet is open precisely during a long investigation, when the operator talks most:
# a 4.9 KB `usage` (where it reached) means ~1.2k tokens on every “how is it going?”. The operator's rule is
# “tools, from least to most”: the LONG contract is served on demand (`worker_guide` → `read_widget`), and each
# turn contains only what the brain cannot infer. The ceiling forces trimming instead of bloating everyone's turn.
_USAGE_BUDGET = 700


def test_the_per_turn_doc_stays_small_and_the_long_contract_is_on_demand():
    with open("widgets/results/manifest.json", encoding="utf-8") as f:
        man = json.load(f)
    usage = man.get("usage") or ""
    assert len(usage) <= _USAGE_BUDGET, (
        f"`usage` viaja en CADA turno con la hoja abierta: {len(usage)} chars > {_USAGE_BUDGET}. "
        "Lo que sea contrato de relleno va a `worker_guide`, que solo se lee con read_widget.")
    # and what was moved must NOT remain duplicated in the expensive path
    for long_only in ("@informe.json", "kind:\"meter\"", "≤34"):
        assert long_only not in usage, f"«{long_only}» es del contrato largo: su sitio es worker_guide"
    assert len(man.get("worker_guide") or "") > len(usage), "el contrato largo existe, solo que bajo demanda"


def test_the_turn_prompt_does_not_carry_the_long_contract(tmp_path, monkeypatch):
    """Verified through the REAL path (`brief.for_prompt`), not by reading the JSON: that is where the cost is paid.

    With the sheet deliberately EMPTY, to measure the cost of DOCUMENTATION rather than CONTENT. Results on screen
    also travel (the digest), and that is money well spent: it allows answering “does that one have Wi-Fi?” without
    searching again. What must not slip into every turn is the manual for filling the sheet, which matters only to
    whoever fills it."""
    from widgets import brief, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    opened = brief.for_prompt(open_ids=["results"], query="")
    closed = brief.for_prompt(open_ids=[], query="")
    assert "results" in opened
    assert "@informe.json" not in opened and "kind:\"meter\"" not in opened
    cost = len(opened) - len(closed)
    assert cost < 1000, f"tener la hoja abierta cuesta {cost} chars de prompt en CADA turno: es un manual, no una guía"


# ── WIPING A WIDGET MUST NOT BE SILENT (2026-08-10) ────────────────────────────────────────────────────────────
# Blind spot discovered firsthand: in another session the results sheet was wiped TWICE in the middle of a
# test (the cause was a test fixture that called the real reset), and there was no way to know — because the
# generic wiping path manually deletes `state.json` and `store.save()` is the ONLY point that announces “this
# widget changed.” Without an event there is no row in the log, and without a signal the canvas keeps showing data
# that no longer exists on disk. It looked like a widget persistence failure: considerable time was spent looking
# for a nonexistent fault. A path that MUTATES data without announcing it is an observability hole, not a detail.
def _emitted(monkeypatch):
    """Capture what is emitted to the observer without touching the real log."""
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda kind, label, text="", role="", extra=None: seen.append((kind, label, extra or {})))
    return seen


def test_wiping_a_widget_leaves_an_audit_row_and_repaints_the_canvas(data_dir, monkeypatch):
    from widgets import reset as wreset

    (data_dir / "hoja").mkdir()
    (data_dir / "hoja" / "state.json").write_text(json.dumps({"items": [1, 2, 3]}), encoding="utf-8")
    seen = _emitted(monkeypatch)

    assert wreset._blank_one("hoja") == "wiped"
    labels = [(k, l) for k, l, _ in seen]
    assert ("widget", "blank") in labels, "sin fila de auditoría, vaciar un widget es indistinguible de perder datos"
    assert ("widget", "data") in labels, (
        "sin la señal que escucha el canvas, la tarjeta abierta sigue mostrando lo que ya no está en disco")
    blank = next(e for k, l, e in seen if l == "blank")
    assert blank["id"] == "hoja" and blank["how"] == "wiped"


def test_the_widgets_own_blank_also_leaves_the_audit_row_without_duplicating_the_signal(data_dir, monkeypatch):
    """The path through `store.save()` already notifies the canvas by itself; what it lacked was SAYING that it was a
    reset — a bare `data` does not distinguish “it was emptied” from “it was updated.”"""
    from widgets import reset as wreset

    (data_dir / "msg").mkdir()
    (data_dir / "msg" / "state.json").write_text(json.dumps({"items": [1]}), encoding="utf-8")
    monkeypatch.setattr(wreset, "_data_module", lambda wid: type("M", (), {"blank": staticmethod(lambda: {"items": []})}))
    seen = _emitted(monkeypatch)

    assert wreset._blank_one("msg") == "blank"
    labels = [l for _, l, _ in seen]
    assert "blank" in labels
    assert labels.count("data") == 1, (
        "`save()` ya emitió el refresco: emitir un segundo `data` haría al canvas re-pintar dos veces por nada")


def test_announcing_can_never_break_the_wipe(data_dir, monkeypatch):
    """Emptying a widget is the operation; reporting it is a side effect. If the observer fails, reset CONTINUES."""
    from widgets import reset as wreset
    import voice.observer as obs

    (data_dir / "x").mkdir()
    (data_dir / "x" / "state.json").write_text("{}", encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("observer caído")

    monkeypatch.setattr(obs, "emit", boom)
    assert wreset._blank_one("x") == "wiped"
    assert not (data_dir / "x" / "state.json").exists()

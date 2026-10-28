"""The worker's search goes through the service, in the form a confined worker can actually type (V2-782 T5.3).

F0 (2026-10-10): four workers wrote `busca.json` to a path the confinement guard refused and stayed blind for the
rest of the task, while their built-in search was out of quota. Now `act use_tool "<query>"` — a quoted sentence,
no braces, no file — is the query, and what comes back is the service's result: the chain's dict for the two doors
that already read it, plus the route, the candidates, the pages and what no row shows.
"""
from __future__ import annotations

import asyncio

from nucleo.cli import usage as bridge_usage


def test_a_quoted_sentence_after_use_tool_is_the_search():
    assert bridge_usage.bare_query_payload("use_tool", "mejores fontaneros Madrid") == {
        "tool": "web_search", "args": {"query": "mejores fontaneros Madrid"}}
    assert bridge_usage.bare_query_payload("web_search", "monitor 27 4K") == {"query": "monitor 27 4K"}
    assert bridge_usage.bare_query_payload("use_tool", '{"tool": "x"}') is None, "a broken JSON stays a JSON error"
    assert bridge_usage.bare_query_payload("use_tool", "@busca.json") is None, "a file reference is read as a file"
    assert bridge_usage.bare_query_payload("show_widget", "results") is None


_QUOTED = 'act use_tool "<qué buscas>"'


def _teaches_the_quoted_form(text: str) -> bool:
    return _QUOTED in text and "busca.json" not in text


def test_the_briefs_a_worker_reads_teach_the_quoted_form_and_no_file():
    """The text the worker RECEIVES (web brief + generic brief, rendered by the real builders) — another goal."""
    from tests.worker_briefs import rendered
    text = rendered("find the cheapest 27-inch 4K monitor in Barcelona")
    assert _teaches_the_quoted_form(text), "the file form is what the guard refused; it must not be taught any more"


class _Rec:
    task_id = "t-relay"

    def __init__(self):
        self.injects = []


class _Worker:
    """What `_relay_search` touches of a session: its record and its inject (no loop → the record's queue)."""

    def __init__(self):
        self._rec = _Rec()

    async def inject(self, msg):          # pragma: no cover — only with a running loop
        self._rec.injects.append(msg)


def test_a_worker_whose_own_search_ran_out_is_told_the_quoted_form_once(monkeypatch):
    from nucleo.workers import session_events
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    w = _Worker()
    session_events._relay_search(w)
    session_events._relay_search(w)
    assert len(w._rec.injects) == 1, "the relay is said once per task"
    msg = w._rec.injects[0].text
    assert 'act use_tool "<qué buscas>"' in msg and "{" not in msg and ".json" not in msg


def test_the_disarm_a_brief_back_on_the_file_form_is_caught(monkeypatch):
    """Put the drawer's search line back on the refused file form: the rendered brief must stop passing."""
    from nucleo.workers.prompts import drawer, web
    from tests.worker_briefs import rendered
    orig = drawer._drawer_rules

    def _file_form(py: str = "") -> str:
        return orig(py).replace(_QUOTED, "act use_tool @busca.json")
    monkeypatch.setattr(drawer, "_drawer_rules", _file_form)
    monkeypatch.setattr(web, "_drawer_rules", _file_form)
    text = rendered("find the cheapest 27-inch 4K monitor in Barcelona")
    assert "@busca.json" in text, "the mutation did not land in the rendered brief"
    assert not _teaches_the_quoted_form(text)


def test_the_disarm_a_relay_back_on_the_file_form_is_caught(monkeypatch):
    """Rebuild `_relay_search` with its spoken line on the refused file form: the relay test's check must flip."""
    import types

    from nucleo.workers import session_events
    fn = session_events._relay_search
    consts = tuple(c.replace(_QUOTED, "act use_tool @busca.json") if isinstance(c, str) else c
                   for c in fn.__code__.co_consts)
    assert consts != fn.__code__.co_consts, "the mutation did not land in the relay's line"
    mutated = types.FunctionType(fn.__code__.replace(co_consts=consts), fn.__globals__, fn.__name__)
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    w = _Worker()
    mutated(w)
    msg = w._rec.injects[0].text
    assert "@busca.json" in msg and _QUOTED not in msg


def test_use_tool_returns_the_chain_dict_plus_the_service_fields(monkeypatch):
    from nucleo.cli import worker_api
    from search import web
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "El Prado abre a las 10.", "source": "openai", "ai": True,
        "results": [{"title": "Prado — horarios", "snippet": "", "url": "https://museodelprado.es/visita"},
                    {"title": "Los 10 mejores museos", "snippet": "", "url": "https://blog/best/museos"}]})
    handed = []
    from nucleo.workers import findings
    monkeypatch.setattr(findings, "hand_web_finding", lambda *a, **k: handed.append(("note", a)))
    monkeypatch.setattr(findings, "hand_search_rows", lambda rec, res: handed.append(("rows", res.get("source"))))

    class Rec:
        task_id = "t-1"
        goal = "horario del Prado"
        sheet = ""

    out = asyncio.run(worker_api._exec_allow("use_tool", {"tool": "web_search", "args": {"query": "horario Prado"}}, Rec()))
    assert out["ok"], out
    res = out["result"]
    assert res["answer"].startswith("El Prado") and res["source"] == "openai" and len(res["results"]) == 2
    assert res["route"] == "inline_fact"
    assert [c["title"] for c in res["candidates"]] == ["Prado — horarios"]
    assert res["pages"][0]["title"] == "Los 10 mejores museos" and res["pages"][0]["why"]
    assert res["unshown"] == []
    assert ("rows", "openai") in handed and any(h[0] == "note" for h in handed)


def test_an_empty_query_still_refuses_loudly():
    from nucleo.cli import worker_api

    class Rec:
        task_id = "t-2"
        goal = ""
        sheet = ""

    out = asyncio.run(worker_api._exec_allow("use_tool", {"tool": "web_search", "args": {}}, Rec()))
    assert not out["ok"] and "query" in out["error"]

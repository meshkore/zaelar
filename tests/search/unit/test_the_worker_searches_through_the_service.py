"""The worker's search goes through the service, in the form a confined worker can actually type (V2-782 T5.3).

F0 (2026-10-10): four workers wrote `busca.json` to a path the confinement guard refused and stayed blind for the
rest of the task, while their built-in search was out of quota. Now `act use_tool "<query>"` — a quoted sentence,
no braces, no file — is the query, and what comes back is the service's result: the chain's dict for the two doors
that already read it, plus the route, the candidates, the pages and what no row shows.
"""
from __future__ import annotations

import asyncio

from nucleo import bridge_usage, dispatch_prompts
from nucleo.workers import session as _session


def test_a_quoted_sentence_after_use_tool_is_the_search():
    assert bridge_usage.bare_query_payload("use_tool", "mejores fontaneros Madrid") == {
        "tool": "web_search", "args": {"query": "mejores fontaneros Madrid"}}
    assert bridge_usage.bare_query_payload("web_search", "monitor 27 4K") == {"query": "monitor 27 4K"}
    assert bridge_usage.bare_query_payload("use_tool", '{"tool": "x"}') is None, "a broken JSON stays a JSON error"
    assert bridge_usage.bare_query_payload("use_tool", "@busca.json") is None, "a file reference is read as a file"
    assert bridge_usage.bare_query_payload("show_widget", "results") is None


def test_the_prompts_teach_the_quoted_form_and_no_file():
    import inspect
    src = inspect.getsource(dispatch_prompts) + inspect.getsource(_session)
    assert 'act use_tool \\"<qué buscas>\\"' in src or 'act use_tool "<qué buscas>"' in src
    assert "busca.json" not in src, "the file form is what the guard refused; it must not be taught any more"


def test_use_tool_returns_the_chain_dict_plus_the_service_fields(monkeypatch):
    from nucleo import worker_api
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
    from nucleo import worker_api

    class Rec:
        task_id = "t-2"
        goal = ""
        sheet = ""

    out = asyncio.run(worker_api._exec_allow("use_tool", {"tool": "web_search", "args": {}}, Rec()))
    assert not out["ok"] and "query" in out["error"]

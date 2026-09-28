"""Demo pass 2026-09-28, R1: «when's the tesla insurance due again?» → «I don't have a Tesla insurance renewal date
on file», with the fact in memory — and the turn capture keeps only the prompt's head and tail, while the MEMORY
block sits in the middle. Nothing on disk could say whether the fact reached the model. The whole prompt goes to
`.meshkore/logs/prompts/<session>.jsonl`, one line per turn, joined to the timeline by `trace`."""
import json


def test_the_capture_writes_the_whole_prompt_beside_the_excerpt(tmp_path, monkeypatch):
    from voice import observer
    monkeypatch.setattr(observer, "PROMPTS_DIR", str(tmp_path))
    monkeypatch.setitem(observer._session_file, "sid", "s-1")
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    middle = "Puede que venga a cuento (de tu memoria): · Tesla insurance renewal due on March 12, 2027."
    system = "HEAD " * 5000 + middle + " TAIL" * 5000
    observer.turn_detail(system=system, window=[{"role": "user", "content": "hi"}], tools=[],
                         user="when's the tesla insurance due again?", decision={"reply": "x"})
    rec = json.loads((tmp_path / "s-1.jsonl").read_text("utf-8").splitlines()[-1])
    assert middle in rec["system"] and rec["user"].startswith("when's")
    assert rec["window"] == [{"role": "user", "content": "hi"}]


def test_a_failed_embedding_keeps_the_providers_words():
    """The same pass ran every recall on FTS alone and the diagnostic said «key, quota or network»; the response
    body said `insufficient_quota`. The failure keeps it, and the retriever's line says it. (The paid call itself
    is stubbed by the suite's conftest — no test reaches the network — so the recording seam is what is tested.)"""
    from pathlib import Path
    from memory import embeddings as E
    E._note_failure(RuntimeError("You have no credits remaining (insufficient_quota)"))
    assert "insufficient_quota" in E.last_error()
    root = Path(__file__).resolve().parents[3]
    assert "_note_failure(e)" in (root / "memory/embeddings.py").read_text("utf-8").split("def _cloud_embed(")[1]
    assert "the provider said: {_why}" in (root / "memory/retriever.py").read_text("utf-8")

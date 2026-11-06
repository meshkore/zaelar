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

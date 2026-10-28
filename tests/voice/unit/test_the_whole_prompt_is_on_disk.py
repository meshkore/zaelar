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


def test_a_failed_embedding_keeps_the_providers_words(monkeypatch):
    """Demo pass R1's second half: the embeddings call was failing and nothing said why — the provider's reply
    body said `insufficient_quota`. Checked at the DOOR: a loopback provider answers 429 with that body, the real
    cloud call (pooled connection, `_post_json`) fails, `last_error()` keeps the provider's words, and the
    retriever's «recall on FTS only» event carries them. No network, no real memory."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from memory import embeddings as E
    from memory import reembed
    from memory.embeddings import cloud
    from memory.retriever import recall
    from voice import observer

    class _NoCredit(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            out = b'{"error": {"message": "You have no credits remaining", "code": "insufficient_quota"}}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _NoCredit)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(E, "_cloud_embed", E._GENUINE_CLOUD_EMBED)      # the suite stubs the network out
        monkeypatch.setattr(E, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "text-embedding-3-small",
                                                    "embed_base_url": f"http://127.0.0.1:{srv.server_port}/v1",
                                                    "embed_api_key": "test-key"})
        monkeypatch.setattr(cloud, "_HTTP", None)
        monkeypatch.setitem(cloud._LAST_ERROR, "v", "")
        E.reset()
        assert E._cloud_embed(["¿cuándo vence el seguro?"]) is None
        assert "insufficient_quota" in E.last_error()

        seen = []
        monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: seen.append(text))
        monkeypatch.setattr(reembed, "signature", lambda: "openai:text-embedding-3-small:768")
        monkeypatch.setattr(reembed, "stored_signature", lambda: "openai:text-embedding-3-small:768")
        monkeypatch.setattr(recall, "_wrong_space_last", 0.0)
        recall._warn_wrong_space()
        assert seen and "the provider said:" in seen[0] and "insufficient_quota" in seen[0], seen
    finally:
        srv.shutdown()
        srv.server_close()
        E.reset()

"""The query's embedding closes inside the recall budget because it does not pay a new connection per turn
(refactor2710-11 T-03).

Measured 2026-10-28: with the reranker off, the vectorial recall costs ~5 ms on a 1 500-pill store; everything
else is the remote embedding of the query. On real traffic a FRESH connection per call took 1.4 s cold and
210-600 ms warm, a reused one 160-250 ms — and the audited session had almost every turn fall back to «recall
léxico entregado» against the 0.8 s budget. The class is the connection, not the budget: raising the budget would
only make every turn slower.

The fixture is a loopback provider that charges `_HANDSHAKE_S` for every NEW connection (what DNS + TCP + TLS +
an egress hop cost) and answers fast on a reused one. No network, no real memory.
"""
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from memory import embeddings as emb
from memory.embeddings import cloud

_HANDSHAKE_S = 0.5
_BUDGET_S = 0.8          # nucleo/turn/recall_budget.py's default


class _Provider(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"       # keep-alive, like the real provider
    connections = 0

    def setup(self):
        type(self).connections += 1
        time.sleep(_HANDSHAKE_S)
        super().setup()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        vecs = [[b / 255 for b in hashlib.sha256(t.encode()).digest()] * 24 for t in body["input"]]
        out = json.dumps({"data": [{"index": i, "embedding": v[:768]} for i, v in enumerate(vecs)],
                          "usage": {"prompt_tokens": 3}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


@pytest.fixture
def provider(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _Provider.connections = 0
    monkeypatch.setattr(emb, "_cloud_embed", emb._GENUINE_CLOUD_EMBED)     # the suite stubs the network out
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "text-embedding-3-small",
                                                  "embed_base_url": f"http://127.0.0.1:{srv.server_port}/v1",
                                                  "embed_api_key": "test-key"})
    monkeypatch.setattr(cloud, "_HTTP", None)                               # a fresh pool for this provider
    emb.reset()
    yield
    srv.shutdown()
    srv.server_close()


def test_after_the_first_turn_every_query_embedding_fits_the_budget(provider):
    queries = ["¿has terminado lo del documento?", "book a table for saturday", "on viu el fuster?",
               "qué te pedí sobre mi estilo", "dónde vivo"]
    took = []
    for q in queries:
        t0 = time.perf_counter()
        assert emb._cloud_embed([q]) is not None
        took.append(time.perf_counter() - t0)
    assert _Provider.connections == 1, f"{_Provider.connections} connections for {len(queries)} turns"
    assert max(took[1:]) < _BUDGET_S / 2, f"a warm turn still paid a handshake: {[round(x, 3) for x in took]}"


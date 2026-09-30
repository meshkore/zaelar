"""full27 A1: «can you find me like three 27 inch 4k monitors…» went through `search_listings`, which launched the
errand; the promise guard counted only some doors as acting, and added «Sorry — I haven't actually looked at that
yet, and nothing is running» to a turn that had just started the search."""
from tests import voice_turn_source as _vts
import pathlib

SRC = _vts.read(pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py")


def test_did_act_counts_every_request_door():
    i = SRC.index("_did_act = bool(")
    block = SRC[i:SRC.index("\n        #", i)]
    for req in ("listing_req", "images_req", "recall_req", "reopen_req", "reveal_req", "search_req", "read_req"):
        assert req in block, req

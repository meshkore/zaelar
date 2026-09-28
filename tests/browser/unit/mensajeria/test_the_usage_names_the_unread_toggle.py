#
# test_the_usage_names_the_unread_toggle.py — demo passes 30, 31 and 33 (2026-09-28).
#
# «oh and leave that inworld one as unread» was answered «the inbox marks things read the moment they're opened,
# and there's no way to flip a message back to unread» three passes in a row, with `unread` declared. The card's
# usage — the one sentence about read state the model reads with the open card — listed read/readchat/clear and
# nothing else, so the model concluded the other direction did not exist. A capability left out of the sentence
# that describes its family is narrated as missing.
#
import json
from pathlib import Path

_MANIFEST = Path(__file__).resolve().parents[4] / "widgets" / "mensajeria" / "manifest.json"


def test_every_read_state_action_is_in_the_usage():
    m = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    usage = m.get("usage") or ""
    for action in ("read", "readchat", "unread"):
        assert action in m["actions"], action
        assert f"{action}" in usage.replace("readchat", " readchat ").split("PROPAGA")[0].split("Marcar leído")[-1], \
            f"`{action}` is declared and missing from the read-state sentence of the usage"

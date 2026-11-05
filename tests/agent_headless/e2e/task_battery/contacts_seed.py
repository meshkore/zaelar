"""A battery sandbox whose directory is the SYNTHETIC one of the contacts test set (V2-854, C14/C15).

The people come from `tests/memory/unit/contacts/directory_fixture.build()` — a few hundred invented rows with the
shape of a real directory (nine «Raquel»s and the favorite «Rakel», five «Catherine»s and the favorite «Katherine»,
groups, e-mail-only and unclassified people). They are written by a CHILD process pointed at the sandbox, through the
contacts store (`seed._run`, the posture every battery seed keeps), and the sandbox's messaging is the LOOPBACK
account for WhatsApp too: a send is appended to `<workspace>/loopback/sent.jsonl`, never delivered.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from tests.memory.unit.contacts import directory_fixture
from tests.platform.sandbox_engine import free_port, spawn_engine, stop_engine

from . import seed
from .probe import Infra, Probe

#: WhatsApp joins the loopback account's platforms: the favorite of the Spanish case is reached by a WhatsApp chat.
PLATFORMS = "telegram,email,whatsapp"

_DIRECTORY = """
import json, sys
from widgets import store
from widgets.contactos import data as cd, model
rows = [model.normalize(r) for r in json.loads(sys.stdin.read())]
db = cd.load_db()
db["contacts"] = rows
db["next_id"] = len(rows) + 1
store.save(cd.WIDGET_ID, db)
print(json.dumps({"count": len(cd.load_db().get("contacts") or [])}))
"""


def seed_directory(workspace: Path) -> list[dict]:
    """Write the synthetic directory into the sandbox. Returns the rows written (READ BACK by count)."""
    rows = directory_fixture.build()
    got = seed._run(Path(workspace), _DIRECTORY, rows)
    if int(got.get("count") or 0) != len(rows):
        raise Infra(f"the sandbox directory holds {got.get('count')} rows, not the {len(rows)} seeded")
    return rows


def boot(workspace: Path, lang: str):
    """An engine of the case's own on the synthetic directory, its language set for the process. Returns
    `(engine, rows by id)`."""
    try:
        rows = seed_directory(workspace)
    except Infra:
        raise
    except Exception as e:  # noqa: BLE001
        raise Infra(f"seeding the synthetic directory failed: {e}") from e
    try:
        eng = spawn_engine(workspace=workspace, port=free_port(), boot_timeout=180.0,
                           extra_env=seed.loopback_env({"ZAELAR_LANGUAGE": lang,
                                                        "ZAELAR_TEST_LOOPBACK_PLATFORMS": PLATFORMS}))
    except Exception as e:  # noqa: BLE001
        raise Infra(f"sandbox did not boot: {e}") from e
    return eng, {r["id"]: r for r in rows}


def store_rows(workspace: Path, widget: str = "contactos") -> dict:
    """The sandbox's store of a card, read as a FILE (read-only; never through a store the test process owns)."""
    f = Path(workspace) / "widgets" / "_data" / widget / "state.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@pytest.fixture
def directory_engine(tmp_path):
    """`directory_engine(lang)` → `(Probe, rows by id)` on an engine of the case's own, the synthetic directory in it."""
    made = []

    def _make(lang: str):
        try:
            eng, rows = boot(tmp_path / f"dir-{lang}", lang)
        except Infra as e:
            pytest.fail(f"INFRA: {e}")
        made.append(eng)
        return Probe(eng, session=f"bat-{uuid.uuid4().hex[:8]}"), rows
    yield _make
    for eng in made:
        stop_engine(eng)

"""Environment loading — the single place that touches os.environ / .env.

Loads the zaelar project-root ``.env`` (shared provider keys). Everything else
reads config via ``core.config``, never the env directly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# voice/engine/core/env.py -> core, engine, voice, <zaelar root>
#   parents[0]=core  parents[1]=engine  parents[2]=voice  parents[3]=ZAELAR_ROOT
# NOTE: the task text said parents[2], but that points at voice/. The zaelar repo
# root (where .env and .meshkore live) is parents[3]; log_dir + dotenv need it.
ZAELAR_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(ZAELAR_ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()

"""Base paths + environment loading, shared by the zaelar server routers."""
import os
import sys

from dotenv import load_dotenv

ZAELAR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../zaelar
# Logging lives in the MeshKore standard location: .meshkore/logs/ (gitignored runtime dir).
LOG_DIR = os.path.join(ZAELAR_DIR, ".meshkore", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

if ZAELAR_DIR not in sys.path:
    sys.path.insert(0, ZAELAR_DIR)
# zaelar is self-contained: its own .env (seeded from the interview prototype's keys).
load_dotenv(os.path.join(ZAELAR_DIR, ".env"), override=True)
# DURABLE credential store (operator convention 2026-07-08): core secrets live in
# .meshkore/credentials/zaelar.env (gitignored, chmod 600) so they are never lost — they are loaded from there.
# Loaded AFTER .env with override=True → the store WINS over .env (same criterion as config/connectors).
load_dotenv(os.path.join(ZAELAR_DIR, ".meshkore", "credentials", "zaelar.env"), override=True)

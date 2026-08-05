"""nucleo/cloud_account.py — "is this process a real paying cloud account" accessor (Fase 3, INI-019
addenda 2026-08-05). Mirrors nucleo/demo_routing.py's is_demo_machine() pattern deliberately: a single
truthy env check behind one accessor, so every gate that needs to distinguish "a real customer's own
Fly Machine" from "self-host" or "the anonymous demo" (energy metering, centralized observability,
provider control) reads the SAME function instead of each re-parsing ZAELAR_USER_ID on its own.

ZAELAR_USER_ID is injected by the provisioner at Machine creation
(cloud/provisioner/src/machineConfig.js::accountMachineConfig) — self-host and the demo never set it.
"""
from __future__ import annotations

import os


def is_cloud_account() -> bool:
    return bool(my_user_id())


def my_user_id() -> str:
    return (os.getenv("ZAELAR_USER_ID") or "").strip()

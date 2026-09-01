#
# bridge_proc.py — lifecycle for the Baileys bridge Node process (vendored, connectors/whatsapp/bridge/).
#
# Starts `node bridge.js --mode observe` (our INI-014 patch: forwards ALL inbound content to triage, without
# replying). The first time it prints a QR in the terminal -> the operator scans it with WhatsApp (Settings ->
# Linked devices). The session stays in connectors/whatsapp/_session/ (gitignored) and no longer asks for QR. We
# inherit stdout so the QR is visible; with WHATSAPP_DEBUG=1 the bridge adds JSON event logs.
#
import asyncio
import os
import shutil

from loguru import logger

from connectors.whatsapp import client, config


class _Bridge:
    def __init__(self):
        self.proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if shutil.which("node") is None:
            raise RuntimeError("node no está en el PATH — el bridge Baileys lo necesita.")
        node_modules = config.bridge_dir() / "node_modules"
        if not node_modules.exists():
            # Self-heal: install bridge deps on first run (so `make run` does not require a manual step).
            if shutil.which("npm") is None:
                raise RuntimeError(f"Faltan deps del bridge y no hay npm. Corre: make install-whatsapp")
            logger.info("WhatsApp: instalando deps del bridge (una vez)… puede tardar ~1 min")
            proc = await asyncio.create_subprocess_exec(
                "npm", "install", cwd=str(config.bridge_dir()),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
            if not node_modules.exists():
                raise RuntimeError(f"npm install del bridge falló. Corre a mano: make install-whatsapp")

        config.session_dir().mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["WHATSAPP_MODE"] = "observe"
        env.setdefault("WHATSAPP_REPLY_PREFIX", "")  # in observe we do not reply; no prefix
        # V2-543 — received media lands DIRECTLY in the messaging widget's own data dir, the one place
        # `GET /widgets/mensajeria/asset/{name}` can serve (flat namespace). Without this the bridge wrote to
        # ~/.hermes/*_cache — downloaded on every receive, served by nothing, garbage-collected by nobody.
        # setdefault: an explicit HERMES_*_CACHE_DIR from the environment still wins (power-user escape hatch).
        try:
            from widgets import store as _wstore
            media_dir = _wstore.data_dir("mensajeria")
            for var in ("HERMES_IMAGE_CACHE_DIR", "HERMES_DOCUMENT_CACHE_DIR", "HERMES_AUDIO_CACHE_DIR"):
                env.setdefault(var, media_dir)
        except Exception as e:
            logger.debug(f"WhatsApp media dir: {e}")   # bridge still runs; media just lands in ~/.hermes

        logger.info(f"WhatsApp bridge → node bridge.js (observe) port={config.bridge_port()}")
        self.proc = await asyncio.create_subprocess_exec(
            "node", "bridge.js",
            "--port", str(config.bridge_port()),
            "--session", str(config.session_dir()),
            "--mode", "observe",
            cwd=str(config.bridge_dir()),
            env=env,
            # inherited stdout/stderr -> pairing QR is visible in the terminal.
        )

    async def wait_connected(self, timeout: float = 180.0) -> bool:
        """Wait until the bridge reports 'connected' (after scanning the QR the first time)."""
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < timeout:
            if self.proc and self.proc.returncode is not None:
                raise RuntimeError(f"el bridge murió (exit {self.proc.returncode})")
            try:
                h = await client.health()
                if (h or {}).get("status") == "connected":
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
        return False

    async def stop(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                self.proc.kill()
        self.proc = None


bridge = _Bridge()

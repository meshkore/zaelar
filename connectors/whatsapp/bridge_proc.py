#
# bridge_proc.py — lifecycle del proceso Node del bridge Baileys (vendorizado, connectors/whatsapp/bridge/).
#
# Arranca `node bridge.js --mode observe` (nuestro parche INI-014: reenvía TODO lo entrante para triaje, sin
# responder). La primera vez imprime un QR en el terminal → el operador lo escanea con WhatsApp (Ajustes →
# Dispositivos vinculados). La sesión queda en connectors/whatsapp/_session/ (gitignored) y ya no vuelve a pedir
# QR. Heredamos stdout para que el QR sea visible; con WHATSAPP_DEBUG=1 el bridge añade logs JSON de eventos.
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
            # Self-heal: instala las deps del bridge la 1ª vez (para que `make run` no requiera un paso manual).
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
        env.setdefault("WHATSAPP_REPLY_PREFIX", "")  # en observe no respondemos; sin prefijo

        logger.info(f"WhatsApp bridge → node bridge.js (observe) port={config.bridge_port()}")
        self.proc = await asyncio.create_subprocess_exec(
            "node", "bridge.js",
            "--port", str(config.bridge_port()),
            "--session", str(config.session_dir()),
            "--mode", "observe",
            cwd=str(config.bridge_dir()),
            env=env,
            # stdout/stderr heredados → el QR de emparejamiento se ve en el terminal.
        )

    async def wait_connected(self, timeout: float = 180.0) -> bool:
        """Espera a que el bridge reporte 'connected' (tras escanear el QR la 1ª vez)."""
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

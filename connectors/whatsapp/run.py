#
# run.py — runnable STANDALONE de la Fase 1 (INI-014): arranca el bridge, te muestra el QR para vincular
# WhatsApp, y a partir de ahí lee tu buzón, tría cada lote con el modelo LOCAL y te imprime un digest de "solo
# lo que importa", marcando como leído lo ya resumido. NO responde a nadie (read-only + mark-read).
#
# Uso:   python -m connectors.whatsapp
# La 1ª vez: escanea el QR (WhatsApp → Ajustes → Dispositivos vinculados). Luego la sesión persiste.
# Corta con Ctrl-C.
#
import asyncio

from loguru import logger

from connectors.messaging import triage
from connectors.whatsapp import client, config
from connectors.whatsapp.bridge_proc import bridge


def _fmt(v: dict) -> str:
    origin = f"grupo {v.get('chatName','?')}" if v.get("isGroup") else f"{v.get('senderName','?')}"
    flag = "★" if v.get("urgencia") == "alta" else ("•" if v.get("urgencia") == "media" else "·")
    dm = "→tú " if v.get("dirigido_a_mi") else "    "
    body = (v.get("body") or "").replace("\n", " ")[:70]
    return f"  {flag} {dm}[{origin}] {body}   « {v.get('motivo','')} »"


async def _tick() -> None:
    msgs = await client.get_messages()
    if not msgs:
        return
    verdicts = await triage.classify(msgs)
    # "merece atención" = importante Y (dirigido a mí o urgencia alta). Afinable.
    surfaced = [v for v in verdicts
                if v.get("importante") and (v.get("dirigido_a_mi") or v.get("urgencia") == "alta")]
    ignored = [v for v in verdicts if v not in surfaced]

    if surfaced:
        print(f"\n📥 {len(surfaced)} mensaje(s) que quizá quieras ver "
              f"(de {len(msgs)} nuevos; {len(ignored)} filtrados):")
        for v in sorted(surfaced, key=lambda x: {"alta": 0, "media": 1, "baja": 2}.get(x.get("urgencia"), 3)):
            print(_fmt(v))
    else:
        logger.info(f"{len(msgs)} mensaje(s) nuevos, nada que merezca atención")

    # Marcar leído SOLO lo ya triado y resumido (lo que te mostramos). Lo filtrado se deja sin tocar por ahora.
    keys = [{"chatId": v["chatId"], "messageId": v["messageId"], "senderId": v.get("senderId")}
            for v in surfaced if v.get("chatId") and v.get("messageId")]
    if keys:
        try:
            await client.mark_read(keys)
        except Exception as e:
            logger.warning(f"mark-read falló: {e}")


async def main() -> None:
    print(f"▶ Clasificador: {config.triage_model()} @ {config.triage_url()}")
    await bridge.start()
    print("⏳ Esperando conexión de WhatsApp… (si es la 1ª vez, escanea el QR de arriba)")
    try:
        if not await bridge.wait_connected():
            print("✗ No se conectó a WhatsApp a tiempo.")
            return
        print("✅ WhatsApp conectado. Escuchando tu buzón (Ctrl-C para parar).")
        while True:
            try:
                await _tick()
            except Exception as e:
                logger.warning(f"tick falló: {e}")
            await asyncio.sleep(config.poll_interval())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n⏹ Parando…")
    finally:
        await bridge.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

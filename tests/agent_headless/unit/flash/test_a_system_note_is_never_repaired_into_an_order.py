"""A [SISTEMA] note is not an order — the act repair never invents a call for it (V2-781, compare-insurance-quotes).

The browser task reported «[SISTEMA] Navegador (tarea t1): la web BLOQUEÓ…»; the model narrated it; the promise
repair read that turn as the operator's order, invented `navegador:open {url: mutuamadrilena.es}`, cleared the
words, and the conversation's last reply was «Hecho.» over the comparison he was waiting for.
"""
import asyncio

from nucleo.flash import act_repair


def test_a_system_note_gets_no_repaired_call(monkeypatch):
    from nucleo.flash import fast_client

    class _FC:
        async def complete(self, messages, *, on_tool_call=None, **kw):
            on_tool_call("widget_data", {"widget_id": "navegador", "action": "open", "payload": {"url": "example.com"}})
            return ""
    monkeypatch.setattr(fast_client, "FastClient", _FC)
    note = "[SISTEMA] Navegador (tarea t1): la web BLOQUEÓ «Comparar aseguradoras de coche…»"
    got = asyncio.new_event_loop().run_until_complete(
        act_repair.call_for_promise(note, "Voy a probar en otra web.", "navegador"))
    assert got is None

"""A backed widget's owner can be asked from a thread (demo pass 30, E1 → E2).

A widget read runs in `asyncio.to_thread`; the owner's mailbox is an asyncio Queue, which is not thread-safe.
`enqueue_from_thread` hands the put to the owner's own loop, so the command lands and the owner wakes up.
"""
import asyncio
import threading

from widgets import supervisor as S


class _Svc:
    def __init__(self, loop):
        self.queue = asyncio.Queue()
        self.task = loop.create_task(asyncio.sleep(3600))
        self.disabled = False

    def enqueue(self, action, payload):
        self.queue.put_nowait((action, payload))
        return True


def test_a_command_from_a_thread_reaches_the_owner(monkeypatch):
    async def main():
        svc = _Svc(asyncio.get_running_loop())
        monkeypatch.setitem(S._services, "mensajeria", svc)
        t = threading.Thread(target=lambda: S.enqueue_from_thread("mensajeria", "search_archive", {"q": "inworld"}))
        t.start()
        t.join()
        got = await asyncio.wait_for(svc.queue.get(), timeout=2)
        svc.task.cancel()
        return got
    assert asyncio.run(main()) == ("search_archive", {"q": "inworld"})


def test_no_owner_is_no_command():
    assert S.enqueue_from_thread("nope-not-a-widget", "x", {}) is False

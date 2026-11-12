"""Fan-out of replay messages to WebSocket and SSE clients.

Every client gets its own bounded queue, so a slow client can never stall the
scheduler or other clients. If a client's queue overflows, its backlog is dropped
and replaced by a fresh snapshot (a `reset`), so it resynchronises instead of
seeing a gap. Single event loop only (like ReplayState).
"""
from __future__ import annotations

import asyncio
from typing import Callable


class Subscriber:
    def __init__(self, maxsize: int = 256):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    def push(self, message: dict) -> bool:
        try:
            self.queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            return False

    def replace_backlog(self, message: dict) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(message)


class ConnectionHub:
    def __init__(self):
        self._subs: dict[str, set[Subscriber]] = {}

    def subscribe(self, replay_id: str, first_message: dict | None = None) -> Subscriber:
        """Register a client. `first_message` (the snapshot) is queued before anything else,
        and because nothing awaits in between, no later message can overtake it."""
        sub = Subscriber()
        if first_message is not None:
            sub.push(first_message)
        self._subs.setdefault(replay_id, set()).add(sub)
        return sub

    def unsubscribe(self, replay_id: str, sub: Subscriber) -> None:
        subs = self._subs.get(replay_id)
        if subs:
            subs.discard(sub)
            if not subs:
                self._subs.pop(replay_id, None)

    def count(self, replay_id: str) -> int:
        return len(self._subs.get(replay_id, ()))

    def publish(self, replay_id: str, message: dict, resync: Callable[[], dict]) -> None:
        snapshot = None
        for sub in list(self._subs.get(replay_id, ())):
            if not sub.push(message):
                snapshot = snapshot or resync()
                sub.replace_backlog(snapshot)

    def drop(self, replay_id: str) -> None:
        self._subs.pop(replay_id, None)

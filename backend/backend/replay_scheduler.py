"""Async scheduler: wakes exactly when the next recorded event is due.

No fixed polling delay between records: the sleep is the recorded timestamp gap
divided by the playback speed (ReplayClock.seconds_until_next). While playing it
also wakes at most every HEARTBEAT seconds so the UI progress bar advances; while
paused it sleeps until a control call pokes it. A tiny floor (MIN_SLEEP) coalesces
events that are less than a few milliseconds apart into one batch; their
timestamps are untouched.
"""
from __future__ import annotations

import asyncio
from typing import Callable

HEARTBEAT = 0.5
MIN_SLEEP = 0.005


class ReplayScheduler:
    def __init__(self, delay: Callable[[], float | None], tick: Callable[[], None]):
        self._delay = delay          # state.seconds_until_next
        self._tick = tick            # settle + publish (sync, atomic)
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())

    def poke(self) -> None:
        """Re-evaluate the next wake-up now (call after any control change)."""
        self._wake.set()

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def timeout(self) -> float | None:
        delay = self._delay()
        return None if delay is None else min(max(delay, MIN_SLEEP), HEARTBEAT)

    async def _run(self) -> None:
        try:
            while True:
                try:
                    await asyncio.wait_for(self._wake.wait(), self.timeout())
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                self._tick()
        except asyncio.CancelledError:
            pass

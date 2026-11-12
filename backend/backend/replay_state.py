"""Per-replay state: one ReplayClock plus the bookkeeping the API needs.

All methods are synchronous and never await, so on the event loop each call is
atomic with respect to every other coroutine: no locks are needed as long as the
HTTP/WebSocket handlers are `async def` (they are). Never call these from threads.
"""
from __future__ import annotations

import time
from datetime import datetime

from backend.replay import Event, Timeline
from backend.replay_clock import ReplayClock

# Position/interval rows are dense (tens of thousands per race). A snapshot only
# needs the latest one per driver; full history is available through SQL analytics.
LATEST_ONLY = ('position', 'interval')


def event_json(e: Event) -> dict:
    return {'t': e.t.isoformat(), 'kind': e.kind, 'driver_number': e.driver_number,
            'lap_number': e.lap_number, 'data': e.data}


class ReplayState:
    def __init__(self, replay_id: str, timeline: Timeline, monotonic=time.monotonic, speed: float = 1.0):
        meta = timeline.meta
        self.id = replay_id
        self.timeline = timeline
        self.clock = ReplayClock(timeline.events, start=meta.get('start'), end=meta.get('end'), speed=speed)
        self.epoch = 0                      # bumped on seek/reset: subscribers must resync
        self.current_lap = 0                # highest lap any driver has started
        self.total_laps = meta.get('total_laps')
        self.created_at = time.time()
        self.last_active = self.created_at
        self._monotonic = monotonic
        self._last = monotonic()

    # ---- time ------------------------------------------------------------
    def touch(self) -> None:
        self.last_active = time.time()

    def settle(self) -> list[Event]:
        """Advance the clock by the real time elapsed since the last call; return newly due events."""
        now = self._monotonic()
        elapsed, self._last = max(0.0, now - self._last), now
        due = self.clock.advance(elapsed)
        self._note_laps(due)
        return due

    def seconds_until_next(self) -> float | None:
        return self.clock.seconds_until_next()

    def _note_laps(self, events) -> None:
        for e in events:
            if e.kind == 'lap_start' and e.lap_number and e.lap_number > self.current_lap:
                self.current_lap = e.lap_number

    def _recount_laps(self) -> None:
        self.current_lap = 0
        self._note_laps(self.clock.seen())

    # ---- controls (call settle() first and publish what it returns) -----------
    def play(self) -> None:
        self.clock.play()

    def pause(self) -> None:
        self.clock.pause()

    def set_speed(self, speed) -> None:
        self.clock.set_speed(speed)

    def seek(self, t: datetime | None = None, offset_seconds: float | None = None) -> None:
        if t is not None:
            self.clock.seek(t)
        else:
            self.clock.seek_offset(offset_seconds)
        self.epoch += 1
        self._recount_laps()

    def restart(self) -> None:
        self.clock.pause()
        self.clock.seek(self.clock.start)
        self.epoch += 1
        self._recount_laps()

    # ---- views -----------------------------------------------------------
    def state_dict(self) -> dict:
        c = self.clock
        return {'replay_id': self.id, 'session_key': self.timeline.session_key,
                'state': c.state, 'speed': c.speed, 'now': c.now.isoformat(),
                'start': c.start.isoformat(), 'end': c.end.isoformat(),
                'elapsed': c.elapsed, 'duration': c.duration, 'finished': c.finished,
                'epoch': self.epoch, 'current_lap': self.current_lap, 'total_laps': self.total_laps,
                'race_name': self.timeline.meta.get('race_name')}

    def snapshot_events(self) -> list[Event]:
        """Everything seen so far, with dense position/interval rows reduced to the latest per driver."""
        keep, latest = [], {}
        for e in self.clock.seen():
            if e.kind in LATEST_ONLY:
                latest[(e.kind, e.driver_number)] = e
            else:
                keep.append(e)
        return sorted(keep + list(latest.values()), key=Event.sort_key)

    def drivers_json(self) -> list[dict]:
        return [{'driver_number': n, 'code': d.get('name_acronym'), 'name': d.get('full_name'),
                 'team': d.get('team_name'), 'team_colour': d.get('team_colour')}
                for n, d in self.timeline.drivers.items()]

    def reset_message(self) -> dict:
        return {'type': 'reset', 'state': self.state_dict(),
                'events': [event_json(e) for e in self.snapshot_events()],
                'drivers': self.drivers_json()}

    def state_message(self) -> dict:
        return {'type': 'state', 'state': self.state_dict()}

    @staticmethod
    def events_message(events, epoch: int) -> dict:
        return {'type': 'events', 'epoch': epoch, 'events': [event_json(e) for e in events]}

"""Historical replay, step 2: a pure virtual clock over a time-ordered event list.

No wall clock, no network, no threads: the caller says how much real time has
passed via advance(). That keeps it deterministic and trivially testable.

Semantics
- Virtual time never exceeds `end`. Events are "due" when event.t <= virtual time.
- advance() returns each event exactly once, in order, only while playing.
- seek() never returns events. It moves the cursor so that everything with
  t <= target counts as already seen (use `seen()` to rebuild a snapshot);
  everything after the target is still in the future and will be emitted later.
- Reaching `end` pauses the clock. play() at the end is a no-op; seek back first.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import datetime, timedelta

MIN_SPEED = 0.25
MAX_SPEED = 10.0
PLAYING = 'playing'
PAUSED = 'paused'


class ReplayClock:
    def __init__(self, events, start: datetime | None = None, end: datetime | None = None, speed: float = 1.0):
        self._events = list(events)
        self._times = [e.t for e in self._events]
        if any(a > b for a, b in zip(self._times, self._times[1:])):
            raise ValueError('events must be sorted by time')
        if start is None or end is None:
            if not self._events:
                raise ValueError('start and end are required when there are no events')
        self.start = start if start is not None else self._times[0]
        self.end = end if end is not None else self._times[-1]
        if self.end < self.start:
            raise ValueError('end must not be before start')
        self._speed = MIN_SPEED  # replaced by the validated value just below
        self.set_speed(speed)
        self._state = PAUSED
        self._now = self.start
        self._cursor = 0  # index of the next event not yet emitted/seen

    # ---- read-only state -------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def now(self) -> datetime:
        return self._now

    @property
    def finished(self) -> bool:
        return self._now >= self.end

    @property
    def elapsed(self) -> float:
        return (self._now - self.start).total_seconds()

    @property
    def duration(self) -> float:
        return (self.end - self.start).total_seconds()

    def seen(self) -> list:
        """Every event with t <= current virtual time (never a future one)."""
        return self._events[:bisect_right(self._times, self._now)]

    # ---- controls --------------------------------------------------------
    def play(self) -> None:
        if not self.finished:
            self._state = PLAYING

    def pause(self) -> None:
        self._state = PAUSED

    def set_speed(self, speed: float) -> None:
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed):
            raise ValueError('speed must be a finite number')
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError(f'speed must be between {MIN_SPEED} and {MAX_SPEED}')
        self._speed = float(speed)

    def seek(self, t: datetime) -> None:
        """Jump to t (clamped to [start, end]). Emits nothing; keeps play/pause state."""
        if not isinstance(t, datetime) or t.tzinfo is None:
            raise ValueError('seek target must be a timezone-aware datetime')
        self._now = min(max(t, self.start), self.end)
        self._cursor = bisect_right(self._times, self._now)
        if self.finished:
            self._state = PAUSED

    def seek_offset(self, seconds: float) -> None:
        """Seek to `start + seconds` (convenience for slider positions)."""
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds):
            raise ValueError('offset must be a finite number')
        self.seek(self.start + timedelta(seconds=seconds))

    # ---- time ------------------------------------------------------------
    def seconds_until_next(self) -> float | None:
        """Real seconds until the next unseen event (or the end) at the current speed.

        None when not playing. This is what lets a scheduler sleep exactly as long as
        the recorded timestamp gap demands, instead of polling on a fixed delay.
        """
        if self._state != PLAYING:
            return None
        target = self._times[self._cursor] if self._cursor < len(self._times) else self.end
        target = min(target, self.end)
        return max(0.0, (target - self._now).total_seconds() / self._speed)

    def advance(self, real_elapsed_seconds: float) -> list:
        """Move virtual time by real_elapsed * speed (if playing); return newly due events."""
        if not math.isfinite(real_elapsed_seconds) or real_elapsed_seconds < 0:
            raise ValueError('real_elapsed_seconds must be a finite, non-negative number')
        if self._state != PLAYING:
            return []
        self._now = min(self.end, self._now + timedelta(seconds=real_elapsed_seconds * self._speed))
        stop = bisect_right(self._times, self._now)
        due = self._events[self._cursor:stop]
        self._cursor = max(self._cursor, stop)
        if self.finished:
            self._state = PAUSED
        return due

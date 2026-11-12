"""Replay service: loads races from PostgreSQL and manages per-user replays.

Historical tables stay immutable. The timeline is read once per session (cached,
shared read-only between users); each user gets their own ReplayState + scheduler,
so clocks never leak between users. The event rules here are the same ones the
`replay.*` SQL views apply, and tests check the two agree.
"""
from __future__ import annotations

import asyncio
import os
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from backend import replay
from backend.replay import Event, Timeline
from backend.replay_scheduler import ReplayScheduler
from backend.replay_state import ReplayState
from backend.websocket_manager import ConnectionHub

load_dotenv(Path(__file__).resolve().parent.parent.parent / '.env')

DEMO_ID = 'demo'            # offline snapshot replay used when no replay_id is given
IDLE_TTL_SECONDS = 30 * 60
TIMELINE_CACHE_SIZE = 4


class ReplayNotReady(ValueError):
    """The race has no lap start times yet (run the replay migration and F1_BACKFILL=1)."""


def connect():
    return psycopg.connect(
        host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'f1_analytics'), user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD'))


def _f(x):
    return None if x is None else float(x)


# ---- reading the database ------------------------------------------------------
def list_sessions() -> list[dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT s.session_id, r.season, r.round_number, r.race_name, c.circuit_name, c.country, r.race_date,
                   (SELECT MAX(l.lap_number) FROM laps l JOIN session_drivers sd USING (session_driver_id)
                     WHERE sd.session_id = s.session_id) AS total_laps,
                   EXISTS (SELECT 1 FROM laps l JOIN session_drivers sd USING (session_driver_id)
                            WHERE sd.session_id = s.session_id AND l.lap_start_at IS NOT NULL) AS replay_ready
            FROM sessions s JOIN races r ON r.race_id = s.race_id JOIN circuits c ON c.circuit_id = r.circuit_id
            WHERE s.session_type = 'Race'
            ORDER BY r.season DESC, r.round_number""")
        cols = ['session_id', 'season', 'round_number', 'race_name', 'circuit_name', 'country', 'race_date',
                'total_laps', 'replay_ready']
        return [dict(zip(cols, row), race_date=str(row[6])) for row in cur.fetchall()]


def load_timeline_db(session_id: int) -> Timeline:
    """All replayable events of one race, using the same visibility rules as the replay.* views."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT r.race_name FROM sessions s JOIN races r ON r.race_id = s.race_id
                       WHERE s.session_id = %s""", (session_id,))
        row = cur.fetchone()
        if not row:
            raise LookupError(f'unknown session {session_id}')
        race_name = row[0]

        cur.execute("""SELECT d.driver_number, d.driver_code, d.driver_name, t.team_name
                       FROM session_drivers sd JOIN drivers d ON d.driver_id = sd.driver_id
                       LEFT JOIN teams t ON t.team_id = sd.team_id WHERE sd.session_id = %s""", (session_id,))
        drivers = {n: {'name_acronym': code, 'full_name': name, 'team_name': team, 'team_colour': None}
                   for n, code, name, team in cur.fetchall()}

        cur.execute("""SELECT d.driver_number, l.lap_number, l.lap_start_at, l.lap_end_at, l.lap_time_seconds,
                              l.sector1_seconds, l.sector2_seconds, l.sector3_seconds, l.speed_trap_kmh, l.is_valid
                       FROM laps l JOIN session_drivers sd ON sd.session_driver_id = l.session_driver_id
                       JOIN drivers d ON d.driver_id = sd.driver_id
                       WHERE sd.session_id = %s AND l.lap_start_at IS NOT NULL""", (session_id,))
        lap_rows = cur.fetchall()
        if not lap_rows:
            raise ReplayNotReady('this race has no lap start times; apply queries/13_replay_time_aware.sql '
                                 'and run F1_BACKFILL=1 python backend/import_f1.py')

        events: list[Event] = []
        lap_times = {}                          # (driver, lap) -> (start, end)
        for num, lap, start, end, dur, s1, s2, s3, spd, valid in lap_rows:
            lap_times[(num, lap)] = (start, end)
            events.append(Event(start, 'lap_start', num, lap, {}))
            if end is not None:
                events.append(Event(end, 'lap_complete', num, lap, {
                    'lap_duration': _f(dur), 'sector_1': _f(s1), 'sector_2': _f(s2), 'sector_3': _f(s3),
                    'st_speed': _f(spd), 'is_valid': bool(valid)}))
        starts = [s for s, _ in lap_times.values()]
        ends = [e for _, e in lap_times.values() if e is not None]

        # Pit stop: visible once the car has left the pit lane (entry + lane duration).
        cur.execute("""SELECT d.driver_number, p.lap_number, p.stop_number, p.pit_timestamp,
                              p.lane_duration_seconds, p.stop_duration_seconds
                       FROM pit_stops p JOIN session_drivers sd ON sd.session_driver_id = p.session_driver_id
                       JOIN drivers d ON d.driver_id = sd.driver_id
                       WHERE sd.session_id = %s AND p.pit_timestamp IS NOT NULL""", (session_id,))
        for num, lap, stop_no, entered, lane, stop in cur.fetchall():
            exit_at = entered + timedelta(seconds=float(lane or 0))
            events.append(Event(exit_at, 'pit_stop', num, lap, {
                'stop_number': stop_no, 'entered_at': entered.isoformat(),
                'lane_duration': _f(lane), 'stop_duration': _f(stop)}))

        cur.execute("""SELECT d.driver_number, rc.recorded_at, rc.lap_number, rc.category, rc.flag, rc.scope,
                              rc.sector, rc.message
                       FROM race_control_events rc LEFT JOIN drivers d ON d.driver_id = rc.driver_id
                       WHERE rc.session_id = %s""", (session_id,))
        for num, when, lap, cat, flag, scope, sector, message in cur.fetchall():
            events.append(Event(when, 'race_control', num, lap, {
                'category': cat, 'flag': flag, 'scope': scope, 'sector': sector, 'message': message}))

        cur.execute("""SELECT recorded_at, air_temperature, track_temperature, humidity, rainfall, wind_speed
                       FROM weather_samples WHERE session_id = %s AND recorded_at IS NOT NULL""", (session_id,))
        for when, air, track, hum, rain, wind in cur.fetchall():
            events.append(Event(when, 'weather', None, None, {
                'air_temperature': _f(air), 'track_temperature': _f(track), 'humidity': _f(hum),
                'rainfall': rain, 'wind_speed': _f(wind)}))

        cur.execute("""SELECT d.driver_number, p.recorded_at, p.position, p.gap_to_leader_seconds,
                              p.interval_ahead_seconds
                       FROM positions p JOIN session_drivers sd ON sd.session_driver_id = p.session_driver_id
                       JOIN drivers d ON d.driver_id = sd.driver_id WHERE sd.session_id = %s""", (session_id,))
        for num, when, pos, gap, ahead in cur.fetchall():
            if pos is not None:
                events.append(Event(when, 'position', num, None, {'position': pos}))
            if gap is not None or ahead is not None:
                events.append(Event(when, 'interval', num, None, {
                    'gap_to_leader': _f(gap), 'interval_ahead': _f(ahead)}))

        # Tyre stints: start once the driver has begun a lap in the stint; end once the end lap is complete.
        cur.execute("""SELECT d.driver_number, ts.stint_number, ts.compound, ts.start_lap, ts.end_lap,
                              ts.starting_tyre_age
                       FROM tyre_stints ts JOIN session_drivers sd ON sd.session_driver_id = ts.session_driver_id
                       JOIN drivers d ON d.driver_id = sd.driver_id WHERE sd.session_id = %s""", (session_id,))
        by_driver: dict[int, list[int]] = {}
        for (num, lap) in lap_times:
            by_driver.setdefault(num, []).append(lap)
        for laps in by_driver.values():
            laps.sort()
        for num, stint_no, compound, start_lap, end_lap, age in cur.fetchall():
            first = next((l for l in by_driver.get(num, ()) if l >= start_lap), None)
            if first is None:
                continue
            base = {'stint_number': stint_no, 'compound': compound, 'start_lap': start_lap,
                    'starting_tyre_age': age}
            events.append(Event(lap_times[(num, first)][0], 'stint', num, start_lap,
                                {**base, 'phase': 'start', 'end_lap': None}))
            end_time = lap_times.get((num, end_lap), (None, None))[1] if end_lap is not None else None
            if end_time is not None:
                events.append(Event(end_time, 'stint', num, end_lap, {**base, 'phase': 'end', 'end_lap': end_lap}))

    return Timeline(session_id, replay.merge(events), drivers, {},
                    meta={'start': min(starts), 'end': max(ends or starts), 'race_name': race_name, 'db_session_id': session_id,
                          'total_laps': max(l for _, l in lap_times)})


# ---- managing per-user replays ---------------------------------------------------
@dataclass
class Entry:
    state: ReplayState
    scheduler: ReplayScheduler


class ReplayService:
    def __init__(self, hub: ConnectionHub | None = None, loader=load_timeline_db, monotonic=None):
        self.hub = hub or ConnectionHub()
        self._loader = loader
        self._monotonic = monotonic
        self._entries: dict[str, Entry] = {}
        self._cache: OrderedDict[int, Timeline] = OrderedDict()
        self._load_locks: dict[int, asyncio.Lock] = {}

    # -- timelines (immutable, shared read-only) ----------------------------------
    async def timeline(self, session_id: int) -> Timeline:
        if session_id in self._cache:
            self._cache.move_to_end(session_id)
            return self._cache[session_id]
        lock = self._load_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            if session_id not in self._cache:
                self._cache[session_id] = await asyncio.to_thread(self._loader, session_id)
                while len(self._cache) > TIMELINE_CACHE_SIZE:
                    self._cache.popitem(last=False)
            return self._cache[session_id]

    # -- lifecycle ----------------------------------------------------------------
    def _register(self, replay_id: str, timeline: Timeline, speed: float = 1.0) -> Entry:
        kw = {'monotonic': self._monotonic} if self._monotonic else {}
        state = ReplayState(replay_id, timeline, speed=speed, **kw)
        entry = Entry(state, None)
        entry.scheduler = ReplayScheduler(state.seconds_until_next, lambda: self._tick(entry))
        self._entries[replay_id] = entry
        return entry

    async def create(self, session_id: int, speed: float = 1.0) -> Entry:
        self.purge_idle()
        timeline = await self.timeline(session_id)
        return self._register(secrets.token_hex(16), timeline, speed)

    def install(self, replay_id: str, timeline: Timeline) -> Entry:
        """Register a ready-made timeline (the offline demo snapshot, or a test fixture)."""
        return self._register(replay_id, timeline)

    async def resolve(self, replay_id: str | None) -> Entry:
        replay_id = replay_id or DEMO_ID
        entry = self._entries.get(replay_id)
        if entry is None and replay_id == DEMO_ID:
            entry = self.install(DEMO_ID, await asyncio.to_thread(replay.load_timeline))
        if entry is None:
            raise KeyError(replay_id)
        entry.state.touch()
        return entry

    def stop(self, replay_id: str) -> bool:
        entry = self._entries.pop(replay_id, None)
        if entry:
            entry.scheduler.stop()
            self.hub.drop(replay_id)
        return entry is not None

    def purge_idle(self, ttl: float = IDLE_TTL_SECONDS) -> int:
        import time
        stale = [rid for rid, e in self._entries.items()
                 if rid != DEMO_ID and self.hub.count(rid) == 0 and time.time() - e.state.last_active > ttl]
        for rid in stale:
            self.stop(rid)
        return len(stale)

    # -- time + publishing (sync, atomic on the event loop) -------------------------
    def _publish(self, entry: Entry, message: dict) -> None:
        self.hub.publish(entry.state.id, message, resync=entry.state.reset_message)

    def _tick(self, entry: Entry) -> None:
        state = entry.state
        due = state.settle()
        if due:
            self._publish(entry, state.events_message(due, state.epoch))
        if state.clock.state == 'playing' or due:
            self._publish(entry, state.state_message())
        elif state.clock.finished:
            self._publish(entry, state.state_message())

    def sync(self, entry: Entry) -> None:
        """Bring the clock up to the present moment (publishes any events that became due)."""
        entry.state.touch()
        self._tick(entry)

    def control(self, entry: Entry, action: str, **params) -> dict:
        """Apply a control action. Events that were due before the change are published first,
        so nothing is lost; a seek/reset then sends every subscriber a fresh snapshot."""
        state = entry.state
        state.touch()
        due = state.settle()
        if due:
            self._publish(entry, state.events_message(due, state.epoch))
        epoch_before = state.epoch
        try:
            if action in ('play', 'resume'):
                state.play()
            elif action == 'pause':
                state.pause()
            elif action == 'speed':
                state.set_speed(params.get('speed'))
            elif action == 'seek':
                state.seek(t=params.get('t'), offset_seconds=params.get('offset_seconds'))
            elif action in ('reset', 'restart'):
                state.restart()
            else:
                raise ValueError(f'unknown action {action!r}')
        finally:
            if state.epoch != epoch_before:
                self._publish(entry, state.reset_message())
            else:
                self._publish(entry, state.state_message())
            if state.clock.state == 'playing':
                entry.scheduler.start()
            entry.scheduler.poke()
        return state.state_dict()


_service: ReplayService | None = None


def get_service() -> ReplayService:
    global _service
    if _service is None:
        _service = ReplayService()
    return _service


def set_service(service: ReplayService | None) -> None:
    """Replace (or clear) the process-wide service; used by tests."""
    global _service
    _service = service

"""Historical replay, step 1: turn one saved session into a time-ordered event list.

Offline only: reads files under demo_data/ and never touches the network or
any API key. Lap start times come from the RAW laps snapshot because the
processed bundle (clean_laps) drops `date_start`.

Leak rule: a lap's duration is only known once the lap is finished, so each lap
yields a `lap_start` event (no timing info) at `date_start` and a
`lap_complete` event (with times) at `date_start + lap_duration`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import demo_core as core

# Tie-break order for events with an identical timestamp.
KIND_ORDER = {'weather': 0, 'race_control': 1, 'interval': 2, 'position': 3, 'pit_stop': 4,
              'stint': 5, 'lap_complete': 6, 'lap_start': 7}


@dataclass(frozen=True)
class Event:
    t: datetime                      # timezone-aware UTC
    kind: str                        # one of KIND_ORDER
    driver_number: int | None = None
    lap_number: int | None = None
    data: dict = field(default_factory=dict, compare=False, hash=False)

    def sort_key(self):
        return (self.t, KIND_ORDER[self.kind], self.driver_number or 0, self.lap_number or 0)


@dataclass
class Timeline:
    session_key: int
    events: list[Event]
    drivers: dict[int, dict]
    skipped: dict[str, list]         # reason -> offending records (summarised)
    meta: dict = field(default_factory=dict)   # optional: start, end, total_laps, race_name ...

    @property
    def start(self) -> datetime | None:
        return self.events[0].t if self.events else None

    @property
    def end(self) -> datetime | None:
        return self.events[-1].t if self.events else None


def parse_time(value) -> datetime | None:
    """ISO-8601 -> aware UTC datetime. None for missing/naive/invalid values."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def lap_events(laps, skipped=None):
    """OpenF1 lap rows -> lap_start / lap_complete events."""
    skipped = skipped if skipped is not None else {}
    events, seen = [], set()
    by_driver: dict[int, dict[int, dict]] = {}
    for row in laps:
        driver, lap = row.get('driver_number'), row.get('lap_number')
        if type(driver) is not int or type(lap) is not int:
            skipped.setdefault('lap_bad_identity', []).append(row)
            continue
        if (driver, lap) in seen:
            skipped.setdefault('lap_duplicate', []).append((driver, lap))
            continue
        seen.add((driver, lap))
        by_driver.setdefault(driver, {})[lap] = row

    for driver, rows in by_driver.items():
        for lap, row in rows.items():
            start = parse_time(row.get('date_start'))
            if start is None:
                skipped.setdefault('lap_no_start_time', []).append((driver, lap))
                continue
            events.append(Event(start, 'lap_start', driver, lap, {'is_pit_out_lap': row.get('is_pit_out_lap')}))

            duration = _number(row.get('lap_duration'))
            if duration is not None and duration > 0:
                end = start + timedelta(seconds=duration)
            else:
                # Duration unknown: the lap still ended when the next one began.
                end = parse_time((rows.get(lap + 1) or {}).get('date_start'))
                if end is None or end <= start:
                    end = None
                    skipped.setdefault('lap_no_completion_time', []).append((driver, lap))
            if end is not None:
                events.append(Event(end, 'lap_complete', driver, lap, {
                    'lap_duration': duration if duration and duration > 0 else None,
                    'sector_1': row.get('duration_sector_1'),
                    'sector_2': row.get('duration_sector_2'),
                    'sector_3': row.get('duration_sector_3'),
                    'st_speed': row.get('st_speed'),
                    'is_pit_out_lap': row.get('is_pit_out_lap'),
                }))
    return events


def pit_events(rows, skipped=None):
    """OpenF1 /pit rows (field `date` = pit entry) -> pit_stop events.

    Leak rule: the durations are only known once the car leaves the pit lane,
    so the event is stamped at exit (entry + lane duration), not at entry.
    With no lane duration it falls back to entry time and carries no durations.
    """
    skipped = skipped if skipped is not None else {}
    out = []
    for row in rows:
        entered = parse_time(row.get('date'))
        if entered is None or type(row.get('driver_number')) is not int:
            skipped.setdefault('pit_unusable', []).append(row)
            continue
        lane = _number(row.get('lane_duration', row.get('pit_duration')))
        stop = _number(row.get('stop_duration'))
        if lane is not None and lane > 0:
            t = entered + timedelta(seconds=lane)
        else:
            t, lane, stop = entered, None, None
            skipped.setdefault('pit_no_duration', []).append((row['driver_number'], row.get('lap_number')))
        out.append(Event(t, 'pit_stop', row['driver_number'], row.get('lap_number'), {
            'entered_at': entered.isoformat(), 'lane_duration': lane, 'stop_duration': stop,
        }))
    return out


def race_control_events(rows, skipped=None):
    skipped = skipped if skipped is not None else {}
    out = []
    for row in rows:
        t = parse_time(row.get('date'))
        if t is None:
            skipped.setdefault('race_control_unusable', []).append(row)
            continue
        out.append(Event(t, 'race_control', row.get('driver_number'), row.get('lap_number'), {
            k: row.get(k) for k in ('category', 'flag', 'scope', 'sector', 'message')}))
    return out


def weather_events(rows, skipped=None):
    skipped = skipped if skipped is not None else {}
    out = []
    for row in rows:
        t = parse_time(row.get('date'))
        if t is None:
            skipped.setdefault('weather_unusable', []).append(row)
            continue
        out.append(Event(t, 'weather', None, None, {k: row.get(k) for k in (
            'air_temperature', 'track_temperature', 'humidity', 'rainfall', 'wind_speed')}))
    return out


def merge(*groups) -> list[Event]:
    """One deterministic, time-ordered list (stable for identical inputs)."""
    return sorted((e for g in groups for e in g), key=Event.sort_key)


def _raw_payload(folder: Path, names, prefix):
    """Payload of the raw snapshot file for an endpoint, or None if absent."""
    for name in names:
        if name.startswith(prefix + '_'):
            return json.loads((folder / name).read_text(encoding='utf-8'))['payload']
    return None


def load_timeline(session_key: int | None = None) -> Timeline:
    """Build the timeline for a saved session (default: demo_data/active.json).

    Raises FileNotFoundError if the session was never saved; never fetches.
    """
    if session_key is None:
        session_key = json.loads((core.root() / 'active.json').read_text())['session_key']
    bundle = core.bundle(session_key)
    folder = core.root() / 'raw'
    names = bundle.get('raw_files', [])

    laps = _raw_payload(folder, names, 'laps')
    if laps is None:
        raise FileNotFoundError(f'Raw laps snapshot missing for session {session_key}')

    skipped: dict[str, list] = {}
    groups = [lap_events(laps, skipped)]
    # Optional endpoints: only present if they were saved with the snapshot.
    for prefix, build in (('pit', pit_events), ('race_control', race_control_events), ('weather', weather_events)):
        rows = _raw_payload(folder, names, prefix)
        if rows is not None:
            groups.append(build(rows, skipped))

    drivers = {d['driver_number']: d for d in bundle['drivers']}
    return Timeline(session_key, merge(*groups), drivers, skipped)

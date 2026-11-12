"""Historical replay, step 4: analytics that can only see the past.

This is a pure Python port of the *rules* in queries/08_lap_pace_analysis.sql and
09_anomaly_detection.sql, run over the events the replay clock has already
released. It never touches PostgreSQL: those SQL objects are whole-session and
would leak future laps (see REPLAY_LEAKS.md).

Rules ported:
  pace (08/09 step 1): valid lap = has a time and is not a pit-out lap; baseline =
    mean of up to the 5 previous valid laps of that driver; needs >= 3 of them;
    anomaly when lap - baseline >= 1.5 s (HIGH >= 3.0 s, else MEDIUM).
  pit (09 step 2): baseline = mean of up to 3 previous stops; needs >= 1;
    anomaly when stop >= max(1.5 x baseline, baseline + 2.0) (HIGH >= 2 x baseline).
Difference from SQL: anomalies are stamped with the *race time* they became
knowable (lap completion / pit exit), not a wall-clock detected_at.
"""
from __future__ import annotations

from datetime import datetime

BASELINE_LAPS = 5
MIN_BASELINE_LAPS = 3
PACE_MEDIUM, PACE_HIGH = 1.5, 3.0
BASELINE_STOPS = 3


class FutureDataError(ValueError):
    """An event later than the replay clock reached the analytics layer."""


def assert_no_future(events, now: datetime) -> None:
    for e in events:
        if e.t > now:
            raise FutureDataError(f'event at {e.t.isoformat()} is after replay time {now.isoformat()}')


def _mean(values):
    return sum(values) / len(values)


def _is_valid_lap(data) -> bool:
    # Database laps carry the importer's is_valid (has a time and not a pit-out lap);
    # raw snapshot laps carry is_pit_out_lap. Both mean the same as demo_core.clean_laps.
    if 'is_valid' in data:
        return bool(data.get('lap_duration')) and bool(data['is_valid'])
    return bool(data.get('lap_duration')) and data.get('is_pit_out_lap') is False


def pace_rows(events):
    """Per valid lap, in (driver, lap) order: baseline and difference from prior laps only."""
    laps: dict[int, list] = {}
    for e in events:
        if e.kind == 'lap_complete' and _is_valid_lap(e.data):
            laps.setdefault(e.driver_number, []).append(e)
    rows = []
    for driver in sorted(laps):
        ordered = sorted(laps[driver], key=lambda e: e.lap_number)
        for i, e in enumerate(ordered):
            prior = [p.data['lap_duration'] for p in ordered[max(0, i - BASELINE_LAPS):i]]
            baseline = _mean(prior) if prior else None
            diff = round(e.data['lap_duration'] - baseline, 3) if baseline is not None else None
            rows.append({'driver_number': driver, 'lap_number': e.lap_number, 'completed_at': e.t.isoformat(),
                         'lap_time': e.data['lap_duration'], 'baseline_lap_time': baseline,
                         'baseline_lap_count': len(prior), 'lap_time_difference': diff})
    return rows


def pace_anomalies(rows):
    out = []
    for r in rows:
        d = r['lap_time_difference']
        if r['baseline_lap_count'] >= MIN_BASELINE_LAPS and d is not None and d >= PACE_MEDIUM:
            out.append({'type': 'PACE_DROP', 'severity': 'HIGH' if d >= PACE_HIGH else 'MEDIUM',
                        'driver_number': r['driver_number'], 'lap_number': r['lap_number'],
                        'at': r['completed_at'], 'observed': r['lap_time'],
                        'baseline': r['baseline_lap_time'], 'deviation': d,
                        'description': f'Lap time {d:.2f}s slower than the recent rolling baseline.'})
    return out


def pit_anomalies(events):
    stops: dict[int, list] = {}
    for e in events:
        duration = e.data.get('stop_duration') if e.kind == 'pit_stop' else None
        if e.kind == 'pit_stop':
            # Prefer stationary time (what 09 uses); fall back to pit-lane time.
            duration = duration if duration else e.data.get('lane_duration')
            if duration:
                stops.setdefault(e.driver_number, []).append((e, duration))
    out = []
    for driver in sorted(stops):
        ordered = sorted(stops[driver], key=lambda x: x[0].t)
        for i, (e, duration) in enumerate(ordered):
            prior = [d for _, d in ordered[max(0, i - BASELINE_STOPS):i]]
            if not prior:
                continue
            baseline = _mean(prior)
            if baseline > 0 and duration >= max(baseline * 1.5, baseline + 2.0):
                out.append({'type': 'LONG_PIT_STOP', 'severity': 'HIGH' if duration >= baseline * 2 else 'MEDIUM',
                            'driver_number': driver, 'lap_number': e.lap_number, 'at': e.t.isoformat(),
                            'observed': duration, 'baseline': baseline, 'deviation': duration - baseline,
                            'description': f'Pit stop {duration:.2f}s vs previous average {baseline:.2f}s.'})
    return out


def analyse(events, now: datetime) -> dict:
    """Analytics as of virtual time `now`. `events` must be the clock's `seen()` list."""
    assert_no_future(events, now)
    rows = pace_rows(events)
    anomalies = sorted(pace_anomalies(rows) + pit_anomalies(events), key=lambda a: (a['at'], a['driver_number']))
    summary = {}
    for r in rows:
        s = summary.setdefault(r['driver_number'], {'driver_number': r['driver_number'], 'valid_laps': 0,
                                                    'best_lap': None, 'last_lap': None, '_diffs': []})
        s['valid_laps'] += 1
        s['last_lap'] = r['lap_time']
        s['best_lap'] = r['lap_time'] if s['best_lap'] is None else min(s['best_lap'], r['lap_time'])
        if r['baseline_lap_count'] >= MIN_BASELINE_LAPS and r['lap_time_difference'] is not None:
            s['_diffs'].append(r['lap_time_difference'])
    drivers = []
    for n in sorted(summary):
        s = summary[n]
        diffs = s.pop('_diffs')
        s['avg_pace_difference'] = round(_mean(diffs), 3) if diffs else None
        drivers.append(s)
    return {'as_of': now.isoformat(), 'drivers': drivers, 'anomalies': anomalies}

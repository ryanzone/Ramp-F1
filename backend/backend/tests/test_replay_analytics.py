import copy
import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend import replay, replay_analytics as ra
from backend.main import app
from backend.replay import Event
from backend.replay_clock import ReplayClock
from backend.replay_service import ReplayService, set_service

T0 = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def lap(n, dur, driver=1, pit_out=False):
    t = T0 + timedelta(seconds=n * 100)
    return Event(t, 'lap_complete', driver, n, {'lap_duration': dur, 'is_pit_out_lap': pit_out})


def pit(secs, stop, driver=1, n=1):
    return Event(T0 + timedelta(seconds=secs), 'pit_stop', driver, n, {'stop_duration': stop, 'lane_duration': 22.0})


class RuleTests(unittest.TestCase):
    def test_baseline_uses_only_previous_five_valid_laps(self):
        evs = [lap(i, 90.0) for i in range(1, 8)] + [lap(8, 93.5)]
        rows = ra.pace_rows(evs)
        last = rows[-1]
        self.assertEqual((last['baseline_lap_count'], last['baseline_lap_time']), (5, 90.0))
        self.assertEqual(last['lap_time_difference'], 3.5)

    def test_pace_anomaly_thresholds_and_min_baseline(self):
        evs = [lap(1, 90.0), lap(2, 90.0), lap(3, 95.0)]               # only 2 prior laps: no anomaly
        self.assertEqual(ra.pace_anomalies(ra.pace_rows(evs)), [])
        evs = [lap(1, 90.0), lap(2, 90.0), lap(3, 90.0), lap(4, 91.5), lap(5, 99.0)]
        an = ra.pace_anomalies(ra.pace_rows(evs))
        self.assertEqual([(a['lap_number'], a['severity']) for a in an], [(4, 'MEDIUM'), (5, 'HIGH')])
        self.assertEqual(an[0]['deviation'], 1.5)                       # boundary is inclusive, like SQL >= 1.5

    def test_invalid_laps_excluded_from_baseline(self):
        evs = [lap(i, 90.0) for i in range(1, 5)] + [lap(5, 120.0, pit_out=True), lap(6, 90.2)]
        rows = ra.pace_rows(evs)
        self.assertEqual([r['lap_number'] for r in rows], [1, 2, 3, 4, 6])
        self.assertEqual(rows[-1]['baseline_lap_time'], 90.0)

    def test_pit_anomaly(self):
        evs = [pit(10, 2.4, n=1), pit(500, 2.5, n=2), pit(900, 7.0, n=3)]
        an = ra.pit_anomalies(evs)
        self.assertEqual(len(an), 1)
        self.assertEqual((an[0]['severity'], an[0]['lap_number']), ('HIGH', 3))
        self.assertEqual(ra.pit_anomalies([pit(10, 2.4), pit(50, 3.9)]), [])   # < max(1.5x, +2.0)

    def test_guard_rejects_future_events(self):
        with self.assertRaises(ra.FutureDataError):
            ra.analyse([lap(5, 90.0)], T0)


class NoLeakTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tl = replay.load_timeline(9165)
        full = ReplayClock(cls.tl.events)
        full.seek(full.end)
        cls.full = ra.analyse(full.seen(), full.now)

    def at(self, minutes):
        c = ReplayClock(self.tl.events)
        c.seek_offset(minutes * 60)
        return c

    def test_analysis_at_t_equals_full_run_restricted_to_t(self):
        self.assertGreater(len(self.full['anomalies']), 0)
        for minutes in (5, 20, 45, 80):
            c = self.at(minutes)
            part = ra.analyse(c.seen(), c.now)
            expected = [a for a in self.full['anomalies'] if datetime.fromisoformat(a['at']) <= c.now]
            self.assertEqual(part['anomalies'], expected, minutes)
            self.assertTrue(all(datetime.fromisoformat(a['at']) <= c.now for a in part['anomalies']))

    def test_changing_the_future_does_not_change_the_past(self):
        c = self.at(30)
        before = ra.analyse(c.seen(), c.now)
        tampered = copy.deepcopy(self.tl.events)
        for e in tampered:
            if e.t > c.now and e.kind == 'lap_complete' and e.data['lap_duration']:
                e.data['lap_duration'] += 50
        c2 = ReplayClock(tampered)
        c2.seek(c.now)
        self.assertEqual(ra.analyse(c2.seen(), c2.now), before)

    def test_driver_summary_only_counts_completed_laps(self):
        c = self.at(10)
        done = sum(1 for e in c.seen() if e.kind == 'lap_complete' and ra._is_valid_lap(e.data))
        out = ra.analyse(c.seen(), c.now)
        self.assertEqual(sum(d['valid_laps'] for d in out['drivers']), done)
        self.assertLess(done, sum(d['valid_laps'] for d in self.full['drivers']))

    def test_endpoint_follows_the_clock(self):
        class Mono:
            t = 0.0
            def __call__(self): return self.t
        service = ReplayService(monotonic=Mono())
        service.install('demo', self.tl)
        set_service(service)
        try:
            with TestClient(app) as client:
                client.post('/api/replay/seek', json={'offset_seconds': 600})
                a = client.get('/api/replay/analytics').json()
                client.post('/api/replay/seek', json={'offset_seconds': 5000})
                b = client.get('/api/replay/analytics').json()
            self.assertLess(sum(d['valid_laps'] for d in a['drivers']), sum(d['valid_laps'] for d in b['drivers']))
            self.assertTrue(all(x['at'] <= a['as_of'] for x in a['anomalies']))
        finally:
            set_service(None)


class NoDatabaseTests(unittest.TestCase):
    def test_replay_modules_never_touch_postgres_or_sql_views(self):
        here = Path(__file__).resolve().parent.parent
        for name in ('replay.py', 'replay_clock.py', 'replay_routes.py', 'replay_analytics.py'):
            src = (here / name).read_text(encoding='utf-8')
            code = '\n'.join(l for l in src.splitlines() if not l.strip().startswith('#'))
            for banned in (r'psycopg', r'get_connection', r'query_db', r'v_lap_pace_analysis', r'detected_events'):
                self.assertIsNone(re.search(banned, code.replace(src.split('"""')[1], '')), (name, banned))


if __name__ == '__main__':
    unittest.main()

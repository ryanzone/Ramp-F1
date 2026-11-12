import unittest
from datetime import datetime, timedelta, timezone

from backend import replay
from backend.replay import Event, lap_events, merge, parse_time

UTC = timezone.utc


class SingaporeSnapshot(unittest.TestCase):
    """Real saved Singapore 2023 race (session 9165); no network."""

    @classmethod
    def setUpClass(cls):
        cls.tl = replay.load_timeline(9165)

    def test_session_and_counts(self):
        self.assertEqual(self.tl.session_key, 9165)
        starts = [e for e in self.tl.events if e.kind == 'lap_start']
        self.assertEqual(len(starts), 1090)          # 1091 laps, 1 without date_start
        self.assertEqual(self.tl.skipped['lap_no_start_time'], [(24, 1)])

    def test_time_ordered_and_deterministic(self):
        keys = [e.sort_key() for e in self.tl.events]
        self.assertEqual(keys, sorted(keys))
        again = replay.load_timeline(9165)
        self.assertEqual([e.sort_key() for e in again.events], keys)

    def test_bounds_inside_race_window(self):
        self.assertEqual(self.tl.start, datetime(2023, 9, 17, 12, 3, 44, 658000, tzinfo=UTC))
        self.assertGreater(self.tl.end, datetime(2023, 9, 17, 13, 50, 23, tzinfo=UTC))
        self.assertTrue(all(e.t.tzinfo is not None for e in self.tl.events))

    def test_lap_complete_never_before_its_start(self):
        starts = {(e.driver_number, e.lap_number): e.t for e in self.tl.events if e.kind == 'lap_start'}
        completes = [e for e in self.tl.events if e.kind == 'lap_complete']
        self.assertTrue(completes)
        for e in completes:
            self.assertGreater(e.t, starts[(e.driver_number, e.lap_number)])

    def test_lap_start_leaks_no_timing(self):
        for e in self.tl.events:
            if e.kind == 'lap_start':
                self.assertNotIn('lap_duration', e.data)

    def test_complete_time_matches_duration(self):
        starts = {(e.driver_number, e.lap_number): e.t for e in self.tl.events if e.kind == 'lap_start'}
        e = next(e for e in self.tl.events if e.kind == 'lap_complete' and e.data['lap_duration'])
        delta = e.t - starts[(e.driver_number, e.lap_number)]
        self.assertAlmostEqual(delta.total_seconds(), e.data['lap_duration'], places=3)

    def test_no_extra_endpoints_in_snapshot(self):
        kinds = {e.kind for e in self.tl.events}
        self.assertEqual(kinds, {'lap_start', 'lap_complete'})


class SyntheticFixtures(unittest.TestCase):
    T0 = '2023-01-01T10:00:00+00:00'

    def lap(self, n, start, dur, driver=1):
        return {'driver_number': driver, 'lap_number': n, 'date_start': start, 'lap_duration': dur}

    def test_null_duration_uses_next_lap_start(self):
        ev = lap_events([self.lap(1, self.T0, None), self.lap(2, '2023-01-01T10:01:30+00:00', 80.0)])
        done = [e for e in ev if e.kind == 'lap_complete' and e.lap_number == 1][0]
        self.assertEqual(done.t, datetime(2023, 1, 1, 10, 1, 30, tzinfo=UTC))
        self.assertIsNone(done.data['lap_duration'])

    def test_last_lap_without_duration_has_no_completion(self):
        skipped = {}
        ev = lap_events([self.lap(1, self.T0, None)], skipped)
        self.assertEqual([e.kind for e in ev], ['lap_start'])
        self.assertEqual(skipped['lap_no_completion_time'], [(1, 1)])

    def test_duplicates_and_naive_times_skipped(self):
        skipped = {}
        ev = lap_events([self.lap(1, self.T0, 90), self.lap(1, self.T0, 91),
                         self.lap(2, '2023-01-01T10:05:00', 90)], skipped)
        self.assertEqual(len(ev), 2)
        self.assertEqual(skipped['lap_duplicate'], [(1, 1)])
        self.assertEqual(skipped['lap_no_start_time'], [(1, 2)])

    def test_pit_race_control_weather_and_merge_order(self):
        sk = {}
        pits = replay.pit_events([{'date': '2023-01-01T10:00:30Z', 'driver_number': 1, 'lap_number': 1,
                                   'pit_duration': 22.5}, {'date': None, 'driver_number': 1}], sk)
        rc = replay.race_control_events([{'date': '2023-01-01T10:00:10Z', 'flag': 'YELLOW', 'category': 'Flag',
                                          'message': 'YELLOW IN TRACK SECTOR 3'}], sk)
        wx = replay.weather_events([{'date': '2023-01-01T10:00:10Z', 'air_temperature': 30.1, 'rainfall': 0}], sk)
        laps = lap_events([self.lap(1, self.T0, 90)])
        merged = merge(laps, pits, rc, wx)
        self.assertEqual([e.kind for e in merged],
                         ['lap_start', 'weather', 'race_control', 'pit_stop', 'lap_complete'])
        self.assertEqual(pits[0].data['lane_duration'], 22.5)
        self.assertEqual(sk['pit_unusable'][0]['date'], None)

    def test_pit_event_is_stamped_at_exit_not_entry(self):
        sk = {}
        (p,) = replay.pit_events([{'date': '2023-01-01T10:00:30Z', 'driver_number': 1, 'lap_number': 1,
                                   'lane_duration': 22.5, 'stop_duration': 2.4}], sk)
        self.assertEqual(p.t, datetime(2023, 1, 1, 10, 0, 52, 500000, tzinfo=UTC))
        self.assertEqual(p.data['entered_at'], '2023-01-01T10:00:30+00:00')
        (q,) = replay.pit_events([{'date': '2023-01-01T10:00:30Z', 'driver_number': 1}], sk)
        self.assertEqual((q.t, q.data['lane_duration']), (datetime(2023, 1, 1, 10, 0, 30, tzinfo=UTC), None))
        self.assertEqual(sk['pit_no_duration'], [(1, None)])

    def test_parse_time(self):
        self.assertEqual(parse_time('2023-01-01T10:00:00Z'), datetime(2023, 1, 1, 10, tzinfo=UTC))
        self.assertEqual(parse_time('2023-01-01T12:00:00+02:00'), datetime(2023, 1, 1, 10, tzinfo=UTC))
        for bad in (None, '', 'nope', '2023-01-01T10:00:00', 5):
            self.assertIsNone(parse_time(bad))


if __name__ == '__main__':
    unittest.main()

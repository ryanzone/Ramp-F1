"""Database-backed replay tests. Skipped automatically when PostgreSQL or the replay
migration (queries/13_replay_time_aware.sql) + backfill are not available."""
import os
import unittest
from datetime import datetime

import psycopg

from backend import replay_service as rs
from backend.replay_clock import ReplayClock


def _setup():
    try:
        sessions = rs.list_sessions()
    except Exception as exc:                      # no DB, or migration not applied
        return None, f'database/migration unavailable: {exc}'
    ready = [s for s in sessions if s['replay_ready'] and s['season'] == 2026]
    if not ready:
        return None, 'no replay-ready 2026 race (run F1_BACKFILL=1 python backend/import_f1.py)'
    return ready[0], None


SESSION, SKIP = _setup()


@unittest.skipIf(SESSION is None, SKIP)
class DatabaseReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sid = SESSION['session_id']
        cls.tl = rs.load_timeline_db(cls.sid)

    def test_sessions_listing(self):
        self.assertEqual(SESSION['replay_ready'], True)
        self.assertGreater(SESSION['total_laps'], 30)

    def test_timeline_shape(self):
        kinds = {e.kind for e in self.tl.events}
        self.assertTrue({'lap_start', 'lap_complete', 'pit_stop', 'race_control', 'weather',
                         'position', 'interval', 'stint'} <= kinds, kinds)
        keys = [e.sort_key() for e in self.tl.events]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(self.tl.meta['total_laps'], SESSION['total_laps'])
        self.assertLess(self.tl.meta['start'], self.tl.meta['end'])
        self.assertEqual(len(self.tl.drivers), 22)

    def test_lap_complete_only_after_its_start_and_has_no_future_info_in_start(self):
        starts = {(e.driver_number, e.lap_number): e.t for e in self.tl.events if e.kind == 'lap_start'}
        done = [e for e in self.tl.events if e.kind == 'lap_complete']
        self.assertTrue(done)
        for e in done:
            self.assertGreater(e.t, starts[(e.driver_number, e.lap_number)])
        self.assertTrue(all(not e.data for e in self.tl.events if e.kind == 'lap_start'))

    def test_pit_stops_are_stamped_at_exit(self):
        pits = [e for e in self.tl.events if e.kind == 'pit_stop' and e.data['lane_duration']]
        self.assertTrue(pits)
        for e in pits:
            entered = datetime.fromisoformat(e.data['entered_at'])
            self.assertAlmostEqual((e.t - entered).total_seconds(), e.data['lane_duration'], places=3)

    def test_full_race_replays_every_event_exactly_once(self):
        clock = ReplayClock(self.tl.events, start=self.tl.meta['start'], end=self.tl.meta['end'], speed=8)
        clock.play()
        emitted = []
        while clock.state == 'playing':
            emitted += clock.advance(120)
        inside = [e for e in self.tl.events if e.t <= self.tl.meta['end']]
        self.assertEqual(len(emitted), len(inside))
        self.assertTrue(all(e.t <= clock.now for e in emitted))


@unittest.skipIf(SESSION is None or not os.getenv('RAMP_RO_PASSWORD') or not os.getenv('REPLAY_CLOCK_SECRET'),
                 'read-only role secrets not configured' if SESSION else SKIP)
class ViewsMatchReplayTests(unittest.TestCase):
    """The events the replay emits up to T must equal what the replay.* views show at T."""

    @classmethod
    def setUpClass(cls):
        cls.tl = rs.load_timeline_db(SESSION['session_id'])
        cls.conn = psycopg.connect(
            host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
            dbname=os.getenv('DB_NAME', 'f1_analytics'), user=os.getenv('RAMP_RO_USER', 'ramp_readonly'),
            password=os.environ['RAMP_RO_PASSWORD'])

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def view_count(self, t, sql):
        cur = self.conn.cursor()
        cur.execute('SELECT replay.set_clock(%s, %s, %s)', (os.environ['REPLAY_CLOCK_SECRET'], SESSION['session_id'], t))
        cur.execute(sql)
        n = cur.fetchone()[0]
        self.conn.commit()
        return n

    def test_counts_agree_at_several_moments(self):
        start, end = self.tl.meta['start'], self.tl.meta['end']
        for fraction in (0.02, 0.2, 0.5, 0.8, 1.0):
            t = start + (end - start) * fraction
            seen = [e for e in self.tl.events if e.t <= t]

            def n(kind, phase=None):
                return sum(1 for e in seen if e.kind == kind and (phase is None or e.data.get('phase') == phase))

            checks = {
                'lap_complete': ('SELECT count(*) FROM replay.laps', n('lap_complete')),
                'pit_stop': ('SELECT count(*) FROM replay.pit_stops', n('pit_stop')),
                'race_control': ('SELECT count(*) FROM replay.race_control', n('race_control')),
                'weather': ('SELECT count(*) FROM replay.weather', n('weather')),
                'position': ('SELECT count(*) FROM replay.positions WHERE position IS NOT NULL', n('position')),
                'interval': ('SELECT count(*) FROM replay.positions WHERE gap_to_leader_seconds IS NOT NULL '
                             'OR interval_ahead_seconds IS NOT NULL', n('interval')),
                'stint start': ('SELECT count(*) FROM replay.tyre_stints', n('stint', 'start')),
                'stint end': ('SELECT count(*) FROM replay.tyre_stints WHERE end_lap IS NOT NULL', n('stint', 'end')),
            }
            for label, (sql, expected) in checks.items():
                self.assertEqual(self.view_count(t, sql), expected, f'{label} at {fraction:.0%}')


if __name__ == '__main__':
    unittest.main()

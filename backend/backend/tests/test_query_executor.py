"""Executor tests against the real database (skipped if the replay setup is unavailable)."""
import os
import unittest
from datetime import timedelta

import psycopg

from backend import replay_service as rs
from backend.query_executor import ExecutorUnavailable, QueryError, QueryExecutor, QueryTimeout
from backend.sql_validator import validate


def _setup():
    if not os.getenv('RAMP_RO_PASSWORD') or not os.getenv('REPLAY_CLOCK_SECRET'):
        return None, 'read-only role secrets not configured'
    try:
        ready = [s for s in rs.list_sessions() if s['replay_ready'] and s['season'] == 2026]
        ex = QueryExecutor()
        ex.catalog()
    except Exception as exc:
        return None, f'database/migration unavailable: {exc}'
    return (ready[0], ex), None


SETUP, SKIP = _setup()


@unittest.skipIf(SETUP is None, SKIP)
class ExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session, cls.ex = SETUP
        cls.sid = cls.session['session_id']
        cls.tl = rs.load_timeline_db(cls.sid)
        cls.start, cls.end = cls.tl.meta['start'], cls.tl.meta['end']
        cls.catalog = cls.ex.catalog()

    def q(self, sql, params=None, at=None):
        v = validate(sql, self.catalog, set(params or {}))
        return self.ex.run(v, params or {}, self.sid, at or (self.start + (self.end - self.start) / 2))

    def test_catalog_lists_only_replay_views(self):
        self.assertTrue({'laps', 'tyre_stints', 'pit_stops', 'race_control', 'weather', 'positions',
                         'current_positions', 'driver_pace', 'current_stints', 'drivers', 'session_info'}
                        <= set(self.catalog))
        self.assertNotIn('clock', self.catalog)
        self.assertNotIn('clock_secret', self.catalog)
        self.assertIn('lap_time_seconds', self.catalog['laps'])

    def test_query_runs_and_returns_json_safe_rows(self):
        r = self.q('SELECT driver_code, COUNT(*) AS laps, ROUND(AVG(lap_time_seconds), 3) AS avg_lap '
                   'FROM laps WHERE is_valid GROUP BY driver_code ORDER BY avg_lap LIMIT 5')
        self.assertEqual(r.columns, ['driver_code', 'laps', 'avg_lap'])
        self.assertEqual(len(r.rows), 5)
        self.assertIsInstance(r.rows[0][2], float)
        self.assertGreaterEqual(r.elapsed_ms, 0)

    def test_the_future_is_invisible_and_moves_with_the_clock(self):
        counts = []
        for fraction in (0.1, 0.5, 1.0):
            t = self.start + (self.end - self.start) * fraction
            r = self.q('SELECT COUNT(*) AS n, MAX(lap_end_at) AS newest FROM laps', at=t)
            counts.append(r.rows[0][0])
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])

    def test_newest_lap_never_after_clock(self):
        from datetime import datetime
        t = self.start + timedelta(minutes=25)
        newest = self.q('SELECT MAX(lap_end_at) FROM laps', at=t).rows[0][0]
        self.assertLessEqual(datetime.fromisoformat(newest), t)
        newest_rc = self.q('SELECT MAX(recorded_at) FROM race_control', at=t).rows[0][0]
        self.assertLessEqual(datetime.fromisoformat(newest_rc), t)

    def test_row_limit_and_truncation_flag(self):
        small = QueryExecutor(row_limit=5)
        r = small.run(validate('SELECT lap_number FROM laps', self.catalog), {}, self.sid, self.end)
        self.assertEqual(len(r.rows), 5)
        self.assertTrue(r.truncated)
        small.close()

    def test_timeout(self):
        slow = QueryExecutor(timeout_ms=50)
        heavy = ('SELECT COUNT(*) FROM laps a CROSS JOIN laps b CROSS JOIN laps c '
                 'CROSS JOIN laps d WHERE a.lap_number + b.lap_number + c.lap_number > d.lap_number')
        with self.assertRaises(QueryTimeout):
            slow.run(validate(heavy, self.catalog), {}, self.sid, self.end)
        slow.close()

    def test_only_validated_queries_are_accepted(self):
        with self.assertRaises(TypeError):
            self.ex.run('SELECT 1', {}, self.sid, self.end)

    def test_connections_survive_errors(self):
        for _ in range(3):
            with self.assertRaises(QueryError):
                self.q('SELECT 1 / 0 FROM laps')
        self.assertEqual(self.q('SELECT 1 AS one').rows, [[1]])

    # ---- the database refuses things even if validation were skipped -----------------
    def raw(self, sql, at=None):
        return self.ex._execute(sql, {}, self.sid, at or self.end)

    def test_db_denies_base_tables_clock_and_writes(self):
        for sql in ('SELECT * FROM public.laps', 'SELECT * FROM public.session_results',
                    'SELECT * FROM replay.clock', 'SELECT * FROM replay.clock_secret'):
            with self.assertRaises((QueryError, QueryTimeout)):
                self.raw(sql)

    def test_db_rejects_clock_changes_without_the_secret(self):
        with self.assertRaises(QueryError):
            self.raw("SELECT replay.set_clock('guess', %d, now())" % self.sid)

    def test_db_read_only_transaction_blocks_writes(self):
        for sql in ('UPDATE public.laps SET lap_number = lap_number', 'DELETE FROM replay.laps'):
            with self.assertRaises(QueryError):
                self.raw(sql)

    def test_missing_secrets_are_reported(self):
        old = os.environ.pop('REPLAY_CLOCK_SECRET')
        try:
            with self.assertRaises(ExecutorUnavailable):
                QueryExecutor()._secret()
        finally:
            os.environ['REPLAY_CLOCK_SECRET'] = old

    def test_users_cannot_see_each_others_clock(self):
        # two executors = two connections with their own clocks
        other = QueryExecutor()
        a = self.ex.run(validate('SELECT COUNT(*) FROM laps', self.catalog), {}, self.sid, self.start + timedelta(minutes=10))
        b = other.run(validate('SELECT COUNT(*) FROM laps', self.catalog), {}, self.sid, self.end)
        a2 = self.ex.run(validate('SELECT COUNT(*) FROM laps', self.catalog), {}, self.sid, self.start + timedelta(minutes=10))
        self.assertEqual(a.rows, a2.rows)
        self.assertLess(a.rows[0][0], b.rows[0][0])
        other.close()


if __name__ == '__main__':
    unittest.main()

"""Time-aware SQL analytics against the real database (skipped when it is not set up)."""
import os
import re
import unittest
from datetime import datetime, timedelta

import psycopg
from fastapi.testclient import TestClient

from backend import replay_service as rs
from backend.analytics_service import AnalyticsService, AnalyticsUnavailable, set_analytics
from backend.main import app
from backend.query_executor import QueryExecutor
from backend.replay_service import ReplayService, set_service
from backend.sql_generator import INTENTS


def _setup():
    if not os.getenv('RAMP_RO_PASSWORD') or not os.getenv('REPLAY_CLOCK_SECRET'):
        return None, 'read-only role secrets not configured'
    try:
        ready = [s for s in rs.list_sessions() if s['replay_ready'] and s['season'] == 2026]
        QueryExecutor().catalog()
    except Exception as exc:
        return None, f'database/migration unavailable: {exc}'
    return ready[0], None


SESSION, SKIP = _setup()
TIME_COLUMNS = ('recorded_at', 'event_time', 'lap_end_at', 'pit_exit_at', 'pit_entry_at',
                'first_lap_finished_at', 'latest_lap_finished_at')


def laps_in_db(session_id):
    with rs.connect() as conn:
        return conn.execute('SELECT COUNT(*) FROM laps l JOIN session_drivers sd USING (session_driver_id) '
                            'WHERE sd.session_id = %s', (session_id,)).fetchone()[0]


@unittest.skipIf(SESSION is None, SKIP)
class AnalyticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.svc = ReplayService()
        set_service(self.svc)
        self.an = AnalyticsService(lambda: self.svc)
        set_analytics(self.an)
        self.sid = SESSION['session_id']
        self.entry = await self.svc.create(self.sid)
        self.rid = self.entry.state.id
        self.start = self.entry.state.clock.start

    async def asyncTearDown(self):
        set_service(None)
        set_analytics(None)
        self.an.executor.close()

    def seek(self, minutes, entry=None):
        entry = entry or self.entry
        self.svc.control(entry, 'seek', offset_seconds=minutes * 60)
        return entry.state.clock.now

    async def ask(self, q, rid=None):
        return await self.an.ask(rid or self.rid, q)

    # ---- every question type runs, validates and respects the clock ---------------------------
    async def test_every_example_runs_and_never_shows_the_future(self):
        problems = []
        for minutes in (12, 45, 80):
            at = self.seek(minutes)
            for intent in INTENTS:
                for example in intent.examples:
                    if 'him' in example.lower() or 'second-fastest' in example:
                        continue
                    r = await self.ask(example)
                    if r['status'] != 'ok':
                        problems.append((minutes, example, r['status'], r['answer'][:80]))
                        continue
                    self.assertTrue(r['sql'].strip().upper().startswith(('SELECT', 'WITH')), example)
                    self.assertLess(r['elapsed_ms'], 1500, example)
                    self.assertTrue(r['answer'])
                    for col in TIME_COLUMNS:
                        if col in r['columns']:
                            i = r['columns'].index(col)
                            for row in r['rows']:
                                if row[i]:
                                    self.assertLessEqual(datetime.fromisoformat(row[i]), at, f'{example}: {col} is in the future')
        self.assertEqual(problems, [])

    async def test_answers_change_as_the_clock_advances(self):
        early = await self.ask('Who is leading?') if self.seek(8) else None
        late = await (self.ask('Who is leading?') if self.seek(75) else None)
        self.assertNotEqual(early['replay_time'], late['replay_time'])
        laps_early = (await self.ask('What lap is it?'))['rows'][0][0] if self.seek(10) else None
        laps_late = (await self.ask('What lap is it?'))['rows'][0][0] if self.seek(70) else None
        self.assertLess(laps_early, laps_late)
        self.seek(10)
        self.assertLessEqual(laps_early, self.entry.state.current_lap)

    async def test_nothing_yet_at_the_very_start(self):
        self.seek(0)
        for q in ('Which driver has been most consistent?', 'Who has been penalised?', 'Which team has the fastest average pit stops?'):
            r = await self.ask(q)
            self.assertEqual(r['status'], 'ok', q)
            self.assertEqual(r['row_count'], 0, q)
            self.assertTrue(r['answer'])

    # ---- penalties: visible only once issued ------------------------------------------------------
    async def test_penalty_appears_only_after_it_was_issued(self):
        tl = self.entry.state.timeline
        penalty = next(e for e in tl.events if e.kind == 'race_control' and 'PENALTY FOR CAR' in (e.data['message'] or '')
                       and 'SERVED' not in e.data['message'])
        code = penalty.data['message'].split('(')[1].split(')')[0]
        self.svc.control(self.entry, 'seek', t=penalty.t - timedelta(seconds=2))
        before = await self.ask(f'Why did {code} get a penalty?')
        self.assertNotIn('received a', before['answer'])
        self.assertTrue(all('PENALTY FOR' not in (row[3] or '') for row in before['rows']))
        self.svc.control(self.entry, 'seek', t=penalty.t + timedelta(seconds=2))
        after = await self.ask(f'Why did {code} get a penalty?')
        self.assertIn('received a', after['answer'])
        self.assertIn('penalty', after['answer'].lower())
        listed = await self.ask('Who has been penalised?')
        self.assertIn(code, listed['answer'])

    # ---- follow-up context -----------------------------------------------------------------------------
    async def test_follow_up_compares_the_top_two_of_the_previous_answer(self):
        self.seek(50)
        first = await self.ask('Which driver has the strongest race pace over the last five laps?')
        top, second = first['rows'][0][first['columns'].index('driver_code')], first['rows'][1][first['columns'].index('driver_code')]
        follow = await self.ask('Compare him with the second-fastest')
        self.assertEqual(follow['status'], 'ok')
        self.assertEqual((follow['params']['a'], follow['params']['b']), (top, second))
        self.assertTrue(follow['used_context'])
        self.assertIn(top, follow['answer'])

    async def test_pronoun_follow_up_for_penalty(self):
        self.seek(80)
        await self.ask('How is NOR doing?')
        r = await self.ask('Why did he get a penalty?')
        self.assertEqual(r['intent'], 'penalty_reason')
        self.assertIn('NOR', r['answer'])

    async def test_clarification_and_unsupported(self):
        self.seek(30)
        r = await self.ask('Compare race pace')
        self.assertEqual(r['status'], 'needs_clarification')
        self.assertIsNone(r['sql'])
        r = await self.ask('What is the meaning of life?')
        self.assertEqual(r['status'], 'unsupported')
        self.assertGreater(len(r['suggestions']), 3)

    # ---- caching, history, explain ---------------------------------------------------------------------------
    async def test_cache_hits_when_paused_and_invalidates_on_seek(self):
        self.seek(40)
        a = await self.ask('Show the standings')
        b = await self.ask('Show the standings')
        self.assertFalse(a['cached'])
        self.assertTrue(b['cached'])
        self.assertEqual(a['rows'], b['rows'])
        self.seek(41)
        c = await self.ask('Show the standings')
        self.assertFalse(c['cached'])

    async def test_history_and_explain(self):
        self.seek(35)
        r = await self.ask('Which driver has been most consistent?')
        history = self.an.history(self.rid)
        self.assertEqual(history[0]['id'], r['id'])
        self.assertNotIn('rows', history[0])
        ex = self.an.explain(self.rid, r['id'])
        self.assertIn('STDDEV', ex['sql'].upper())
        self.assertTrue(any('window' in t for t in ex['techniques']))
        self.assertIn('replay.* views', ' '.join(ex['safety']))
        self.assertIsNone(self.an.explain(self.rid, 'nope'))
        self.assertEqual(self.an.history('unknown-replay'), [])

    async def test_results_use_the_sql_features_the_project_promises(self):
        self.seek(60)
        seen = set()
        for intent in INTENTS:
            if intent.name in ('compare_drivers', 'qualifying_vs_race'):
                continue
            r = await self.ask(intent.examples[0]) if 'him' not in intent.examples[0] else None
            if r and r['status'] == 'ok':
                seen.update(r['features'])
        joined = ' '.join(seen)
        for feature in ('CTE', 'JOIN', 'window function', 'subquery', 'aggregate', 'CASE', 'GROUP BY', 'HAVING', 'set operation'):
            self.assertIn(feature, joined)

    # ---- isolation and safety ---------------------------------------------------------------------------------------
    async def test_two_users_have_independent_clocks_and_context(self):
        other = await self.svc.create(self.sid)
        self.seek(15)
        self.seek(70, other)
        a = await self.ask('What lap is it?')
        b = await self.ask('What lap is it?', other.state.id)
        self.assertLess(a['rows'][0][0], b['rows'][0][0])
        await self.ask('How is VER doing?')
        await self.ask('How is NOR doing?', other.state.id)
        mine = await self.ask('Why did he get a penalty?')
        theirs = await self.ask('Why did he get a penalty?', other.state.id)
        self.assertEqual((mine['params']['code_pat'], theirs['params']['code_pat']), ('%(VER)%', '%(NOR)%'))
        self.assertEqual(self.an.history('nobody'), [])
        self.assertNotEqual({h['id'] for h in self.an.history(self.rid)}, {h['id'] for h in self.an.history(other.state.id)})

    async def test_injection_in_the_question_cannot_change_anything(self):
        before = laps_in_db(self.sid)
        self.seek(60)
        attacks = ["'; DROP TABLE laps; --", "Why did NOR'; DELETE FROM laps; -- get a penalty?",
                   "Who is leading? ; UPDATE laps SET lap_number = 0", "Compare VER and NOR\"; DROP SCHEMA replay CASCADE; --",
                   "SELECT * FROM public.laps", "Why did %(code_pat)s get a penalty %s", "Why did NOR get a penalty? \x00 /* */"]
        for q in attacks:
            r = await self.ask(q)
            self.assertIn(r['status'], ('ok', 'unsupported', 'needs_clarification'), q)
            if r['sql']:
                self.assertIsNone(re.search(r'\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE)\b', r['sql'].upper()), q)
                self.assertNotIn(';', r['sql'])
                self.assertNotIn(q, r['sql'])                       # the question text never reaches the SQL
        self.assertEqual(laps_in_db(self.sid), before)
        self.assertEqual((await self.ask('Who is leading?'))['status'], 'ok')

    async def test_background_queries_do_not_touch_history_or_follow_up_context(self):
        self.seek(50)
        await self.ask('How is NOR doing?')
        before = len(self.an.history(self.rid))
        silent = await self.an.ask(self.rid, 'Who has the best race pace?', remember=False)
        self.assertEqual(silent['status'], 'ok')
        self.assertEqual(len(self.an.history(self.rid)), before)
        follow = await self.ask('Why did he get a penalty?')
        self.assertEqual(follow['params']['code_pat'], '%(NOR)%')        # "he" is still NOR, not the pace leader

    async def test_demo_replay_cannot_run_sql_analytics(self):
        self.svc.install('demo', rs.replay.load_timeline(9165))
        with self.assertRaises(AnalyticsUnavailable):
            await self.an.ask('demo', 'Who is leading?')


@unittest.skipIf(SESSION is None, SKIP)
class AnalyticsRouteTests(unittest.TestCase):
    def setUp(self):
        set_service(ReplayService())
        set_analytics(None)

    def tearDown(self):
        set_service(None)
        set_analytics(None)

    def start(self, c, minutes=40):
        rid = c.post('/api/replay/start', json={'session_id': SESSION['session_id']}).json()['replay_id']
        c.post('/api/replay/seek', json={'offset_seconds': minutes * 60}, params={'replay_id': rid})
        return rid

    def test_query_history_explain_intents(self):
        with TestClient(app) as c:
            rid = self.start(c)
            r = c.post('/api/analytics/query', json={'replay_id': rid, 'question': 'Which driver has been most consistent?'})
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body['status'], 'ok')
            self.assertIn('STDDEV_SAMP', body['sql'])
            self.assertEqual(body['chart']['type'], 'bar')
            h = c.get('/api/analytics/history', params={'replay_id': rid}).json()
            self.assertEqual(h[0]['id'], body['id'])
            e = c.post('/api/analytics/explain', json={'replay_id': rid, 'query_id': body['id']}).json()
            self.assertTrue(e['techniques'])
            self.assertGreater(len(c.get('/api/analytics/intents').json()), 20)

    def test_errors(self):
        with TestClient(app) as c:
            self.assertEqual(c.post('/api/analytics/query', json={'question': 'Who is leading?'}).status_code, 409)   # demo
            self.assertEqual(c.post('/api/analytics/query', json={'replay_id': 'nope', 'question': 'x'}).status_code, 404)
            rid = self.start(c)
            self.assertEqual(c.post('/api/analytics/query', json={'replay_id': rid, 'question': ''}).status_code, 422)
            self.assertEqual(c.post('/api/analytics/query', json={'replay_id': rid, 'question': 'x' * 600}).status_code, 422)
            self.assertEqual(c.post('/api/analytics/explain', json={'replay_id': rid, 'query_id': 'nope'}).status_code, 404)
            self.assertEqual(c.post('/api/analytics/explain', json={'query_id': 'x'}).status_code, 422)

    def test_websocket_streams_status_then_result(self):
        with TestClient(app) as c:
            rid = self.start(c)
            with c.websocket_connect('/ws/analytics') as ws:
                ws.send_json({'question': 'Who is leading?', 'replay_id': rid})
                kinds, stages = [], []
                while True:
                    m = ws.receive_json()
                    kinds.append(m['type'])
                    if m['type'] == 'status':
                        stages.append(m['stage'])
                    if m['type'] in ('result', 'error'):
                        break
                self.assertEqual(kinds[-1], 'result')
                self.assertEqual(stages[:2], ['parsing', 'validating'])
                self.assertIn('executing', stages)
                self.assertEqual(m['result']['status'], 'ok')
                ws.send_json({'question': '', 'replay_id': rid})
                self.assertEqual(ws.receive_json()['type'], 'error')
                ws.send_json({'question': 'Who is leading?', 'replay_id': 'nope'})
                err = ws.receive_json()
                self.assertEqual((err['type'], err['status']), ('error', 404))

    def test_websocket_rejects_foreign_origin(self):
        from starlette.websockets import WebSocketDisconnect
        with TestClient(app) as c:
            with self.assertRaises(WebSocketDisconnect):
                with c.websocket_connect('/ws/analytics', headers={'origin': 'http://evil.example'}):
                    pass


if __name__ == '__main__':
    unittest.main()

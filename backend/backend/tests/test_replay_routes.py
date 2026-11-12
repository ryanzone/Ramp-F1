import asyncio
import json
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend import replay
from backend.main import app
from backend.replay_routes import sse_stream
from backend.replay_service import ReplayNotReady, ReplayService, set_service


class FakeMono:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def parse_sse(chunk):
    lines = chunk.strip().split('\n')
    return lines[0].removeprefix('event: '), json.loads(lines[1].removeprefix('data: '))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.timeline = replay.load_timeline(9165)

    def setUp(self):
        self.mono = FakeMono()
        self.service = ReplayService(monotonic=self.mono)
        self.service.install('demo', self.timeline)
        set_service(self.service)

    def tearDown(self):
        set_service(None)

    def advance(self, seconds):
        self.mono.t += seconds


class ControlTests(Base):
    def test_state_initial(self):
        with TestClient(app) as c:
            s = c.get('/api/replay/state').json()
        self.assertEqual((s['state'], s['speed'], s['elapsed'], s['finished']), ('paused', 1.0, 0, False))
        self.assertGreater(s['duration'], 6000)
        self.assertEqual(s['replay_id'], 'demo')

    def test_play_pause_and_time_only_moves_while_playing(self):
        with TestClient(app) as c:
            self.advance(50)
            self.assertEqual(c.get('/api/replay/state').json()['elapsed'], 0)
            self.assertEqual(c.post('/api/replay/play').json()['state'], 'playing')
            self.advance(10)
            self.assertAlmostEqual(c.get('/api/replay/state').json()['elapsed'], 10)
            self.assertEqual(c.post('/api/replay/pause').json()['state'], 'paused')
            self.advance(30)
            self.assertAlmostEqual(c.get('/api/replay/state').json()['elapsed'], 10)
            self.assertEqual(c.post('/api/replay/resume').json()['state'], 'playing')

    def test_speed_applies_to_future_time_only(self):
        with TestClient(app) as c:
            c.post('/api/replay/play')
            self.advance(10)
            self.assertEqual(c.post('/api/replay/speed', json={'speed': 4}).json()['speed'], 4)
            self.advance(10)
            self.assertAlmostEqual(c.get('/api/replay/state').json()['elapsed'], 10 + 40)

    def test_all_requested_speeds_accepted_and_bad_rejected(self):
        with TestClient(app) as c:
            for ok in (0.5, 1, 2, 5, 10):
                self.assertEqual(c.post('/api/replay/speed', json={'speed': ok}).status_code, 200)
            for bad in (0.1, 11, 0, -2, 'fast', None, True):
                self.assertEqual(c.post('/api/replay/speed', json={'speed': bad}).status_code, 422, bad)

    def test_seek_both_directions_and_validation(self):
        with TestClient(app) as c:
            fwd = c.post('/api/replay/seek', json={'offset_seconds': 600}).json()
            self.assertAlmostEqual(fwd['elapsed'], 600)
            back = c.post('/api/replay/seek', json={'offset_seconds': 100}).json()
            self.assertAlmostEqual(back['elapsed'], 100)
            self.assertEqual(back['epoch'], fwd['epoch'] + 1)
            start = datetime.fromisoformat(back['start'])
            s = c.post('/api/replay/seek', json={'t': start.replace(minute=start.minute + 1).isoformat()}).json()
            self.assertAlmostEqual(s['elapsed'], 60)
            self.assertTrue(c.post('/api/replay/seek', json={'offset_seconds': 10**9}).json()['finished'])
            for bad in ({}, {'t': 'x'}, {'t': '2023-09-17T12:30:00'}, {'t': 'x', 'offset_seconds': 1},
                        {'offset_seconds': 'a'}, {'offset_seconds': None}):
                self.assertEqual(c.post('/api/replay/seek', json=bad).status_code, 422, bad)

    def test_reset_returns_to_start_paused(self):
        with TestClient(app) as c:
            c.post('/api/replay/play')
            self.advance(100)
            s = c.post('/api/replay/reset').json()
        self.assertEqual((s['elapsed'], s['state']), (0, 'paused'))

    def test_current_lap_follows_clock_and_resets_on_seek_back(self):
        with TestClient(app) as c:
            self.assertEqual(c.get('/api/replay/state').json()['current_lap'], 0)
            late = c.post('/api/replay/seek', json={'offset_seconds': 3000}).json()
            self.assertGreater(late['current_lap'], 10)
            early = c.post('/api/replay/seek', json={'offset_seconds': 5}).json()
            self.assertLess(early['current_lap'], late['current_lap'])

    def test_unknown_replay_and_missing_snapshot(self):
        with TestClient(app) as c:
            self.assertEqual(c.get('/api/replay/state', params={'replay_id': 'nope'}).status_code, 404)
        set_service(ReplayService())
        orig = replay.load_timeline
        replay.load_timeline = lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError())
        try:
            with TestClient(app) as c:
                self.assertEqual(c.get('/api/replay/state').status_code, 503)
        finally:
            replay.load_timeline = orig

    def test_existing_routes_still_registered_and_cors(self):
        paths = {r.path for r in app.routes}
        self.assertTrue({'/api/races', '/api/laps', '/api/demo/summary', '/api/replay/stream',
                         '/api/replay/sessions', '/api/replay/start', '/ws/replay'} <= paths)
        with TestClient(app) as c:
            r = c.options('/api/replay/play', headers={'Origin': 'http://localhost:5173',
                                                        'Access-Control-Request-Method': 'POST'})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(c.get('/api/demo/summary').status_code, 200)


class MultiUserTests(Base):
    def make_service(self, loader):
        service = ReplayService(loader=loader, monotonic=self.mono)
        set_service(service)
        return service

    def test_start_creates_independent_replays_that_share_one_loaded_timeline(self):
        calls = []

        def loader(session_id):
            calls.append(session_id)
            return self.timeline

        self.make_service(loader)
        with TestClient(app) as c:
            a = c.post('/api/replay/start', json={'session_id': 7, 'autoplay': True}).json()
            b = c.post('/api/replay/start', json={'session_id': 7}).json()
            self.assertNotEqual(a['replay_id'], b['replay_id'])
            self.advance(120)
            sa = c.get('/api/replay/state', params={'replay_id': a['replay_id']}).json()
            sb = c.get('/api/replay/state', params={'replay_id': b['replay_id']}).json()
            self.assertAlmostEqual(sa['elapsed'], 120)      # A was playing
            self.assertEqual((sb['elapsed'], sb['state']), (0, 'paused'))   # B untouched
            c.post('/api/replay/seek', json={'offset_seconds': 2000}, params={'replay_id': b['replay_id']})
            self.assertAlmostEqual(c.get('/api/replay/state', params={'replay_id': a['replay_id']}).json()['elapsed'], 120)
        self.assertEqual(calls, [7])                         # loaded once, shared read-only

    def test_start_errors(self):
        def missing(_):
            raise LookupError('nope')

        def not_ready(_):
            raise ReplayNotReady('no lap starts')

        with TestClient(app) as c:
            self.make_service(missing)
            self.assertEqual(c.post('/api/replay/start', json={'session_id': 1}).status_code, 404)
            self.make_service(not_ready)
            self.assertEqual(c.post('/api/replay/start', json={'session_id': 1}).status_code, 409)
            self.assertEqual(c.post('/api/replay/start', json={'session_id': 'x'}).status_code, 422)

    def test_delete_stops_a_replay(self):
        self.make_service(lambda _: self.timeline)
        with TestClient(app) as c:
            rid = c.post('/api/replay/start', json={'session_id': 1}).json()['replay_id']
            self.assertEqual(c.delete(f'/api/replay/{rid}').status_code, 200)
            self.assertEqual(c.get('/api/replay/state', params={'replay_id': rid}).status_code, 404)
            self.assertEqual(c.delete(f'/api/replay/{rid}').status_code, 404)

    def test_idle_replays_are_purged(self):
        service = self.make_service(lambda _: self.timeline)

        async def run():
            entry = await service.create(1)
            entry.state.last_active -= 10_000
            self.assertEqual(service.purge_idle(ttl=60), 1)
            with self.assertRaises(KeyError):
                await service.resolve(entry.state.id)

        asyncio.run(run())


class StreamTests(Base):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_stream_starts_with_reset_then_events_and_never_future(self):
        async def run():
            entry = await self.service.resolve(None)
            gen = sse_stream(entry)
            first = parse_sse(await gen.__anext__())
            self.assertEqual(first[0], 'reset')
            self.assertEqual(len(first[1]['drivers']), 19)
            self.service.control(entry, 'speed', speed=8)
            self.service.control(entry, 'play')
            await gen.__anext__()                            # state from speed
            await gen.__anext__()                            # state from play
            seen = []
            for _ in range(30):
                self.advance(20)                             # 160s virtual each
                self.service._tick(entry)
            self.service.control(entry, 'pause')
            for _ in range(80):
                try:
                    name, data = parse_sse(await asyncio.wait_for(gen.__anext__(), 0.05))
                except asyncio.TimeoutError:
                    break
                if name == 'events':
                    seen += data['events']
            await gen.aclose()
            return seen, entry.state.clock.now

        seen, now = self.run_async(run())
        self.assertGreater(len(seen), 50)
        self.assertTrue(all(datetime.fromisoformat(e['t']) <= now for e in seen))
        keys = [(e['t'], e['kind'], e['driver_number'], e['lap_number']) for e in seen]
        self.assertEqual(len(keys), len(set(keys)))

    def test_seek_sends_reset_with_only_past_events(self):
        async def run():
            entry = await self.service.resolve(None)
            sub = self.service.hub.subscribe(entry.state.id, entry.state.reset_message())
            self.service.control(entry, 'seek', offset_seconds=1200)
            messages = []
            while not sub.queue.empty():
                messages.append(sub.queue.get_nowait())
            return messages

        messages = self.run_async(run())
        resets = [m for m in messages if m['type'] == 'reset']
        self.assertEqual(len(resets), 2)
        snap = resets[1]
        limit = datetime.fromisoformat(snap['state']['now'])
        self.assertTrue(all(datetime.fromisoformat(e['t']) <= limit for e in snap['events']))
        self.assertGreater(len(snap['events']), 100)

    def test_two_subscribers_both_get_every_event(self):
        async def run():
            entry = await self.service.resolve(None)
            a = self.service.hub.subscribe(entry.state.id)
            b = self.service.hub.subscribe(entry.state.id)
            self.service.control(entry, 'speed', speed=8)
            self.service.control(entry, 'play')
            self.advance(60)
            self.service._tick(entry)
            def drain(sub):
                out = []
                while not sub.queue.empty():
                    m = sub.queue.get_nowait()
                    if m['type'] == 'events':
                        out += m['events']
                return out
            return drain(a), drain(b)

        ea, eb = self.run_async(run())
        self.assertGreater(len(ea), 0)
        self.assertEqual(ea, eb)


def until(ws, kind, limit=40):
    """Next message of this type (the live scheduler may interleave heartbeat state/events)."""
    for _ in range(limit):
        message = ws.receive_json()
        if message['type'] == kind:
            return message
    raise AssertionError(f'no {kind} message within {limit} messages')


class WebSocketTests(Base):
    def test_reset_then_controls_then_errors(self):
        with TestClient(app) as c, c.websocket_connect('/ws/replay') as ws:
            first = ws.receive_json()
            self.assertEqual(first['type'], 'reset')
            self.assertEqual(first['state']['state'], 'paused')
            ws.send_json({'action': 'speed', 'speed': 2})
            self.assertEqual(until(ws, 'state')['state']['speed'], 2.0)
            ws.send_json({'action': 'play'})
            self.assertEqual(until(ws, 'state')['state']['state'], 'playing')
            self.advance(300)
            ws.send_json({'action': 'pause'})             # settles first: due events are not lost
            got = until(ws, 'events')
            self.assertGreater(len(got['events']), 0)
            for _ in range(40):                             # heartbeat 'playing' states may still be queued
                if until(ws, 'state')['state']['state'] == 'paused':
                    break
            else:
                self.fail('never saw the paused state')
            ws.send_json({'action': 'speed', 'speed': 99})
            until(ws, 'error')
            ws.send_json({'action': 'fly'})
            until(ws, 'error')
            ws.send_json({'action': 'seek', 'offset_seconds': 5})
            self.assertEqual(until(ws, 'reset')['state']['elapsed'], 5)

    def test_unknown_replay_and_foreign_origin_rejected(self):
        with TestClient(app) as c:
            with self.assertRaises(WebSocketDisconnect):
                with c.websocket_connect('/ws/replay?replay_id=nope'):
                    pass
            with self.assertRaises(WebSocketDisconnect):
                with c.websocket_connect('/ws/replay', headers={'origin': 'http://evil.example'}):
                    pass
            with c.websocket_connect('/ws/replay', headers={'origin': 'http://localhost:5173'}) as ws:
                self.assertEqual(ws.receive_json()['type'], 'reset')


if __name__ == '__main__':
    unittest.main()

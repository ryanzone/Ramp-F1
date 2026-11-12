import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from backend.replay import Event, Timeline
from backend.replay_scheduler import HEARTBEAT, MIN_SLEEP, ReplayScheduler
from backend.replay_state import ReplayState
from backend.websocket_manager import ConnectionHub

T0 = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def at(s):
    return T0 + timedelta(seconds=s)


def timeline(*secs):
    ev = [Event(at(s), 'weather', None, None, {'i': i}) for i, s in enumerate(secs)]
    return Timeline(1, ev, {}, {}, meta={'start': T0, 'end': at(max(secs))})


class Mono:
    t = 0.0

    def __call__(self):
        return self.t


class TimingTests(unittest.TestCase):
    def state(self, *secs, speed=1.0):
        self.mono = Mono()
        return ReplayState('x', timeline(*secs), monotonic=self.mono, speed=speed)

    def test_delay_is_recorded_gap_divided_by_speed(self):
        s = self.state(10, 25, 40, speed=5)                  # clock starts at t=0, first event 10s away
        self.assertIsNone(s.seconds_until_next())            # paused
        s.clock.play()
        self.assertAlmostEqual(s.seconds_until_next(), 10 / 5)

    def test_after_an_event_the_next_gap_is_used(self):
        s = self.state(10, 25, 40, speed=5)
        s.clock.play(); s.settle()
        self.mono.t += 2.0                                   # 2s real = 10s virtual: event 0 is due
        self.assertEqual([e.data['i'] for e in s.settle()], [0])
        self.assertAlmostEqual(s.seconds_until_next(), 15 / 5)
        self.mono.t += 3.0
        self.assertEqual([e.data['i'] for e in s.settle()], [1])
        self.assertAlmostEqual(s.seconds_until_next(), 15 / 5)

    def test_speed_change_changes_the_wait(self):
        s = self.state(40, 80)
        s.clock.play(); s.settle()
        self.assertAlmostEqual(s.seconds_until_next(), 40)
        s.set_speed(8)
        self.assertAlmostEqual(s.seconds_until_next(), 5)
        s.set_speed(0.5)
        self.assertAlmostEqual(s.seconds_until_next(), 80)

    def test_wait_never_overshoots_the_end(self):
        s = self.state(10, 20)
        s.clock.seek(at(20)); s.clock.play()
        self.assertIsNone(s.seconds_until_next())            # finished clocks do not play

    def test_scheduler_timeout_is_capped_and_floored(self):
        s = self.state(10, 100)
        sched = ReplayScheduler(s.seconds_until_next, lambda: None)
        self.assertIsNone(sched.timeout())                   # paused -> sleep until poked
        s.clock.play(); s.settle()
        self.assertEqual(sched.timeout(), HEARTBEAT)         # long gap -> heartbeat only
        s.clock.seek(at(99.999)); s.clock.play()
        self.assertEqual(sched.timeout(), MIN_SLEEP)         # sub-ms gap -> floor


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduler_wakes_on_poke_when_paused(self):
        ticks = []
        paused = {'v': True}
        sched = ReplayScheduler(lambda: None if paused['v'] else 0.01, lambda: ticks.append(1))
        sched.start()
        await asyncio.sleep(0.05)
        self.assertEqual(ticks, [])                          # nothing happens while paused
        sched.poke()
        await asyncio.sleep(0.02)
        self.assertEqual(len(ticks), 1)
        sched.stop()

    async def test_scheduler_ticks_on_the_event_delay_while_playing(self):
        ticks = []
        sched = ReplayScheduler(lambda: 0.02, lambda: ticks.append(1))
        sched.start()
        await asyncio.sleep(0.2)
        sched.stop()
        self.assertGreaterEqual(len(ticks), 4)               # woke on the 20ms delay, not on a coarse poll

    async def test_hub_drops_backlog_and_resyncs_slow_clients(self):
        hub = ConnectionHub()
        slow = hub.subscribe('r')
        for i in range(slow.queue.maxsize):
            slow.push({'type': 'events', 'i': i})
        hub.publish('r', {'type': 'events', 'i': 'new'}, resync=lambda: {'type': 'reset', 'x': 1})
        self.assertEqual(slow.queue.qsize(), 1)
        self.assertEqual(slow.queue.get_nowait()['type'], 'reset')

    async def test_first_message_is_queued_before_anything_else(self):
        hub = ConnectionHub()
        sub = hub.subscribe('r', first_message={'type': 'reset'})
        hub.publish('r', {'type': 'events'}, resync=dict)
        self.assertEqual([sub.queue.get_nowait()['type'] for _ in range(2)], ['reset', 'events'])
        hub.unsubscribe('r', sub)
        self.assertEqual(hub.count('r'), 0)


if __name__ == '__main__':
    unittest.main()

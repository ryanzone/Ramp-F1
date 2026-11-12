import unittest
from datetime import datetime, timedelta, timezone

from backend import replay
from backend.replay import Event
from backend.replay_clock import PAUSED, PLAYING, ReplayClock

T0 = datetime(2023, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def at(s):
    return T0 + timedelta(seconds=s)


def events(*secs):
    return [Event(at(s), 'weather', None, None, {'i': i}) for i, s in enumerate(secs)]


def ids(evs):
    return [e.data['i'] for e in evs]


class ClockTests(unittest.TestCase):
    def clock(self, *secs, **kw):
        return ReplayClock(events(*secs or (0, 10, 20, 30)), **kw)

    def test_initial_state(self):
        c = self.clock()
        self.assertEqual((c.state, c.speed, c.now, c.elapsed, c.duration), (PAUSED, 1.0, at(0), 0, 30))

    def test_paused_does_not_advance(self):
        c = self.clock()
        self.assertEqual(c.advance(100), [])
        self.assertEqual(c.now, at(0))

    def test_play_advance_returns_due_events_once(self):
        c = self.clock()
        c.play()
        self.assertEqual(ids(c.advance(0)), [0])           # event exactly at start
        self.assertEqual(ids(c.advance(9.9)), [])
        self.assertEqual(ids(c.advance(0.1)), [1])          # boundary t == now is due
        self.assertEqual(ids(c.advance(10)), [2])
        self.assertEqual(c.advance(0)  , [])

    def test_never_returns_future_events(self):
        c = self.clock()
        c.play()
        got = c.advance(15)
        self.assertTrue(all(e.t <= c.now for e in got))
        self.assertEqual(ids(got), [0, 1])

    def test_speed_multiplier(self):
        c = self.clock(speed=4)
        c.play()
        self.assertEqual(ids(c.advance(5)), [0, 1, 2])      # 5s real = 20s virtual
        self.assertEqual(c.now, at(20))
        c.set_speed(0.25)
        c.advance(4)                                        # 1s virtual
        self.assertEqual(c.now, at(21))

    def test_speed_validation(self):
        c = self.clock()
        for ok in (0.25, 0.5, 1, 2, 5, 10):
            c.set_speed(ok)
        for bad in (0.2, 10.01, 0, -1, float('nan'), float('inf'), True, '2', None):
            with self.assertRaises(ValueError):
                c.set_speed(bad)
        self.assertEqual(c.speed, 10.0)                     # unchanged by failures

    def test_reaches_end_then_pauses_and_clamps(self):
        c = self.clock()
        c.play()
        got = c.advance(1000)
        self.assertEqual(ids(got), [0, 1, 2, 3])
        self.assertEqual((c.now, c.state, c.finished), (at(30), PAUSED, True))
        c.play()
        self.assertEqual(c.state, PAUSED)                   # no-op at the end
        self.assertEqual(c.advance(5), [])

    def test_seek_forward_skips_without_emitting(self):
        c = self.clock()
        c.play()
        c.seek(at(25))
        self.assertEqual(c.state, PLAYING)
        self.assertEqual(ids(c.seen()), [0, 1, 2])
        self.assertEqual(ids(c.advance(5)), [3])            # 2 was skipped, not replayed

    def test_seek_backward_replays_future_events(self):
        c = self.clock()
        c.play()
        c.advance(30)
        c.seek(at(5))
        c.play()
        self.assertEqual(ids(c.seen()), [0])
        self.assertEqual(ids(c.advance(30)), [1, 2, 3])     # no duplicates of 0

    def test_seek_clamps_and_validates(self):
        c = self.clock()
        c.seek(at(-50)); self.assertEqual(c.now, at(0))
        c.seek(at(500)); self.assertEqual((c.now, c.state), (at(30), PAUSED))
        for bad in (5, None, datetime(2023, 1, 1)):
            with self.assertRaises(ValueError):
                c.seek(bad)

    def test_seek_offset(self):
        c = self.clock()
        c.seek_offset(12)
        self.assertEqual(c.now, at(12))
        with self.assertRaises(ValueError):
            c.seek_offset(float('nan'))

    def test_seen_equals_union_of_advances(self):
        c = self.clock(0, 3, 3, 7, 12, 12, 30)
        c.play()
        emitted = []
        for _ in range(50):                                 # 35s of virtual time > 30s span
            emitted += c.advance(0.7)
        self.assertEqual(ids(emitted), ids(c.seen()))
        self.assertEqual(len(emitted), 7)

    def test_chunking_does_not_change_result(self):
        a, b = self.clock(0, 3, 3, 7, 12, 30), self.clock(0, 3, 3, 7, 12, 30)
        a.play(); b.play()
        one = a.advance(30)
        many = [e for _ in range(300) for e in b.advance(0.1)]
        self.assertEqual(ids(one), ids(many))

    def test_bad_elapsed(self):
        c = self.clock(); c.play()
        for bad in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                c.advance(bad)

    def test_unsorted_or_empty_input(self):
        with self.assertRaises(ValueError):
            ReplayClock(events(5, 1))
        with self.assertRaises(ValueError):
            ReplayClock([])
        c = ReplayClock([], start=at(0), end=at(10))
        c.play(); self.assertEqual(c.advance(20), [])

    def test_explicit_bounds(self):
        c = ReplayClock(events(10, 20), start=at(0), end=at(40))
        c.play()
        self.assertEqual(c.advance(5), [])
        self.assertEqual(c.duration, 40)

    def test_with_real_singapore_timeline(self):
        tl = replay.load_timeline(9165)
        c = ReplayClock(tl.events, speed=8)
        c.play()
        total, steps = 0, 0
        while c.state == PLAYING:
            got = c.advance(30)                             # 30s real = 4 min virtual
            self.assertTrue(all(e.t <= c.now for e in got))
            total += len(got); steps += 1
        self.assertEqual(total, len(tl.events))


if __name__ == '__main__':
    unittest.main()

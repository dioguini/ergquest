import random
import unittest

from ergquest.server import anticheat as ac
from ergquest.shared import physics


def ride(watts_fn, n=1500, weight=70, hr_fn=None, inflate=1.0, seed=1):
    rng = random.Random(seed)
    v = dist = 0.0
    hr = 100.0
    out = []
    for t in range(n):
        w = watts_fn(t, rng)
        v = physics.step_velocity(weight + physics.BIKE_KG, physics.DEFAULT_CDA, physics.DEFAULT_CRR, v, w, 0.0, 1.0)
        dist += v * inflate
        hr += (100 + w * 0.3 - hr) * 0.03
        h = hr_fn(t) if hr_fn else round(hr)
        out.append(ac.Sample(t, w, h, 88 if w > 0 else 0, 0.0, dist))
    return out


def human(t, rng):
    return (300 if (t // 120) % 2 else 180) * rng.uniform(0.9, 1.1)


class AntiCheatTest(unittest.TestCase):
    def test_honest_ride_is_trusted(self):
        rep = ac.validate(ride(human), 70)
        self.assertTrue(rep.ranked_ok, rep.flags)
        self.assertEqual(rep.trust, 1.0)

    def test_superhuman_power_flagged(self):
        rep = ac.validate(ride(lambda t, r: 650 * r.uniform(0.98, 1.02)), 70)
        self.assertIn("envelope", [f.code for f in rep.flags])
        self.assertFalse(rep.ranked_ok)

    def test_bot_signature(self):
        rep = ac.validate(ride(lambda t, r: 250.0, n=900), 70)
        self.assertIn("robotic_power", [f.code for f in rep.flags])

    def test_inflated_distance_flagged_by_physics(self):
        rep = ac.validate(ride(human, inflate=1.15), 70)
        self.assertIn("physics_distance", [f.code for f in rep.flags])
        self.assertFalse(rep.ranked_ok)

    def test_power_without_cadence(self):
        s = [ac.Sample(t, 250 * (1 + 0.05 * (t % 3)), 140, None) for t in range(60)]
        rep = ac.validate(s, 70)
        self.assertIn("power_without_cadence", [f.code for f in rep.flags])

    def test_frozen_heart_rate(self):
        rep = ac.validate(ride(human, hr_fn=lambda t: 150), 70)
        codes = [f.code for f in rep.flags]
        self.assertIn("hr_flatline", codes)

    def test_time_must_advance(self):
        s = ride(human, n=100)
        s[50] = ac.Sample(s[49].t, 200, 120, 80)
        self.assertIn("time_order", [f.code for f in ac.validate(s, 70).flags])


class DemoTest(unittest.TestCase):
    def test_demo_runs(self):
        import contextlib, io
        from ergquest import demo
        with contextlib.redirect_stdout(io.StringIO()):
            res = demo.main()
        self.assertEqual(len(res["loads"]), 4)              # treino + 3 trabalhos de jogo
        self.assertEqual(len(res["stars"]), 3)              # só o jogo dá estrelas
        self.assertEqual(res["trust"], 1.0)
        self.assertGreater(res["compliance"], 90)
        self.assertTrue(res["errand"])

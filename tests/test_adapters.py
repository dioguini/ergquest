import unittest

from ergquest.devices import sim
from ergquest.devices.adapters import (MANUAL_TREADMILL, DomyosRower, ManualTreadmill, RowerPowerEstimator,
                                       looks_like_domyos)
from ergquest.devices.hub import check
from ergquest.game.cities import Sport
from ergquest.game.progression import Profile, xp_for_level
from ergquest.game.session import PlayerState


class ManualTreadmillTest(unittest.TestCase):
    def test_speed_incline_and_distance(self):
        tm = ManualTreadmill()
        tm.set(10.8, 1.0, now=0)
        r = tm.reading(now=100)
        self.assertAlmostEqual(r.speed_mps, 3.0)
        self.assertAlmostEqual(r.distance_m, 300.0)
        self.assertTrue(r.extra["estimated"])
        tm.nudge(+0.5, now=100)
        tm.nudge(d_incline=-0.5, now=100)
        self.assertEqual((tm.speed_kmh, tm.incline_pct), (11.3, 0.5))
        tm.set(99)
        self.assertEqual(tm.speed_kmh, 22.0)                       # limite

    def test_prompt_cleared_when_athlete_changes_speed(self):
        tm = ManualTreadmill()
        self.assertEqual(tm.ask(14), "põe a passadeira a 14.0 km/h")
        tm.set(14)
        self.assertIsNone(tm.prompt)

    def test_hr_plausibility(self):
        tm = ManualTreadmill(speed_kmh=16)
        self.assertFalse(tm.plausible_with_hr(110, 190, threshold_kmh=13))
        self.assertTrue(tm.plausible_with_hr(170, 190, threshold_kmh=13))


class RowerEstimateTest(unittest.TestCase):
    def test_formulas_and_calibration(self):
        est = RowerPowerEstimator()
        self.assertAlmostEqual(est.estimate(pace_s_500m=120), 202.5, delta=0.2)   # 2:00/500 m ≈ 203 W
        self.assertEqual(est.estimate(kcal_h=1100), 200.0)
        self.assertAlmostEqual(est.estimate(stroke_rate=24, level=5), 132.0)
        self.assertIsNone(est.estimate())
        est.calibrate(200, 180)
        self.assertEqual(est.estimate(kcal_h=1100), 180.0)

    def test_domyos(self):
        self.assertTrue(looks_like_domyos("DOMYOS-ROW-1234"))
        self.assertFalse(looks_like_domyos("KICKR CORE 5A2B"))
        d = DomyosRower()
        self.assertIsNone(d.decode(b"\xf0\xbc\x01"))
        self.assertEqual(len(d.frames), 1)
        self.assertTrue(d.device.estimated)


class EstimatedSessionsTest(unittest.TestCase):
    def test_estimated_data_is_out_of_rankings(self):
        self.assertTrue(check("run", [MANUAL_TREADMILL]).ok)
        self.assertFalse(check("run", [MANUAL_TREADMILL]).ranked)
        self.assertTrue(check("bike", [sim.SMART_TRAINER]).ranked)
        ana = Profile("ana", 64, xp={"run": xp_for_level(3)})
        p = PlayerState("ana", "lisboa", "n-baixa")
        s = p.start(Sport.RUN, 0, devices=[MANUAL_TREADMILL, sim.HR_STRAP], profile=ana)
        self.assertFalse(s.ranked)
        self.assertIn("dados estimados", p.devices_check.summary())

import unittest
from datetime import date, timedelta

from ergquest.shared import load, physics


class PhysicsTest(unittest.TestCase):
    def test_equilibrium_speed_round_trips(self):
        v = physics.speed_from_power(80, 0.32, 0.004, 250, 0.0)
        self.assertAlmostEqual(physics.power_required(80, 0.32, 0.004, v, 0.0), 250, delta=2)

    def test_climb_is_slower(self):
        flat = physics.speed_from_power(80, 0.32, 0.004, 250, 0.0)
        climb = physics.speed_from_power(80, 0.32, 0.004, 250, 0.08)
        self.assertLess(climb, flat / 2)

    def test_step_converges_to_equilibrium(self):
        v = 0.0
        for _ in range(600):
            v = physics.step_velocity(80, 0.32, 0.004, v, 200, 0.0, 1.0)
        self.assertAlmostEqual(v, physics.speed_from_power(80, 0.32, 0.004, 200, 0.0), delta=0.05)

    def test_trainer_grade_is_clamped(self):
        self.assertEqual(physics.trainer_grade(40), physics.MAX_TRAINER_GRADE)
        self.assertEqual(physics.trainer_grade(10, difficulty=0.5), 5.0)


class LoadTest(unittest.TestCase):
    def test_one_hour_at_ftp_is_100_tss(self):
        self.assertAlmostEqual(load.tss([250.0] * 3600, 250), 100.0, places=6)

    def test_np_above_average_for_intervals(self):
        series = ([400.0] * 60 + [100.0] * 60) * 10
        self.assertGreater(load.normalized(series), sum(series) / len(series))

    def test_rtss_threshold_hour(self):
        self.assertAlmostEqual(load.rtss([4.0] * 3600, 4.0), 100.0, places=6)

    def test_uphill_running_costs_more(self):
        self.assertGreater(load.grade_factor(8), 1.3)
        self.assertLess(load.grade_factor(-5), 1.0)

    def test_pmc_constant_load_converges(self):
        today = date(2026, 1, 1)
        daily = {today - timedelta(days=i): 100.0 for i in range(400)}
        last = load.pmc(daily, today)[-1]
        self.assertAlmostEqual(last["ctl"], 100.0, delta=0.1)
        self.assertAlmostEqual(last["atl"], 100.0, delta=0.01)

    def test_form_states(self):
        self.assertEqual(load.form_state(30), "transição")
        self.assertEqual(load.form_state(-20), "ótimo")
        self.assertEqual(load.form_state(-50), "sobrecarga")

import unittest

from ergquest.shared.movement import Bike
from ergquest.training.setup import Branch, TrainingSetup, Venue, rank_branches, trainer_command
from ergquest.training.workout import Step, Workout, WorkoutRunner

WO = Workout("t", [Step("steady", 300, target_lo=60), Step("steady", 240, target_lo=100),
                   Step("freeride", 120, target_type="none")])


class TrainerCommandTest(unittest.TestCase):
    def test_erg_on_trainer_rules_anywhere(self):
        for venue in Venue:
            cmd = trainer_command(TrainingSetup(True, venue), 250, 8.0)
            self.assertEqual((cmd.mode, cmd.target_w, cmd.grade_pct), ("erg", 250, None))

    def test_erg_off_world_sends_real_grade(self):
        cmd = trainer_command(TrainingSetup(False, Venue.WORLD), 250, 6.0)
        self.assertEqual((cmd.mode, cmd.grade_pct), ("sim", 6.0))
        soft = trainer_command(TrainingSetup(False, Venue.WORLD, difficulty=0.5), 250, 6.0)
        self.assertEqual(soft.grade_pct, 3.0)

    def test_erg_off_screen_is_flat_road(self):
        cmd = trainer_command(TrainingSetup(False, Venue.SCREEN), 250, 6.0)
        self.assertEqual((cmd.mode, cmd.grade_pct), ("sim", 0.0))

    def test_freeride_step_falls_back_to_sim_even_with_erg(self):
        cmd = trainer_command(TrainingSetup(True, Venue.WORLD), None, 4.0)
        self.assertEqual((cmd.mode, cmd.grade_pct), ("sim", 4.0))

    def test_who_controls(self):
        self.assertTrue(TrainingSetup(False, Venue.WORLD).athlete_controls_power)
        self.assertFalse(TrainingSetup(True, Venue.WORLD).athlete_controls_power)


class WorkoutRunnerTest(unittest.TestCase):
    def test_targets_and_compliance(self):
        r = WorkoutRunner(WO, 250)
        self.assertEqual(r.target_watts(10), 150)
        self.assertEqual(r.target_watts(400), 250)
        self.assertIsNone(r.target_watts(600))
        self.assertIsNone(r.step_at(10_000))
        for t in range(540):
            r.observe(t, 150 if t < 300 else 200)     # falha o bloco de 100 %
        res = r.results()
        self.assertEqual(res[0]["pct_in_target"], 100.0)
        self.assertEqual(res[1]["pct_in_target"], 0.0)
        self.assertAlmostEqual(r.overall_compliance(), 300 / 540 * 100)

    def test_estimated_tss(self):
        one_hour_ftp = Workout("h", [Step("steady", 3600, target_lo=100)])
        self.assertAlmostEqual(one_hour_ftp.estimated_tss(250), 100.0)

    def test_upcoming_horizon(self):
        up = WorkoutRunner(WO, 250).upcoming(240, 180)
        self.assertEqual(up[0], (60.0, 0.6))
        self.assertEqual(up[1][1], 1.0)


class BranchAdviceTest(unittest.TestCase):
    def setUp(self):
        self.bike = Bike(70, 250)
        self.climb = Branch("rampa", [(600, 10.0)])
        self.flat = Branch("plano", [(1000, 0.0)])
        self.descent = Branch("descida", [(1000, -8.0)])

    def test_recovery_avoids_steep_climb(self):
        ranked = rank_branches(self.bike, [self.climb, self.flat], [(300, 0.5)])
        self.assertEqual(ranked[0][0], "plano")

    def test_threshold_block_avoids_descent(self):
        ranked = rank_branches(self.bike, [self.descent, self.climb], [(300, 1.0)])
        self.assertEqual(ranked[0][0], "rampa")

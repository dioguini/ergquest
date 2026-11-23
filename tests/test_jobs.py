import unittest

from ergquest.game import errands, taxi
from ergquest.shared.movement import (PEDICAB, ROAD_BIKE, WATER_TAXI, Bike, Rower, Runner, estimated_load,
                                      intensity_for, time_for, watts_to_hold)


class MovementTest(unittest.TestCase):
    def test_load_slows_every_sport(self):
        prof = [(1000, 4.0)]
        for mover in (Bike(70, 250), Runner(70, 3.5), Rower(75, 200)):
            self.assertGreater(time_for(mover, prof, 0.8, 60), time_for(mover, prof, 0.8))

    def test_pedicab_with_passenger_changes_physics(self):
        solo, cab = Bike(70, 250, ROAD_BIKE), Bike(70, 250, PEDICAB)
        self.assertLess(cab.speed_at(0.8, 8, 90), solo.speed_at(0.8, 8) / 2.5)

    def test_intensity_for_inverts_time_for(self):
        m, prof = Bike(70, 250), [(500, 2.0), (500, -1.0)]
        t = time_for(m, prof, 0.8)
        self.assertAlmostEqual(intensity_for(m, prof, t), 0.8, places=2)

    def test_water_taxi_heavier_is_slower(self):
        self.assertGreater(Rower(75, 200).speed_at(0.8), Rower(75, 200, WATER_TAXI).speed_at(0.8, 0, 200))

    def test_estimated_load(self):
        self.assertAlmostEqual(estimated_load(3600, 1.0), 100.0)


class ErrandTest(unittest.TestCase):
    def setUp(self):
        self.runner = Runner(65, 3.6)
        self.offer = errands.make_offer("ana", 4, self.runner, 9)

    def test_plan_shown_before_accepting(self):
        o = self.offer
        self.assertEqual(len(o.stops), len(o.legs))
        self.assertTrue(o.stops[-1].startswith("Casa de"))
        self.assertGreater(o.deadline_s, o.est_s)          # há margem…
        self.assertLess(o.required_intensity, 0.65)       # …em esforço
        self.assertIn("precisa de", o.summary())
        self.assertGreater(o.est_load, 0)

    def test_deterministic_for_same_player_and_npc(self):
        again = errands.make_offer("ana", 4, self.runner, 9)
        self.assertEqual((again.npc, again.stops, again.deadline_s), (self.offer.npc, self.offer.stops, self.offer.deadline_s))

    def test_carried_weight_shows_in_later_legs(self):
        o = errands.make_offer("ana", 2, self.runner, 9)
        self.assertEqual(o.legs[0].carrying_kg, 0.0)

    def test_must_follow_plan_in_order_and_on_time(self):
        run = errands.accept(self.offer, 0)
        with self.assertRaises(errands.ErrandError):
            run.arrive(self.offer.stops[-1], 10)
        for i, stop in enumerate(self.offer.stops):
            run.arrive(stop, (i + 1) * self.offer.deadline_s / len(self.offer.stops) * 0.9)
        self.assertTrue(run.result["completed"])
        self.assertEqual(run.result["xp"], self.offer.reward_xp)

    def test_late_is_failed(self):
        run = errands.accept(self.offer, 0)
        for stop in self.offer.stops:
            run.arrive(stop, self.offer.deadline_s * 2)
        self.assertFalse(run.result["completed"])
        self.assertEqual(run.result["xp"], 0)
        self.assertGreater(run.result["reputation_penalty"], 0)

    def test_abandon(self):
        run = errands.accept(self.offer, 0)
        self.assertEqual(run.abandon(100)["reputation_penalty"], 1.0)


class TaxiTest(unittest.TestCase):
    CASTELO = [(300, 1.0), (300, 6.0), (200, 9.0), (200, -3.0)]

    def test_license_needs_level_and_gym(self):
        self.assertFalse(taxi.can_drive(PEDICAB, 5, 1.0)[0])
        self.assertFalse(taxi.can_drive(PEDICAB, 10, 0.1)[0])
        self.assertTrue(taxi.can_drive(PEDICAB, 10, 0.5)[0])
        offer = taxi.make_offer("a", 1, Bike(70, 250, PEDICAB), 10)
        with self.assertRaises(PermissionError):
            taxi.accept(offer, 0, 10, 0.0)

    def test_quote_shows_passenger_physics(self):
        o = taxi.make_offer("a", 1, Bike(70, 250, PEDICAB), 10, profile=self.CASTELO)
        self.assertGreater(o.extra_kg, 40)
        self.assertGreater(o.est_s, o.solo_s * 1.2)
        self.assertEqual(o.steepest_pct, 9.0)
        cab = Bike(70, 250, PEDICAB)
        self.assertAlmostEqual(o.steepest_w, watts_to_hold(cab, 9.0, 1.4, o.extra_kg), delta=1)
        self.assertIn("rampa mais dura", o.summary())

    def test_road_bike_cannot_be_a_taxi(self):
        with self.assertRaises(ValueError):
            taxi.make_offer("a", 1, Bike(70, 250), 10)

    def test_water_taxi(self):
        o = taxi.make_offer("a", 2, Rower(75, 200, WATER_TAXI), 14)
        self.assertIsNone(o.steepest_w)
        self.assertLessEqual(len(o.passengers), WATER_TAXI.seats)

    def test_comfort_safety_and_crawling(self):
        o = taxi.make_offer("a", 1, Bike(70, 250, PEDICAB), 10, profile=self.CASTELO)
        smooth = taxi.accept(o, 0, 10, 0.5)
        for _ in range(60):
            smooth.observe(1.0, 4.0, 2.0)
        rough = taxi.accept(o, 0, 10, 0.5)
        for i in range(60):
            rough.observe(1.0, 0.8 if i % 2 else 10.0, -4.0)   # solavancos, a descer depressa e a rastejar
        a, b = smooth.finish(o.est_s), rough.finish(o.est_s)
        self.assertEqual(a["stars"], 5)
        self.assertLess(b["stars"], a["stars"])
        self.assertLess(b["safety"], 1.0)
        self.assertGreater(b["crawl_s"], 0)


class SteepestTest(unittest.TestCase):
    def test_short_spike_is_diluted(self):
        from ergquest.shared.movement import steepest
        prof = [(10.0, 2.0)] * 4 + [(10.0, 25.0)] + [(10.0, 2.0)] * 4
        self.assertAlmostEqual(steepest(prof), (25 + 3 * 2) / 4)
        self.assertAlmostEqual(steepest([(100.0, 9.0)]), 9.0)

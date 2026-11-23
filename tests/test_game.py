import math
import random
import unittest
from datetime import date, timedelta

from ergquest.game import challenges as chl
from ergquest.game import chase, progression, rowing, strength
from ergquest.game.missions import Kind, OrderBoard, sources_for
from ergquest.game.session import Mode, PlayerState, SessionError
from ergquest.training.setup import TrainingSetup, Venue
from ergquest.game.cities import CITIES, Sport, can_swap_at_street

TODAY = date(2026, 11, 23)


class WorldTest(unittest.TestCase):
    def test_every_city_has_three_indoor_crits_and_one_velodrome(self):
        for c in CITIES.values():
            kinds = [v.kind for v in c.venues]
            self.assertEqual(kinds.count("crit_indoor"), 3, c.id)
            self.assertEqual(kinds.count("velodrome"), 1, c.id)
            self.assertTrue(any(z.water for z in c.zones), c.id)

    def test_street_swaps(self):
        self.assertTrue(can_swap_at_street(Sport.BIKE, Sport.RUN))
        self.assertFalse(can_swap_at_street(Sport.BIKE, Sport.ROW))


class StrengthTest(unittest.TestCase):
    def test_no_gym_no_buff(self):
        self.assertEqual(strength.robustness([], TODAY), 0.0)
        self.assertAlmostEqual(strength.xp_multiplier(0.0), 0.85)

    def test_regular_gym_with_hr_is_full(self):
        s = [strength.GymSession(TODAY - timedelta(days=d), 45, True) for d in (1, 4, 8, 11, 15, 18, 22, 25)]
        self.assertEqual(strength.robustness(s, TODAY), 1.0)
        self.assertEqual(strength.extra_order_slots(1.0), 2)

    def test_manual_and_old_sessions_count_less(self):
        manual = [strength.GymSession(TODAY - timedelta(days=d), 45) for d in (1, 4, 8, 11, 15, 18, 22, 25)]
        old = [strength.GymSession(TODAY - timedelta(days=40), 45, True)]
        short = [strength.GymSession(TODAY, 10, True)]
        self.assertLess(strength.robustness(manual, TODAY), 1.0)
        self.assertEqual(strength.robustness(old + short, TODAY), 0.0)


class ProgressionTest(unittest.TestCase):
    def test_level_curve(self):
        self.assertEqual(progression.level_for(0, 0), 1)
        self.assertGreater(progression.level_for(10_000, 1.0), 5)

    def test_gym_gates_max_potential(self):
        xp = progression.xp_for_level(35)
        self.assertEqual(progression.level_for(xp, 0.0), 19)
        self.assertEqual(progression.level_for(xp, 0.35), 29)
        self.assertEqual(progression.level_for(xp, 0.5), 35)

    def test_xp_rewards_effort_and_stars(self):
        p = progression.Profile("x", 70)
        gained = p.add_session(60, [5, 4])
        self.assertEqual(gained, round((600 + 9 * 40) * 0.85))

    def test_unlocks(self):
        p = progression.Profile("x", 70)
        self.assertTrue(p.city_unlocked("lisboa"))
        self.assertFalse(p.city_unlocked("london"))
        self.assertEqual(p.zones_unlocked("lisboa"), ["n-baixa"])
        p.xp, p.active_weeks_last8 = progression.xp_for_level(12), 4
        self.assertTrue(p.city_unlocked("london"))
        self.assertIn("n-este", p.zones_unlocked("lisboa"))

    def test_jobs_unlock_establishments(self):
        from ergquest.game.missions import sources_for
        p = progression.Profile("x", 70)
        food = [s for s in sources_for("lisboa", "baixa") if s.kind is Kind.FOOD]
        self.assertEqual(len(p.available_sources(food)), 1)
        for _ in range(5):
            p.record_job("food")
        self.assertEqual(len(p.available_sources(food)), 2)

    def test_reputation_drops_with_abandons(self):
        p = progression.Profile("x", 70, ratings=[5] * 10)
        p.abandons = 3
        self.assertAlmostEqual(p.reputation, 4.7)


class RowingTest(unittest.TestCase):
    def test_smooth_beats_jerky(self):
        one = [math.sin(math.pi * i / 20) for i in range(21)]
        two = [abs(math.sin(2 * math.pi * i / 20)) for i in range(21)]
        self.assertGreater(rowing.curve_quality(one), 0.9)
        self.assertLess(rowing.curve_quality(two), 0.75)
        rng = random.Random(1)
        steady = [200 * rng.gauss(1, 0.03) for _ in range(50)]
        surging = [200 * rng.gauss(1, 0.2) for _ in range(50)]
        self.assertGreater(rowing.smoothness(steady, [one]), rowing.smoothness(surging, [two]) + 0.3)


class ChaseTest(unittest.TestCase):
    def test_slow_runner_lets_thief_escape(self):
        c = chase.Chase(4.0, seed=3)
        while not c.outcome:
            c.step(1.0, 2.5)
        self.assertEqual(c.outcome, "escaped")

    def test_fast_runner_catches_and_gets_warning_first(self):
        c = chase.Chase(4.0, seed=3, head_start_m=150)
        events = []
        while not c.outcome:
            events += c.step(1.0, 4.6)
        self.assertEqual(c.outcome, "caught")
        self.assertLess(events.index("sprint_warning"), events.index("sprint"))


class SessionTest(unittest.TestCase):
    def test_swap_bike_to_run_parks_bike(self):
        p = PlayerState("a", "lisboa", "n-baixa")
        p.start(Sport.BIKE, 0)
        old, new = p.swap(Sport.RUN, 600)
        self.assertEqual((old.sport, old.ended_at, new.sport), (Sport.BIKE, 600, Sport.RUN))
        self.assertEqual(p.parked_bike, ("lisboa", "n-baixa"))

    def test_rowing_needs_a_dock_and_gym_is_offworld(self):
        p = PlayerState("a", "lisboa", "n-baixa")
        with self.assertRaises(SessionError):
            p.start(Sport.ROW, 0)
        with self.assertRaises(SessionError):
            p.start(Sport.GYM, 0)
        p.zone, p.at_dock = "n-centro", True
        self.assertEqual(p.start(Sport.ROW, 0).sport, Sport.ROW)

    def test_training_on_screen_needs_no_dock(self):
        p = PlayerState("a", "lisboa", "n-baixa")
        s = p.start(Sport.ROW, 0, Mode.TRAINING, training=TrainingSetup(erg=True, venue=Venue.SCREEN))
        self.assertFalse(s.in_world)

    def test_training_mode_requires_setup(self):
        p = PlayerState("a", "lisboa", "n-baixa")
        with self.assertRaises(SessionError):
            p.start(Sport.BIKE, 0, Mode.TRAINING)
        with self.assertRaises(SessionError):
            p.start(Sport.BIKE, 0, Mode.MISSION, training=TrainingSetup(False, Venue.WORLD))

    def test_cannot_swap_with_active_missions(self):
        p = PlayerState("a", "lisboa", "n-baixa")
        p.start(Sport.BIKE, 0, Mode.MISSION)
        with self.assertRaises(SessionError):
            p.swap(Sport.RUN, 10, active_missions=1)


class ChallengeTest(unittest.TestCase):
    def setUp(self):
        self.low = progression.Profile("low", 70)
        self.high = progression.Profile("high", 70, xp=progression.xp_for_level(15), active_weeks_last8=5)
        self.s_low = PlayerState("low", "lisboa", "n-baixa")
        self.s_high = PlayerState("high", "london", "city")

    def test_cross_level_and_cross_city(self):
        ch = chl.propose(self.high, self.s_high, "london", chl.Format.SEGMENT)
        chl.join(ch, self.low, self.s_low)
        self.assertIn("low", ch.opponents)
        self.assertIn("low", ch.traveling)
        with self.assertRaises(chl.ChallengeError):
            chl.propose(self.low, self.s_low, "london", chl.Format.SEGMENT)

    def test_players_in_training_cannot_be_challenged(self):
        self.s_low.start(Sport.BIKE, 0, Mode.TRAINING, training=TrainingSetup(True, Venue.SCREEN))
        ch = chl.propose(self.high, self.s_high, "london", chl.Format.SEGMENT)
        with self.assertRaises(chl.ChallengeError):
            chl.join(ch, self.low, self.s_low)

    def test_busy_players_cannot_challenge(self):
        self.s_low.start(Sport.BIKE, 0, Mode.MISSION)
        with self.assertRaises(chl.ChallengeError):
            chl.propose(self.low, self.s_low, "lisboa", chl.Format.SEGMENT)
        ch = chl.propose(self.high, self.s_high, "london", chl.Format.SEGMENT)
        with self.assertRaises(chl.ChallengeError):
            chl.join(ch, self.low, self.s_low)

    def test_venue_and_free_route_rules(self):
        ok = chl.propose(self.low, self.s_low, "lisboa", chl.Format.VELODROME, venue="lis-velo", event="keirin")
        self.assertEqual(ok.event, "keirin")
        with self.assertRaises(chl.ChallengeError):
            chl.propose(self.low, self.s_low, "lisboa", chl.Format.VELODROME, venue="lis-velo", event="jogging")
        with self.assertRaises(chl.ChallengeError):
            chl.propose(self.low, self.s_low, "lisboa", chl.Format.CRIT_INDOOR, venue="lis-velo")
        with self.assertRaises(chl.ChallengeError):
            chl.propose(self.low, self.s_low, "lisboa", chl.Format.FREE, waypoints=[(0, 0), (100, 0)])
        free = chl.propose(self.low, self.s_low, "lisboa", chl.Format.FREE, waypoints=[(0, 0), (300, 0), (300, 300)])
        self.assertEqual(len(free.waypoints), 3)

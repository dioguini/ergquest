import unittest

from ergquest.game import missions as m
from ergquest.game.cities import Sport


def speed_at(sport, intensity):
    return {Sport.BIKE: 8.0, Sport.RUN: 3.5, Sport.ROW: 3.8}[sport] * intensity


class MissionsTest(unittest.TestCase):
    def setUp(self):
        self.srcs = m.sources_for("lisboa", "baixa")
        self.food = [s for s in self.srcs if s.kind is m.Kind.FOOD]

    def board(self, level=1, rob=0.0, cargo=2.0, pid="p1"):
        return m.OrderBoard(pid, level, speed_at, rob, cargo)

    def test_sources_are_deterministic_and_fictional(self):
        again = m.sources_for("lisboa", "baixa")
        self.assertEqual([s.name for s in self.srcs], [s.name for s in again])
        self.assertTrue(all(s.city == "lisboa" for s in self.srcs))

    def test_offers_deterministic_per_player_and_isolated(self):
        a1, a2, b = self.board(pid="a"), self.board(pid="a"), self.board(pid="b")
        o1 = [(o.source.id, o.route_m) for o in a1.refresh(self.srcs)]
        o2 = [(o.source.id, o.route_m) for o in a2.refresh(self.srcs)]
        self.assertEqual(o1, o2)
        # o mesmo restaurante serve dois jogadores sem conflito
        oa = a1.make_order(self.food[0], 2000)
        ob = b.make_order(self.food[0], 2000)
        a1.accept(oa.id, 0)
        b.accept(ob.id, 0)
        self.assertNotEqual(oa.id, ob.id)

    def test_difficulty_scales_with_level(self):
        lo, hi = m.difficulty(1), m.difficulty(40)
        self.assertLess(hi.margin, lo.margin)
        self.assertGreater(hi.intensity, lo.intensity)
        self.assertGreater(hi.cooling, lo.cooling)
        self.assertGreater(hi.smooth_min, lo.smooth_min)
        self.assertEqual((lo.base_slots, m.difficulty(10).base_slots, hi.base_slots), (1, 2, 3))

    def test_personal_deadline(self):
        b = self.board()
        o = b.make_order(self.food[0], 2400)
        self.assertAlmostEqual(o.expected_s, 2400 / (8.0 * b.diff.intensity), places=0)
        self.assertAlmostEqual(o.deadline_s, 2400 / (8.0 * b.diff.intensity * (1 - b.diff.margin)), places=0)

    def test_slots_and_same_sport(self):
        b = self.board(level=1)
        o1, o2 = b.make_order(self.food[0], 2000), b.make_order(self.food[1], 2000)
        b.accept(o1.id, 0)
        with self.assertRaises(m.BoardError):
            b.accept(o2.id, 0)
        b2 = self.board(level=12)
        run_src = next(s for s in self.srcs if s.kind is m.Kind.EXPRESS)
        x, y = b2.make_order(self.food[0], 2000), b2.make_order(run_src, 800)
        b2.accept(x.id, 0)
        with self.assertRaises(m.BoardError):
            b2.accept(y.id, 0)

    def test_robustness_adds_slots_and_cargo(self):
        self.assertEqual(self.board(level=1, rob=0.9).slots, 3)
        parcel = next(s for s in self.srcs if s.kind is m.Kind.PARCEL)
        b = self.board(cargo=2.0)
        heavy = b.make_order(parcel, 2000, cargo_kg=5.0)
        with self.assertRaises(m.BoardError):
            b.accept(heavy.id, 0)

    def test_food_cools_and_pause_slows_it(self):
        self.assertAlmostEqual(m.food_temperature(0), m.FOOD_T0)
        self.assertAlmostEqual(m.food_temperature(900), 55.0, places=3)
        self.assertGreater(m.food_temperature(300, paused_s=600), m.food_temperature(900))

    def test_hot_fast_delivery_is_five_stars(self):
        b = self.board()
        o = b.make_order(self.food[0], 2000)
        b.accept(o.id, 0)
        b.pick_up(o.id, 60)
        d = b.deliver(o.id, 60 + o.expected_s)
        self.assertEqual(d.stars, 5)

    def test_late_cold_delivery_is_one_star(self):
        b = self.board(level=30)
        o = b.make_order(self.food[0], 2000)
        b.accept(o.id, 0)
        b.pick_up(o.id, 0)
        self.assertEqual(b.deliver(o.id, o.deadline_s * 1.5 + 3000).stars, 1)

    def test_pause_freezes_deadline(self):
        b = self.board()
        o = b.make_order(self.food[0], 2000)
        b.accept(o.id, 0)
        b.pick_up(o.id, 0)
        b.pause(100)
        b.resume(100 + 3600)
        d = b.deliver(o.id, 3600 + o.expected_s)
        self.assertEqual(d.detail["punctuality"], 1.0)

    def test_rowing_tour_needs_smoothness(self):
        b = self.board(level=20)
        tour = next(s for s in m.sources_for("lisboa", "ribeira") if s.kind is m.Kind.TOUR)
        smooth, rough = b.make_order(tour, 1500, tag="a"), b.make_order(tour, 1500, tag="b")
        for o, sm in ((smooth, 0.95), (rough, 0.4)):
            b.accept(o.id, 0)
            b.pick_up(o.id, 0)
            b.deliver(o.id, o.expected_s, smoothness=sm)
        self.assertEqual(smooth.stars, 5)
        self.assertLessEqual(rough.stars, 2)

    def test_chase_rating(self):
        b = self.board()
        police = next(s for s in self.srcs if s.kind is m.Kind.CHASE)
        o = b.make_order(police, 800)
        b.accept(o.id, 0); b.pick_up(o.id, 0)
        self.assertEqual(b.deliver(o.id, 10, caught=False).stars, 1)

    def test_abandon_penalises_and_frees_slot(self):
        b = self.board()
        o = b.make_order(self.food[0], 2000)
        b.accept(o.id, 0)
        b.pick_up(o.id, 10)
        res = b.abandon(o.id, 200)
        self.assertEqual(res["xp"], 0)
        self.assertGreater(res["reputation_penalty"], 1.0)
        self.assertEqual(b.active(), [])
        with self.assertRaises(m.BoardError):
            b.abandon(o.id, 300)

    def test_stars_mapping(self):
        self.assertEqual([m.stars_from_score(x) for x in (0, 0.3, 0.5, 0.7, 0.9, 1)], [1, 2, 3, 4, 5, 5])

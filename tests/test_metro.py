import math
import random
import struct
import unittest
from pathlib import Path

from ergquest.game.progression import Profile, xp_for_level
from ergquest.shared.movement import Bike, Rower, Runner
from ergquest.world import metro, metrobuild
from ergquest.world.access import Access
from ergquest.world.graph import CityGraph, Edge, Junction, build
from ergquest.world.jobs import cross_bank_allowed, pick_destination
from ergquest.world.navigation import Navigator, fastest_route
from ergquest.world.osm import OsmData, Projection, Way

REAL = Path(__file__).resolve().parents[1] / "data" / "lisboa-metro.json.gz"


def wkb(points):
    """LineString WKB (lon, lat), little-endian."""
    return struct.pack("<BII", 1, 2, len(points)) + b"".join(struct.pack("<dd", lon, lat) for lat, lon in points)


class ZonesTest(unittest.TestCase):
    def test_known_places(self):
        cases = {"n-baixa": (38.711, -9.137), "n-centro": (38.697, -9.206), "n-norte": (38.83, -9.17),
                 "n-este": (38.955, -8.99), "n-oeste": (38.697, -9.42), "s-norte": (38.676, -9.165),
                 "s-sul": (38.524, -8.89), "s-este": (38.705, -8.975), "s-oeste": (38.64, -9.235)}
        for zone, p in cases.items():
            self.assertEqual(metro.zone_of(*p), zone, p)

    def test_unlock_order_and_levels(self):
        self.assertEqual(metro.UNLOCK_ORDER, ["n-baixa", "n-centro", "n-norte", "n-este", "n-oeste",
                                              "s-norte", "s-sul", "s-este", "s-oeste"])
        levels = [z.level for z in metro.ZONES]
        self.assertEqual(levels, sorted(levels))
        self.assertTrue(all(z.bank == "norte" for z in metro.ZONES[:5]))
        self.assertEqual(metro.BRIDGE_LEVEL, metro.ZONE["s-norte"].level)

    def test_bank_override(self):
        self.assertEqual(metro.zone_of(38.95, -8.97, bank="sul"), "s-este")


class AccessTest(unittest.TestCase):
    def test_access_grows_with_level(self):
        a1, a9, a15, a18 = (Access.for_level(n) for n in (1, 9, 15, 18))
        self.assertEqual(a1.zones, {"n-baixa"})
        self.assertEqual(a9.zones, {"n-baixa", "n-centro", "n-norte", "n-este"})
        self.assertFalse(a9.locks)
        self.assertIn("ponte-25-abril", a15.locks)
        self.assertNotIn("travessia-belem", a15.locks)
        self.assertIn("travessia-belem", a18.locks)
        self.assertEqual(a9.next_unlock(), ("Oeste", 12))

    def test_profile_access(self):
        p = Profile("x", 70, xp=xp_for_level(15), robustness=1.0)
        self.assertIn("s-norte", p.access().zones)
        self.assertTrue(cross_bank_allowed(15, "bike"))
        self.assertFalse(cross_bank_allowed(15, "row"))


class OvertureTest(unittest.TestCase):
    def test_connectors_oneway_bridge_and_clipping(self):
        box = (38.0, -9.5, 39.0, -9.0)
        rows = [
            {"subtype": "road", "class": "primary", "names": {"primary": "Estrada A"},
             "geometry": wkb([(38.5, -9.4), (38.5, -9.3), (38.5, -9.2)]),
             "connectors": [{"connector_id": "c1", "at": 0.0}, {"connector_id": "c2", "at": 0.5},
                            {"connector_id": "c3", "at": 1.0}],
             "access_restrictions": [{"access_type": "denied", "when": {"heading": "backward"}}],
             "road_flags": [{"values": ["is_bridge"]}]},
            {"subtype": "road", "class": "secondary", "names": None,
             "geometry": wkb([(38.5, -9.3), (38.9, -9.3), (39.2, -9.3)]),       # sai da caixa a norte
             "connectors": [{"connector_id": "c2", "at": 0.0}, {"connector_id": "c9", "at": 1.0}]},
            {"subtype": "road", "class": "residential", "geometry": wkb([(38.5, -9.4), (38.6, -9.4)]),
             "connectors": []},                                                   # fora da cidade: não entra
            {"subtype": "rail", "class": "standard_gauge", "geometry": wkb([(38.5, -9.4), (38.6, -9.4)])},
        ]
        data, stubs = metrobuild.from_overture(rows, box=box)
        self.assertEqual(len(data.ways), 2)
        a, b = data.ways
        self.assertEqual(a.tags, {"highway": "primary", "name": "Estrada A", "bridge": "yes", "oneway": "yes"})
        self.assertEqual(a.nodes[1], b.nodes[0])                     # interseção partilhada em c2
        self.assertEqual(len(b.nodes), 2)                            # o ponto a 39,2° ficou de fora
        self.assertEqual(stubs, {b.nodes[-1]})                       # ponta cortada na extremidade

    def test_wkb_3d(self):
        raw = struct.pack("<BII", 1, 1002, 2) + struct.pack("<ddd", -9.1, 38.7, 5) + struct.pack("<ddd", -9.2, 38.8, 6)
        self.assertEqual(metrobuild.parse_wkb_linestring(raw), [(-9.1, 38.7), (-9.2, 38.8)])


def flat(lat, lon):
    return 50.0


class StitchAndClimbTest(unittest.TestCase):
    """Três estradas da margem norte que acabam no limite norte; a Serra Grande nasce lá."""

    @classmethod
    def setUpClass(cls):
        d = OsmData()
        nid = iter(range(1, 1000))
        stubs = set()
        for lon in (-9.30, -9.20, -9.10):
            a, b = next(nid), next(nid)
            d.nodes[a] = (38.95, lon)
            d.nodes[b] = (39.069, lon)
            d.ways.append(Way(len(d.ways) + 1, [a, b], {"highway": "primary"}))
            stubs.add(b)
        c1, c2 = next(nid), next(nid)
        d.nodes[c1], d.nodes[c2] = (38.95, -9.30), (38.95, -9.10)
        base = [w.nodes[0] for w in d.ways]
        d.ways.append(Way(99, base, {"highway": "primary"}))
        cls.data, cls.stubs = d, stubs
        cls.climbs = metrobuild.stitch_edges(d, set(stubs))
        cls.g = build(d, flat, center=metro.BAIXA_CENTER)
        cls.report = metrobuild.finish(cls.g, cls.climbs, is_water=lambda lat, lon: False)

    def test_edge_roads_are_joined(self):
        links = [w for w in self.data.ways if w.tags["highway"] == "ligação"]
        self.assertGreaterEqual(len(links), 1)
        deg = {}
        for e in self.g.edges.values():
            if e.mode == "road":
                for j in (e.a, e.b):
                    deg[j] = deg.get(j, 0) + 1
        self.assertFalse([j for j, k in deg.items() if k == 1])     # nenhuma estrada sem saída

    def test_serra_grande(self):
        s = self.report["serras"]["Serra Grande"]
        self.assertEqual((s["subida_km"], s["descida_km"]), (20.0, 20.0))
        self.assertEqual(s["cume_m"], 50 + 2000)
        up = [e for e in self.g.edges.values() if e.name == "Serra Grande" and self.g.junctions[e.b].ele > 2000]
        rise = sum(l * g / 100 for e in up for l, g in e.profile)
        length = sum(e.length for e in up)
        self.assertAlmostEqual(rise / length * 100, 10.0, places=1)
        self.assertEqual(self.g.junctions[up[0].b].zone, "n-norte")

    def test_climb_profile_and_undulation(self):
        prof = metrobuild.climb_profile(4000, 360, seed=1)
        self.assertAlmostEqual(sum(l * g / 100 for l, g in prof), 360, places=6)
        self.assertGreater(max(g for _, g in prof) - min(g for _, g in prof), 2)
        und = metrobuild._undulate([(100.0, 2.0)] * 20)
        self.assertAlmostEqual(sum(l * g for l, g in und), 4000.0, places=6)


def two_banks() -> CityGraph:
    """Norte: A(baixa)–B(centro)–C(oeste); ponte B–S; sul: S(s-norte)–T(s-sul); rio com doca e travessia."""
    g = CityGraph(Projection(*metro.BAIXA_CENTER))
    J = {"A": (0, 0, "n-baixa"), "B": (1000, 0, "n-centro"), "C": (2000, 0, "n-oeste"),
         "S": (1000, -2000, "s-norte"), "T": (1000, -3000, "s-sul"),
         "W1": (0, -500, "n-baixa"), "W2": (0, -1500, "s-norte"), "D2": (0, -1800, "s-norte")}
    ids = {k: i + 1 for i, k in enumerate(J)}
    for k, (x, y, z) in J.items():
        jid = -ids[k] if k.startswith("W") else ids[k]
        g.junctions[jid] = Junction(jid, x, y, 0.0, k in ("A", "D2"), z)
    ids = {k: (-v if k.startswith("W") else v) for k, v in ids.items()}

    def edge(eid, a, b, mode="road", lock="", name=""):
        ja, jb = g.junctions[ids[a]], g.junctions[ids[b]]
        L = math.hypot(jb.x - ja.x, jb.y - ja.y)
        g.edges[eid] = Edge(eid, ids[a], ids[b], name or f"{a}{b}", "primary", [(ja.x, ja.y), (jb.x, jb.y)], L,
                            [(L, 0.0)], True, True, 0, mode, lock)
    edge(1, "A", "B")
    edge(2, "B", "C")
    edge(3, "B", "S", lock="ponte-25-abril", name="Ponte 25 de Abril")
    edge(4, "S", "T")
    edge(5, "A", "W1", "dock")
    edge(6, "W1", "W2", "water", "travessia-belem")
    edge(7, "W2", "D2", "dock")
    edge(8, "D2", "S")
    g.index()
    return g, ids


class LimitsTest(unittest.TestCase):
    def setUp(self):
        self.g, self.ids = two_banks()

    def test_locked_options_show_why(self):
        nav = Navigator(self.g, "bike", self.g.edges[1], True, access=Access.for_level(3))
        opts = {o.name: o.locked for o in nav.options()}
        self.assertEqual(opts["BC"], "Zona Oeste — abre no nível 12")
        self.assertEqual(opts["Ponte 25 de Abril"], "Ponte 25 de Abril — abre no nível 15")

    def test_free_ride_turns_back_at_the_limit(self):
        nav = Navigator(self.g, "bike", self.g.edges[1], True, access=Access.for_level(3))
        nav.advance(1500)                         # chega a B: Oeste e ponte fechadas
        self.assertIn("meia-volta", nav.log)
        self.assertTrue(any(l.startswith("limite: Zona Oeste") for l in nav.log))
        self.assertFalse(nav.forward)             # a voltar para a Baixa pela mesma rua
        self.assertAlmostEqual(nav.offset_m, 500)

    def test_turn_around_and_go_back(self):
        acc = Access.for_level(12)
        nav = Navigator(self.g, "bike", self.g.edges[2], True, offset_m=900, access=acc)
        nav.turn_around()
        self.assertEqual((nav.forward, nav.offset_m), (False, 100))
        nav2 = Navigator(self.g, "bike", self.g.edges[2], True, offset_m=100, access=acc)
        route = nav2.go_back(self.ids["A"], Bike(70, 250))
        self.assertFalse(nav2.forward)            # mais perto de B: meia-volta já
        self.assertEqual([self.g.edges[e].name for e, _ in route], ["AB"])

    def test_bridge_gps_and_jobs_across_banks(self):
        bike = Bike(70, 250)
        a, t = self.ids["A"], self.ids["T"]
        self.assertIsNone(fastest_route(self.g, a, t, bike, access=Access.for_level(12)))
        route = fastest_route(self.g, a, t, bike, access=Access.for_level(18))
        self.assertIn("Ponte 25 de Abril", [self.g.edges[e].name for e, _ in route])
        rng = random.Random(1)
        self.assertIsNone(pick_destination(self.g, a, "bike", Access.for_level(12), rng, 100, 9000, other_bank=True))
        self.assertIn(pick_destination(self.g, a, "bike", Access.for_level(18), rng, 100, 9000, other_bank=True),
                      {self.ids["S"], self.ids["T"], self.ids["D2"]})

    def test_rowing_crossing_needs_experience(self):
        a = self.ids["A"]
        rng = random.Random(2)
        self.assertIsNone(pick_destination(self.g, a, "row", Access.for_level(15), rng, 10, 9000, other_bank=True))
        self.assertEqual(pick_destination(self.g, a, "row", Access.for_level(18), rng, 10, 9000, other_bank=True),
                         self.ids["D2"])
        r = fastest_route(self.g, a, self.ids["D2"], Rower(75, 200), access=Access.for_level(18))
        self.assertEqual([self.g.edges[e].mode for e, _ in r], ["dock", "water", "dock"])


@unittest.skipUnless(REAL.exists(), "sem data/lisboa-metro.json.gz")
class RealMetroTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = CityGraph.load(REAL)

    def test_all_zones_bridges_and_climbs(self):
        zones = {j.zone for j in self.g.junctions.values()}
        self.assertTrue(set(metro.UNLOCK_ORDER) <= zones)
        locks = {e.lock for e in self.g.edges.values() if e.lock}
        self.assertTrue(set(metro.BRIDGES) <= locks and set(metro.ROW_CROSSINGS) <= locks)
        for c in metro.CLIMBS:
            up = sum(e.length for e in self.g.edges.values() if e.name == c.name) / 2
            self.assertAlmostEqual(up / 1000, c.up_km, delta=0.1)

    def test_banks_only_meet_on_bridges(self):
        acc = Access({z.id for z in metro.ZONES}, set())             # tudo aberto menos pontes
        start = self.g.nearest(*self.g.projection.to_xy(*metro.BAIXA_CENTER), sport="bike").id
        seen, stack = {start}, [start]
        while stack:
            for e, f in self.g.outgoing(stack.pop(), "bike", acc):
                k = self.g.end_of(e, f)
                if k not in seen:
                    seen.add(k)
                    stack.append(k)
        self.assertFalse([j for j in seen if self.g.junctions[j].zone.startswith("s-")])

    def test_baixa_to_almada_by_bridge(self):
        P = self.g.projection
        a = self.g.nearest(*P.to_xy(38.7075, -9.1365), sport="bike").id
        b = self.g.nearest(*P.to_xy(38.676, -9.165), sport="bike").id
        self.assertIsNone(fastest_route(self.g, a, b, Bike(70, 250), access=Access.for_level(12)))
        r = fastest_route(self.g, a, b, Bike(70, 250), access=Access.for_level(15))
        self.assertIn("ponte-25-abril", {self.g.edges[e].lock for e, _ in r})

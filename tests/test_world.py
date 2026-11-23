import gzip
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ergquest.shared.movement import PEDICAB, Bike, Runner
from ergquest.world import dem, osm
from ergquest.world.graph import CityGraph, build
from ergquest.world.navigation import Navigator, fastest_route, route_profile, turn_label

PROJ = osm.Projection(38.7100, -9.1400)      # Baixa de Lisboa


def ll(x, y):
    return PROJ.to_latlon(x, y)


def elevation(lat, lon):
    """Sobe 8 % para norte a partir da margem (y = 0)."""
    _, y = PROJ.to_xy(lat, lon)
    return 5.0 + 0.08 * max(y, 0.0)


def bairro() -> dict:
    pts = {1: (0, 0), 2: (200, 0), 3: (400, 0), 4: (0, 200), 5: (200, 200), 6: (400, 200), 7: (0, 100),
           20: (-100, -30), 21: (500, -30), 30: (210, 205), 31: (390, 10)}
    els = []
    for nid, (x, y) in pts.items():
        lat, lon = ll(x, y)
        n = {"type": "node", "id": nid, "lat": lat, "lon": lon}
        if nid == 30:
            n["tags"] = {"amenity": "restaurant", "name": "Real"}
        if nid == 31:
            n["tags"] = {"amenity": "police"}
        els.append(n)
    ways = [
        (100, [1, 2, 3], {"highway": "secondary", "name": "Avenida Ribeirinha"}),
        (101, [4, 5, 6], {"highway": "residential", "name": "Rua de Cima"}),
        (102, [1, 7, 4], {"highway": "residential", "name": "Calçada Íngreme"}),
        (103, [2, 5], {"highway": "steps", "name": "Escadinhas"}),
        (104, [3, 6], {"highway": "residential", "name": "Rua do Sentido Único", "oneway": "yes"}),
        (105, [20, 21], {"natural": "coastline"}),
        (106, [1, 4], {"highway": "motorway", "name": "Via Rápida"}),
    ]
    els += [{"type": "way", "id": i, "nodes": n, "tags": t} for i, n, t in ways]
    return {"elements": els}


class OsmTest(unittest.TestCase):
    def test_projection_round_trip(self):
        lat, lon = PROJ.to_latlon(1234.0, -567.0)
        x, y = PROJ.to_xy(lat, lon)
        self.assertAlmostEqual(x, 1234.0, places=3)
        self.assertAlmostEqual(y, -567.0, places=3)

    def test_parse_and_access(self):
        d = osm.parse(bairro())
        ways = {w.id: w for w in d.ways}
        self.assertFalse(ways[103].bike_ok())
        self.assertTrue(ways[103].foot_ok())
        self.assertEqual(ways[104].oneway_for_bike(), 1)
        self.assertFalse(ways[106].bike_ok() or ways[106].foot_ok())
        self.assertEqual(len(d.water_edges), 1)

    def test_query_mentions_bbox(self):
        q = osm.overpass_query(38.70, -9.15, 38.72, -9.12)
        self.assertIn("38.7,-9.15,38.72,-9.12", q)
        self.assertIn("out body", q)


class DemTest(unittest.TestCase):
    def test_tile_name(self):
        self.assertEqual(dem.tile_name(38.71, -9.14), "N38W010")
        self.assertEqual(dem.tile_name(-0.5, 0.5), "S01E000")

    def test_hgt_bilinear_and_gzip(self):
        n = 11
        grid = np.zeros((n, n), dtype=">i2")
        for r in range(n):
            grid[r, :] = (n - 1 - r) * 10          # sobe para norte: 0 a sul, 100 a norte
        grid[0, 0] = dem.VOID
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "N38W010.hgt.gz"
            p.write_bytes(gzip.compress(grid.tobytes()))
            t = dem.Tile.from_hgt(p)
        self.assertEqual((t.south, t.west), (38, -10))
        self.assertAlmostEqual(t.elevation(38.5, -9.5), 50.0)
        self.assertAlmostEqual(t.elevation(38.05, -9.5), 5.0)
        d = dem.Dem([t])
        with self.assertRaises(ValueError):
            d.elevation(40.0, -9.5)


class GraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = build(osm.parse(bairro()), elevation, center=(PROJ.lat0, PROJ.lon0))

    def edge(self, name):
        return next(e for e in self.g.edges.values() if e.name == name)

    def test_junctions_and_edges(self):
        self.assertEqual(set(self.g.junctions), {1, 2, 3, 4, 5, 6})
        names = sorted(e.name for e in self.g.edges.values())
        self.assertNotIn("Via Rápida", names)
        self.assertEqual(names.count("Avenida Ribeirinha"), 2)          # cortada em B

    def test_real_gradient_and_ascent(self):
        e = self.edge("Calçada Íngreme")
        self.assertAlmostEqual(e.length, 200, delta=1)
        fwd = 1 if self.g.junctions[e.a].y < self.g.junctions[e.b].y else 0
        prof = e.profile_dir(bool(fwd))
        self.assertTrue(all(abs(g - 8.0) < 0.6 for _, g in prof), prof)
        self.assertAlmostEqual(e.ascent(bool(fwd)), 16.0, delta=0.5)
        self.assertAlmostEqual(e.ascent(not fwd), 0.0, delta=0.1)
        self.assertAlmostEqual(self.g.junctions[4].ele - self.g.junctions[1].ele, 16.0, delta=0.1)

    def test_access_by_sport(self):
        steps, ow = self.edge("Escadinhas"), self.edge("Rua do Sentido Único")
        self.assertFalse(steps.allows("bike", True))
        self.assertTrue(steps.allows("run", False))
        self.assertTrue(ow.allows("bike", True))
        self.assertFalse(ow.allows("bike", False))
        self.assertTrue(ow.allows("run", False))

    def test_docks_and_anchors(self):
        self.assertEqual({j.id for j in self.g.docks()}, {1, 2, 3})
        kinds = {a.kind: a.junction for a in self.g.anchors}
        self.assertEqual(kinds["restaurant"], 5)
        self.assertEqual(kinds["police"], 3)

    def test_save_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bairro.json"
            self.g.save(p)
            g2 = CityGraph.load(p)
        self.assertEqual(g2.stats(), self.g.stats())
        self.assertIn("OpenStreetMap", p.name + g2.to_json()["attribution"])


class NavigationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = build(osm.parse(bairro()), elevation, center=(PROJ.lat0, PROJ.lon0))

    def names(self, route):
        return [self.g.edges[e].name for e, _ in route]

    def test_bike_respects_oneway_and_steps(self):
        r = fastest_route(self.g, 4, 3, Bike(70, 250))
        self.assertEqual(self.names(r), ["Calçada Íngreme", "Avenida Ribeirinha", "Avenida Ribeirinha"])

    def test_runner_takes_the_steps(self):
        r = fastest_route(self.g, 5, 2, Runner(65, 3.5))
        self.assertEqual(self.names(r), ["Escadinhas"])

    def test_route_profile_climbs(self):
        r = fastest_route(self.g, 1, 4, Bike(70, 250))
        prof = route_profile(self.g, r)
        self.assertAlmostEqual(sum(l * g / 100 for l, g in prof if g > 0), 16.0, delta=1.0)

    def test_oneway_forces_bike_around(self):
        bike = self.names(fastest_route(self.g, 6, 3, Bike(70, 250)))
        self.assertNotIn("Rua do Sentido Único", bike)                    # de bicicleta dá a volta
        self.assertEqual(self.names(fastest_route(self.g, 6, 3, Runner(65, 3.5))), ["Rua do Sentido Único"])

    def test_turn_labels(self):
        self.assertEqual(turn_label(0), "em frente")
        self.assertEqual(turn_label(90), "esquerda")
        self.assertEqual(turn_label(-90), "direita")
        self.assertEqual(turn_label(-40), "ligeiro à direita")
        self.assertEqual(turn_label(180), "inversão")

    def test_navigator_follows_gps_then_arrows(self):
        route = fastest_route(self.g, 1, 3, Bike(70, 250))
        nav = Navigator.at(self.g, 1, "bike", route)
        opts = nav.options()                                    # em B, de bicicleta
        self.assertEqual([o.label for o in opts], ["em frente"])  # as escadinhas não aparecem
        self.assertTrue(opts[0].suggested)
        entered = nav.advance(250)
        self.assertEqual(entered, ["Avenida Ribeirinha"])
        self.assertAlmostEqual(nav.travelled_m, 250, delta=0.01)

        run = Navigator.at(self.g, 1, "run", fastest_route(self.g, 1, 3, Runner(65, 3.5)))
        labels = {o.label: o.name for o in run.options()}
        self.assertEqual(labels.get("esquerda"), "Escadinhas")
        run.press("esquerda")
        self.assertEqual(run.advance(210), ["Escadinhas"])
        self.assertTrue(run.off_route())
        self.assertGreater(run.grade(), 5.0)                    # a subir as escadinhas

    def test_pedicab_route_time_grows_with_passengers(self):
        from ergquest.world.navigation import edge_time
        cab = Bike(70, 250, PEDICAB)
        e = next(e for e in self.g.edges.values() if e.name == "Calçada Íngreme")
        up = self.g.junctions[e.a].y < self.g.junctions[e.b].y
        self.assertGreater(edge_time(cab, e, up, 0.75, 150), 2 * edge_time(cab, e, up, 0.75))


class PlacesAndMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = build(osm.parse(bairro()), elevation, center=(PROJ.lat0, PROJ.lon0))

    def test_sources_on_real_anchors(self):
        from ergquest.game.missions import Kind, sources_for
        from ergquest.world.places import place
        srcs = sources_for("lisboa", "centro")
        spots = place(self.g, srcs)
        by_kind = {s.kind: spots[s.id] for s in srcs}
        self.assertEqual(by_kind[Kind.CHASE], 3)                    # a esquadra real
        self.assertIn(by_kind[Kind.TOUR], {1, 2, 3})                # numa doca
        self.assertEqual(spots, place(self.g, srcs))                # determinístico
        food = [spots[s.id] for s in srcs if s.kind is Kind.FOOD]
        self.assertIn(5, food)                                       # o restaurante real

    def test_map_page(self):
        from ergquest.world import mapview
        route = fastest_route(self.g, 4, 3, Bike(70, 250))
        page = mapview.render(self.g, "Bairro de teste", route)
        self.assertIn("<svg", page)
        self.assertIn("Calçada Íngreme", page)
        self.assertIn('class="route"', page)
        self.assertIn("OpenStreetMap", page)
        self.assertIn("prefers-color-scheme:dark", page)


class TrainerGradeTest(unittest.TestCase):
    def test_grade_window_dilutes_spikes(self):
        from ergquest.world.graph import Edge
        e = Edge(1, 1, 2, "Rua", "residential", [(0, 0), (100, 0)], 100.0,
                 [(10.0, 2.0)] * 4 + [(10.0, 22.0)] + [(10.0, 2.0)] * 5, True, True)
        g = CityGraph(PROJ)
        nav = Navigator(g, "bike", e, True, offset_m=45.0)
        self.assertAlmostEqual(nav.grade(window_m=1.0), 22.0)
        self.assertAlmostEqual(nav.grade(), 7.0)                 # 10 m a 22 % em 40 m a 2 %
        self.assertAlmostEqual(Navigator(g, "bike", e, False, offset_m=5.0).grade(), -2.0)

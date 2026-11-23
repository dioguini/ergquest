"""O grafo jogável de uma zona: interseções e ruas com perfil de altimetria.

* **Interseções** — nós OSM partilhados por duas ou mais ruas, e pontas de rua.
  São os sítios onde o atleta escolhe o caminho.
* **Ruas** (arestas) — cada rua OSM é cortada nas interseções. Cada troço tem
  o traçado em metros, o comprimento, o perfil de altimetria (reamostrado a
  passo fixo e suavizado, porque o DEM tem ruído de ~30 m) e o acesso por
  desporto (escadinhas só a pé; sentidos únicos para a bicicleta).
* **Docas** — interseções junto à margem: é aí que se começa a remar.
* **Âncoras** — sítios reais (restaurantes, esquadras, terminais) onde se põem
  os estabelecimentos fictícios do jogo.
"""
from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .osm import OsmData, Projection

STEP_M = 10.0            # passo de reamostragem da altimetria
SMOOTH_M = 50.0          # janela da média móvel (o DEM de 30 m é ruidoso)
MAX_GRADE = 25.0         # Lisboa tem rampas a 20 %+; acima disto é ruído
DOCK_M = 40.0            # interseção a menos disto da margem = doca
SHORT_EDGE_M = 120.0     # troços mais curtos: rampa uniforme entre as interseções
SPIKE_GRADE = 15.0       # declive para todos os lados que denuncia um pico
SPIKE_ITERS = 3
ATTRIBUTION = "© contribuidores do OpenStreetMap (ODbL)"
COPERNICUS = ("altimetria: Copernicus GLO-30 — © DLR e.V. 2010–2014 e © Airbus Defence and Space GmbH "
              "2014–2018, fornecido pelo programa Copernicus da União Europeia e da ESA")
SRTM = "altimetria: NASA SRTM (domínio público)"


@dataclass
class Junction:
    id: int
    x: float
    y: float
    ele: float
    dock: bool = False
    zone: str = ""


@dataclass
class Edge:
    id: int
    a: int
    b: int
    name: str
    highway: str
    points: list[tuple[float, float]]
    length: float
    profile: list[tuple[float, float]]        # [(comprimento_m, declive_%)] no sentido a → b
    bike: bool
    foot: bool
    oneway: int = 0                           # bicicleta: 1 só a→b, -1 só b→a
    mode: str = "road"                        # road | water | dock (cais entre a terra e a água)
    lock: str = ""                            # ponte ou travessia que tem de estar desbloqueada

    def allows(self, sport: str, forward: bool) -> bool:
        if sport == "row":
            return self.mode in ("water", "dock")
        if self.mode != "road":
            return False
        if sport == "run":
            return self.foot
        if sport == "bike":
            if not self.bike:
                return False
            return self.oneway == 0 or (self.oneway == 1) == forward
        return False

    def profile_dir(self, forward: bool) -> list[tuple[float, float]]:
        return self.profile if forward else [(l, -g) for l, g in reversed(self.profile)]

    def ascent(self, forward: bool = True) -> float:
        return sum(l * g / 100 for l, g in self.profile_dir(forward) if g > 0)


@dataclass
class Anchor:
    kind: str            # restaurant | cafe | fast_food | police | ferry_terminal
    junction: int
    x: float
    y: float


@dataclass
class CityGraph:
    projection: Projection
    junctions: dict[int, Junction] = field(default_factory=dict)
    edges: dict[int, Edge] = field(default_factory=dict)
    anchors: list[Anchor] = field(default_factory=list)
    water: list[list[tuple[float, float]]] = field(default_factory=list)
    attribution: str = ATTRIBUTION
    _adj: dict[int, list[tuple[int, bool]]] = field(default_factory=dict, repr=False)

    def index(self) -> None:
        self.__dict__.pop("_networks", None)
        self.__dict__.pop("_grid_cache", None)
        self._adj = {j: [] for j in self.junctions}
        for e in self.edges.values():
            self._adj[e.a].append((e.id, True))
            self._adj[e.b].append((e.id, False))

    def outgoing(self, junction: int, sport: str, access=None) -> list[tuple[Edge, bool]]:
        """Ruas que se podem tomar a partir de uma interseção, neste desporto.

        Com `access` (ver `world.access`), só as que levam a zonas abertas e
        não passam por pontes ou travessias ainda bloqueadas.
        """
        out = []
        for eid, fwd in self._adj.get(junction, []):
            e = self.edges[eid]
            if e.allows(sport, fwd) and (access is None or access.can_use(self, e, fwd)):
                out.append((e, fwd))
        return out

    def end_of(self, edge: Edge, forward: bool) -> int:
        return edge.b if forward else edge.a

    def docks(self) -> list[Junction]:
        return [j for j in self.junctions.values() if j.dock]

    def _reach(self, start: int, sport: str, reverse: bool) -> set[int]:
        seen, stack = {start}, [start]
        while stack:
            j = stack.pop()
            for eid, fwd in self._adj.get(j, []):
                e = self.edges[eid]
                # ao contrário: chega-se a j por esta rua se ela permite o sentido oposto
                if e.allows(sport, (not fwd) if reverse else fwd):
                    k = self.end_of(e, fwd)
                    if k not in seen:
                        seen.add(k)
                        stack.append(k)
        return seen

    def main_network(self, sport: str) -> set[int]:
        """A maior rede onde, neste desporto, se vai de qualquer ponto a qualquer ponto.

        Ruas pedonais, becos e sentidos únicos criam ilhas: um restaurante ou
        um destino de táxi tem de ficar na rede principal.
        """
        cache = self.__dict__.setdefault("_networks", {})
        if sport not in cache:
            best: set[int] = set()
            remaining = {j for j in self.junctions if self.outgoing(j, sport)}
            while remaining and len(remaining) > len(best):
                j = next(iter(remaining))
                scc = self._reach(j, sport, False) & self._reach(j, sport, True)
                if len(scc) > len(best):
                    best = scc
                remaining -= scc | {j}
            cache[sport] = best
        return cache[sport]

    GRID_M = 250.0

    def _grid(self) -> dict[tuple[int, int], list[int]]:
        grid = self.__dict__.get("_grid_cache")
        if grid is None:
            grid = {}
            for j in self.junctions.values():
                grid.setdefault((int(j.x // self.GRID_M), int(j.y // self.GRID_M)), []).append(j.id)
            self.__dict__["_grid_cache"] = grid
            xs = [i for i, _ in grid] or [0]
            ys = [k for _, k in grid] or [0]
            self.__dict__["_grid_bounds"] = (min(xs), max(xs), min(ys), max(ys))
        return grid

    def nearest(self, x: float, y: float, sport: str | None = None, within: float | None = None,
                where=None) -> Junction | None:
        """Interseção mais próxima (índice em grelha); com `sport`, só na rede
        principal desse desporto; `where(j)` filtra; `within` limita a distância."""
        allowed = self.main_network(sport) if sport else None
        grid, g = self._grid(), self.GRID_M
        cx, cy = int(x // g), int(y // g)
        best, best_d = None, math.inf
        max_r = int((within or 1e9) // g) + 1
        x0, x1, y0, y1 = self.__dict__["_grid_bounds"]
        span = max(abs(cx - x0), abs(cx - x1)) + max(abs(cy - y0), abs(cy - y1))
        for r in range(0, min(max_r, span + 1) + 1):
            if best is not None and (r - 1) * g > math.sqrt(best_d):
                break
            for i in range(cx - r, cx + r + 1):
                for k in (range(cy - r, cy + r + 1) if i in (cx - r, cx + r) else (cy - r, cy + r)):
                    for jid in grid.get((i, k), ()):
                        if allowed is not None and jid not in allowed:
                            continue
                        j = self.junctions[jid]
                        if where is not None and not where(j):
                            continue
                        d = (j.x - x) ** 2 + (j.y - y) ** 2
                        if d < best_d:
                            best, best_d = j, d
        if best is None or (within is not None and best_d > within * within):
            return None
        return best

    def stats(self) -> dict:
        bike = sum(e.length for e in self.edges.values() if e.bike)
        foot = sum(e.length for e in self.edges.values() if e.foot)
        eles = [j.ele for j in self.junctions.values()]
        steep = max((abs(g) for e in self.edges.values() for _, g in e.profile), default=0.0)
        return {"junctions": len(self.junctions), "edges": len(self.edges),
                "bike_km": round(bike / 1000, 2), "foot_km": round(foot / 1000, 2),
                "ele_min": round(min(eles), 1) if eles else None, "ele_max": round(max(eles), 1) if eles else None,
                "steepest_pct": round(steep, 1), "docks": len(self.docks()), "anchors": len(self.anchors),
                "water_km": round(sum(e.length for e in self.edges.values() if e.mode == "water") / 1000, 1)}

    # ------------------------------------------------------------ ficheiro
    def to_json(self) -> dict:
        return {
            "attribution": self.attribution,
            "projection": [self.projection.lat0, self.projection.lon0],
            "junctions": [[j.id, round(j.x, 1), round(j.y, 1), round(j.ele, 1), int(j.dock), j.zone]
                          for j in self.junctions.values()],
            "edges": [{"id": e.id, "a": e.a, "b": e.b, "name": e.name, "hw": e.highway,
                       "pts": [[round(x, 1), round(y, 1)] for x, y in e.points],
                       "len": round(e.length, 1), "prof": [[round(l, 1), round(g, 2)] for l, g in e.profile],
                       "bike": int(e.bike), "foot": int(e.foot), "ow": e.oneway, "mode": e.mode, "lock": e.lock}
                      for e in self.edges.values()],
            "anchors": [[a.kind, a.junction, round(a.x, 1), round(a.y, 1)] for a in self.anchors],
            "water": [[[round(x, 1), round(y, 1)] for x, y in line] for line in self.water],
        }

    @classmethod
    def from_json(cls, d: dict) -> "CityGraph":
        g = cls(Projection(*d["projection"]))
        for jid, x, y, ele, dock, *rest in d["junctions"]:
            g.junctions[jid] = Junction(jid, x, y, ele, bool(dock), rest[0] if rest else "")
        for e in d["edges"]:
            g.edges[e["id"]] = Edge(e["id"], e["a"], e["b"], e["name"], e["hw"], [tuple(p) for p in e["pts"]],
                                    e["len"], [tuple(p) for p in e["prof"]], bool(e["bike"]), bool(e["foot"]), e["ow"],
                                    e.get("mode", "road"), e.get("lock", ""))
        g.anchors = [Anchor(k, j, x, y) for k, j, x, y in d.get("anchors", [])]
        g.water = [[tuple(p) for p in line] for line in d.get("water", [])]
        g.attribution = d.get("attribution", ATTRIBUTION)
        g.index()
        return g

    def save(self, path: str | Path) -> None:
        """Grava em JSON (comprimido se o nome acabar em .gz)."""
        raw = json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        p = Path(path)
        p.write_bytes(gzip.compress(raw, 9) if p.suffix == ".gz" else raw)

    @classmethod
    def load(cls, path: str | Path) -> "CityGraph":
        p = Path(path)
        raw = p.read_bytes()
        return cls.from_json(json.loads(gzip.decompress(raw) if p.suffix == ".gz" else raw))


# ---------------------------------------------------------------- construção
def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _resample(points: list[tuple[float, float]], step: float) -> list[tuple[float, float, float]]:
    """Pontos (x, y, distância acumulada) a passo fixo ao longo do traçado."""
    out = [(points[0][0], points[0][1], 0.0)]
    acc, nxt = 0.0, step
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        while seg > 0 and nxt <= acc + seg:
            t = (nxt - acc) / seg
            out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1), nxt))
            nxt += step
        acc += seg
    if acc - out[-1][2] > 0.5:
        out.append((points[-1][0], points[-1][1], acc))
    return out


def compress_profile(prof: list[tuple[float, float]], tol: float = 0.4) -> list[tuple[float, float]]:
    """Junta passos seguidos com declive quase igual (mantém a subida total)."""
    out: list[list[float]] = []
    for length, g in prof:
        if out and abs(out[-1][1] - g) <= tol:
            l0, g0 = out[-1]
            out[-1] = [l0 + length, (g0 * l0 + g * length) / (l0 + length)]
        else:
            out.append([length, g])
    return [(l, g) for l, g in out]


def simplify(points: list[tuple[float, float]], tol: float = 2.0) -> list[tuple[float, float]]:
    """Douglas–Peucker: tira vértices que não mudam o traçado mais de `tol` metros."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, k = stack.pop()
        best, idx = 0.0, None
        for m in range(i + 1, k):
            d = _seg_dist(*points[m], *points[i], *points[k])
            if d > best:
                best, idx = d, m
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, k)]
    return [p for p, kp in zip(points, keep) if kp]


def _smooth(values: list[float], window: int) -> list[float]:
    """Média móvel com janela simétrica que encolhe junto às pontas (não enviesa as rampas)."""
    if window <= 1 or len(values) < 3:
        return values[:]
    n, h = len(values), window // 2
    out = []
    for i in range(n):
        k = min(h, i, n - 1 - i)
        out.append(sum(values[i - k:i + k + 1]) / (2 * k + 1))
    return out


def build(osm: OsmData, elevation, center: tuple[float, float] | None = None) -> CityGraph:
    """Constrói o grafo. `elevation(lat, lon) -> metros` (um `Dem` ou um falso nos testes)."""
    proj = Projection(*(center or osm.center()))
    xy = {nid: proj.to_xy(*ll) for nid, ll in osm.nodes.items()}
    streets = [w for w in osm.streets if w.bike_ok() or w.foot_ok()]

    use: dict[int, int] = {}
    for w in streets:
        for n in w.nodes:
            use[n] = use.get(n, 0) + 1
    junction_ids = {n for n, c in use.items() if c >= 2} | {w.nodes[0] for w in streets} | {w.nodes[-1] for w in streets}

    g = CityGraph(proj)
    ele_cache: dict[int, float] = {}

    def node_ele(n: int) -> float:
        if n not in ele_cache:
            ele_cache[n] = float(elevation(*osm.nodes[n]))
        return ele_cache[n]

    for n in junction_ids:
        x, y = xy[n]
        g.junctions[n] = Junction(n, x, y, node_ele(n))

    # 1) troços com a altimetria bruta ao longo do traçado
    raw_edges = []
    for w in streets:
        start = 0
        for i in range(1, len(w.nodes)):
            if w.nodes[i] not in junction_ids:
                continue
            ids = w.nodes[start:i + 1]
            start = i
            if ids[0] == ids[-1] and len(ids) <= 2:
                continue
            pts = [xy[n] for n in ids]
            samples = _resample(pts, STEP_M)
            if samples[-1][2] < 1.0:
                continue
            raw = [float(elevation(*proj.to_latlon(x, y))) for x, y, _ in samples]
            raw_edges.append((w, ids, pts, samples, raw))

    # 2) picos isolados nas interseções: o DEM é um modelo de superfície e,
    #    numa rua estreita, a célula pode ser um telhado. Uma interseção acima
    #    (ou abaixo) de TODAS as vizinhas, com declives implausíveis para todos
    #    os lados, passa para a mediana das vizinhas. Colinas reais ficam.
    nbrs: dict[int, list[tuple[int, float]]] = {}
    for _, ids, _, samples, _ in raw_edges:
        a, b, length = ids[0], ids[-1], samples[-1][2]
        if a != b:
            nbrs.setdefault(a, []).append((b, length))
            nbrs.setdefault(b, []).append((a, length))
    ele = {n: j.ele for n, j in g.junctions.items()}
    for _ in range(SPIKE_ITERS):
        fixed = {}
        for n, e0 in ele.items():
            ns = nbrs.get(n, [])
            if len(ns) < 2:
                continue
            grades = [(e0 - ele[m]) / max(length, 5.0) * 100 for m, length in ns]
            if all(gr > SPIKE_GRADE for gr in grades) or all(gr < -SPIKE_GRADE for gr in grades):
                vals = sorted(ele[m] for m, _ in ns)
                fixed[n] = vals[len(vals) // 2]
        if not fixed:
            break
        ele.update(fixed)
    for n, v in ele.items():
        g.junctions[n].ele = v

    # 3) perfil de cada troço: rampa entre as interseções suavizadas; nos
    #    troços longos junta-se a forma interior (lomba, vale), suavizada.
    eid = 0
    window = max(1, int(SMOOTH_M / STEP_M))
    for w, ids, pts, samples, raw in raw_edges:
        length = samples[-1][2]
        ea, eb = ele[ids[0]], ele[ids[-1]]
        line = [ea + (eb - ea) * d / length for _, _, d in samples]
        if length >= SHORT_EDGE_M:
            trend = [raw[0] + (raw[-1] - raw[0]) * d / length for _, _, d in samples]
            shape = _smooth([r - t for r, t in zip(raw, trend)], window)
            shape[0] = shape[-1] = 0.0
            prof_ele = [l + sh for l, sh in zip(line, shape)]
        else:
            prof_ele = line
        prof = []
        for (_, _, d1), (_, _, d2), e1, e2 in zip(samples, samples[1:], prof_ele, prof_ele[1:]):
            seg = d2 - d1
            if seg > 0:
                prof.append((seg, max(-MAX_GRADE, min(MAX_GRADE, (e2 - e1) / seg * 100))))
        eid += 1
        g.edges[eid] = Edge(eid, ids[0], ids[-1], w.name, w.highway or "", simplify(pts), length,
                            compress_profile(prof), w.bike_ok(), w.foot_ok(), w.oneway_for_bike())

    # margens e docas
    g.water = [[xy[n] for n in w.nodes] for w in osm.water_edges]
    if g.water:
        cell = 200.0
        segs: dict[tuple[int, int], list] = {}
        for line in g.water:
            for a, b in zip(line, line[1:]):
                for cx in range(int(min(a[0], b[0]) // cell) - 1, int(max(a[0], b[0]) // cell) + 2):
                    for cy in range(int(min(a[1], b[1]) // cell) - 1, int(max(a[1], b[1]) // cell) + 2):
                        segs.setdefault((cx, cy), []).append((a, b))
        for j in g.junctions.values():
            near = segs.get((int(j.x // cell), int(j.y // cell)), ())
            j.dock = any(_seg_dist(j.x, j.y, *a, *b) < DOCK_M for a, b in near)

    g.index()
    # junções sem nenhuma rua (pontas de vias excluídas) saem
    for jid in [j for j, adj in g._adj.items() if not adj]:
        del g.junctions[jid]
    g.index()

    # âncoras para estabelecimentos fictícios
    for nid, tags in osm.node_tags.items():
        kind = tags.get("amenity")
        if kind in ("restaurant", "cafe", "fast_food", "police", "ferry_terminal") and g.junctions:
            x, y = xy[nid]
            j = g.nearest(x, y)
            g.anchors.append(Anchor(kind, j.id, x, y))
    return g

"""Construção do grafo da Área Metropolitana de Lisboa.

Passos (todos determinísticos):

1. `from_overture` — segmentos do Overture (rede viária do OpenStreetMap) →
   `OsmData`: interseções partilhadas (`connectors`), sentidos únicos, pontes;
   na cidade de Lisboa entra toda a malha, fora dela a rede principal
   (autoestradas incluídas). Corta tudo à caixa do mapa e regista as pontas
   cortadas ("pontas soltas").
2. `stitch_edges` — une as pontas soltas de cada margem com estradas de
   ligação ao longo da extremidade do mapa: não há estradas sem saída nas
   pontas do mundo. Em dois desses troços nascem as serras fictícias
   (`metro.CLIMBS`), com traçado em ziguezague para fora do mapa.
3. `graph.build` — altimetria do DEM em todos os troços (as ligações ficam
   com a altimetria real do terreno que atravessam).
4. `finish` — zonas, pontes bloqueadas, perfil das serras, ondulação das
   ligações, rede fluvial com docas e travessias, estabelecimentos reais.
"""
from __future__ import annotations

import math
import struct
from collections import defaultdict

from . import metro
from .graph import CityGraph, Edge, Junction, compress_profile
from .osm import OsmData, Projection, Way

PROJ = Projection(*metro.BAIXA_CENTER)
WATER_ID0 = -1_000_000


# ---------------------------------------------------------------- 1. Overture
def parse_wkb_linestring(b: bytes) -> list[tuple[float, float]]:
    """(lon, lat) de um LineString WKB (2D, ou 3D/M, que se ignoram)."""
    end = "<" if b[0] == 1 else ">"
    gtype = struct.unpack(end + "I", b[1:5])[0]
    dims = 3 if (gtype & 0xFFFF) in (1002, 2002) or gtype & 0x80000000 or gtype & 0x40000000 else 2
    if (gtype & 0xFFFF) == 3002:
        dims = 4
    n = struct.unpack(end + "I", b[5:9])[0]
    vals = struct.unpack(end + "d" * (n * dims), b[9:9 + 8 * n * dims])
    return [(vals[i * dims], vals[i * dims + 1]) for i in range(n)]


def _inside(lat: float, lon: float, box) -> bool:
    s, w, n, e = box
    return s <= lat <= n and w <= lon <= e


def _oneway(restrictions) -> str | None:
    for r in restrictions or []:
        if r.get("access_type") != "denied" or r.get("between"):
            continue
        when = r.get("when") or {}
        modes = set(when.get("mode") or [])
        if modes and not modes & {"vehicle", "bicycle"}:
            continue
        if when.get("using") or when.get("recognized") or when.get("during"):
            continue
        if when.get("heading") == "backward":
            return "yes"
        if when.get("heading") == "forward":
            return "-1"
    return None


def keep_class(cls: str | None, lat: float, lon: float) -> bool:
    if not cls:
        return False
    city = metro.zone_of(lat, lon) in ("n-baixa", "n-centro")
    return cls in (metro.CITY_CLASSES if city else metro.MAIN_CLASSES)


def from_overture(rows: list[dict], box=metro.BOX, keep=keep_class) -> tuple[OsmData, set[int]]:
    """Segmentos (dicts com id, names, subtype, class, connectors, road_flags,
    access_restrictions, geometry) → (OsmData, ids das pontas soltas)."""
    data = OsmData()
    conn_ids: dict[str, int] = {}
    nxt = [1]

    def new_id() -> int:
        nxt[0] += 1
        return nxt[0]

    stubs: set[int] = set()
    for wid, r in enumerate(rows):
        if r.get("subtype") != "road" or not r.get("geometry"):
            continue
        pts = parse_wkb_linestring(r["geometry"])
        if len(pts) < 2:
            continue
        mid_lon, mid_lat = pts[len(pts) // 2]
        if not keep(r.get("class"), mid_lat, mid_lon):
            continue
        # distância acumulada (m) para colocar as interseções pela fração "at"
        cum = [0.0]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx = (x2 - x1) * 111_320 * math.cos(math.radians(y1))
            cum.append(cum[-1] + math.hypot(dx, (y2 - y1) * 111_320))
        total = cum[-1] or 1.0
        seq = [[d, None, lat, lon] for d, (lon, lat) in zip(cum, pts)]
        for c in r.get("connectors") or []:
            cid = conn_ids.setdefault(c["connector_id"], new_id())
            d = (c.get("at") or 0.0) * total
            k = min(range(len(cum)), key=lambda i: abs(cum[i] - d))
            if abs(cum[k] - d) < 0.5:
                seq[k][1] = cid
            else:
                i = max(0, min(len(cum) - 2, next((i for i in range(len(cum) - 1) if cum[i + 1] >= d), len(cum) - 2)))
                t = (d - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
                (lo1, la1), (lo2, la2) = pts[i], pts[i + 1]
                seq.append([d, cid, la1 + t * (la2 - la1), lo1 + t * (lo2 - lo1)])
        seq.sort(key=lambda s: s[0])
        for s in seq:
            if s[1] is None:
                s[1] = new_id()
        flags = {v for f in (r.get("road_flags") or []) for v in (f.get("values") or [])}
        tags = {"highway": r["class"]}
        name = (r.get("names") or {}).get("primary")
        if name:
            tags["name"] = name
        if "is_bridge" in flags:
            tags["bridge"] = "yes"
        ow = _oneway(r.get("access_restrictions"))
        if ow:
            tags["oneway"] = ow
        # cortar à caixa: cada sequência contínua de pontos dentro é uma via
        run: list = []
        cut_before = False
        for i, s in enumerate(seq + [None]):
            if s is not None and _inside(s[2], s[3], box):
                if not run:
                    cut_before = i > 0
                run.append(s)
                continue
            if len(run) >= 2:
                for p in run:
                    data.nodes[p[1]] = (p[2], p[3])
                ids = [p[1] for p in run]
                if cut_before:
                    stubs.add(ids[0])
                if s is not None:
                    stubs.add(ids[-1])
                data.ways.append(Way(wid * 10 + len(data.ways) % 10, ids, dict(tags)))
            run = []
    data.ways = [w for w in data.ways if len(w.nodes) >= 2]
    return data, stubs


# ---------------------------------------------------------------- 2. pontas
def _perimeter(lat: float, lon: float, box) -> float:
    """Posição ao longo do contorno da caixa, no sentido dos ponteiros do relógio a partir de NO."""
    s, w, n, e = box
    d = [abs(lat - n), abs(lon - e), abs(lat - s), abs(lon - w)]
    side = d.index(min(d))
    W, H = e - w, n - s
    return [lon - w, W + (n - lat), W + H + (e - lon), 2 * W + H + (lat - s)][side]


def _zigzag(a: tuple[float, float], b: tuple[float, float], length: float, legs: int,
            outward: tuple[float, float]) -> list[tuple[float, float]]:
    """Traçado em ziguezague (ganchos) de comprimento ~`length` entre a e b (metros).

    Se a e b estão próximos, o traçado afasta-se primeiro na direção `outward`.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    dist = math.hypot(dx, dy)
    if dist < 1:
        ux, uy = outward
        dist = 1.0
    else:
        ux, uy = dx / dist, dy / dist
    vx, vy = -uy, ux
    step = dist / legs

    def path(w: float) -> list[tuple[float, float]]:
        pts = [a]
        for i in range(1, legs):
            side = w if i % 2 else -w
            pts.append((ax + ux * step * i + vx * side, ay + uy * step * i + vy * side))
        pts.append(b)
        return pts

    def size(pts) -> float:
        return sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))

    lo, hi = 0.0, length            # largura dos ganchos que dá o comprimento pedido
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if size(path(mid)) < length else (lo, mid)
    pts = path((lo + hi) / 2)
    return pts


def is_bridge_way(data: OsmData, w: Way) -> bool:
    """Via de ponte sobre o Tejo: tem nome de uma das pontes, ou é ponte perto de uma."""
    name = (w.tags.get("name") or "").lower()
    if any(n.lower() in name for n, _ in metro.BRIDGES.values()):
        return True
    if w.tags.get("bridge") == "yes":
        lat, lon = data.nodes[w.nodes[len(w.nodes) // 2]]
        return metro.bridge_distance_km(lat, lon) < metro.BRIDGE_REACH_KM
    return False


def north_nodes(data: OsmData) -> set[int]:
    """Nós alcançáveis a partir da Baixa sem atravessar pontes: a margem norte."""
    adj: dict[int, list[int]] = defaultdict(list)
    for w in data.ways:
        if is_bridge_way(data, w):
            continue
        for a, b in zip(w.nodes, w.nodes[1:]):
            adj[a].append(b)
            adj[b].append(a)
    lat0, lon0 = metro.BAIXA_CENTER
    start = min(adj, key=lambda n: (data.nodes[n][0] - lat0) ** 2 + (data.nodes[n][1] - lon0) ** 2)
    seen, stack = {start}, [start]
    while stack:
        for k in adj[stack.pop()]:
            if k not in seen:
                seen.add(k)
                stack.append(k)
    return seen


def stitch_edges(data: OsmData, stubs: set[int], box=metro.BOX, climbs=metro.CLIMBS) -> dict[str, tuple]:
    """Une as pontas soltas de cada margem e cria as serras. Devolve {serra: (a, cume, b)}."""
    # becos a menos de LAND_EDGE_KM do limite terrestre também se ligam
    use: dict[int, int] = defaultdict(int)
    for w in data.ways:
        for n in w.nodes:
            use[n] += 1
    for w in data.ways:
        for n in (w.nodes[0], w.nodes[-1]):
            if use[n] == 1 and n not in stubs:
                d = metro.land_edge_km(*data.nodes[n])
                if d is not None and d < metro.LAND_EDGE_KM:
                    stubs.add(n)
    # a margem de cada ponta vem da ligação das estradas (sem pontes), não da geometria:
    # na lezíria o rio e a terra estão ao mesmo nível e a linha do meio é aproximada
    north = north_nodes(data)
    big_south = _south_component(data, north)
    by_bank: dict[str, list[int]] = defaultdict(list)
    for n in stubs:
        if n in north:
            by_bank["norte"].append(n)
        elif n in big_south:
            by_bank["sul"].append(n)
    ids = [max(data.nodes) + 1]

    def nid() -> int:
        ids[0] += 1
        return ids[0]

    out: dict[str, tuple] = {}
    for bank, nodes in by_bank.items():
        nodes.sort(key=lambda n: _perimeter(*data.nodes[n], box))
        pairs = list(zip(nodes, nodes[1:]))
        climb_at: dict[int, metro.Climb] = {}
        for c in climbs:
            if c.bank != bank or not pairs:
                continue
            def mid_d(p):
                (la1, lo1), (la2, lo2) = data.nodes[p[0]], data.nodes[p[1]]
                return ((la1 + la2) / 2 - c.anchor[0]) ** 2 + ((lo1 + lo2) / 2 - c.anchor[1]) ** 2
            k = min(range(len(pairs)), key=lambda i: mid_d(pairs[i]))
            climb_at[k] = c
        for k, (a, b) in enumerate(pairs):
            if k in climb_at:
                # a serra nasce em A e volta à ligação em C (300 m adiante): é um colo,
                # passa-se nos dois sentidos, com o comprimento exato pedido
                c = climb_at[k]
                pa, pb = PROJ.to_xy(*data.nodes[a]), PROJ.to_xy(*data.nodes[b])
                gap = math.hypot(pb[0] - pa[0], pb[1] - pa[1]) or 1.0
                along = min(300.0, gap / 2)
                pc = (pa[0] + (pb[0] - pa[0]) * along / gap, pa[1] + (pb[1] - pa[1]) * along / gap)
                cnode = nid()
                data.nodes[cnode] = PROJ.to_latlon(*pc)
                reach = c.up_km * 1000 / 4                         # o cume fica a ~¼ do comprimento, para fora
                summit_xy = (pa[0] + c.outward[0] * reach + (pc[0] - pa[0]) / 2,
                             pa[1] + c.outward[1] * reach + (pc[1] - pa[1]) / 2)
                summit = nid()
                data.nodes[summit] = PROJ.to_latlon(*summit_xy)
                for (p, q, n1, n2, length, tag) in ((pa, summit_xy, a, summit, c.up_km * 1000, "subida"),
                                                    (summit_xy, pc, summit, cnode, c.down_km * 1000, "descida")):
                    legs = max(4, int(length / 1200))
                    zz = _zigzag(p, q, length, legs, c.outward)
                    chain = [n1]
                    for x, y in zz[1:-1]:
                        m = nid()
                        data.nodes[m] = PROJ.to_latlon(x, y)
                        chain.append(m)
                    chain.append(n2)
                    data.ways.append(Way(-len(data.ways) - 1, chain,
                                         {"highway": "serra", "name": c.name, "climb": c.id, "side": tag}))
                data.ways.append(Way(-len(data.ways) - 1, [cnode, b], {"highway": "ligação", "name": "Estrada de ligação"}))
                out[c.id] = (a, summit, cnode)
            else:
                data.ways.append(Way(-len(data.ways) - 1, [a, b], {"highway": "ligação", "name": "Estrada de ligação"}))
    return out


def _south_component(data: OsmData, north: set[int]) -> set[int]:
    """A maior rede da margem sul (sem pontes): onde se ligam as pontas da margem sul."""
    adj: dict[int, list[int]] = defaultdict(list)
    for w in data.ways:
        if is_bridge_way(data, w):
            continue
        for a, b in zip(w.nodes, w.nodes[1:]):
            if a not in north and b not in north:
                adj[a].append(b)
                adj[b].append(a)
    best: set[int] = set()
    seen: set[int] = set()
    for s0 in adj:
        if s0 in seen:
            continue
        comp, stack = {s0}, [s0]
        while stack:
            for k in adj[stack.pop()]:
                if k not in comp:
                    comp.add(k)
                    stack.append(k)
        seen |= comp
        if len(comp) > len(best):
            best = comp
    return best


# ---------------------------------------------------------------- 4. acabamentos
def climb_profile(length: float, rise: float, seed: int, step: float = 250.0) -> list[tuple[float, float]]:
    """Perfil de serra: declive médio exato, com variações e um ou outro replano."""
    n = max(1, int(round(length / step)))
    seg = length / n
    avg = rise / length * 100
    raw = [avg + 0.25 * abs(avg) * math.sin(2 * math.pi * i / 7 + seed)
           + 0.12 * abs(avg) * math.sin(2 * math.pi * i / 3.3 + 2 * seed) for i in range(n)]
    if n > 10:                                   # replano a meio
        for i in range(n // 2, n // 2 + 2):
            raw[i] = avg * 0.5
    fix = avg - sum(raw) / n
    return [(seg, g + fix) for g in raw]


def _undulate(prof: list[tuple[float, float]], amp: float = 1.5, wave: float = 700.0, seed: float = 0.0):
    """Ondulação de média zero: a altimetria das pontas não muda."""
    if not prof:
        return prof
    d, out = 0.0, []
    for length, g in prof:
        out.append((length, g + amp * math.sin(2 * math.pi * (d + length / 2) / wave + seed)))
        d += length
    total = sum(l for l, _ in out)
    shift = (sum(l * g for l, g in prof) - sum(l * g for l, g in out)) / total
    return [(l, g + shift) for l, g in out]


def _set_zone_and_locks(g: CityGraph) -> dict:
    """Pontes bloqueadas; margem de cada interseção pela ligação das estradas; zonas."""
    names = {name.lower(): bid for bid, (name, _) in metro.BRIDGES.items()}
    for e in g.edges.values():
        if e.mode != "road":
            continue
        ja, jb = g.junctions[e.a], g.junctions[e.b]
        la, lb = g.projection.to_latlon(ja.x, ja.y), g.projection.to_latlon(jb.x, jb.y)
        mid = g.projection.to_latlon((ja.x + jb.x) / 2, (ja.y + jb.y) / 2)
        named = next((bid for n, bid in names.items() if n in (e.name or "").lower()), "")
        if named:
            e.lock = named
        elif metro.bank_of(*la) != metro.bank_of(*lb) and metro.bridge_distance_km(*mid) < metro.BRIDGE_REACH_KM:
            e.lock = metro.nearest_bridge(*mid)
    # margem norte = tudo o que se alcança da Baixa sem atravessar uma ponte
    start = g.nearest(*g.projection.to_xy(*metro.BAIXA_CENTER), where=lambda j: j.id > 0)
    north, stack = {start.id}, [start.id]
    while stack:
        j = stack.pop()
        for eid, fwd in g._adj.get(j, []):
            e = g.edges[eid]
            if e.mode == "road" and not e.lock:
                k = g.end_of(e, fwd)
                if k not in north:
                    north.add(k)
                    stack.append(k)
    moved = 0
    for j in g.junctions.values():
        lat, lon = g.projection.to_latlon(j.x, j.y)
        bank = "norte" if j.id in north else "sul"
        moved += bank != metro.bank_of(lat, lon)
        j.zone = metro.zone_of(lat, lon, bank)
    return {"interseções_com_margem_corrigida": moved}


def _keep_big_components(g: CityGraph) -> int:
    """Fica só a rede principal (as duas margens, unidas pelas pontes): ilhas de
    filtragem e redes isoladas (como Tróia, só ligada por ferry) saem."""
    seen: set[int] = set()
    drop: set[int] = set()
    comps: list[set[int]] = []
    for start in list(g.junctions):
        if start in seen:
            continue
        comp, stack = {start}, [start]
        while stack:
            j = stack.pop()
            for eid, fwd in g._adj.get(j, []):
                k = g.end_of(g.edges[eid], fwd)
                if k not in comp:
                    comp.add(k)
                    stack.append(k)
        seen |= comp
        comps.append(comp)
    biggest = max(comps, key=len) if comps else set()
    for comp in comps:
        if comp is not biggest:
            drop |= comp
    for e in [e for e in g.edges.values() if e.a in drop or e.b in drop]:
        del g.edges[e.id]
    for j in drop:
        g.junctions.pop(j, None)
    g.index()
    return len(drop)


def _add_water(g: CityGraph, is_water, spacing: float = 400.0) -> None:
    """Faixas de remo, travessias e docas (cais que ligam a terra à água)."""
    jid = [WATER_ID0]
    eid = [max(g.edges) + 1 if g.edges else 1]

    def add_j(x, y) -> int:
        jid[0] -= 1
        g.junctions[jid[0]] = Junction(jid[0], x, y, 0.0)
        return jid[0]

    def add_e(a, b, mode, name, lock=""):
        ja, jb = g.junctions[a], g.junctions[b]
        length = max(1.0, math.hypot(jb.x - ja.x, jb.y - ja.y))
        e = Edge(eid[0], a, b, name, "rio" if mode == "water" else "cais", [(ja.x, ja.y), (jb.x, jb.y)], length,
                 [(length, 0.0)], False, False, 0, mode, lock)
        g.edges[eid[0]] = e
        eid[0] += 1

    lane_nodes: list[int] = []
    for lane, pts in metro.ROW_LANES.items():
        xy = [g.projection.to_xy(*p) for p in pts]
        chain = []
        for (x1, y1), (x2, y2) in zip(xy, xy[1:]):
            n = max(1, int(math.hypot(x2 - x1, y2 - y1) // spacing))
            for i in range(n):
                chain.append(add_j(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n))
        chain.append(add_j(*xy[-1]))
        for a, b in zip(chain, chain[1:]):
            add_e(a, b, "water", "Rio Tejo")
        lane_nodes += chain

    def nearest_lane(lat, lon):
        x, y = g.projection.to_xy(lat, lon)
        return min(lane_nodes, key=lambda j: (g.junctions[j].x - x) ** 2 + (g.junctions[j].y - y) ** 2)

    for cid, (p, q) in metro.ROW_CROSSINGS.items():
        add_e(nearest_lane(*p), nearest_lane(*q), "water", "Travessia do Tejo", lock=cid)

    # docas: a interseção de terra mais próxima de cada nó da faixa, se estiver na margem
    g.index()
    used: set[int] = set()
    for w in lane_nodes:
        wj = g.junctions[w]
        land = g.nearest(wj.x, wj.y, within=metro.DOCK_REACH_M,
                         where=lambda j: j.id > 0 and j.id not in used and any(
                             e.mode == "road" and (e.bike or e.foot) for e, _ in g.outgoing(j.id, "run") + g.outgoing(j.id, "bike")))
        if land is None:
            continue
        lat, lon = g.projection.to_latlon(land.x, land.y)
        if not is_water(lat, lon):
            continue
        land.dock = True
        used.add(land.id)
        add_e(land.id, w, "dock", "Cais")
    g.index()
    # zona de cada nó de água: a da terra que o acompanha (a interseção mais próxima)
    for w in lane_nodes:
        wj = g.junctions[w]
        land = g.nearest(wj.x, wj.y, within=5000, where=lambda j: j.id > 0)
        wj.zone = land.zone if land else metro.zone_of(*g.projection.to_latlon(wj.x, wj.y))


PLACE_KINDS = {"restaurant": "restaurant", "fast_food_restaurant": "fast_food", "cafe": "cafe",
               "coffee_shop": "cafe", "police_station": "police", "pier": "ferry_terminal", "marina": "ferry_terminal"}


def add_anchors(g: CityGraph, places: list[tuple[str, float, float]], within: float = 250.0) -> None:
    """Estabelecimentos reais (categoria, lat, lon) → âncoras na interseção mais próxima."""
    for cat, lat, lon in places:
        kind = PLACE_KINDS.get(cat)
        if not kind:
            continue
        x, y = g.projection.to_xy(lat, lon)
        j = g.nearest(x, y, within=within, where=lambda j: j.id > 0)
        if j is not None:
            from .graph import Anchor
            g.anchors.append(Anchor(kind, j.id, x, y))


def finish(g: CityGraph, climbs: dict[str, tuple], is_water, places=()) -> dict:
    """Zonas, pontes, serras, ligações, rio, docas e estabelecimentos."""
    removed = _keep_big_components(g)
    report = {"ilhas_removidas": removed, **_set_zone_and_locks(g), "serras": {}}
    for k, (cid, (a, summit, b)) in enumerate(climbs.items()):
        c = next(c for c in metro.CLIMBS if c.id == cid)
        if summit not in g.junctions:
            continue
        top = g.junctions[a].ele + c.up_km * 1000 * c.avg_pct / 100
        g.junctions[summit].ele = top
        for e in g.edges.values():
            if e.highway != "serra" or e.name != c.name:
                continue
            start, end = g.junctions[e.a], g.junctions[e.b]
            e.profile = compress_profile(climb_profile(e.length, end.ele - start.ele, seed=k + 1))
        up = sum(e.length for e in g.edges.values() if e.name == c.name and e.b == summit)
        down = sum(e.length for e in g.edges.values() if e.name == c.name and e.a == summit)
        report["serras"][c.name] = {"subida_km": round(up / 1000, 1), "média_%": round(c.avg_pct, 1),
                                    "cume_m": round(top), "descida_km": round(down / 1000, 1)}
    for e in g.edges.values():
        if e.highway == "ligação":
            e.profile = compress_profile(_undulate(e.profile, seed=e.id % 7))
    _add_water(g, is_water)
    add_anchors(g, places)
    g.index()
    report["pontes"] = sorted({e.lock for e in g.edges.values() if e.lock.startswith("ponte")})
    return report

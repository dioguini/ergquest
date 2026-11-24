"""Mapa interativo da Área Metropolitana: dados compactos + página em canvas.

`export(g)` reduz o grafo ao que o mapa desenha (traçados simplificados, em
metros inteiros, agrupados por zona e por classe de via). `PAGE` (o ficheiro
`metromap.html`, sem esqueleto HTML) lê `metro-map.json` ao lado e desenha um
separador por modalidade: Ciclismo e Corrida (o mesmo mapa de terra, cada um
com o seu nível) e Remo (o rio, com a sua escada).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import metro
from .graph import CityGraph, simplify

MAJOR = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
MID = {"secondary", "tertiary", "unclassified", "secondary_link", "tertiary_link", "cycleway"}

LABELS = {
    "Baixa": (38.7110, -9.1370), "Belém": (38.6970, -9.2060), "Parque das Nações": (38.7680, -9.0940),
    "Benfica": (38.7510, -9.2000), "Loures": (38.8300, -9.1690), "Odivelas": (38.7930, -9.1830),
    "Vila Franca de Xira": (38.9550, -8.9900), "Sintra": (38.8000, -9.3800), "Cascais": (38.6970, -9.4200),
    "Oeiras": (38.6910, -9.3100), "Mafra": (38.9400, -9.3300), "Almada": (38.6790, -9.1570),
    "Seixal": (38.6400, -9.1000), "Barreiro": (38.6630, -9.0720), "Montijo": (38.7060, -8.9740),
    "Alcochete": (38.7550, -8.9610), "Costa da Caparica": (38.6420, -9.2350), "Sesimbra": (38.4440, -9.1010),
    "Setúbal": (38.5240, -8.8930), "Palmela": (38.5690, -8.9010),
}


def _cls(e) -> int:
    if e.highway == "serra":
        return 4
    if e.highway == "ligação":
        return 3
    if e.highway in MAJOR:
        return 0
    if e.highway in MID:
        return 1
    return 2


def export(g: CityGraph) -> dict:
    from ..devices.hub import KIND_NAMES, REQUIREMENTS
    xs = [j.x for j in g.junctions.values()]
    ys = [j.y for j in g.junctions.values()]
    roads: dict[str, list] = {z.id: [] for z in metro.ZONES}
    water: dict[str, list] = {z.id: [] for z in metro.ROW_ZONES}
    bridges: dict[str, list] = {}
    crossings: list = []
    climbs: dict[str, list] = {}
    docks: list = []
    for e in g.edges.values():
        pts = simplify(e.points, 8.0 if e.highway not in MAJOR else 15.0)
        flat_pts = [int(round(v)) for p in pts for v in p]
        if e.mode == "water":
            if e.lock:
                crossings.append({"id": e.lock, "name": metro.CROSSING_NAMES.get(e.lock, e.lock), "pts": flat_pts})
            else:
                z = g.junctions[e.a].zone
                if z in water:
                    water[z].append(flat_pts)
            continue
        if e.mode == "dock":
            land, wet = (e.a, e.b) if e.a > 0 else (e.b, e.a)
            j = g.junctions[land]
            docks.append([round(j.x), round(j.y), g.junctions[wet].zone])
            continue
        if e.lock in metro.BRIDGES:
            bridges.setdefault(e.lock, []).append(flat_pts)
            continue
        if e.highway == "serra":
            climbs.setdefault(e.name, []).append(flat_pts)
        zone = g.junctions[e.a].zone or g.junctions[e.b].zone
        if zone in roads:
            roads[zone].append([_cls(e)] + flat_pts)
    summits = {}
    for c in metro.CLIMBS:
        es = [e for e in g.edges.values() if e.name == c.name]
        if es:
            top = max((g.junctions[j] for e in es for j in (e.a, e.b)), key=lambda j: j.ele)
            summits[c.name] = {"x": round(top.x), "y": round(top.y), "ele": round(top.ele),
                               "up_km": c.up_km, "avg": c.avg_pct, "zone": top.zone}

    def zones(ladder):
        return [{"id": z.id, "name": z.name, "bank": z.bank, "level": z.level, "hue": z.hue} for z in ladder]

    def needs(sport):
        req = REQUIREMENTS[sport]
        return " ou ".join(KIND_NAMES[k] for k in req.any_of)

    return {
        "attribution": g.attribution,
        "bounds": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
        "land_zones": zones(metro.ZONES), "row_zones": zones(metro.ROW_ZONES),
        "bridge_level": metro.BRIDGE_LEVEL, "crossing_level": metro.CROSSING_LEVEL,
        "devices": {s: needs(s) for s in ("bike", "run", "row")},
        "bridges": [{"id": b, "name": metro.BRIDGES[b][0], "lines": lines} for b, lines in bridges.items()],
        "crossings": crossings, "water": water, "roads": roads, "docks": docks,
        "climbs": [{"name": n, "lines": lines, **summits.get(n, {})} for n, lines in climbs.items()],
        "labels": [[n, *[round(v) for v in g.projection.to_xy(*p)]] for n, p in LABELS.items()],
        "stats": g.stats(),
    }


def save_data(g: CityGraph, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(export(g), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


PAGE = (Path(__file__).with_name("metromap.html")).read_text(encoding="utf-8")


def save_page(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(PAGE, encoding="utf-8")
    return p

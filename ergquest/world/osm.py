"""Leitura de dados OpenStreetMap (formato JSON do Overpass).

Dados © contribuidores do OpenStreetMap, licença ODbL — a atribuição tem de
aparecer no jogo e nos mapas publicados.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

EARTH_R = 6_371_000.0

# Que ruas servem a que desporto. Autoestradas e vias rápidas ficam de fora.
BIKE_HIGHWAYS = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
                 "service", "cycleway", "primary_link", "secondary_link", "tertiary_link", "pedestrian", "track"}
FOOT_HIGHWAYS = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
                 "service", "pedestrian", "footway", "steps", "path", "track", "cycleway",
                 "primary_link", "secondary_link", "tertiary_link"}


@dataclass(frozen=True)
class Projection:
    """Projeção equirretangular local: (lat, lon) ↔ metros à volta de um centro.

    Numa zona de poucos km o erro é desprezável e as contas ficam em metros.
    """
    lat0: float
    lon0: float

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        x = math.radians(lon - self.lon0) * EARTH_R * math.cos(math.radians(self.lat0))
        y = math.radians(lat - self.lat0) * EARTH_R
        return x, y

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat0 + math.degrees(y / EARTH_R)
        lon = self.lon0 + math.degrees(x / (EARTH_R * math.cos(math.radians(self.lat0))))
        return lat, lon


@dataclass
class Way:
    id: int
    nodes: list[int]
    tags: dict[str, str]

    @property
    def highway(self) -> str | None:
        return self.tags.get("highway")

    @property
    def name(self) -> str:
        return self.tags.get("name", "")

    def bike_ok(self) -> bool:
        if self.tags.get("bicycle") in ("no", "dismount"):
            return False
        if self.highway in ("pedestrian", "footway") and self.tags.get("bicycle") not in ("yes", "designated"):
            return False
        return self.highway in BIKE_HIGHWAYS

    def foot_ok(self) -> bool:
        return self.tags.get("foot") != "no" and self.highway in FOOT_HIGHWAYS

    def oneway_for_bike(self) -> int:
        """1 = só no sentido do traçado, -1 = só ao contrário, 0 = dois sentidos."""
        if self.tags.get("oneway:bicycle") == "no" or self.tags.get("cycleway") == "opposite":
            return 0
        ow = self.tags.get("oneway")
        if ow in ("yes", "true", "1") or self.tags.get("junction") == "roundabout":
            return 1
        return -1 if ow == "-1" else 0


@dataclass
class OsmData:
    nodes: dict[int, tuple[float, float]] = field(default_factory=dict)      # id → (lat, lon)
    node_tags: dict[int, dict[str, str]] = field(default_factory=dict)
    ways: list[Way] = field(default_factory=list)

    @property
    def streets(self) -> list[Way]:
        return [w for w in self.ways if w.highway]

    @property
    def water_edges(self) -> list[Way]:
        """Linhas de margem: costa, cais e margens de rio."""
        return [w for w in self.ways if w.tags.get("natural") == "coastline"
                or w.tags.get("man_made") in ("quay", "pier") or w.tags.get("waterway") == "riverbank"]

    def center(self) -> tuple[float, float]:
        lats = [p[0] for p in self.nodes.values()]
        lons = [p[1] for p in self.nodes.values()]
        return (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2


def parse(doc: dict) -> OsmData:
    data = OsmData()
    for el in doc.get("elements", []):
        if el.get("type") == "node":
            data.nodes[el["id"]] = (el["lat"], el["lon"])
            if el.get("tags"):
                data.node_tags[el["id"]] = el["tags"]
    for el in doc.get("elements", []):
        if el.get("type") == "way":
            nodes = [n for n in el.get("nodes", []) if n in data.nodes]
            if len(nodes) >= 2:
                data.ways.append(Way(el["id"], nodes, el.get("tags", {})))
    return data


def load(path: str | Path) -> OsmData:
    return parse(json.loads(Path(path).read_text(encoding="utf-8")))


def overpass_query(south: float, west: float, north: float, east: float) -> str:
    """A consulta Overpass que descarrega uma zona jogável."""
    bb = f"{south},{west},{north},{east}"
    return (f'[out:json][timeout:120];('
            f'way["highway"]({bb});'
            f'way["natural"="coastline"]({bb});'
            f'way["man_made"~"^(pier|quay)$"]({bb});'
            f'node["amenity"~"^(restaurant|cafe|fast_food|police|ferry_terminal)$"]({bb});'
            f');(._;>;);out body;')

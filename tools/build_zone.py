"""Descarrega e constrói o grafo jogável de uma zona.

    python tools/build_zone.py lisboa-centro

1. Ruas, margens e pontos de interesse do OpenStreetMap (Overpass API).
2. Altimetria Copernicus GLO-30 (~30 m; precisa de `tifffile` e `imagecodecs`),
   ou SRTM 1″ se não der, dos mosaicos públicos na AWS.
3. Constrói o grafo e grava-o em data/<zona>.json, com o mapa 2D em
   data/<zona>.html (os dados brutos ficam em data/raw/).

Precisa de acesso a overpass-api.de e a s3.amazonaws.com.
"""
from __future__ import annotations

import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ergquest.world import dem, osm  # noqa: E402
from ergquest.world.graph import ATTRIBUTION, COPERNICUS, SRTM as SRTM_CREDIT, build  # noqa: E402
from ergquest.world.mapview import save as save_map  # noqa: E402
from ergquest.world.zones import ZONES  # noqa: E402

OVERPASS = "https://overpass-api.de/api/interpreter"
SRTM = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/{lat}/{name}.hgt.gz"
COP30 = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{la:02d}_00_{ew}{lo:03d}_00_DEM/"
         "Copernicus_DSM_COG_10_{ns}{la:02d}_00_{ew}{lo:03d}_00_DEM.tif")
UA = {"User-Agent": "ErgQuest-zone-builder/0.1"}


def fetch(url: str, dest: Path, data: bytes | None = None) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r:
        dest.write_bytes(r.read())
    return dest


def main(key: str) -> None:
    zone = ZONES[key]
    raw = ROOT / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    print(f"→ OpenStreetMap: {zone.key} {zone.south},{zone.west} – {zone.north},{zone.east}")
    q = osm.overpass_query(zone.south, zone.west, zone.north, zone.east)
    osm_path = fetch(OVERPASS, raw / f"{zone.key}.osm.json", urllib.parse.urlencode({"data": q}).encode())
    data = osm.load(osm_path)
    print(f"  {len(data.nodes)} nós, {len(data.ways)} vias")

    tiles, credits = [], set()
    for lat in range(math.floor(zone.south), math.floor(zone.north) + 1):
        for lon in range(math.floor(zone.west), math.floor(zone.east) + 1):
            name = dem.tile_name(lat, lon)
            try:      # Copernicus GLO-30 (2011–15, melhor em cidade); senão SRTM (2000)
                url = COP30.format(ns="N" if lat >= 0 else "S", la=abs(lat), ew="E" if lon >= 0 else "W", lo=abs(lon))
                tiles.append(dem.Tile.from_geotiff(fetch(url, raw / f"cop30_{name}.tif")))
                credits.add(COPERNICUS)
                print(f"→ Altimetria {name}: Copernicus GLO-30")
            except (ImportError, OSError, ValueError) as err:
                print(f"→ Altimetria {name}: SRTM ({type(err).__name__}: {err})")
                tiles.append(dem.Tile.from_hgt(fetch(SRTM.format(lat=name[:3], name=name), raw / f"{name}.hgt.gz")))
                credits.add(SRTM_CREDIT)

    graph = build(data, dem.Dem(tiles).ground, center=zone.center)
    graph.attribution = " · ".join([ATTRIBUTION, *sorted(credits)])
    out = ROOT / "data" / f"{zone.key}.json"
    graph.save(out)
    print(f"✔ {out.relative_to(ROOT)}: " + json.dumps(graph.stats(), ensure_ascii=False))
    page = save_map(graph, ROOT / "data" / f"{zone.key}.html", f"ErgQuest · {zone.city.title()} {zone.zone}")
    print(f"✔ mapa: {page.relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "lisboa-centro")

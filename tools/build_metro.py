"""Constrói o mapa da Área Metropolitana de Lisboa.

    python tools/build_metro.py

Entradas (em data/raw/): segmentos e locais do Overture Maps (tools/overture.py
descarrega-os) e os mosaicos Copernicus GLO-30. Saídas: data/lisboa-metro.json.gz
e o mapa data/lisboa-metro.html.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import pyarrow.parquet as pq  # noqa: E402

from ergquest.world import dem, metro, metrobuild  # noqa: E402
from ergquest.world.graph import ATTRIBUTION, COPERNICUS, build  # noqa: E402

RAW = ROOT / "data" / "raw"
TILES = ("N38W010", "N38W009", "N39W010", "N39W009")
COP30 = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{k}_DEM/Copernicus_DSM_COG_10_{k}_DEM.tif")


def ensure_inputs() -> None:
    import urllib.request
    import overture
    (RAW / "metro").mkdir(parents=True, exist_ok=True)
    for t in TILES:
        p = RAW / f"cop30_{t}.tif"
        if not p.exists():
            k = f"{t[:3]}_00_{t[3:]}_00"
            print(f"→ altimetria {t}")
            urllib.request.urlretrieve(COP30.format(k=k), p)
    seg, pla = RAW / "metro" / "segments.parquet", RAW / "metro" / "places.parquet"
    if not seg.exists() or not pla.exists():
        rel = overture.latest_release()
        box = metro.BOX
        if not seg.exists():
            print(f"→ Overture {rel}: estradas")
            pq.write_table(overture.read_bbox(rel, "transportation", "segment", box,
                           ["id", "names", "subtype", "class", "connectors", "road_flags",
                            "access_restrictions", "geometry"]), seg)
        if not pla.exists():
            print(f"→ Overture {rel}: locais")
            pq.write_table(overture.read_bbox(rel, "places", "place", box,
                           ["id", "names", "basic_category", "confidence", "geometry"]), pla)


def main() -> None:
    t0 = time.time()
    ensure_inputs()
    D = dem.Dem([dem.Tile.from_geotiff(RAW / f"cop30_{t}.tif") for t in TILES])

    def is_water(lat, lon, r=150.0):
        dl, do = r / 111_320, r / (111_320 * math.cos(math.radians(lat)))
        return any(D.elevation(lat + a * dl, lon + b * do) <= 0.5
                   for a, b in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7)))

    rows = pq.read_table(RAW / "metro" / "segments.parquet").to_pylist()
    print(f"→ {len(rows)} segmentos ({time.time() - t0:.0f}s)")
    # análise: o que sai do mapa de terra e porquê (km)
    removed: dict[str, float] = {}
    for r in rows:
        if r.get("subtype") != "road" or not r.get("geometry"):
            continue
        cls, surf = r.get("class"), metrobuild.surfaces_of(r)
        why = ("escadas" if cls == "steps" else "passeios à parte" if cls == "footway"
               else "trilhos e caminhos" if cls in ("path", "track", "bridleway")
               else "terra/gravilha" if surf & metro.UNPAVED_SURFACES else None)
        if why:
            pts = metrobuild.parse_wkb_linestring(r["geometry"])
            km = sum(math.hypot((b[0] - a[0]) * 87.0, (b[1] - a[1]) * 111.3) for a, b in zip(pts, pts[1:]))
            removed[why] = removed.get(why, 0.0) + km
    print("  fora do mapa (km):", {k: round(v) for k, v in sorted(removed.items())})
    data, stubs = metrobuild.from_overture(rows)
    print(f"  {len(data.ways)} vias, {len(data.nodes)} nós, {len(stubs)} pontas soltas na extremidade")
    climbs = metrobuild.stitch_edges(data, stubs)
    g = build(data, D.ground, center=metro.BAIXA_CENTER)
    print(f"→ grafo: {len(g.junctions)} interseções ({time.time() - t0:.0f}s)")
    pl = pq.read_table(RAW / "metro" / "places.parquet", columns=["basic_category", "confidence", "geometry"]).to_pylist()
    places = []
    for p in pl:
        if (p.get("confidence") or 0) < 0.5 or p.get("basic_category") not in metrobuild.PLACE_KINDS:
            continue
        b = p["geometry"]
        import struct
        end = "<" if b[0] == 1 else ">"
        lon, lat = struct.unpack(end + "dd", b[5:21])
        places.append((p["basic_category"], lat, lon))
    report = metrobuild.finish(g, climbs, is_water, places)
    g.attribution = f"{ATTRIBUTION} via Overture Maps Foundation · locais © Overture Maps Foundation (CDLA Permissive 2.0) · {COPERNICUS}"
    out = ROOT / "data" / "lisboa-metro.json.gz"
    g.save(out)
    st = g.stats()
    st["zonas"] = {z.id: sum(1 for j in g.junctions.values() if j.zone == z.id) for z in metro.ZONES}
    print("✔", out.relative_to(ROOT), f"{out.stat().st_size / 2**20:.1f} MB ({time.time() - t0:.0f}s)")
    print(json.dumps({**st, **report}, ensure_ascii=False, indent=1))
    from ergquest.world import metromap
    metromap.save_data(g, ROOT / "data" / "metro-map.json")
    metromap.save_page(ROOT / "data" / "lisboa-metro.html")
    print("✔ mapa: data/lisboa-metro.html (abre com um servidor local na pasta data/)")


if __name__ == "__main__":
    main()

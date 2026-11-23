"""Altimetria a partir de um DEM em mosaicos SRTM (.hgt).

Os .hgt (SRTM ou Copernicus GLO-30 convertido) são grelhas de inteiros de 16
bits big-endian, de 1°×1°, com 3601 (1″, ~30 m) ou 1201 (3″, ~90 m) linhas.
O canto noroeste é o primeiro valor; o nome do ficheiro diz o canto sudoeste
(ex.: N38W010 cobre 38–39° N e 10–9° O).
"""
from __future__ import annotations

import gzip
import math
from pathlib import Path

import numpy as np

VOID = -32768


def tile_name(lat: float, lon: float) -> str:
    la, lo = math.floor(lat), math.floor(lon)
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


class Tile:
    """Grelha de 1°×1° com os valores nos centros dos píxeis.

    `top`/`west` são as coordenadas do centro do píxel (0, 0) e `step` o
    espaçamento em graus (.hgt: 1/(n−1); Copernicus GLO-30: 1/3600).
    """

    def __init__(self, grid: np.ndarray, south: int, west: int, step: float | None = None):
        if grid.ndim != 2 or grid.shape[0] != grid.shape[1]:
            raise ValueError("um mosaico é uma grelha quadrada")
        self.grid = grid.astype(np.float64)
        self.grid[grid == VOID] = np.nan
        self.n = grid.shape[0]
        self.south, self.west = south, west
        self.step = step or 1.0 / (self.n - 1)
        self.top = south + 1

    @classmethod
    def from_geotiff(cls, path: str | Path) -> "Tile":
        """Copernicus GLO-30 (GeoTIFF, float32, PixelIsPoint). Precisa de `tifffile` e `imagecodecs`."""
        import tifffile
        with tifffile.TiffFile(path) as t:
            page = t.pages[0]
            grid = page.asarray()
            tags = {tg.name: tg.value for tg in page.tags.values()}
        _, _, _, west, top, _ = tags["ModelTiepointTag"]
        step = tags["ModelPixelScaleTag"][0]
        tile = cls(grid, int(round(top)) - 1, int(round(west)), step)
        tile.top = top
        return tile

    @classmethod
    def from_hgt(cls, path: str | Path) -> "Tile":
        p = Path(path)
        raw = gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes()
        side = int(round(math.sqrt(len(raw) // 2)))
        if side * side * 2 != len(raw):
            raise ValueError(f"{p.name}: tamanho inesperado para um .hgt")
        name = p.name[:7]
        south = int(name[1:3]) * (1 if name[0] == "N" else -1)
        west = int(name[4:7]) * (1 if name[3] == "E" else -1)
        return cls(np.frombuffer(raw, dtype=">i2").reshape(side, side), south, west)

    def covers(self, lat: float, lon: float) -> bool:
        span = (self.n - 1) * self.step
        return self.top - span <= lat <= self.top and self.west <= lon <= self.west + span

    def elevation(self, lat: float, lon: float) -> float:
        """Interpolação bilinear; vazios (NaN) contam como nível do mar."""
        if not self.covers(lat, lon):
            raise ValueError(f"({lat}, {lon}) fora do mosaico {tile_name(self.south, self.west)}")
        r = (self.top - lat) / self.step
        c = (lon - self.west) / self.step
        r0, c0 = min(int(r), self.n - 2), min(int(c), self.n - 2)
        fr, fc = r - r0, c - c0
        g = np.nan_to_num(self.grid[r0:r0 + 2, c0:c0 + 2], nan=0.0)
        top = g[0, 0] * (1 - fc) + g[0, 1] * fc
        bot = g[1, 0] * (1 - fc) + g[1, 1] * fc
        return float(top * (1 - fr) + bot * fr)


class Dem:
    """Vários mosaicos; escolhe o certo para cada ponto."""

    def __init__(self, tiles: list[Tile]):
        self.tiles = tiles

    def ground(self, lat: float, lon: float, radius_m: float = 15.0) -> float:
        """Cota do chão: o mínimo entre o ponto e quatro vizinhos a `radius_m`.

        O SRTM/Copernicus é um modelo de superfície (inclui edifícios e
        árvores); numa rua, o ponto mais baixo à volta é o mais próximo do
        pavimento.
        """
        dlat = radius_m / 111_320.0
        dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
        pts = ((lat, lon), (lat + dlat, lon), (lat - dlat, lon), (lat, lon + dlon), (lat, lon - dlon))
        return min(self.elevation(a, b) for a, b in pts)

    def elevation(self, lat: float, lon: float) -> float:
        for t in self.tiles:
            if t.covers(lat, lon):
                return t.elevation(lat, lon)
        raise ValueError(f"sem altimetria para ({lat:.5f}, {lon:.5f}): falta {tile_name(lat, lon)}.hgt")

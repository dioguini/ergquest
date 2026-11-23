"""Zonas jogáveis com dados reais: a caixa geográfica de cada uma."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZoneBox:
    city: str
    zone: str
    south: float
    west: float
    north: float
    east: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.south + self.north) / 2, (self.west + self.east) / 2

    @property
    def key(self) -> str:
        return f"{self.city}-{self.zone}"


# Baixa, Chiado, Alfama até ao Castelo, Cais do Sodré e a margem do Tejo.
LISBOA_CENTRO = ZoneBox("lisboa", "centro", 38.7030, -9.1500, 38.7170, -9.1250)

ZONES = {z.key: z for z in (LISBOA_CENTRO,)}

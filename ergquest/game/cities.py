"""Cidades, zonas e locais especiais do mundo.

A geometria real (ruas, rios, altimetria) vem do OpenStreetMap e de um DEM,
pré-processados offline. Aqui fica só o *catálogo* de jogo: que zonas
existem, em que nível abrem, onde se pode remar, e as pistas de competição.
Os estabelecimentos são fictícios e gerados por semente (ver `missions`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Sport(str, Enum):
    BIKE = "bike"
    RUN = "run"
    ROW = "row"
    GYM = "gym"          # não existe no mundo: só registo (buff de Robustez)

    @property
    def in_world(self) -> bool:
        return self is not Sport.GYM


# Trocas possíveis num ponto de troca de rua. O remo só começa numa doca.
STREET_SWAPS = {(Sport.BIKE, Sport.RUN), (Sport.RUN, Sport.BIKE)}


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    unlock_level: int
    water: bool = False          # tem docas: permite remar


@dataclass(frozen=True)
class Venue:
    id: str
    name: str
    kind: str                    # "crit_outdoor" | "crit_indoor" | "velodrome"
    sport: Sport = Sport.BIKE


@dataclass(frozen=True)
class City:
    id: str
    name: str
    unlock_level: int
    unlock_active_weeks: int     # consistência: semanas com treino nas últimas 8
    zones: tuple[Zone, ...]
    venues: tuple[Venue, ...] = field(default_factory=tuple)

    def zone(self, zid: str) -> Zone:
        for z in self.zones:
            if z.id == zid:
                return z
        raise KeyError(zid)


def _venues(prefix: str, outdoor: tuple[str, ...], indoor: tuple[str, str, str], velo: str) -> tuple[Venue, ...]:
    vs = [Venue(f"{prefix}-crit-out-{i}", n, "crit_outdoor") for i, n in enumerate(outdoor, 1)]
    vs += [Venue(f"{prefix}-crit-in-{i}", n, "crit_indoor") for i, n in enumerate(indoor, 1)]
    vs.append(Venue(f"{prefix}-velo", velo, "velodrome"))
    return tuple(vs)


CITIES: dict[str, City] = {c.id: c for c in (
    City("lisboa", "Lisboa", 1, 0, (
        Zone("baixa", "Baixa-Chiado", 1),
        Zone("alfama", "Alfama e Graça", 3),
        Zone("ribeira", "Cais do Sodré e Ribeira", 5, water=True),
        Zone("belem", "Belém e Restelo", 8, water=True),
        Zone("oriente", "Parque das Nações", 12, water=True),
        Zone("monsanto", "Monsanto", 16),
    ), _venues("lis", ("Circuito da Avenida", "Volta ao Parque Eduardo VII"),
               ("Arena Tejo", "Pavilhão Alcântara", "Hangar Oriente"), "Velódromo do Tejo")),
    City("london", "London", 10, 4, (
        Zone("city", "The City", 10),
        Zone("southbank", "South Bank", 12, water=True),
        Zone("regents", "Regent's Park", 14),
        Zone("greenwich", "Greenwich", 18, water=True),
        Zone("richmond", "Richmond Hill", 22),
    ), _venues("ldn", ("Regent's Loop", "Embankment Crit"),
               ("Docklands Arena", "Shoreditch Box", "Battersea Hall"), "Thames Velodrome")),
    City("nyc", "New York", 20, 6, (
        Zone("midtown", "Midtown", 20),
        Zone("centralpark", "Central Park", 22),
        Zone("hudson", "Hudson River Greenway", 24, water=True),
        Zone("brooklyn", "Brooklyn Waterfront", 27, water=True),
        Zone("harlem", "Harlem Hills", 30),
    ), _venues("nyc", ("Central Park Loop", "Prospect Park Crit"),
               ("Pier 40 Arena", "Bronx Hall", "Queens Track"), "Hudson Velodrome")),
)}


def can_swap_at_street(current: Sport, target: Sport) -> bool:
    """Bicicleta ↔ corrida em qualquer rua; o remo exige uma doca."""
    return (current, target) in STREET_SWAPS


def can_start_rowing(city: City, zone_id: str, at_dock: bool) -> bool:
    return at_dock and city.zone(zone_id).water

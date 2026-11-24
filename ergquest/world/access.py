"""O que um atleta pode usar de cada mapa, pelo nível NESSE desporto.

* **Terra** (ciclismo e corrida: o mesmo mapa, cada desporto com o seu nível):
  zonas por ordem de `metro.ZONES`; pontes com `metro.BRIDGE_LEVEL`.
* **Rio** (remo): zonas por ordem de `metro.ROW_ZONES`; travessias entre
  margens com `metro.CROSSING_LEVEL`.

Uma rua (ou troço de rio) só se pode tomar se a zona onde acaba estiver aberta
e se não passar por uma ponte ou travessia bloqueada. É isto que, numa sessão
livre, faz o atleta encontrar o limite do mundo e dar meia-volta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import metro
from .graph import CityGraph, Edge


@dataclass
class Access:
    zones: set[str] = field(default_factory=set)
    locks: set[str] = field(default_factory=set)
    sport: str = "bike"

    @classmethod
    def for_level(cls, level: int, sport: str = "bike") -> "Access":
        steps = metro.ladder(sport)
        zones = {z.id for z in steps if level >= z.level} | {steps[0].id}
        locks: set[str] = set()
        if sport == "row":
            if level >= metro.CROSSING_LEVEL:
                locks |= set(metro.ROW_CROSSINGS)
        elif level >= metro.BRIDGE_LEVEL:
            locks |= set(metro.BRIDGES)
        return cls(zones, locks, sport)

    @classmethod
    def everything(cls, sport: str = "bike") -> "Access":
        return cls.for_level(999, sport)

    def _zone_at(self, g: CityGraph, e: Edge, forward: bool) -> str:
        end = g.junctions[g.end_of(e, forward)]
        if self.sport == "row" and end.id > 0:           # cais: conta o lado da água
            return g.junctions[g.end_of(e, not forward)].zone
        return end.zone

    def can_use(self, g: CityGraph, e: Edge, forward: bool) -> bool:
        if e.lock and e.lock not in self.locks:
            return False
        z = self._zone_at(g, e, forward)
        return not z or z in self.zones

    def reason(self, g: CityGraph, e: Edge, forward: bool) -> str | None:
        """Porque é que esta rua está fechada (o que o ecrã mostra), ou None."""
        if e.lock and e.lock not in self.locks:
            if e.lock in metro.BRIDGES:
                return f"{metro.BRIDGES[e.lock][0]} — abre no nível {metro.BRIDGE_LEVEL}"
            return f"Travessia {metro.CROSSING_NAMES.get(e.lock, '')} — abre no nível {metro.CROSSING_LEVEL} de remo"
        z = self._zone_at(g, e, forward)
        if z and z not in self.zones:
            zz = metro.any_zone(z)
            return f"Zona {zz.name} — abre no nível {zz.level}"
        return None

    def next_unlock(self) -> tuple[str, int] | None:
        for z in metro.ladder(self.sport):
            if z.id not in self.zones:
                return z.name, z.level
        return None

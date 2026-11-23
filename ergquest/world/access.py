"""O que um atleta pode usar do mapa: zonas abertas, pontes e travessias.

* **Zonas** abrem pela ordem de `metro.ZONES`, com o nível.
* **Pontes** (bicicleta/corrida entre margens) abrem com `metro.BRIDGE_LEVEL`.
* **Travessias de remo** entre margens: `metro.CROSSING_LEVEL`, e as zonas
  das duas margens abertas (é para remadores experientes).

Uma rua só se pode tomar se a zona onde ela acaba estiver aberta e se não
passar por uma ponte ou travessia bloqueada. É isto que, numa sessão livre,
faz o atleta encontrar o limite do mundo e dar meia-volta.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import metro
from .graph import CityGraph, Edge


@dataclass
class Access:
    zones: set[str] = field(default_factory=set)
    locks: set[str] = field(default_factory=set)

    @classmethod
    def for_level(cls, level: int) -> "Access":
        zones = {z.id for z in metro.ZONES if level >= z.level} | {metro.ZONES[0].id}
        locks: set[str] = set()
        if level >= metro.BRIDGE_LEVEL:
            locks |= set(metro.BRIDGES)
        if level >= metro.CROSSING_LEVEL:
            locks |= set(metro.ROW_CROSSINGS)
        return cls(zones, locks)

    @classmethod
    def everything(cls) -> "Access":
        return cls({z.id for z in metro.ZONES}, set(metro.BRIDGES) | set(metro.ROW_CROSSINGS))

    def can_use(self, g: CityGraph, e: Edge, forward: bool) -> bool:
        if e.lock and e.lock not in self.locks:
            return False
        end = g.junctions[g.end_of(e, forward)]
        return not end.zone or end.zone in self.zones

    def reason(self, g: CityGraph, e: Edge, forward: bool) -> str | None:
        """Porque é que esta rua está fechada (o que o ecrã mostra), ou None."""
        if e.lock and e.lock not in self.locks:
            if e.lock in metro.BRIDGES:
                return f"{metro.BRIDGES[e.lock][0]} — abre no nível {metro.BRIDGE_LEVEL}"
            return f"Travessia do Tejo — abre no nível {metro.CROSSING_LEVEL}, com as duas margens abertas"
        end = g.junctions[g.end_of(e, forward)]
        if end.zone and end.zone not in self.zones:
            z = metro.ZONE[end.zone]
            return f"Zona {z.name} — abre no nível {z.level}"
        return None

    def next_unlock(self) -> tuple[str, int] | None:
        for z in metro.ZONES:
            if z.id not in self.zones:
                return z.name, z.level
        return None

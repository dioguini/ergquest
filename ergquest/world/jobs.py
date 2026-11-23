"""Destinos dos trabalhos no mapa, respeitando o que o atleta tem aberto.

Atletas com nível para isso recebem pedidos na outra margem: de bicicleta ou
a correr, pelas pontes (`metro.BRIDGE_LEVEL`); no remo, pelas travessias do
Tejo (`metro.CROSSING_LEVEL`), com as zonas das duas margens abertas.
"""
from __future__ import annotations

import heapq
import math

from . import metro
from .graph import CityGraph


def bank(g: CityGraph, junction: int) -> str:
    z = g.junctions[junction].zone
    return "sul" if z.startswith("s-") else "norte"


def cross_bank_allowed(level: int, sport: str) -> bool:
    return level >= (metro.CROSSING_LEVEL if sport == "row" else metro.BRIDGE_LEVEL)


def distances(g: CityGraph, start: int, sport: str, access=None, limit: float = math.inf) -> dict[int, float]:
    """Distância pela rede (m) de `start` a tudo o que se alcança, até `limit`."""
    best = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        d, j = heapq.heappop(heap)
        if d > best.get(j, math.inf) or d > limit:
            continue
        for e, fwd in g.outgoing(j, sport, access):
            k = g.end_of(e, fwd)
            nd = d + e.length
            if nd < best.get(k, math.inf) and nd <= limit:
                best[k] = nd
                heapq.heappush(heap, (nd, k))
    return best


def pick_destination(g: CityGraph, start: int, sport: str, access, rng, min_m: float, max_m: float,
                     other_bank: bool = False) -> int | None:
    """Um destino alcançável entre `min_m` e `max_m`; com `other_bank`, na outra margem.

    No remo, o destino é sempre uma doca (onde os passageiros desembarcam).
    """
    dist = distances(g, start, sport, access, max_m)
    home = bank(g, start)
    docks = ({j for e in g.edges.values() if e.mode == "dock" for j in (e.a, e.b) if j > 0}
             if sport == "row" else None)
    cands = sorted(j for j, d in dist.items()
                   if min_m <= d <= max_m and j > 0
                   and (docks is None or j in docks)
                   and (bank(g, j) != home) == other_bank)
    return rng.choice(cands) if cands else None

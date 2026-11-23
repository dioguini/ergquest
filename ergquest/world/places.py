"""Estabelecimentos fictícios em sítios reais.

Cada fonte de pedidos do jogo (restaurante, esquadra, operador fluvial…) é
colocada numa âncora real do mapa do tipo certo — onde no mundo real há um
restaurante, o jogo põe um restaurante inventado. Sem âncoras suficientes,
usa interseções da zona. Determinístico: a mesma cidade para todos.
"""
from __future__ import annotations

from ..game.missions import Kind, Source, _rng
from .graph import CityGraph

ANCHOR_KINDS = {
    Kind.FOOD: ("restaurant", "fast_food", "cafe"),
    Kind.CHASE: ("police",),
    Kind.FERRY: ("ferry_terminal",),
    Kind.TOUR: ("ferry_terminal",),
}


def place(graph: CityGraph, sources: list[Source]) -> dict[str, int]:
    """{id da fonte: interseção}. Remo → docas; resto → âncoras do tipo, ou interseções."""
    used: set[int] = set()
    docks = sorted(j.id for j in graph.docks())
    all_j = sorted(graph.junctions)
    reserved = {a.junction for a in graph.anchors} | set(docks)
    out = {}
    # primeiro quem tem âncora real (restaurantes, esquadras, terminais); depois o resto
    for src in sorted(sources, key=lambda s: (s.kind not in ANCHOR_KINDS, s.id)):
        rng = _rng("place", src.id)
        kinds = ANCHOR_KINDS.get(src.kind, ())
        cands = sorted({a.junction for a in graph.anchors if a.kind in kinds} - used)
        if src.kind in (Kind.FERRY, Kind.TOUR):
            cands = sorted(set(cands) & set(docks)) or [d for d in docks if d not in used] or docks
        if not cands:
            cands = ([j for j in all_j if j not in used and j not in reserved]
                     or [j for j in all_j if j not in used] or all_j)
        j = rng.choice(cands)
        used.add(j)
        out[src.id] = j
    return out

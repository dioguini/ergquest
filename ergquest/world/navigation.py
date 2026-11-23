"""Andar no grafo: rota sugerida pelo GPS e escolha livre nas interseções.

* `fastest_route` — o GPS: o caminho mais rápido para ESTE atleta, com a
  física e a altimetria reais (para um ciclista forte a subida direta pode
  compensar; com um riquexó carregado, a volta pela marginal é melhor).
* `Navigator` — a posição do atleta numa rua. Ao chegar a uma interseção
  mostra as opções (esquerda, em frente, direita…), com a sugestão do GPS
  marcada. As setas escolhem; sem escolha, segue a sugestão (ou em frente).
* **Limites do mundo** — com um `Access`, as ruas que entram em zonas,
  pontes ou travessias fechadas aparecem como bloqueadas (com o nível a que
  abrem) e não se podem tomar. Se não houver outra saída, o atleta dá
  meia-volta. A qualquer momento: `turn_around()` (meia-volta) e
  `go_back(destino)` (o GPS leva-o de volta, pelo lado mais rápido).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from ..shared.movement import Mover, time_for
from .graph import CityGraph, Edge


def _sport_of(mover: Mover) -> str:
    return {"Bike": "bike", "Runner": "run", "Rower": "row"}.get(type(mover).__name__, "bike")


def edge_time(mover: Mover, edge: Edge, forward: bool, intensity: float, extra_kg: float = 0.0) -> float:
    return time_for(mover, edge.profile_dir(forward), intensity, extra_kg)


def fastest_route(graph: CityGraph, src: int, dst: int, mover: Mover, intensity: float = 0.75,
                  extra_kg: float = 0.0, access=None) -> list[tuple[int, bool]] | None:
    """[(aresta, sentido)] mais rápido de `src` a `dst` (Dijkstra pelo tempo).

    Com `access`, só por zonas abertas e pontes/travessias desbloqueadas.
    """
    sport = _sport_of(mover)
    best = {src: 0.0}
    prev: dict[int, tuple[int, int, bool]] = {}
    heap = [(0.0, src)]
    while heap:
        t, j = heapq.heappop(heap)
        if j == dst:
            break
        if t > best.get(j, math.inf):
            continue
        for e, fwd in graph.outgoing(j, sport, access):
            k = graph.end_of(e, fwd)
            nt = t + edge_time(mover, e, fwd, intensity, extra_kg)
            if nt < best.get(k, math.inf):
                best[k] = nt
                prev[k] = (j, e.id, fwd)
                heapq.heappush(heap, (nt, k))
    if dst not in best:
        return None
    path, j = [], dst
    while j != src:
        pj, eid, fwd = prev[j]
        path.append((eid, fwd))
        j = pj
    return list(reversed(path))


def route_profile(graph: CityGraph, route: list[tuple[int, bool]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for eid, fwd in route:
        out += graph.edges[eid].profile_dir(fwd)
    return out


def street_names(graph: CityGraph, route: list[tuple[int, bool]]) -> list[str]:
    """Nomes das ruas por onde passa a rota, sem repetições seguidas."""
    out: list[str] = []
    for eid, _ in route:
        n = graph.edges[eid].name
        if n and (not out or out[-1] != n):
            out.append(n)
    return out


def lookahead_profile(graph: CityGraph, edge: Edge, forward: bool, sport: str,
                      metres: float = 1500.0) -> list[tuple[float, float]]:
    """O perfil de seguir por esta rua e depois "sempre em frente" (a menor viragem).

    É o que o jogo usa para avaliar cada ramo de uma interseção no modo treino.
    """
    prof: list[tuple[float, float]] = []
    done, seen = 0.0, set()
    while done < metres and (edge.id, forward) not in seen:
        seen.add((edge.id, forward))
        prof += edge.profile_dir(forward)
        done += edge.length
        j = graph.end_of(edge, forward)
        h_in = _heading(edge.points, at_start=not forward) + 180
        nxt = [(e, f) for e, f in graph.outgoing(j, sport) if e.id != edge.id]
        if not nxt:
            break
        edge, forward = min(nxt, key=lambda ef: abs(((_heading(ef[0].points, at_start=ef[1]) - h_in) + 180) % 360 - 180))
    return prof


# ---------------------------------------------------------------- viragens
def _heading(points: list[tuple[float, float]], at_start: bool) -> float:
    """Rumo (graus, 0 = este, anti-horário) ao sair de uma ponta do traçado."""
    if at_start:
        (x1, y1), (x2, y2) = points[0], _far(points, 0, 1)
    else:
        (x1, y1), (x2, y2) = points[-1], _far(points, len(points) - 1, -1)
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _far(points, i, step, min_d: float = 15.0):
    """O primeiro ponto a pelo menos `min_d` m (evita rumos tortos por vértices colados)."""
    x0, y0 = points[i]
    j = i
    while 0 <= j + step < len(points):
        j += step
        if math.hypot(points[j][0] - x0, points[j][1] - y0) >= min_d:
            break
    return points[j]


def turn_label(delta: float) -> str:
    d = (delta + 180) % 360 - 180          # −180..180; positivo = esquerda
    if abs(d) < 25:
        return "em frente"
    if abs(d) > 155:
        return "inversão"
    side = "esquerda" if d > 0 else "direita"
    return f"ligeiro à {side}" if abs(d) < 60 else side


@dataclass
class Option:
    edge: Edge
    forward: bool
    label: str
    suggested: bool = False
    locked: str | None = None        # porque está fechada (zona, ponte, travessia)

    @property
    def name(self) -> str:
        return self.edge.name or self.edge.highway


@dataclass
class Navigator:
    graph: CityGraph
    sport: str
    edge: Edge
    forward: bool = True
    offset_m: float = 0.0
    route: list[tuple[int, bool]] = field(default_factory=list)     # sugestão do GPS
    pending: str | None = None                                      # escolha das setas: "esquerda"…
    travelled_m: float = 0.0
    log: list[str] = field(default_factory=list)
    access: object | None = None                                    # world.access.Access

    @classmethod
    def at(cls, graph: CityGraph, junction: int, sport: str, route: list[tuple[int, bool]] | None = None,
           access=None):
        if route:
            eid, fwd = route[0]
            return cls(graph, sport, graph.edges[eid], fwd, route=list(route[1:]), access=access)
        e, fwd = graph.outgoing(junction, sport, access)[0]
        return cls(graph, sport, e, fwd, access=access)

    @property
    def junction_ahead(self) -> int:
        return self.graph.end_of(self.edge, self.forward)

    @property
    def remaining_on_edge(self) -> float:
        return self.edge.length - self.offset_m

    def grade(self, window_m: float = 40.0) -> float:
        """Declive (%) a enviar ao rolo: média ponderada nos `window_m` à volta do atleta.

        Como nos simuladores, o rolo não sente cada degrau do modelo de terreno:
        um pico de 20 % em 10 m, vindo do ruído do DEM, dilui-se na rua.
        """
        lo, hi = self.offset_m - window_m / 2, self.offset_m + window_m / 2
        prof = self.edge.profile_dir(self.forward)
        if prof:
            lo, hi = max(0.0, lo), min(self.edge.length, max(hi, lo + 1.0))
        acc = wsum = d = 0.0
        for length, g in prof:
            a, b = max(d, lo), min(d + length, hi)
            if b > a:
                acc += g * (b - a)
                wsum += b - a
            d += length
        return acc / wsum if wsum else 0.0

    def options(self) -> list[Option]:
        """O que aparece no ecrã ao aproximar da próxima interseção."""
        j = self.junction_ahead
        in_heading = _heading(self.edge.points, at_start=not self.forward) + 180
        suggested = self.route[0] if self.route else None
        opts = []
        for e, fwd in self.graph.outgoing(j, self.sport):
            h = _heading(e.points, at_start=fwd)
            why = self.access.reason(self.graph, e, fwd) if self.access is not None else None
            opts.append(Option(e, fwd, turn_label(h - in_heading), (e.id, fwd) == suggested, why))
        back = [o for o in opts if o.edge.id == self.edge.id and o.forward != self.forward]
        if len([o for o in opts if not o.locked]) > len([o for o in back if not o.locked]):
            opts = [o for o in opts if o not in back]     # voltar para trás só num beco ou num limite
        return opts

    def press(self, arrow: str) -> None:
        """Setas: "esquerda", "direita" ou "em frente" para a próxima interseção."""
        self.pending = arrow

    def _choose(self, opts: list[Option]) -> Option:
        opts = [o for o in opts if not o.locked]
        if self.pending:
            want = self.pending
            self.pending = None
            match = [o for o in opts if want in o.label]
            if match:
                return match[0]
        for o in opts:
            if o.suggested:
                return o
        for o in opts:
            if o.label == "em frente":
                return o
        return opts[0]

    def advance(self, metres: float) -> list[str]:
        """Avança; devolve os nomes das ruas em que entrou."""
        entered = []
        while metres > 0:
            room = self.remaining_on_edge
            if metres < room:
                self.offset_m += metres
                self.travelled_m += metres
                break
            metres -= room
            self.travelled_m += room
            opts = self.options()
            for o in opts:
                if o.locked:
                    self.log.append(f"limite: {o.locked}")
            if not [o for o in opts if not o.locked]:
                # fim do mundo aberto (ou beco): meia-volta automática
                if not self.edge.allows(self.sport, not self.forward):
                    self.log.append("parado: sentido único sem saída")
                    self.offset_m = self.edge.length
                    break
                self.log.append("meia-volta")
                self.forward, self.offset_m = not self.forward, 0.0
                self.route = []
                entered.append(self.edge.name or self.edge.highway)
                continue
            pick = self._choose(opts)
            if pick.edge.id == self.edge.id and pick.forward != self.forward:
                self.log.append("meia-volta")
            if self.route and (pick.edge.id, pick.forward) == self.route[0]:
                self.route.pop(0)
            elif self.route:
                self.route = []           # saiu da rota: o GPS recalcula fora daqui
                self.log.append("fora da rota")
            self.edge, self.forward, self.offset_m = pick.edge, pick.forward, 0.0
            entered.append(pick.name)
        return entered

    def off_route(self) -> bool:
        return bool(self.log) and self.log[-1] == "fora da rota"

    def turn_around(self) -> None:
        """Meia-volta aqui mesmo (tecla para trás): o mesmo sítio, no outro sentido."""
        if not self.edge.allows(self.sport, not self.forward):
            raise ValueError("sentido único: só se pode voltar na próxima interseção")
        self.forward, self.offset_m = not self.forward, self.edge.length - self.offset_m
        self.route = []
        self.log.append("meia-volta")

    def go_back(self, target: int, mover: Mover, intensity: float = 0.6) -> list[tuple[int, bool]]:
        """Regressar: o GPS calcula o caminho até `target` pelo lado mais rápido
        (seguir até à próxima interseção, ou dar meia-volta já)."""
        ahead = self.junction_ahead
        behind = self.graph.end_of(self.edge, not self.forward)
        t_edge = edge_time(mover, self.edge, self.forward, intensity)
        frac = self.offset_m / max(self.edge.length, 1.0)
        options = []
        r = fastest_route(self.graph, ahead, target, mover, intensity, access=self.access) if ahead != target else []
        if r is not None:
            options.append((t_edge * (1 - frac) + _route_time(self.graph, r, mover, intensity), False, r))
        if self.edge.allows(self.sport, not self.forward):
            r = fastest_route(self.graph, behind, target, mover, intensity, access=self.access) if behind != target else []
            if r is not None:
                options.append((t_edge * frac + _route_time(self.graph, r, mover, intensity), True, r))
        if not options:
            raise ValueError("sem caminho de regresso")
        _, flip, route = min(options, key=lambda o: o[0])
        if flip:
            self.turn_around()
        self.route = list(route)
        self.log.append("a regressar")
        return route


def _route_time(g: CityGraph, route, mover: Mover, intensity: float) -> float:
    return sum(edge_time(mover, g.edges[e], f, intensity) for e, f in route)

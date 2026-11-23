"""Missões: o "telemóvel" de pedidos, o arrefecimento da comida e as estrelas.

Regras do conceito, tal como implementadas:

* **Fontes instanciadas por jogador** — cada jogador tem o seu `OrderBoard`.
  O Restaurante A é uma *fábrica* de pedidos, não um recurso partilhado:
  pode emitir pedidos para mil jogadores ao mesmo tempo sem conflitos. A
  geração é determinística (semente = jogador + fonte + ronda), por isso o
  servidor e o cliente chegam aos mesmos pedidos.
* **Prazos à medida do atleta** — o prazo é o tempo que *este* atleta leva a
  fazer o percurso a uma intensidade-alvo (fração do limiar) menos uma
  margem de esforço que encolhe com o nível. Todos trabalham na intensidade pretendida,
  seja qual for a FTP.
* **Dificuldade cresce com o nível** — mais intensidade e menos margem, comida a arrefecer mais
  depressa, exigência de suavidade maior no remo, mais pedidos em simultâneo.
* **Estrelas 1–5** por missão; **abandonar** anula e penaliza.
* **Pausar é sempre livre** — a comida arrefece muito mais devagar em pausa
  e o prazo congela.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from enum import Enum

from .cities import Sport


class Kind(str, Enum):
    FOOD = "food"              # bicicleta: comida quente
    PARCEL = "parcel"          # bicicleta/corrida: encomenda
    EXPRESS = "express"        # corrida: entrega rápida a pé
    CHASE = "chase"            # corrida: apoio à polícia
    FERRY = "ferry"            # remo: carga entre docas
    TOUR = "tour"              # remo: passeio com passageiros


KIND_SPORT = {
    Kind.FOOD: Sport.BIKE, Kind.PARCEL: Sport.BIKE, Kind.EXPRESS: Sport.RUN,
    Kind.CHASE: Sport.RUN, Kind.FERRY: Sport.ROW, Kind.TOUR: Sport.ROW,
}


class State(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    PICKED_UP = "picked_up"
    DONE = "done"
    ABANDONED = "abandoned"


# ---------------------------------------------------------------- dificuldade
@dataclass(frozen=True)
class Difficulty:
    margin: float              # o prazo = tempo a intensidade × (1 − margin)
    cooling: float             # multiplicador da taxa de arrefecimento
    smooth_min: float          # suavidade mínima da remada para 5 ★
    intensity: float           # intensidade-alvo por omissão (fração do limiar)
    base_slots: int            # pedidos simultâneos (sem o bónus de Robustez)


def difficulty(level: int) -> Difficulty:
    x = min(max((level - 1) / 39.0, 0.0), 1.0)       # 0 no nível 1, 1 no nível 40
    return Difficulty(
        margin=round(0.20 - 0.16 * x, 3),
        cooling=round(1.0 + 0.8 * x, 3),
        smooth_min=round(0.60 + 0.30 * x, 3),
        intensity=round(0.65 + 0.20 * x, 3),
        base_slots=1 + (level >= 10) + (level >= 25),
    )


# ---------------------------------------------------------------- temperatura
FOOD_T0 = 70.0
AMBIENT = 20.0
COLD = 40.0                   # comida "fria": 0 na componente de temperatura
HOT = 60.0                    # acima disto: perfeita
# Numa mala térmica, 15 min levam a comida de 70 °C a ~55 °C.
K_COOL = math.log((FOOD_T0 - AMBIENT) / (55.0 - AMBIENT)) / 900.0
PAUSE_COOL_FACTOR = 0.25


def food_temperature(hot_s: float, paused_s: float = 0.0, cooling: float = 1.0) -> float:
    """Lei de Newton: T = amb + (T0 − amb)·e^(−k·t). Em pausa arrefece a 25 %."""
    k = K_COOL * cooling
    t_eff = hot_s + paused_s * PAUSE_COOL_FACTOR
    return AMBIENT + (FOOD_T0 - AMBIENT) * math.exp(-k * t_eff)


# ---------------------------------------------------------------- estrelas
def stars_from_score(score: float) -> int:
    """0–1 → 1–5 estrelas (5 ★ a partir de 0,9)."""
    s = max(0.0, min(1.0, score))
    for limit, stars in ((0.9, 5), (0.7, 4), (0.5, 3), (0.3, 2)):
        if s >= limit:
            return stars
    return 1


def punctuality(elapsed_s: float, deadline_s: float) -> float:
    if elapsed_s <= deadline_s:
        return 1.0
    late = (elapsed_s - deadline_s) / deadline_s
    return max(0.0, 1.0 - 3.0 * late)        # 33 % de atraso → 0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------- fontes
SOURCE_NAMES = {
    Kind.FOOD: ("Tasca do {}", "Pizzaria {}", "Ramen {}", "Churrasqueira {}", "Bowl {}"),
    Kind.PARCEL: ("Correio {}", "Loja {}"),
    Kind.EXPRESS: ("Farmácia {}", "Florista {}"),
    Kind.CHASE: ("Esquadra {}",),
    Kind.FERRY: ("Fluvial {}",),
    Kind.TOUR: ("Passeios {}",),
}
FICTIONAL = ("Avelar", "Sol Nascente", "Marquês", "Gaivota", "Barbosa", "Estrela", "Cotovia",
             "Tágide", "Ninho", "Varanda", "Bairro", "Azulejo", "Farol", "Corvo")


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: Kind
    city: str
    zone: str


def _rng(*parts: object) -> random.Random:
    digest = hashlib.sha256(":".join(map(str, parts)).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def sources_for(city: str, zone: str, kinds: tuple[Kind, ...] = tuple(Kind), per_kind: int = 3) -> list[Source]:
    """Fontes fictícias de uma zona. Mesma semente → mesma cidade para todos."""
    out = []
    for kind in kinds:
        rng = _rng("sources", city, zone, kind.value)
        n = 1 if kind in (Kind.CHASE, Kind.FERRY, Kind.TOUR) else per_kind
        for i in range(n):
            tpl = rng.choice(SOURCE_NAMES[kind])
            out.append(Source(f"{city}.{zone}.{kind.value}.{i}", tpl.format(rng.choice(FICTIONAL)),
                              kind, city, zone))
    return out


# ---------------------------------------------------------------- pedidos
@dataclass
class Order:
    id: str
    source: Source
    kind: Kind
    route_m: float
    expected_s: float           # tempo à intensidade-alvo
    deadline_s: float
    intensity: float
    cargo_kg: float = 0.0
    canonical: bool = False     # entra nos rankings da fonte
    state: State = State.OFFERED
    accepted_at: float | None = None
    picked_at: float | None = None
    paused_s: float = 0.0
    hot_paused_s: float = 0.0
    finished_at: float | None = None
    stars: int | None = None
    detail: dict = field(default_factory=dict)

    @property
    def sport(self) -> Sport:
        return KIND_SPORT[self.kind]

    def elapsed(self, now: float) -> float:
        """Tempo de prazo gasto: desde a aceitação, sem as pausas."""
        if self.accepted_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else now
        return max(0.0, end - self.accepted_at - self.paused_s)


def expected_seconds(sport: Sport, route_m: float, profile_speed_mps: float) -> float:
    return route_m / max(profile_speed_mps, 0.1)


# ---------------------------------------------------------------- telemóvel
class BoardError(RuntimeError):
    pass


class OrderBoard:
    """O telemóvel de pedidos de UM jogador. Todo o estado é deste jogador.

    `speed_at(sport, intensity)` devolve a velocidade média (m/s) do atleta a
    essa fração do limiar: é o que torna os prazos pessoais.
    """

    def __init__(self, player_id: str, level: int, speed_at, robustness: float = 0.0,
                 max_cargo_kg: float = 2.0, movers: dict | None = None):
        self.player_id = player_id
        self.level = level
        self.diff = difficulty(level)
        self.speed_at = speed_at
        self.movers = movers or {}        # {Sport: Mover} para prazos com a altimetria real
        self.robustness = robustness
        self.max_cargo_kg = max_cargo_kg
        self.orders: dict[str, Order] = {}
        self.round = 0
        self.paused_since: float | None = None
        self.abandoned: list[Order] = []

    # ---- capacidade
    @property
    def slots(self) -> int:
        from .strength import extra_order_slots
        return self.diff.base_slots + extra_order_slots(self.robustness)

    def active(self) -> list[Order]:
        return [o for o in self.orders.values() if o.state in (State.ACCEPTED, State.PICKED_UP)]

    def offers(self) -> list[Order]:
        return [o for o in self.orders.values() if o.state is State.OFFERED]

    # ---- geração
    def make_order(self, source: Source, route_m: float | None = None, intensity: float | None = None,
                   cargo_kg: float = 0.0, canonical: bool = False, tag: str = "",
                   profile: list[tuple[float, float]] | None = None) -> Order:
        """Cria uma oferta. O prazo é o tempo a fazer o percurso a
        `intensity × (1 − margem)`: a folga está no esforço, não no relógio.

        Com `profile` (o percurso real, do GPS) e um `Mover` para o desporto, os
        tempos contam com cada rampa; sem ele, usa-se a velocidade em plano.
        """
        intensity = intensity or self.diff.intensity
        sport = KIND_SPORT[source.kind]
        lo_int = intensity * (1 - self.diff.margin)
        mover = self.movers.get(sport)
        if profile and mover is not None:
            from ..shared.movement import distance, time_for
            route_m = distance(profile)
            exp_s = time_for(mover, profile, intensity, cargo_kg)
            deadline = time_for(mover, profile, lo_int, cargo_kg)
        else:
            if route_m is None:
                raise ValueError("indica route_m ou profile")
            exp_s = expected_seconds(sport, route_m, self.speed_at(sport, intensity))
            deadline = expected_seconds(sport, route_m, self.speed_at(sport, lo_int))
        oid = f"{self.player_id}:{source.id}:{self.round}:{tag or len(self.orders)}"
        order = Order(oid, source, source.kind, route_m, round(exp_s, 1),
                      round(deadline, 1), intensity, cargo_kg, canonical)
        self.orders[oid] = order
        return order

    def refresh(self, sources: list[Source], n: int = 3) -> list[Order]:
        """Nova ronda de ofertas, determinística para este jogador e ronda."""
        self.round += 1
        for o in self.offers():
            del self.orders[o.id]
        rng = _rng("offers", self.player_id, self.round)
        ranges = {Sport.BIKE: (1500, 6000), Sport.RUN: (600, 2500), Sport.ROW: (800, 4000)}
        made = []
        for i, src in enumerate(rng.sample(sources, min(n, len(sources)))):
            lo, hi = ranges[KIND_SPORT[src.kind]]
            cargo = round(rng.uniform(0.5, 8.0), 1) if src.kind is Kind.PARCEL else 0.0
            made.append(self.make_order(src, round(rng.uniform(lo, hi), -1), cargo_kg=cargo, tag=str(i)))
        return made

    # ---- ciclo de vida
    def accept(self, oid: str, now: float) -> Order:
        o = self._get(oid, State.OFFERED)
        act = self.active()
        if len(act) >= self.slots:
            raise BoardError("sem espaço para mais pedidos neste nível")
        if act and act[0].sport is not o.sport:
            raise BoardError("pedidos simultâneos têm de ser da mesma modalidade")
        if o.cargo_kg + sum(a.cargo_kg for a in act) > self.max_cargo_kg:
            raise BoardError("carga acima do que a tua Robustez permite")
        o.state, o.accepted_at = State.ACCEPTED, now
        return o

    def pick_up(self, oid: str, now: float) -> Order:
        o = self._get(oid, State.ACCEPTED)
        o.state, o.picked_at = State.PICKED_UP, now
        o.hot_paused_s = 0.0
        return o

    def pause(self, now: float) -> None:
        if self.paused_since is None:
            self.paused_since = now

    def resume(self, now: float) -> None:
        if self.paused_since is None:
            return
        dt = now - self.paused_since
        for o in self.active():
            o.paused_s += dt
            if o.state is State.PICKED_UP:
                o.hot_paused_s += dt
        self.paused_since = None

    def carried_kg(self) -> float:
        return sum(o.cargo_kg for o in self.active() if o.state is State.PICKED_UP)

    def deliver(self, oid: str, now: float, *, smoothness: float | None = None,
                harsh_brakes: int = 0, caught: bool | None = None) -> Order:
        o = self._get(oid, State.PICKED_UP)
        o.finished_at = now
        o.state = State.DONE
        p = punctuality(o.elapsed(now), o.deadline_s)
        detail: dict = {"punctuality": round(p, 3)}
        if o.kind is Kind.FOOD:
            hot = now - o.picked_at - o.hot_paused_s
            temp = food_temperature(hot, o.hot_paused_s, self.diff.cooling)
            t_score = _clamp01((temp - COLD) / (HOT - COLD))
            detail["temperature_c"] = round(temp, 1)
            score = 0.5 * p + 0.5 * t_score
        elif o.kind in (Kind.PARCEL, Kind.EXPRESS):
            integrity = max(0.0, 1.0 - 0.1 * harsh_brakes)
            detail["integrity"] = integrity
            score = 0.6 * p + 0.4 * integrity
        elif o.kind is Kind.CHASE:
            detail["caught"] = bool(caught)
            score = (0.6 + 0.4 * p) if caught else 0.0
        else:  # FERRY / TOUR
            sm = smoothness if smoothness is not None else 0.0
            need = self.diff.smooth_min
            sm_score = _clamp01((sm - (need - 0.25)) / 0.25)
            detail["smoothness"] = round(sm, 3)
            w = 0.6 if o.kind is Kind.TOUR else 0.3     # passageiros notam mais
            score = (1 - w) * p + w * sm_score
        o.stars = stars_from_score(score)
        o.detail = detail
        return o

    def abandon(self, oid: str, now: float) -> dict:
        """Anula a missão. Penalização proporcional ao que já ia feito."""
        o = self.orders[oid]
        if o.state not in (State.ACCEPTED, State.PICKED_UP):
            raise BoardError("só se abandona uma missão em curso")
        o.state, o.finished_at = State.ABANDONED, now
        self.abandoned.append(o)
        progress = min(1.0, o.elapsed(now) / max(o.expected_s, 1.0))
        # Abandonar com a comida na mala é pior do que antes de a recolher.
        penalty = 0.5 + 0.5 * progress + (0.5 if o.picked_at is not None else 0.0)
        return {"order": o.id, "reputation_penalty": round(penalty, 2), "xp": 0}

    def _get(self, oid: str, state: State) -> Order:
        o = self.orders.get(oid)
        if o is None:
            raise BoardError(f"pedido desconhecido: {oid}")
        if o.state is not state:
            raise BoardError(f"pedido {oid} está em {o.state.value}, esperado {state.value}")
        return o

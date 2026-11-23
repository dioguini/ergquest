"""Recados *ad-hoc*: qualquer NPC pode pedir um favor ("moço dos recados").

Antes de aceitar, o atleta vê o **plano**: as paragens por ordem, distância,
subida, o que vai carregar em cada perna, o tempo estimado, o prazo, a
intensidade necessária para o cumprir e a carga (TSS) que vai custar. Ao
aceitar, assume o compromisso: tem de passar pelas paragens por ordem e
chegar dentro do prazo. Falhar não anula o esforço (a carga conta sempre),
mas não dá recompensa e custa reputação.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..shared.movement import Mover, Profile, ascent, distance, estimated_load, time_for
from .missions import _rng, difficulty, punctuality, stars_from_score

NPC_NAMES = ("Dona Amélia", "Sr. Joaquim", "Marta", "Tio Zé", "Inês", "Sr. Abílio", "Rosa", "Duarte")

# (pedido, [(paragem, kg recolhidos aí)]) — a última paragem é a casa do NPC.
TEMPLATES = (
    ("Vai-me buscar pão à padaria e traz-mo, se fazes favor.", [("Padaria", 1.0)]),
    ("Leva esta carta aos correios e passa na farmácia pelos meus remédios.",
     [("Correios", -0.3), ("Farmácia", 0.4)]),
    ("Preciso das compras do mercado — a lista está paga.", [("Mercado", 5.0)]),
    ("Leva estas chaves à minha filha e traz-me o guarda-chuva que lá deixei.",
     [("Casa da filha", 0.8)]),
    ("Vai ao alfaiate buscar o fato e depois ao sapateiro buscar os sapatos.",
     [("Alfaiate", 1.5), ("Sapateiro", 1.2)]),
)

ZONE_LABELS = ((0.55, "Z1 recuperação"), (0.75, "Z2 resistência"), (0.90, "Z3 tempo"),
               (1.05, "Z4 limiar"), (9.9, "Z5+ VO2máx"))


def zone_label(intensity: float) -> str:
    return next(label for lim, label in ZONE_LABELS if intensity < lim)


@dataclass(frozen=True)
class LegPlan:
    to: str
    distance_m: float
    ascent_m: float
    carrying_kg: float          # o que se leva durante esta perna
    est_s: float


@dataclass(frozen=True)
class ErrandOffer:
    id: str
    npc: str
    text: str
    stops: tuple[str, ...]
    legs: tuple[LegPlan, ...]
    profiles: tuple[tuple[tuple[float, float], ...], ...]
    est_s: float                # à intensidade habitual do nível
    deadline_s: float
    required_intensity: float   # para chegar exatamente no prazo
    est_load: float
    reward_xp: int

    @property
    def distance_m(self) -> float:
        return sum(l.distance_m for l in self.legs)

    @property
    def ascent_m(self) -> float:
        return sum(l.ascent_m for l in self.legs)

    def summary(self) -> str:
        lines = [f"{self.npc}: «{self.text}»"]
        for i, l in enumerate(self.legs, 1):
            kg = f" · a carregar {l.carrying_kg:.1f} kg" if l.carrying_kg else ""
            lines.append(f"  {i}. → {l.to:<14} {l.distance_m/1000:4.2f} km  +{l.ascent_m:3.0f} m{kg}")
        lines.append(f"  Total {self.distance_m/1000:.2f} km, +{self.ascent_m:.0f} m · prazo {self.deadline_s/60:.1f} min · "
                     f"precisa de {self.required_intensity:.0%} do limiar ({zone_label(self.required_intensity)}) · "
                     f"~{self.est_load:.0f} TSS · {self.reward_xp} XP")
        return "\n".join(lines)


def _random_profile(rng, length_m: float) -> Profile:
    out, done = [], 0.0
    while done < length_m:
        seg = min(rng.uniform(150, 450), length_m - done)
        out.append((round(seg), round(rng.choice((-5, -3, -1, 0, 1, 2, 3, 5, 7)) * rng.uniform(0.6, 1.0), 1)))
        done += seg
    return out


def make_offer(player_id: str, npc_seed: int, mover: Mover, level: int, route_for=None) -> ErrandOffer:
    """Um pedido de um NPC, já com o plano calculado para ESTE atleta.

    `route_for(perna, n_pernas) -> (nome do sítio, perfil)` dá o percurso real
    de cada perna (do GPS no mapa da cidade); sem ele, gera-se um plausível.
    """
    rng = _rng("errand", player_id, npc_seed)
    npc = rng.choice(NPC_NAMES)
    text, stops = rng.choice(TEMPLATES)
    diff = difficulty(level)
    names, profiles, legs = [], [], []
    carrying = 0.0
    route = [(f"{s} {rng.choice(('do Largo', 'da Esquina', 'Central', 'Nova'))}", kg) for s, kg in stops]
    route.append((f"Casa de {npc}", 0.0))
    for i, (name, kg) in enumerate(route):
        if route_for is not None:
            place, prof = route_for(i, len(route))
            if place and i < len(route) - 1:
                name = f"{name.split(' ')[0]} na {place}" if place.split(" ")[0] in ("Rua", "Calçada", "Travessa", "Praça", "Avenida") \
                    else f"{name.split(' ')[0]} no {place}"
        else:
            prof = _random_profile(rng, rng.uniform(600, 2000))
        est = time_for(mover, prof, diff.intensity, carrying)
        legs.append(LegPlan(name, distance(prof), ascent(prof), round(carrying, 1), est))
        profiles.append(tuple(prof))
        names.append(name)
        carrying = max(0.0, carrying + kg)
    est_s = sum(l.est_s for l in legs)
    deadline = sum(time_for(mover, list(pr), diff.intensity * (1 - diff.margin), l.carrying_kg)
                   for l, pr in zip(legs, profiles))
    # intensidade para cumprir o prazo, perna a perna com a carga de cada uma
    req = _required(mover, legs, profiles, deadline)
    load = estimated_load(deadline, req)
    return ErrandOffer(f"{player_id}:errand:{npc_seed}", npc, text, tuple(names), tuple(legs),
                       tuple(profiles), round(est_s, 1), round(deadline, 1), req, round(load, 1),
                       int(80 + load * 6))


def _required(mover: Mover, legs, profiles, seconds: float) -> float:
    lo, hi = 0.05, 3.0
    for _ in range(50):
        mid = (lo + hi) / 2
        t = sum(time_for(mover, list(p), mid, l.carrying_kg) for l, p in zip(legs, profiles))
        lo, hi = (mid, hi) if t > seconds else (lo, mid)
    return round((lo + hi) / 2, 3)


class ErrandError(RuntimeError):
    pass


@dataclass
class ErrandRun:
    """O compromisso depois de aceitar: paragens por ordem, dentro do prazo."""
    offer: ErrandOffer
    started_at: float
    visited: list[tuple[str, float]] = field(default_factory=list)
    result: dict | None = None

    @property
    def next_stop(self) -> str | None:
        n = len(self.visited)
        return self.offer.stops[n] if n < len(self.offer.stops) else None

    def arrive(self, stop: str, now: float) -> str | None:
        if self.result:
            raise ErrandError("recado já terminado")
        if stop != self.next_stop:
            raise ErrandError(f"a próxima paragem é {self.next_stop}, não {stop}")
        self.visited.append((stop, now))
        if self.next_stop is None:
            self._finish(now)
        return self.next_stop

    def _finish(self, now: float) -> None:
        elapsed = now - self.started_at
        on_time = elapsed <= self.offer.deadline_s
        p = punctuality(elapsed, self.offer.deadline_s)
        self.result = {
            "completed": on_time, "elapsed_s": round(elapsed, 1),
            "stars": stars_from_score(p) if on_time else 1,
            "xp": self.offer.reward_xp if on_time else 0,
            "reputation_penalty": 0.0 if on_time else 0.5,
        }

    def abandon(self, now: float) -> dict:
        if self.result:
            raise ErrandError("recado já terminado")
        self.result = {"completed": False, "elapsed_s": now - self.started_at, "stars": None,
                       "xp": 0, "reputation_penalty": 1.0}
        return self.result


def accept(offer: ErrandOffer, now: float) -> ErrandRun:
    return ErrandRun(offer, now)

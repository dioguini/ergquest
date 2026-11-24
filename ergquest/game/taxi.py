"""Táxi: levar NPCs. A física muda por completo.

De bicicleta conduz-se um **riquexó** (65 kg, mais arrasto, três rodas); no
rio, um **bote-táxi** a remos. O passageiro e a bagagem somam-se à massa:
uma rampa que sozinho se sobe a 15 km/h passa a 5 km/h. Antes de aceitar, o
atleta vê a cotação: peso a transportar, tempo sozinho vs. com passageiro,
intensidade necessária para o prazo e a carga que vai custar.

A avaliação inclui o **conforto** (solavancos: acelerações e travagens
bruscas) e a **segurança** (velocidade a descer com gente a bordo).

Só se conduz um táxi com nível e Robustez suficientes — é aqui que o
ginásio se nota.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..shared.movement import (PEDICAB, WATER_TAXI, Bike, Mover, Profile, Rower, Vehicle, ascent, distance,
                               estimated_load, intensity_for, steepest, time_for, watts_to_hold)
from ..shared.movement import WALK_MPS
from .errands import zone_label
from .missions import _rng, difficulty, punctuality, stars_from_score

LICENSES = {PEDICAB.id: (8, 0.30), WATER_TAXI.id: (12, 0.30)}   # (nível, Robustez)
JOLT_MPS2 = 1.2              # aceleração/travagem que o passageiro sente
SAFE_DESCENT_MPS = 8.5       # ~30 km/h a descer com passageiros
FIRST_NAMES = ("Carlos", "Beatriz", "Hiroshi", "Fatou", "Liam", "Sofia", "Rui", "Ingrid", "Omar")


@dataclass(frozen=True)
class Passenger:
    name: str
    weight_kg: float
    luggage_kg: float = 0.0

    @property
    def total_kg(self) -> float:
        return self.weight_kg + self.luggage_kg


def can_drive(vehicle: Vehicle, level: int, robustness: float) -> tuple[bool, str]:
    """Licença. `level` é o nível NA MODALIDADE do veículo: ciclismo para o
    riquexó, remo para o bote-táxi."""
    need_lvl, need_rob = LICENSES[vehicle.id]
    if level < need_lvl:
        return False, f"{vehicle.name}: precisa de nível {need_lvl}"
    if robustness < need_rob:
        return False, f"{vehicle.name}: precisa de Robustez {need_rob:.2f} (treina força no ginásio)"
    return True, "ok"


@dataclass(frozen=True)
class TaxiOffer:
    id: str
    vehicle: Vehicle
    passengers: tuple[Passenger, ...]
    destination: str
    profile: tuple[tuple[float, float], ...]
    solo_s: float               # o mesmo percurso sem ninguém, à intensidade do nível
    est_s: float                # com os passageiros, à mesma intensidade
    deadline_s: float
    required_intensity: float
    est_load: float
    fare: float
    steepest_pct: float = 0.0
    steepest_w: float | None = None   # watts para não ir mais devagar do que a pé (bicicleta)

    @property
    def extra_kg(self) -> float:
        return sum(p.total_kg for p in self.passengers)

    def summary(self) -> str:
        who = ", ".join(f"{p.name} ({p.weight_kg:.0f} kg + {p.luggage_kg:.0f} kg)" for p in self.passengers)
        prof = list(self.profile)
        return (f"🚕 {self.vehicle.name} → {self.destination}: {who}\n"
                f"   {distance(prof)/1000:.2f} km, +{ascent(prof):.0f} m · +{self.extra_kg:.0f} kg a bordo\n"
                f"   sozinho {self.solo_s/60:.1f} min · com eles {self.est_s/60:.1f} min · prazo {self.deadline_s/60:.1f} min\n"
                f"   precisa de {self.required_intensity:.0%} do limiar ({zone_label(self.required_intensity)}) · "
                f"~{self.est_load:.0f} TSS · tarifa {self.fare:.2f} ¤"
                + (f"\n   rampa mais dura ({self.steepest_pct:.0f} %): ≥ {self.steepest_w:.0f} W para não ir "
                   f"mais devagar do que a pé" if self.steepest_w else ""))


def make_offer(player_id: str, seed: int, mover: Mover, level: int, destination: str = "Castelo",
               profile: Profile | None = None) -> TaxiOffer:
    """Cotação para ESTE atleta. `profile` é o percurso real até ao destino (do grafo
    da cidade); sem ele gera-se um percurso urbano plausível."""
    rng = _rng("taxi", player_id, seed)
    vehicle = mover.vehicle
    if vehicle.seats == 0:
        raise ValueError("este veículo não leva passageiros")
    n = rng.randint(1, vehicle.seats)
    pax = tuple(Passenger(rng.choice(FIRST_NAMES), round(rng.uniform(45, 105)), round(rng.choice((0, 0, 5, 12, 20))))
                for _ in range(n))
    extra = sum(p.total_kg for p in pax)
    if profile is not None:
        prof: Profile = list(profile)
    elif isinstance(mover, Rower):
        prof = [(round(rng.uniform(1200, 3000)), 0.0)]
    else:
        prof = [(round(rng.uniform(200, 500)), round(rng.uniform(-4, 6), 1)) for _ in range(rng.randint(4, 8))]
    diff = difficulty(level)
    solo = time_for(mover, prof, diff.intensity)
    est = time_for(mover, prof, diff.intensity, extra)
    deadline = time_for(mover, prof, diff.intensity * (1 - diff.margin), extra)
    req = intensity_for(mover, prof, deadline, extra)
    fare = round(2.0 + distance(prof) / 1000 * 1.2 + ascent(prof) * 0.05 + extra * 0.02, 2)
    return TaxiOffer(f"{player_id}:taxi:{seed}", vehicle, pax, destination, tuple(prof), round(solo, 1),
                     round(est, 1), round(deadline, 1), req, round(estimated_load(deadline, req), 1), fare,
                     *_steepest(mover, prof, extra))


def _steepest(mover: Mover, prof: Profile, extra: float) -> tuple[float, float | None]:
    g = round(steepest(prof), 1)
    if not isinstance(mover, Bike) or g <= 0:
        return g, None
    return g, round(watts_to_hold(mover, g, WALK_MPS, extra))


@dataclass
class TaxiRide:
    offer: TaxiOffer
    started_at: float
    jolts: int = 0
    overspeed_s: float = 0.0
    crawl_s: float = 0.0            # tempo mais devagar do que a pé
    _last_v: float | None = None
    result: dict | None = field(default=None)

    def observe(self, dt: float, speed_mps: float, grade_pct: float) -> None:
        """Chamado a cada amostra: mede conforto e segurança."""
        if self._last_v is not None and dt > 0 and abs(speed_mps - self._last_v) / dt > JOLT_MPS2:
            self.jolts += 1
        if grade_pct < -1 and speed_mps > SAFE_DESCENT_MPS:
            self.overspeed_s += dt
        if speed_mps < WALK_MPS and self._last_v is not None:
            self.crawl_s += dt
        self._last_v = speed_mps

    def finish(self, now: float) -> dict:
        elapsed = now - self.started_at
        p = punctuality(elapsed, self.offer.deadline_s)
        # solavancos e a lentidão de quem "ia mais depressa a pé"
        comfort = max(0.0, 1.0 - 0.1 * self.jolts - self.crawl_s / 180.0)
        safety = max(0.0, 1.0 - self.overspeed_s / 30.0)
        stars = stars_from_score(0.5 * p + 0.3 * comfort + 0.2 * safety)
        tip = {5: 0.25, 4: 0.10}.get(stars, 0.0)
        self.result = {"stars": stars, "elapsed_s": round(elapsed, 1), "punctuality": round(p, 3),
                       "crawl_s": round(self.crawl_s),
                       "comfort": round(comfort, 2), "safety": round(safety, 2),
                       "earned": round(self.offer.fare * (1 + tip) * (1 if p > 0 else 0.3), 2)}
        return self.result


def accept(offer: TaxiOffer, now: float, level: int, robustness: float) -> TaxiRide:
    ok, why = can_drive(offer.vehicle, level, robustness)
    if not ok:
        raise PermissionError(why)
    return TaxiRide(offer, now)

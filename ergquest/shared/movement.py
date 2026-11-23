"""Como cada desporto transforma esforço em movimento, com a carga que leva.

Um mesmo interface para bicicleta, corrida e remo, usado pelo treino (que
caminho encaixa no próximo bloco?), pelos recados (quanto tempo demora?) e
pelo táxi (que esforço exige levar um passageiro de 90 kg ao Castelo?).

`Profile` = [(comprimento_m, declive_%)].
"""
from __future__ import annotations

from dataclasses import dataclass

from . import physics
from .load import grade_factor

Profile = list[tuple[float, float]]


@dataclass(frozen=True)
class Vehicle:
    id: str
    name: str
    mass_kg: float
    cda: float = physics.DEFAULT_CDA        # bicicleta: área frontal × coef. de arrasto
    crr: float = physics.DEFAULT_CRR        # bicicleta: resistência ao rolamento
    hull: float = 1.0                       # remo: arrasto do casco face a um single
    seats: int = 0                          # lugares para passageiros
    min_v: float = 1.0                      # piso numérico da física (mais baixo em veículos pesados)


ROAD_BIKE = Vehicle("road_bike", "Bicicleta de estrada", 9.0)
CARGO_BIKE = Vehicle("cargo_bike", "Bicicleta de carga", 28.0, cda=0.45, crr=0.006, min_v=0.5)
PEDICAB = Vehicle("pedicab", "Riquexó", 65.0, cda=0.80, crr=0.009, seats=2, min_v=0.3)
SINGLE_SCULL = Vehicle("single", "Barco individual", 14.0)
WATER_TAXI = Vehicle("water_taxi", "Bote-táxi a remos", 110.0, hull=2.2, seats=4)

ROW_K = 2.8             # Concept2: P = 2,8 · v³ para um single com ~90 kg
ROW_REF_MASS = 90.0


@dataclass(frozen=True)
class Bike:
    weight_kg: float
    ftp_w: float
    vehicle: Vehicle = ROAD_BIKE

    def speed(self, watts: float, grade_pct: float, extra_kg: float = 0.0) -> float:
        m = self.weight_kg + self.vehicle.mass_kg + extra_kg
        return physics.speed_from_power(m, self.vehicle.cda, self.vehicle.crr, watts, grade_pct / 100.0)

    def speed_at(self, intensity: float, grade_pct: float, extra_kg: float = 0.0) -> float:
        return self.speed(self.ftp_w * intensity, grade_pct, extra_kg)


@dataclass(frozen=True)
class Runner:
    weight_kg: float
    threshold_mps: float

    def speed_at(self, intensity: float, grade_pct: float, extra_kg: float = 0.0) -> float:
        # carregar peso custa na proporção da massa; subir custa pelo fator de Minetti
        load = self.weight_kg / (self.weight_kg + extra_kg)
        return self.threshold_mps * intensity * load / grade_factor(grade_pct)


@dataclass(frozen=True)
class Rower:
    weight_kg: float
    ftp_w: float
    vehicle: Vehicle = SINGLE_SCULL

    def speed_at(self, intensity: float, grade_pct: float = 0.0, extra_kg: float = 0.0) -> float:
        mass = self.weight_kg + self.vehicle.mass_kg + extra_kg
        k = ROW_K * self.vehicle.hull * (mass / ROW_REF_MASS) ** (2 / 3)   # arrasto ∝ área molhada
        return (self.ftp_w * intensity / k) ** (1 / 3)


Mover = Bike | Runner | Rower


def time_for(mover: Mover, profile: Profile, intensity: float, extra_kg: float = 0.0) -> float:
    """Segundos para fazer o perfil a uma intensidade constante (fração do limiar)."""
    return sum(length / max(mover.speed_at(intensity, g, extra_kg), 0.1) for length, g in profile)


def intensity_for(mover: Mover, profile: Profile, seconds: float, extra_kg: float = 0.0) -> float:
    """Intensidade constante necessária para fazer o perfil em `seconds` (bissecção)."""
    lo, hi = 0.05, 3.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if time_for(mover, profile, mid, extra_kg) > seconds:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


WALK_MPS = 1.4    # ~5 km/h: abaixo disto, os passageiros iam mais depressa a pé


def watts_to_hold(bike: Bike, grade_pct: float, speed_mps: float, extra_kg: float = 0.0) -> float:
    """Watts para manter `speed_mps` num declive, com a carga a bordo."""
    veh = bike.vehicle
    return physics.power_required(bike.weight_kg + veh.mass_kg + extra_kg, veh.cda, veh.crr,
                                  speed_mps, grade_pct / 100.0)


def steepest(profile: Profile, window_m: float = 40.0) -> float:
    """A rampa mais dura do perfil, em média móvel de `window_m` (o que se sente).

    Um pico de 10 m no modelo de terreno não é uma rampa: como no rolo, conta
    a média ao longo de alguns metros.
    """
    best, segs = 0.0, list(profile)
    for i in range(len(segs)):
        acc = rise = 0.0
        for length, g in segs[i:]:
            take = min(length, window_m - acc)
            acc += take
            rise += take * g / 100.0
            if acc >= window_m:
                break
        if acc > 0:
            best = max(best, rise / acc * 100.0)
    return best


def distance(profile: Profile) -> float:
    return sum(length for length, _ in profile)


def ascent(profile: Profile) -> float:
    return sum(length * g / 100.0 for length, g in profile if g > 0)


def estimated_load(seconds: float, intensity: float) -> float:
    """TSS aproximada de um esforço constante: h · IF² · 100."""
    return seconds / 3600.0 * intensity ** 2 * 100.0

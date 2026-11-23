"""Física da bicicleta: potência ↔ velocidade num declive.

Cliente e servidor usam este mesmo código, por isso calculam exatamente a
mesma velocidade a partir dos mesmos watts. É isto que torna o e-sport justo: no mundo, só a
física decide.
"""
from __future__ import annotations

import math

G = 9.80665
RHO = 1.225           # densidade do ar ao nível do mar, 15 °C
MAX_SPEED_MPS = 30.0  # 108 km/h: travão de segurança numérica
MIN_TRAINER_GRADE = -5.0
MAX_TRAINER_GRADE = 25.0

# Valores por omissão de uma bicicleta de estrada com o ciclista nas manetes.
DEFAULT_CDA = 0.32
DEFAULT_CRR = 0.004
BIKE_KG = 9.0


def power_required(mass_kg: float, cda: float, crr: float, v: float, grade: float) -> float:
    """Potência (W) para manter `v` m/s num declive `grade` (fração)."""
    theta = math.atan(grade)
    f_grav = mass_kg * G * math.sin(theta)
    f_roll = mass_kg * G * crr * math.cos(theta)
    f_aero = 0.5 * RHO * cda * v * v
    return (f_grav + f_roll + f_aero) * v


def step_velocity(mass_kg: float, cda: float, crr: float, v: float, watts: float,
                  grade: float, dt: float, min_v: float = 1.0) -> float:
    """Integra um passo de `dt` segundos e devolve a nova velocidade.

    v_eff tem um mínimo (1 m/s por omissão) para evitar a força
    infinita no arranque. Com cargas pesadas (riquexó com passageiros) esse
    mínimo faz parar em rampas que na realidade se sobem devagar: aí usa-se
    `min_v` mais baixo.
    """
    v_eff = max(v, min_v)
    f_drive = watts / v_eff
    f_resist = power_required(mass_kg, cda, crr, v_eff, grade) / v_eff
    a = (f_drive - f_resist) / mass_kg
    return min(max(v + a * dt, 0.0), MAX_SPEED_MPS)


def trainer_grade(route_grade_pct: float, difficulty: float = 1.0, extra_pct: float = 0.0) -> float:
    """Declive a enviar ao rolo (a velocidade no mundo usa sempre o declive real)."""
    g = route_grade_pct * difficulty + extra_pct
    return min(max(g, MIN_TRAINER_GRADE), MAX_TRAINER_GRADE)


def speed_from_power(mass_kg: float, cda: float, crr: float, watts: float,
                     grade: float, tol: float = 0.01) -> float:
    """Velocidade de equilíbrio para uma potência constante (bissecção)."""
    if watts <= 0:
        return 0.0
    lo, hi = 0.0, MAX_SPEED_MPS
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if power_required(mass_kg, cda, crr, mid, grade) < watts:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2.0

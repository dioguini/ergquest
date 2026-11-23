"""Como se faz um treino: ERG ligado/desligado × no mundo/só no ecrã.

| ERG | Onde | Quem manda na resistência | O que o atleta faz |
| :-- | :-- | :-- | :-- |
| ligado | ecrã | o rolo (watts-alvo) | pedala; vê só o treino no ecrã |
| ligado | mundo | o rolo (watts-alvo) | pedala; o avatar anda pela física com o declive real, mas o declive não se sente; escolhe os caminhos |
| desligado | mundo | a estrada (declive enviado ao rolo) | entra na estrada, escolhe os caminhos e cumpre o alvo com as mudanças, como lá fora |
| desligado | ecrã | o atleta (rolo em plano) | cumpre o alvo com as mudanças, vendo só o treino |

No mundo, o GPS não impõe percurso: em cada interseção o atleta escolhe
(setas). Com ERG desligado o terreno importa — uma rampa de 10 % num bloco
de recuperação, ou uma descida num bloco de limiar, tornam o alvo difícil de
cumprir — por isso o jogo **sugere** o ramo que melhor encaixa nos próximos
blocos (`rank_branches`), sem obrigar.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..shared import physics
from ..shared.movement import Bike, Profile


class Venue(str, Enum):
    WORLD = "world"
    SCREEN = "screen"


@dataclass(frozen=True)
class TrainingSetup:
    erg: bool
    venue: Venue
    difficulty: float = 1.0          # "sensação de declive" (só com ERG desligado no mundo)

    @property
    def in_world(self) -> bool:
        return self.venue is Venue.WORLD

    @property
    def athlete_controls_power(self) -> bool:
        return not self.erg


@dataclass(frozen=True)
class TrainerCommand:
    mode: str                         # "erg" | "sim"
    target_w: int | None = None
    grade_pct: float | None = None


def trainer_command(setup: TrainingSetup, target_w: int | None, route_grade_pct: float = 0.0) -> TrainerCommand:
    """O que enviar ao rolo neste segundo.

    Num passo livre (sem alvo) o ERG não tem o que impor: passa a simulação.
    """
    if setup.erg and target_w:
        return TrainerCommand("erg", target_w=int(target_w))
    if setup.in_world:
        return TrainerCommand("sim", grade_pct=physics.trainer_grade(route_grade_pct, setup.difficulty))
    return TrainerCommand("sim", grade_pct=0.0)


# --------------------------------------------------------------- caminhos
COMFORT_MIN_MPS = 3.0     # abaixo de ~11 km/h é difícil manter watts baixos e a cadência
COMFORT_MAX_MPS = 15.0    # acima de ~54 km/h as mudanças acabam: não se consegue pôr watts


@dataclass(frozen=True)
class Branch:
    name: str
    profile: Profile


def _fit(bike: Bike, profile: Profile, seconds: float, fraction: float | None) -> tuple[float, float]:
    """(segundos confortáveis, segundos percorridos) a fazer o alvo neste perfil."""
    frac = fraction if fraction is not None else 0.6
    watts = bike.ftp_w * frac
    good = t = 0.0
    i = 0
    while t < seconds and profile:
        length, g = profile[i % len(profile)]
        v = bike.speed(watts, g)
        dt = min(length / max(v, 0.1), seconds - t)
        if COMFORT_MIN_MPS <= v <= COMFORT_MAX_MPS:
            good += dt
        t += dt
        i += 1
    return good, t


def rank_branches(bike: Bike, branches: list[Branch],
                  upcoming: list[tuple[float, float | None]]) -> list[tuple[str, float]]:
    """Ordena os ramos pela fração do tempo em que o alvo é cumprível com conforto.

    `upcoming` = [(segundos, fração da FTP)] dos próximos blocos. Assume-se que
    o ramo continua com o mesmo perfil enquanto durar o horizonte.
    """
    scored = []
    for br in branches:
        good = total = 0.0
        offset = 0.0
        for seconds, frac in upcoming:
            g, t = _fit(bike, _rotate(br.profile, bike, offset, frac), seconds, frac)
            good += g
            total += t
            offset += seconds
        scored.append((br.name, round(good / total, 3) if total else 0.0))
    return sorted(scored, key=lambda x: -x[1])


def _rotate(profile: Profile, bike: Bike, seconds_in: float, frac: float | None) -> Profile:
    """O perfil a partir do ponto onde se estará daqui a `seconds_in` segundos."""
    if seconds_in <= 0 or not profile:
        return profile
    watts = bike.ftp_w * (frac or 0.6)
    t, i = 0.0, 0
    while True:
        length, g = profile[i % len(profile)]
        dt = length / max(bike.speed(watts, g), 0.1)
        if t + dt > seconds_in:
            n = i % len(profile)
            return profile[n:] + profile[:n]
        t += dt
        i += 1

"""Desafios instantâneos ("no momento") entre jogadores.

Regras do conceito:
* só entre jogadores que NÃO estejam em missão nem em treino estruturado;
* qualquer nível desafia qualquer nível (o nível não dá velocidade);
* quem é desafiado para uma cidade que não desbloqueou **pode viajar e
  competir**, mas não pode **propor** desafios nessa cidade até a desbloquear.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum

from .progression import Profile
from .session import Mode, PlayerState
from .cities import CITIES, Sport

BUSY_MODES = {Mode.MISSION, Mode.TRAINING, Mode.CHALLENGE}


class Format(str, Enum):
    SEGMENT = "segment"            # segmento/rota predefinida
    FREE = "free"                  # partida, trajeto e meta desenhados no mapa
    CRIT_OUTDOOR = "crit_outdoor"
    CRIT_INDOOR = "crit_indoor"
    VELODROME = "velodrome"


TRACK_EVENTS = ("sprint", "keirin", "kilo", "individual_pursuit", "team_pursuit",
                "scratch", "points_race", "elimination", "madison", "omnium")

MIN_FREE_ROUTE_M = 400.0


class ChallengeError(RuntimeError):
    pass


@dataclass
class Challenge:
    id: int
    challenger: str
    city: str
    fmt: Format
    sport: Sport
    venue: str | None = None
    event: str | None = None
    waypoints: list[tuple[float, float]] = field(default_factory=list)
    opponents: list[str] = field(default_factory=list)
    traveling: set[str] = field(default_factory=set)   # quem veio de fora


_ids = itertools.count(1)


def is_available(state: PlayerState) -> bool:
    return state.current is None or state.current.ended_at is not None or state.current.mode not in BUSY_MODES


def _route_len(wps: list[tuple[float, float]]) -> float:
    return sum(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 for (x1, y1), (x2, y2) in zip(wps, wps[1:]))


def propose(profile: Profile, state: PlayerState, city: str, fmt: Format, sport: Sport = Sport.BIKE,
            venue: str | None = None, event: str | None = None,
            waypoints: list[tuple[float, float]] | None = None) -> Challenge:
    if not is_available(state):
        raise ChallengeError("não podes desafiar durante uma missão ou treino estruturado")
    if not profile.city_unlocked(city):
        raise ChallengeError("só propões desafios em cidades que já desbloqueaste")
    c = CITIES[city]
    if fmt in (Format.CRIT_OUTDOOR, Format.CRIT_INDOOR, Format.VELODROME):
        v = next((v for v in c.venues if v.id == venue), None)
        if v is None or v.kind != fmt.value:
            raise ChallengeError(f"local inválido para {fmt.value} em {c.name}")
        if fmt is Format.VELODROME and event not in TRACK_EVENTS:
            raise ChallengeError("escolhe uma prova oficial de pista")
        if sport is not Sport.BIKE:
            raise ChallengeError("crits e velódromo são de ciclismo")
    if fmt is Format.FREE:
        if not waypoints or len(waypoints) < 2 or _route_len(waypoints) < MIN_FREE_ROUTE_M:
            raise ChallengeError(f"desenha partida e meta com pelo menos {MIN_FREE_ROUTE_M:.0f} m")
    return Challenge(next(_ids), profile.player_id, city, fmt, sport, venue, event, list(waypoints or []))


def join(ch: Challenge, profile: Profile, state: PlayerState) -> Challenge:
    """Aceitar: qualquer nível, qualquer cidade (viaja-se se preciso)."""
    if profile.player_id == ch.challenger:
        raise ChallengeError("não te podes desafiar a ti próprio")
    if not is_available(state):
        raise ChallengeError("o jogador está ocupado")
    if not profile.city_unlocked(ch.city):
        ch.traveling.add(profile.player_id)
    ch.opponents.append(profile.player_id)
    return ch

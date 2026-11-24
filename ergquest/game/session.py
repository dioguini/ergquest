"""Estado da sessão de um jogador.

Três maneiras de usar o ErgQuest, todas com o mesmo perfil e todas com
efeito colateral na forma real (a carga entra sempre no CTL/ATL/TSB):

* **TRAINING** — cumprir um treino estruturado, com ERG ligado ou
  desligado, no mundo ou só no ecrã (ver `ergquest.training.setup`).
* **MISSION** — o "mood" de jogar: entregas, polícia, passeios de barco,
  recados de NPCs, táxi. Dá estrelas, XP e desbloqueios.
* **FREE** — andar no mundo sem compromisso (conta para a carga e o XP).

Uma sessão = um desporto = um `.fit`.

Ao começar, e a cada troca de desporto, verifica-se:
1. se há aparelhos compatíveis ligados (rolo, passadeira, remo; banda
   cardíaca se o atleta a exigir) — `devices.hub.check`;
2. se o sítio onde se está pertence a uma zona aberta NESSE desporto: o mapa
   muda com a troca (terra para ciclismo/corrida, rio para remo) e cada
   desporto tem o seu nível. Trocar de desporto num ponto de troca
fecha a sessão atual (a bicicleta fica guardada nesse ponto) e abre a
seguinte depois de uma transição física (o atleta muda de máquina).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..training.setup import TrainingSetup
from .cities import CITIES, Sport, can_start_rowing, can_swap_at_street


class Mode(str, Enum):
    FREE = "free"                  # Free Ride/Run/Row: conta para a progressão
    MISSION = "mission"            # modo jogo com um trabalho em curso (entrega, recado, táxi…)
    TRAINING = "training"          # treino estruturado em curso
    CHALLENGE = "challenge"        # desafio PvP em curso


class SessionError(RuntimeError):
    pass


@dataclass
class Session:
    player_id: str
    sport: Sport
    city: str
    zone: str
    mode: Mode = Mode.FREE
    started_at: float = 0.0
    ended_at: float | None = None
    distance_m: float = 0.0
    paused: bool = False
    training: TrainingSetup | None = None

    @property
    def in_world(self) -> bool:
        return self.training is None or self.training.in_world


@dataclass
class PlayerState:
    player_id: str
    city: str
    zone: str
    sport: Sport = Sport.BIKE
    at_dock: bool = False
    parked_bike: tuple[str, str] | None = None        # (cidade, zona) onde ficou a bicicleta
    current: Session | None = None
    history: list[Session] = field(default_factory=list)
    devices_check: object | None = None                # resultado da última verificação de aparelhos

    @property
    def world_map(self) -> str:
        """O mapa em uso: "terra" (ciclismo e corrida) ou "rio" (remo)."""
        return "rio" if self.sport is Sport.ROW else "terra"

    def map_zone(self, sport: Sport | None = None) -> str:
        """A zona do sítio atual no mapa desse desporto (no rio: a zona do Tejo junto à doca)."""
        from ..world import metro
        sport = sport or self.sport
        return metro.LAND_TO_ROW.get(self.zone, self.zone) if sport is Sport.ROW else self.zone

    def _ready(self, sport: Sport, devices, profile, hr_required: bool) -> None:
        if devices is not None:
            from ..devices.hub import check
            chk = check(sport.value, devices, hr_required)
            if not chk.ok:
                from ..devices.hub import SPORT_NAMES
                raise SessionError(f"sem aparelho para {SPORT_NAMES[sport.value]}: liga {chk.missing_text()}")
            self.devices_check = chk
        if profile is not None and self.city == "lisboa":
            from ..world import metro
            zone = self.map_zone(sport)
            acc = profile.access(sport.value)
            known = zone in metro.ZONE or zone in metro.ROW_ZONE
            if known and zone not in acc.zones:
                z = metro.any_zone(zone)
                raise SessionError(f"a zona {z.name} ainda está fechada para {sport.value} "
                                   f"(nível {profile.level_in(sport.value)}; abre no {z.level})")

    def start(self, sport: Sport, now: float, mode: Mode = Mode.FREE,
              training: TrainingSetup | None = None, devices=None, profile=None,
              hr_required: bool = False) -> Session:
        if not sport.in_world:
            raise SessionError("o ginásio regista-se fora do mundo")
        if (mode is Mode.TRAINING) != (training is not None):
            raise SessionError("um treino precisa da configuração ERG/mundo, e só um treino a tem")
        in_world = training is None or training.in_world
        if in_world and sport is Sport.ROW and not can_start_rowing(CITIES[self.city], self.zone, self.at_dock):
            raise SessionError("no mundo, o remo começa numa doca, junto ao rio")
        if self.current and self.current.ended_at is None:
            raise SessionError("já há uma sessão aberta")
        if in_world:
            self._ready(sport, devices, profile, hr_required)
        elif devices is not None:
            self._ready(sport, devices, None, hr_required)
        self.sport = sport
        self.current = Session(self.player_id, sport, self.city, self.zone, mode, now, training=training)
        return self.current

    def end(self, now: float) -> Session:
        s = self.current
        if s is None or s.ended_at is not None:
            raise SessionError("não há sessão aberta")
        s.ended_at = now
        self.history.append(s)
        return s

    def swap(self, target: Sport, now: float, active_missions: int = 0, devices=None, profile=None,
             hr_required: bool = False) -> tuple[Session, Session]:
        """Ponto de troca: verifica aparelhos e zona, fecha a sessão, guarda a bicicleta, abre a nova.

        Com `devices`/`profile`, a troca só acontece se houver aparelho para o
        novo desporto e se o sítio estiver numa zona aberta para ele. O mapa
        passa a ser o do novo desporto (`world_map`).
        """
        if self.current is None:
            raise SessionError("não há sessão aberta")
        if active_missions:
            raise SessionError("termina ou abandona os pedidos antes de trocar de desporto")
        cur = self.current.sport
        if target is Sport.ROW:
            if not self.at_dock:
                raise SessionError("o remo começa numa doca")
        elif cur is not Sport.ROW and not can_swap_at_street(cur, target):
            raise SessionError(f"troca {cur.value}→{target.value} não é possível na rua")
        self._ready(target, devices, profile, hr_required)          # antes de fechar a sessão atual
        old = self.end(now)
        if cur is Sport.BIKE:
            self.parked_bike = (self.city, self.zone)
        return old, self.start(target, now, devices=devices, profile=profile, hr_required=hr_required)

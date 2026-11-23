"""Estado da sessão de um jogador.

Três maneiras de usar o ErgQuest, todas com o mesmo perfil e todas com
efeito colateral na forma real (a carga entra sempre no CTL/ATL/TSB):

* **TRAINING** — cumprir um treino estruturado, com ERG ligado ou
  desligado, no mundo ou só no ecrã (ver `ergquest.training.setup`).
* **MISSION** — o "mood" de jogar: entregas, polícia, passeios de barco,
  recados de NPCs, táxi. Dá estrelas, XP e desbloqueios.
* **FREE** — andar no mundo sem compromisso (conta para a carga e o XP).

Uma sessão = um desporto = um `.fit`. Trocar de desporto num ponto de troca
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

    def start(self, sport: Sport, now: float, mode: Mode = Mode.FREE,
              training: TrainingSetup | None = None) -> Session:
        if not sport.in_world:
            raise SessionError("o ginásio regista-se fora do mundo")
        if (mode is Mode.TRAINING) != (training is not None):
            raise SessionError("um treino precisa da configuração ERG/mundo, e só um treino a tem")
        in_world = training is None or training.in_world
        if in_world and sport is Sport.ROW and not can_start_rowing(CITIES[self.city], self.zone, self.at_dock):
            raise SessionError("no mundo, o remo começa numa doca, junto ao rio")
        if self.current and self.current.ended_at is None:
            raise SessionError("já há uma sessão aberta")
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

    def swap(self, target: Sport, now: float, active_missions: int = 0) -> tuple[Session, Session]:
        """Ponto de troca: fecha a sessão, guarda a bicicleta, abre a nova."""
        if self.current is None:
            raise SessionError("não há sessão aberta")
        if active_missions:
            raise SessionError("termina ou abandona os pedidos antes de trocar de desporto")
        cur = self.current.sport
        if target is Sport.ROW:
            if not self.at_dock:
                raise SessionError("o remo começa numa doca")
        elif not can_swap_at_street(cur, target):
            raise SessionError(f"troca {cur.value}→{target.value} não é possível na rua")
        old = self.end(now)
        if cur is Sport.BIKE:
            self.parked_bike = (self.city, self.zone)
        return old, self.start(target, now)

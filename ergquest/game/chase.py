"""Perseguição policial (corrida): apanhar o ladrão em fuga.

O ladrão corre a uma fração da velocidade de limiar do atleta e faz
arrancadas. Numa passadeira quem muda a velocidade é o atleta, por isso
cada arrancada é **anunciada com antecedência** (`WARN_S`) para dar tempo
de carregar no "+". É um treino de sprints repetidos disfarçado.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

CATCH_M = 2.0
ESCAPE_M = 250.0
WARN_S = 5.0


@dataclass
class Chase:
    threshold_mps: float
    level: int = 1
    head_start_m: float = 60.0
    time_limit_s: float = 300.0
    seed: int = 0
    t: float = 0.0
    gap_m: float = field(init=False)
    _rng: random.Random = field(init=False, repr=False)
    _next_burst: float = field(init=False)
    _burst_end: float = -1.0
    _warned: bool = False
    outcome: str | None = None        # "caught" | "escaped" | "timeout"

    def __post_init__(self) -> None:
        self.gap_m = self.head_start_m
        self._rng = random.Random(self.seed)
        self._next_burst = self._rng.uniform(20, 40)

    @property
    def cruise_mps(self) -> float:
        # nível 1: 80 % do limiar; nível 40: 95 %
        return self.threshold_mps * (0.80 + 0.15 * min(self.level - 1, 39) / 39)

    @property
    def burst_mps(self) -> float:
        return self.threshold_mps * 1.25

    def thief_speed(self) -> float:
        return self.burst_mps if self.t < self._burst_end else self.cruise_mps

    def step(self, dt: float, runner_mps: float) -> list[str]:
        """Avança `dt` s. Devolve eventos para o HUD."""
        if self.outcome:
            return []
        events = []
        self.t += dt
        if not self._warned and self.t >= self._next_burst - WARN_S:
            events.append("sprint_warning")
            self._warned = True
        if self.t >= self._next_burst:
            self._burst_end = self.t + self._rng.uniform(12, 20)
            self._next_burst = self._burst_end + self._rng.uniform(25, 45)
            self._warned = False
            events.append("sprint")
        self.gap_m += (self.thief_speed() - runner_mps) * dt
        if self.gap_m <= CATCH_M:
            self.outcome = "caught"
        elif self.gap_m >= ESCAPE_M:
            self.outcome = "escaped"
        elif self.t >= self.time_limit_s:
            self.outcome = "timeout"
        if self.outcome:
            events.append(self.outcome)
        return events

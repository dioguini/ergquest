"""Adaptadores para aparelhos que não falam FTMS / FE-C, ou que nem comunicam.

Cada adaptador devolve a mesma `Reading` normalizada que o resto do jogo usa,
e diz se os dados são **estimados** (`estimated=True`): nesse caso a sessão
conta para o treino, o XP e os desbloqueios, mas fica fora de rankings e
desafios PvP (o anti-cheat não consegue garantir justiça).

* `ManualTreadmill` — passadeira sem ligação: o atleta indica no ERGQuest a
  velocidade e a inclinação que pôs na passadeira; o jogo avisa quando mudar.
* `RowerPowerEstimator` — remo sem medidor de potência: estima watts a
  partir do ritmo, das calorias ou da cadência × resistência, com calibração.
* `DomyosRower` — remos Domyos com protocolo Bluetooth próprio. O protocolo
  não é público: o banco de testes (`ergquest.bench`) grava as notificações
  para o descodificar; até lá o adaptador regista e estima o que puder.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ble import Reading
from .hub import Device, Kind

# ---------------------------------------------------------------- passadeira manual
MANUAL_TREADMILL = Device("manual-treadmill", "Passadeira manual", Kind.TREADMILL, "manual",
                          controllable=False, estimated=True)


@dataclass
class ManualTreadmill:
    """Velocidade e inclinação indicadas pelo atleta; distância integrada pelo tempo."""
    speed_kmh: float = 0.0
    incline_pct: float = 0.0
    distance_m: float = 0.0
    max_kmh: float = 22.0
    _t: float | None = None
    prompt: str | None = None                  # o que o jogo pede ("sobe para 14 km/h")
    device: Device = MANUAL_TREADMILL

    def set(self, speed_kmh: float | None = None, incline_pct: float | None = None, now: float | None = None) -> None:
        if now is not None:
            self.tick(now)
        if speed_kmh is not None:
            self.speed_kmh = round(min(max(speed_kmh, 0.0), self.max_kmh), 1)
        if incline_pct is not None:
            self.incline_pct = round(min(max(incline_pct, -3.0), 15.0), 1)
        if self.prompt and speed_kmh is not None:
            self.prompt = None

    def nudge(self, d_speed: float = 0.0, d_incline: float = 0.0, now: float | None = None) -> None:
        """Teclas: ↑/↓ velocidade (±0,5 km/h), ←/→ inclinação (±0,5 %)."""
        self.set(self.speed_kmh + d_speed, self.incline_pct + d_incline, now)

    def ask(self, speed_kmh: float) -> str:
        """O jogo pede uma mudança (p. ex. antes do sprint do ladrão)."""
        self.prompt = f"põe a passadeira a {speed_kmh:.1f} km/h"
        return self.prompt

    def tick(self, now: float) -> None:
        if self._t is not None and now > self._t:
            self.distance_m += self.speed_kmh / 3.6 * (now - self._t)
        self._t = now

    def reading(self, now: float) -> Reading:
        self.tick(now)
        return Reading(speed_mps=self.speed_kmh / 3.6, incline_pct=self.incline_pct, distance_m=self.distance_m,
                       extra={"estimated": True, "prompt": self.prompt})

    def plausible_with_hr(self, hr_bpm: int, hr_max: int, threshold_kmh: float) -> bool:
        """Verificação grosseira: correr bem acima do limiar com a FC baixa não bate certo."""
        if not hr_bpm or self.speed_kmh <= threshold_kmh * 1.1:
            return True
        return hr_bpm >= 0.7 * hr_max


# ---------------------------------------------------------------- potência de remo estimada
@dataclass
class RowerPowerEstimator:
    """Watts estimados para remos sem medidor de potência.

    Por ordem de preferência:
    1. ritmo (s/500 m) → watts com a fórmula da Concept2: P = 2,80 / (ritmo/500)³;
    2. calorias por hora → watts (Concept2: kcal/h = 4·W + 300);
    3. cadência × nível de resistência (modelo simples).
    `factor` calibra a máquina (um teste com banda cardíaca afina-o).
    """
    factor: float = 1.0
    per_level: float = 1.1          # watts por (remada/min × nível) no modelo 3

    def estimate(self, pace_s_500m: float | None = None, kcal_h: float | None = None,
                 stroke_rate: float | None = None, level: float | None = None) -> float | None:
        if pace_s_500m:
            w = 2.80 / (pace_s_500m / 500) ** 3
        elif kcal_h and kcal_h > 300:
            w = (kcal_h - 300) / 4
        elif stroke_rate and level:
            w = self.per_level * stroke_rate * level
        else:
            return None
        return round(w * self.factor, 1)

    def calibrate(self, estimated_w: float, reference_w: float) -> float:
        """Ajusta o fator a partir de uma referência (p. ex. teste num remo com potência, ou FC)."""
        if estimated_w > 0 and reference_w > 0:
            self.factor *= reference_w / estimated_w
        return self.factor


# ---------------------------------------------------------------- Domyos
# Os remos Domyos com Bluetooth usam um serviço próprio. O banco de testes grava
# as notificações (hex) com marcas do que o atleta está a fazer; o descodificador
# afina-se a partir dessas capturas.
DOMYOS_NAMES = ("DOMYOS", "DECATHLON")


def looks_like_domyos(name: str | None) -> bool:
    return bool(name) and any(n in name.upper() for n in DOMYOS_NAMES)


@dataclass
class DomyosRower:
    name: str = "Domyos (remo)"
    estimator: RowerPowerEstimator = field(default_factory=RowerPowerEstimator)
    frames: list[bytes] = field(default_factory=list)

    @property
    def device(self) -> Device:
        return Device("domyos-rower", self.name, Kind.ROWER, "ble", estimated=True)

    def decode(self, data: bytes) -> Reading | None:
        """Ainda por descodificar: guarda a trama; devolve None até o protocolo ser conhecido."""
        self.frames.append(bytes(data))
        return None

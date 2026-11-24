"""Inventário, requisitos por desporto e junção das leituras.

Um atleta não tem de ter todos os ergómetros. Ao começar uma sessão, ou ao
trocar de desporto, o jogo verifica se há um aparelho compatível ligado:

| Desporto | Obrigatório (um destes) | Recomendado |
| :-- | :-- | :-- |
| Ciclismo | rolo (FTMS / FE-C) ou medidor de potência | banda cardíaca |
| Corrida | passadeira (FTMS / FE-C) ou sensor de passada | banda cardíaca |
| Remo | remo (FTMS / FE-C) | banda cardíaca |
| Ginásio | — | banda cardíaca (a sessão vale mais para a Robustez) |

A banda cardíaca é obrigatória só se o atleta o pedir nas preferências
(`hr_required`), por exemplo para treinar por zonas de FC.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from .ble import Reading


class Kind(str, Enum):
    TRAINER = "trainer"
    POWER_METER = "power_meter"
    TREADMILL = "treadmill"
    FOOTPOD = "footpod"
    ROWER = "rower"
    HEART_RATE = "heart_rate"


KIND_NAMES = {Kind.TRAINER: "rolo", Kind.POWER_METER: "medidor de potência", Kind.TREADMILL: "passadeira",
              Kind.FOOTPOD: "sensor de passada", Kind.ROWER: "remo", Kind.HEART_RATE: "banda cardíaca"}


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    kind: Kind
    transport: str                     # "ble" | "ant" | "sim"
    address: str = ""                  # BLE: endereço; ANT+: número do dispositivo
    controllable: bool = False         # aceita ERG / simulação (rolo FTMS/FE-C, passadeira FTMS)


@dataclass(frozen=True)
class Requirement:
    any_of: tuple[Kind, ...]           # pelo menos um destes
    recommended: tuple[Kind, ...] = (Kind.HEART_RATE,)


REQUIREMENTS = {
    "bike": Requirement((Kind.TRAINER, Kind.POWER_METER)),
    "run": Requirement((Kind.TREADMILL, Kind.FOOTPOD)),
    "row": Requirement((Kind.ROWER,)),
    "gym": Requirement(()),
}
SPORT_NAMES = {"bike": "ciclismo", "run": "corrida", "row": "remo", "gym": "ginásio"}


@dataclass
class DeviceCheck:
    sport: str
    ok: bool
    main: Device | None                # o aparelho que dá os dados do desporto
    hr: Device | None
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def missing_text(self) -> str:
        """"um rolo ou um medidor de potência" — o que o atleta tem de ligar."""
        art = {"passadeira": "uma", "banda cardíaca": "uma"}
        return " ou ".join(f"{art.get(m, 'um')} {m}" for m in self.missing)

    @property
    def erg_capable(self) -> bool:
        """Se o modo ERG (ou o declive do mapa no aparelho) está disponível."""
        return bool(self.main and self.main.controllable)

    def summary(self) -> str:
        if not self.ok:
            return f"{SPORT_NAMES[self.sport]}: falta {' ou '.join(self.missing)}"
        parts = [f"{SPORT_NAMES[self.sport]}: {self.main.name} ({self.main.transport.upper()})" if self.main
                 else SPORT_NAMES[self.sport]]
        if self.hr:
            parts.append(f"FC {self.hr.name} ({self.hr.transport.upper()})")
        return " · ".join(parts + self.warnings)


def check(sport: str, devices: list[Device], hr_required: bool = False) -> DeviceCheck:
    """Há aparelhos para este desporto? `devices` são os que estão ligados agora."""
    req = REQUIREMENTS[sport]
    main = None
    for kind in req.any_of:                            # por ordem de preferência
        cands = [d for d in devices if d.kind is kind]
        if cands:
            main = sorted(cands, key=lambda d: not d.controllable)[0]
            break
    hr = next((d for d in devices if d.kind is Kind.HEART_RATE), None)
    missing = [KIND_NAMES[k] for k in req.any_of] if req.any_of and main is None else []
    warnings = []
    if hr is None:
        if hr_required:
            missing.append(KIND_NAMES[Kind.HEART_RATE])
        else:
            warnings.append("sem banda cardíaca: a carga conta pela potência/ritmo")
    if main is not None and not main.controllable and sport in ("bike", "run"):
        warnings.append("sem controlo: ERG e declive do mapa indisponíveis no aparelho")
    return DeviceCheck(sport, not missing, main, hr, missing, warnings)


def available_sports(devices: list[Device], hr_required: bool = False) -> list[str]:
    return [s for s in ("bike", "run", "row") if check(s, devices, hr_required).ok]


# ---------------------------------------------------------------- leituras
@dataclass
class Live:
    """O estado atual da sessão, juntando vários aparelhos."""
    t: float = 0.0
    power_w: float | None = None
    cadence: float | None = None
    speed_mps: float | None = None
    distance_m: float | None = None
    hr_bpm: int | None = None
    stroke_count: int | None = None
    sources: dict = field(default_factory=dict)        # métrica → aparelho


# Prioridade por métrica: quem manda quando vários aparelhos medem o mesmo.
PRIORITY = {
    "power_w": (Kind.POWER_METER, Kind.TRAINER, Kind.ROWER, Kind.TREADMILL),
    "cadence": (Kind.POWER_METER, Kind.FOOTPOD, Kind.TRAINER, Kind.ROWER, Kind.TREADMILL),
    "speed_mps": (Kind.TREADMILL, Kind.FOOTPOD, Kind.ROWER, Kind.TRAINER),
    "distance_m": (Kind.TREADMILL, Kind.ROWER, Kind.TRAINER, Kind.FOOTPOD),
    "hr_bpm": (Kind.HEART_RATE, Kind.TRAINER, Kind.TREADMILL, Kind.ROWER),
    "stroke_count": (Kind.ROWER,),
}
STALE_S = 3.0


class Hub:
    """Recebe leituras de qualquer transporte e dá uma visão única, por prioridade."""

    def __init__(self, devices: list[Device], clock=time.monotonic):
        self.devices = {d.id: d for d in devices}
        self.clock = clock
        self._last: dict[str, tuple[float, Reading]] = {}
        self.commands: list[tuple[str, str, float]] = []   # (aparelho, comando, valor) — registo

    def feed(self, device_id: str, reading: Reading) -> None:
        self._last[device_id] = (self.clock(), reading)

    def live(self) -> Live:
        now = self.clock()
        out = Live(t=now)
        for metric, order in PRIORITY.items():
            for kind in order:
                for dev_id, (t, r) in self._last.items():
                    d = self.devices.get(dev_id)
                    v = getattr(r, metric)
                    if d and d.kind is kind and v is not None and now - t <= STALE_S:
                        setattr(out, metric, v)
                        out.sources[metric] = d.name
                        break
                if metric in out.sources:
                    break
        return out

    # controlo: o envio real é do transporte (BleLink.send / AntStick.send)
    def set_erg(self, device: Device, watts: float) -> None:
        self.commands.append((device.id, "erg", watts))

    def set_grade(self, device: Device, grade_pct: float) -> None:
        self.commands.append((device.id, "grade", grade_pct))

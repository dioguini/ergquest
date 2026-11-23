"""Validação da telemetria no servidor: a fisiologia é a regra.

Camadas (cada uma devolve avisos com gravidade):

1. **Envelope humano** — melhores médias em W/kg acima do que um humano faz.
2. **Coerência de sensores** — potência sem cadência; FC parada enquanto a
   potência varia; FC que não responde à potência.
3. **Assinatura de bot** — potência demasiado constante; degraus impossíveis.
4. **Física** — a distância que o cliente diz ter feito tem de bater com a
   física recalculada a partir dos watts e do declive.
5. **Tempo** — amostras fora de ordem ou repetidas.

Nunca se bane automaticamente: uma sessão com avisos graves sai dos
rankings e vai para revisão humana.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from ..shared import physics

# Melhores médias (W/kg) acima das quais nenhum humano está (margem sobre os
# topos da tabela de Coggan e os recordes conhecidos).
ENVELOPE_WKG = {5: 25.0, 60: 12.0, 300: 7.8, 1200: 6.8, 3600: 6.5}
SEVERITY = {"low": 0.05, "medium": 0.2, "high": 0.5}


@dataclass(frozen=True)
class Sample:
    t: float                       # s desde o início (relógio do sensor)
    power: float | None = None
    hr: float | None = None
    cadence: float | None = None   # rpm ou remadas/min
    grade_pct: float = 0.0
    distance_m: float | None = None   # distância que o cliente diz ter feito


@dataclass
class Flag:
    code: str
    severity: str
    detail: str


@dataclass
class Report:
    flags: list[Flag] = field(default_factory=list)

    @property
    def trust(self) -> float:
        return round(max(0.0, 1.0 - sum(SEVERITY[f.severity] for f in self.flags)), 3)

    @property
    def ranked_ok(self) -> bool:
        return self.trust >= 0.7 and not any(f.severity == "high" for f in self.flags)

    def add(self, code: str, severity: str, detail: str) -> None:
        self.flags.append(Flag(code, severity, detail))


def best_mean(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    acc = sum(values[:window])
    best = acc
    for i in range(window, len(values)):
        acc += values[i] - values[i - window]
        best = max(best, acc)
    return best / window


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3 or statistics.pstdev(a) == 0 or statistics.pstdev(b) == 0:
        return None
    return statistics.correlation(a, b)


def validate(samples: list[Sample], weight_kg: float, *, sport: str = "bike",
             rider_mass_extra_kg: float = physics.BIKE_KG,
             cda: float = physics.DEFAULT_CDA, crr: float = physics.DEFAULT_CRR) -> Report:
    rep = Report()
    if not samples:
        return rep

    # 5. tempo
    ts = [s.t for s in samples]
    if any(b <= a for a, b in zip(ts, ts[1:])):
        rep.add("time_order", "high", "amostras fora de ordem ou repetidas")

    power = [s.power or 0.0 for s in samples]
    has_power = any(p > 0 for p in power)

    # 1. envelope humano
    if has_power and weight_kg > 0:
        for win, lim in ENVELOPE_WKG.items():
            bm = best_mean(power, win)
            if bm is None:
                continue
            wkg = bm / weight_kg
            if wkg > lim:
                rep.add("envelope", "high", f"{win}s a {wkg:.1f} W/kg (> {lim})")
            elif wkg > 0.95 * lim:
                rep.add("envelope_near", "low", f"{win}s a {wkg:.1f} W/kg, perto do limite")

    # 2. coerência de sensores
    if has_power and sport in ("bike", "row"):
        run = longest = 0
        for s in samples:
            run = run + 1 if (s.power or 0) > 150 and not s.cadence else 0
            longest = max(longest, run)
        if longest >= 10:
            rep.add("power_without_cadence", "medium", f"{longest}s com potência e sem cadência")

    hrs = [s.hr for s in samples]
    if all(h is not None for h in hrs) and len(hrs) >= 120:
        run = longest = 1
        for a, b in zip(hrs, hrs[1:]):
            run = run + 1 if a == b else 1
            longest = max(longest, run)
        if longest >= 120 and statistics.pstdev(power) > 20:
            rep.add("hr_flatline", "medium", f"FC igual durante {longest}s com a potência a variar")
        if len(samples) >= 1200 and statistics.pstdev(power) > 25:
            lag = 30
            p30 = [statistics.fmean(power[max(0, i - 29):i + 1]) for i in range(len(power))]
            r = _pearson(p30[:-lag], [float(h) for h in hrs[lag:]])
            if r is not None and r < 0.1:
                rep.add("hr_unresponsive", "medium", f"FC não acompanha a potência (r={r:.2f})")

    # 3. assinatura de bot
    if has_power and len(power) >= 300:
        flat = 0
        for i in range(60, len(power)):
            win = power[i - 60:i]
            if statistics.fmean(win) > 100 and statistics.pstdev(win) < 1.5:
                flat += 1
        if flat >= 300:
            rep.add("robotic_power", "medium", f"{flat}s de potência sem variação humana")
    if has_power and weight_kg > 0:
        jumps = sum(1 for a, b in zip(power, power[1:]) if (b - a) / weight_kg > 15)
        if jumps:
            rep.add("power_step", "medium", f"{jumps} degraus de potência impossíveis num segundo")

    # 4. física (ciclismo): recalcular a distância a partir dos watts
    reported = [s.distance_m for s in samples if s.distance_m is not None]
    if sport == "bike" and has_power and len(reported) == len(samples) and len(samples) > 60:
        mass = weight_kg + rider_mass_extra_kg
        v = dist = 0.0
        for a, b in zip(samples, samples[1:]):
            dt = b.t - a.t
            if dt <= 0:
                continue
            v = physics.step_velocity(mass, cda, crr, v, a.power or 0.0, a.grade_pct / 100.0, dt)
            dist += v * dt
        claimed = reported[-1] - reported[0]
        if dist > 50:
            err = (claimed - dist) / dist
            if err > 0.05:
                rep.add("physics_distance", "high",
                        f"distância declarada {claimed:.0f} m vs {dist:.0f} m pela física (+{err:.0%})")
            elif err > 0.02:
                rep.add("physics_distance", "low", f"desvio de distância de {err:.1%}")
    return rep

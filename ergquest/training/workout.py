"""Treinos estruturados e o seu cumprimento.

Passos de treino (como nos .zwo/.mrc/.erg/.fit) e o cumprimento, com uma
tolerância de ±5 % do alvo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TOLERANCE_PCT = 5.0


@dataclass
class Step:
    kind: str                      # steady | ramp | freeride
    duration_s: int
    target_type: str = "pct_ftp"   # pct_ftp | watts | none
    target_lo: float | None = None
    target_hi: float | None = None
    text_cue: str | None = None

    def watts(self, progress: float, ftp_w: float) -> int | None:
        if self.target_type == "none" or self.target_lo is None:
            return None
        hi = self.target_hi if self.target_hi is not None else self.target_lo
        value = self.target_lo + (hi - self.target_lo) * min(max(progress, 0.0), 1.0)
        return int(round(value / 100.0 * ftp_w)) if self.target_type == "pct_ftp" else int(round(value))

    def fraction(self, progress: float = 0.5) -> float | None:
        """Intensidade do passo em fração da FTP (só para pct_ftp)."""
        if self.target_type != "pct_ftp" or self.target_lo is None:
            return None
        hi = self.target_hi if self.target_hi is not None else self.target_lo
        return (self.target_lo + (hi - self.target_lo) * progress) / 100.0


@dataclass
class Workout:
    name: str
    steps: list[Step]

    @property
    def total_seconds(self) -> int:
        return sum(s.duration_s for s in self.steps)

    def estimated_tss(self, ftp_w: float) -> float:
        total = 0.0
        for s in self.steps:
            w = s.watts(0.5, ftp_w) or ftp_w * 0.55
            total += s.duration_s * (w / max(ftp_w, 1)) ** 2
        return total / 3600.0 * 100.0


@dataclass
class WorkoutRunner:
    workout: Workout
    ftp_w: float
    _acc: dict[int, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._starts, acc = [], 0
        for s in self.workout.steps:
            self._starts.append(acc)
            acc += s.duration_s
        self.total_s = acc

    def step_at(self, elapsed_s: float) -> tuple[int, Step, float] | None:
        if elapsed_s >= self.total_s:
            return None
        idx = max(i for i, st in enumerate(self._starts) if st <= elapsed_s)
        step = self.workout.steps[idx]
        return idx, step, (elapsed_s - self._starts[idx]) / max(step.duration_s, 1)

    def target_watts(self, elapsed_s: float) -> int | None:
        found = self.step_at(elapsed_s)
        return None if found is None else found[1].watts(found[2], self.ftp_w)

    def upcoming(self, elapsed_s: float, horizon_s: float = 300) -> list[tuple[float, float | None]]:
        """[(segundos, fração FTP)] dos próximos `horizon_s` — para sugerir caminhos."""
        out, t = [], elapsed_s
        while t < elapsed_s + horizon_s:
            found = self.step_at(t)
            if found is None:
                break
            idx, step, prog = found
            left = min(self._starts[idx] + step.duration_s - t, elapsed_s + horizon_s - t)
            out.append((left, step.fraction()))
            t += max(left, 1)
        return out

    @staticmethod
    def compliance(actual_w: float | None, target_w: float | None) -> int:
        """-1 abaixo, 0 no alvo (±5 %), +1 acima."""
        if actual_w is None or not target_w:
            return 0
        tol = target_w * TOLERANCE_PCT / 100.0
        return -1 if actual_w < target_w - tol else 1 if actual_w > target_w + tol else 0

    def observe(self, elapsed_s: float, power_w: float | None) -> None:
        found = self.step_at(elapsed_s)
        if found is None:
            return
        idx, step, prog = found
        a = self._acc.setdefault(idx, {"n": 0, "in": 0, "p": 0.0, "targeted": 0})
        a["n"] += 1
        a["p"] += power_w or 0.0
        target = step.watts(prog, self.ftp_w)
        if target is not None:
            a["targeted"] += 1
            if self.compliance(power_w, target) == 0:
                a["in"] += 1

    def results(self) -> list[dict]:
        return [{"step": i, "avg_power_w": a["p"] / max(a["n"], 1),
                 "pct_in_target": (a["in"] / a["targeted"] * 100.0) if a["targeted"] else None}
                for i, a in sorted(self._acc.items())]

    def overall_compliance(self) -> float | None:
        """% do tempo com alvo em que o atleta esteve dentro de ±5 %."""
        n = sum(a["targeted"] for a in self._acc.values())
        return sum(a["in"] for a in self._acc.values()) / n * 100.0 if n else None

"""Suavidade da remada — a qualidade técnica que os passageiros sentem.

Dois ingredientes, ambos medíveis num ergómetro com FTMS/PM5:

* **Consistência** entre remadas: a variação (CV) da potência por remada.
  Um barco que acelera e trava aos solavancos é desconfortável.
* **Forma da curva de força** dentro da remada (quando o remo a envia):
  uma boa remada é uma única "bossa" suave. Duas bossas (pernas e braços
  desligados) ou um pico agressivo aumentam o solavanco.

Resultado entre 0 (só solavancos) e 1 (seda).
"""
from __future__ import annotations

import statistics

CV_ZERO = 0.25              # CV a partir do qual a consistência vale 0
IDEAL_PEAK_RATIO = 1.57     # pico/média de meia sinusoide (π/2)


def consistency(stroke_watts: list[float]) -> float:
    vals = [w for w in stroke_watts if w > 0]
    if len(vals) < 3:
        return 0.0
    cv = statistics.pstdev(vals) / statistics.fmean(vals)
    return max(0.0, 1.0 - cv / CV_ZERO)


def curve_quality(force: list[float]) -> float:
    """1 para uma bossa suave; desconta bossas extra e picos agressivos."""
    f = [max(0.0, x) for x in force]
    if len(f) < 5 or max(f) <= 0:
        return 0.0
    peak, mean = max(f), statistics.fmean(f)
    # bossas: máximos locais (≥ 30 % do pico) separados por um vale fundo (≥ 8 % do pico)
    peaks = [i for i in range(1, len(f) - 1)
             if f[i] > f[i - 1] and f[i] >= f[i + 1] and f[i] >= 0.3 * peak]
    humps = 1 if peaks else 0
    for p, q in zip(peaks, peaks[1:]):
        if min(f[p], f[q]) - min(f[p:q + 1]) >= 0.08 * peak:
            humps += 1
    hump_pen = 0.3 * max(0, humps - 1)
    ratio_pen = min(0.5, abs(peak / mean - IDEAL_PEAK_RATIO) * 0.5)
    return max(0.0, 1.0 - hump_pen - ratio_pen)


def smoothness(stroke_watts: list[float], force_curves: list[list[float]] | None = None) -> float:
    c = consistency(stroke_watts)
    if not force_curves:
        return round(c, 3)
    q = statistics.fmean(curve_quality(fc) for fc in force_curves)
    return round(0.6 * c + 0.4 * q, 3)

"""Carga de treino à TrainingPeaks: NP, TSS, rTSS e PMC (CTL/ATL/TSB)."""
from __future__ import annotations

import math
from datetime import date, timedelta


def normalized(values: list[float], window: int = 30) -> float | None:
    """Média móvel de `window` amostras (1 Hz), à 4.ª potência, média e raiz quarta."""
    vals = [float(v or 0.0) for v in values]
    if len(vals) < window:
        return (sum(v ** 4 for v in vals) / len(vals)) ** 0.25 if vals else None
    acc = sum(vals[:window])
    rolling = [acc / window]
    for i in range(window, len(vals)):
        acc += vals[i] - vals[i - window]
        rolling.append(acc / window)
    return (sum(r ** 4 for r in rolling) / len(rolling)) ** 0.25


def tss(power_1hz: list[float], ftp_w: float) -> float | None:
    """TSS = h · IF² · 100, com IF = NP / FTP (ciclismo e remo)."""
    np_w = normalized(power_1hz)
    if np_w is None or ftp_w <= 0:
        return None
    hours = len(power_1hz) / 3600.0
    return hours * (np_w / ftp_w) ** 2 * 100.0


def grade_factor(grade_pct: float) -> float:
    """Quanto custa correr a esta inclinação, face ao plano (Minetti, 2002)."""
    g = max(-0.45, min(0.45, grade_pct / 100.0))
    cost = 155.4 * g ** 5 - 30.4 * g ** 4 - 43.3 * g ** 3 + 46.3 * g ** 2 + 19.5 * g + 3.6
    return max(0.3, cost / 3.6)


def rtss(speeds_mps: list[float], threshold_mps: float, grades_pct: list[float] | None = None) -> float | None:
    """rTSS = h · IF² · 100, com IF = NGS / velocidade de limiar."""
    if threshold_mps <= 0:
        return None
    adj = speeds_mps if grades_pct is None else [
        v * grade_factor(g) for v, g in zip(speeds_mps, grades_pct)]
    ngs = normalized(adj)
    if ngs is None:
        return None
    return len(speeds_mps) / 3600.0 * (ngs / threshold_mps) ** 2 * 100.0


def hr_load(minutes: float, avg_hr: float, lthr: float) -> float:
    """Carga pela FC (para o ginásio): uma hora no limiar = 100."""
    if lthr <= 0:
        return 0.0
    return minutes / 60.0 * (avg_hr / lthr) ** 2 * 100.0


CTL_DAYS, ATL_DAYS = 42.0, 7.0
K_CTL = 1.0 - math.exp(-1.0 / CTL_DAYS)
K_ATL = 1.0 - math.exp(-1.0 / ATL_DAYS)

FORM_STATES = (
    (25.0, "transição"),     # muito fresco: a perder forma
    (5.0, "fresco"),         # bom para competir
    (-10.0, "neutro"),
    (-30.0, "ótimo"),        # a construir forma
    (float("-inf"), "sobrecarga"),
)


def form_state(tsb: float) -> str:
    for lo, key in FORM_STATES:
        if tsb >= lo:
            return key
    return "sobrecarga"


def pmc(daily: dict[date, float], today: date) -> list[dict]:
    """[{date, load, ctl, atl, tsb}] do 1.º dia com carga até `today`.

    TSB de um dia = CTL − ATL do dia anterior (a forma com que se entra no dia).
    """
    if not daily:
        return []
    ctl = atl = 0.0
    out = []
    day = min(daily)
    while day <= today:
        load = daily.get(day, 0.0)
        tsb = ctl - atl
        ctl += (load - ctl) * K_CTL
        atl += (load - atl) * K_ATL
        out.append({"date": day, "load": load, "ctl": ctl, "atl": atl, "tsb": tsb})
        day += timedelta(days=1)
    return out

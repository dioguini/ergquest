"""Robustez: o *buff* do ginásio.

O ginásio não existe no mundo virtual e nunca aumenta watts — no ErgQuest
a velocidade vem só da física. A força entra como **Robustez** (0–1), que:

* multiplica o XP ganho (0,85× sem ginásio → 1,15× com regularidade);
* abre os escalões altos de nível (`progression.TIER_GATES`);
* deixa aceitar mais pedidos ao mesmo tempo e encomendas mais pesadas —
  e a carga extra entra na massa da física, por isso é mesmo mais dura.

Não conta nos desafios PvP nem nos rankings.

Como o ginásio não é verificável, uma sessão só com registo manual vale
menos do que uma com FC gravada, e a Robustez decai sem regularidade.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

WINDOW_DAYS = 28
TARGET_SESSIONS = 8            # 2 por semana durante 4 semanas
MANUAL_WEIGHT = 0.7            # sessão sem FC: vale 70 %
MIN_MINUTES = 20


@dataclass(frozen=True)
class GymSession:
    day: date
    minutes: float
    with_hr: bool = False


def robustness(sessions: list[GymSession], today: date) -> float:
    """0–1: 60 % pelo volume ponderado, 40 % pela regularidade semanal."""
    start = today - timedelta(days=WINDOW_DAYS - 1)
    valid = [s for s in sessions if start <= s.day <= today and s.minutes >= MIN_MINUTES]
    if not valid:
        return 0.0
    weighted = sum(1.0 if s.with_hr else MANUAL_WEIGHT for s in valid)
    weeks = {(s.day - start).days // 7 for s in valid}
    volume = min(1.0, weighted / TARGET_SESSIONS)
    regularity = len(weeks) / 4.0
    return round(0.6 * volume + 0.4 * regularity, 3)


def xp_multiplier(rob: float) -> float:
    return 0.85 + 0.30 * max(0.0, min(1.0, rob))


def extra_order_slots(rob: float) -> int:
    return 2 if rob >= 0.85 else 1 if rob >= 0.5 else 0


def max_cargo_kg(rob: float) -> float:
    """Peso máximo de encomenda que o atleta pode aceitar (soma à massa da física)."""
    return round(2.0 + 8.0 * max(0.0, min(1.0, rob)), 1)

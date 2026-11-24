"""Progressão: XP, níveis, reputação e desbloqueios — por modalidade.

Um atleta não tem de ter todos os ergómetros em casa, por isso cada
modalidade evolui sozinha: ciclismo, corrida e remo têm o seu XP e o seu
nível. Ciclismo e corrida partilham o mapa de terra (cada um com o que já
abriu); o remo tem o mapa do rio. O ginásio não tem nível: dá Robustez, que
vale para todos.

O XP vem do esforço real (a carga TSS de qualquer sessão, livre ou missão)
e do desempenho nas missões (estrelas), e vai para o desporto da sessão.
Nada disto mexe na velocidade.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import strength
from .cities import CITIES, City

SPORTS = ("bike", "run", "row")
SPORT_NAMES = {"bike": "Ciclismo", "run": "Corrida", "row": "Remo"}
XP_PER_TSS = 10.0
XP_PER_STAR = 40.0

# A partir destes níveis, a Robustez mínima para continuar a subir:
# é o "potencial máximo" que só o ginásio abre.
TIER_GATES = ((20, 0.30), (30, 0.50), (40, 0.70))


def xp_for_level(level: int) -> int:
    """XP acumulado necessário para chegar a `level` (nível 1 = 0 XP)."""
    return int(round(120 * (level - 1) ** 1.6))


def required_robustness(level: int) -> float:
    req = 0.0
    for lvl, rob in TIER_GATES:
        if level >= lvl:
            req = rob
    return req


def level_for(xp: float, rob: float) -> int:
    """Nível alcançado: o XP manda, mas os portões de Robustez travam."""
    lvl = 1
    while xp >= xp_for_level(lvl + 1) and rob >= required_robustness(lvl + 1):
        lvl += 1
    return lvl


def session_xp(tss: float, stars: list[int], rob: float) -> int:
    base = max(0.0, tss) * XP_PER_TSS + sum(stars) * XP_PER_STAR
    return int(round(base * strength.xp_multiplier(rob)))


@dataclass
class Profile:
    """Perfil único do atleta (uma conta, quatro modalidades, três níveis)."""
    player_id: str
    weight_kg: float
    ftp_w: float = 200.0
    run_threshold_mps: float = 3.3
    row_ftp_w: float = 180.0
    xp: dict[str, float] = field(default_factory=dict)       # XP por desporto
    robustness: float = 0.0
    ratings: list[int] = field(default_factory=list)
    abandons: int = 0
    active_weeks_last8: int = 0
    home_city: str = "lisboa"
    jobs_done: dict[str, int] = field(default_factory=dict)   # por tipo de trabalho (food, chase, tour…)

    def __post_init__(self) -> None:
        if isinstance(self.xp, (int, float)):        # atalho: um número é XP de ciclismo
            self.xp = {"bike": float(self.xp)}

    def level_in(self, sport: str) -> int:
        """Nível numa modalidade (o que abre o mapa desse desporto)."""
        return level_for(self.xp.get(sport, 0.0), self.robustness)

    @property
    def levels(self) -> dict[str, int]:
        return {s: self.level_in(s) for s in SPORTS}

    @property
    def level(self) -> int:
        """Nível de atleta: o mais alto das modalidades (cidades, desafios, licenças gerais)."""
        return max(self.levels.values())

    @property
    def reputation(self) -> float:
        """Média das últimas 50 estrelas, menos 0,1 por abandono recente (mín. 1)."""
        recent = self.ratings[-50:]
        avg = sum(recent) / len(recent) if recent else 3.0
        return round(max(1.0, avg - 0.1 * self.abandons), 2)

    def add_session(self, tss: float, stars: list[int], sport: str = "bike") -> int:
        """XP da sessão para o desporto dela (o ginásio não dá XP: dá Robustez)."""
        if sport not in SPORTS:
            raise ValueError(f"o XP é por modalidade de ergómetro: {SPORTS}")
        gained = session_xp(tss, stars, self.robustness)
        self.xp[sport] = self.xp.get(sport, 0.0) + gained
        self.ratings.extend(stars)
        return gained

    def record_job(self, kind: str) -> None:
        self.jobs_done[kind] = self.jobs_done.get(kind, 0) + 1

    # ------------------------------------------------------------ desbloqueios
    def establishments_unlocked(self, kind: str) -> int:
        """Quantas fontes deste tipo (restaurantes, esquadras, operadores) estão abertas.

        Começa-se com uma; abre-se mais uma a cada 5 trabalhos desse tipo e a
        cada 10 níveis. Jogar desbloqueia o mundo; treinar só dá XP.
        """
        return 1 + self.jobs_done.get(kind, 0) // 5 + self.level // 10

    def available_sources(self, sources: list) -> list:
        out, seen = [], {}
        for src in sources:
            k = src.kind.value
            seen[k] = seen.get(k, 0) + 1
            if seen[k] <= self.establishments_unlocked(k):
                out.append(src)
        return out

    def city_unlocked(self, city: City | str) -> bool:
        c = CITIES[city] if isinstance(city, str) else city
        if c.id == self.home_city:
            return True
        return self.level >= c.unlock_level and self.active_weeks_last8 >= c.unlock_active_weeks

    def access(self, sport: str = "bike"):
        """O que o atleta pode usar no mapa desse desporto: terra (ciclismo/corrida) ou rio (remo)."""
        from ..world.access import Access
        return Access.for_level(self.level_in(sport), sport)

    def zones_unlocked(self, city: City | str, sport: str = "bike") -> list[str]:
        """Zonas de terra abertas para um desporto (o rio do remo: `access("row")`)."""
        c = CITIES[city] if isinstance(city, str) else city
        if not self.city_unlocked(c):
            return []
        lvl = self.level_in(sport)
        return [z.id for z in c.zones if lvl >= z.unlock_level or z is c.zones[0]]

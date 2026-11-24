"""Área Metropolitana de Lisboa: margens, zonas, ordem de desbloqueio, pontes,
zonas de remo e serras.

Tudo o que é "regra do mundo" sobre a geografia está aqui, em dados: mudar a
ordem de desbloqueio ou o nível de uma ponte é mudar uma linha.

* **Margens** — o Tejo divide o mapa. Um polígono (`NORTH_BANK`) traça a linha
  a meio do estuário, da barra até Vila Franca; o que está a norte/oeste dele
  é a margem norte.
* **Zonas** — margem norte: Baixa, Centro (a cidade de Lisboa), e o resto por
  pontos cardeais a partir da Baixa (Norte, Este, Oeste). Margem sul: Norte
  (junto ao rio), Sul, Este, Oeste.
* **Pontes** — os únicos caminhos entre margens; abrem com o nível.
* **Remo** — cada troço do rio pertence à zona de terra que o acompanha e abre
  com ela; as travessias entre margens são para remadores experientes.
* **Serras** — duas subidas fictícias nas extremidades do mapa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

BOX = (38.40, -9.52, 39.07, -8.70)              # sul, oeste, norte, este
BAIXA_BOX = (38.7030, -9.1500, 38.7170, -9.1250)
BAIXA_CENTER = (38.7110, -9.1370)

# Linha a meio do Tejo (lat, lon), da barra a Vila Franca de Xira e para norte.
TEJO_DIVIDER = [
    (38.660, -9.60), (38.666, -9.30), (38.680, -9.24), (38.687, -9.20), (38.692, -9.177),
    (38.696, -9.150), (38.690, -9.120), (38.700, -9.080), (38.740, -9.050), (38.790, -9.040),
    (38.850, -9.020), (38.900, -8.975), (38.950, -8.968), (39.000, -8.940), (39.070, -8.880),
    (39.200, -8.850),
]
NORTH_BANK = TEJO_DIVIDER + [(39.20, -9.60)]

# Cidade de Lisboa (aproximação do limite do concelho), a "zona Centro".
LISBOA_CITY = [
    (38.690, -9.240), (38.735, -9.225), (38.755, -9.210), (38.770, -9.190), (38.796, -9.175),
    (38.800, -9.140), (38.797, -9.100), (38.795, -9.080), (38.760, -9.085), (38.720, -9.105),
    (38.700, -9.150),
]


@dataclass(frozen=True)
class MetroZone:
    id: str
    name: str
    bank: str            # "norte" | "sul"
    level: int           # nível a que abre
    hue: int             # cor no mapa (graus HSL)


# Dois mapas: TERRA (ciclismo e corrida, o mesmo mapa; cada desporto com o seu
# nível) e RIO (remo, com a sua própria escada). A ordem de desbloqueio é a
# ordem de cada lista.
ZONES: tuple[MetroZone, ...] = (
    MetroZone("n-baixa", "Baixa", "norte", 1, 18),
    MetroZone("n-centro", "Centro", "norte", 3, 205),
    MetroZone("n-norte", "Norte", "norte", 6, 140),
    MetroZone("n-este", "Este", "norte", 9, 270),
    MetroZone("n-oeste", "Oeste", "norte", 12, 45),
    MetroZone("s-norte", "Margem Sul · Norte", "sul", 15, 330),
    MetroZone("s-sul", "Margem Sul · Sul", "sul", 18, 95),
    MetroZone("s-este", "Margem Sul · Este", "sul", 21, 180),
    MetroZone("s-oeste", "Margem Sul · Oeste", "sul", 24, 0),
)
ZONE = {z.id: z for z in ZONES}
UNLOCK_ORDER = [z.id for z in ZONES]

# Pontes: abrem com a primeira zona da margem sul ("atletas com bastante nível").
BRIDGE_LEVEL = ZONE["s-norte"].level
BRIDGES = {   # id → (nome, (lat, lon) do meio)
    "ponte-25-abril": ("Ponte 25 de Abril", (38.6915, -9.1770)),
    "ponte-vasco-da-gama": ("Ponte Vasco da Gama", (38.7600, -9.0400)),
    "ponte-vila-franca": ("Ponte Marechal Carmona", (38.9530, -8.9750)),
    "ponte-leziria": ("Ponte da Lezíria", (38.9330, -8.9530)),
}
# ---------------------------------------------------------------- remo
# O rio tem a sua escada: cada troço do Tejo segue a zona de terra ao lado,
# mas abre com o nível de REMO. As travessias abrem com a primeira zona da
# margem sul do rio — é aí que os pedidos podem ligar as duas margens.
ROW_ZONES: tuple[MetroZone, ...] = (
    MetroZone("r-baixa", "Tejo · Baixa", "norte", 1, 200),
    MetroZone("r-centro", "Tejo · Centro", "norte", 3, 215),
    MetroZone("r-este", "Tejo · Este", "norte", 6, 260),
    MetroZone("r-oeste", "Tejo · Oeste", "norte", 9, 175),
    MetroZone("r-sul-norte", "Tejo Sul · Norte", "sul", 12, 320),
    MetroZone("r-sul-este", "Tejo Sul · Este", "sul", 15, 150),
    MetroZone("r-sul-oeste", "Tejo Sul · Oeste", "sul", 18, 25),
)
ROW_ZONE = {z.id: z for z in ROW_ZONES}
ROW_UNLOCK_ORDER = [z.id for z in ROW_ZONES]
LAND_TO_ROW = {"n-baixa": "r-baixa", "n-centro": "r-centro", "n-este": "r-este", "n-norte": "r-este",
               "n-oeste": "r-oeste", "s-norte": "r-sul-norte", "s-sul": "r-sul-norte",
               "s-este": "r-sul-este", "s-oeste": "r-sul-oeste"}
CROSSING_LEVEL = ROW_ZONE["r-sul-norte"].level

LAND_SPORTS = ("bike", "run")


def ladder(sport: str) -> tuple[MetroZone, ...]:
    """A escada de zonas de um desporto: terra para ciclismo/corrida, rio para remo."""
    return ROW_ZONES if sport == "row" else ZONES


def any_zone(zid: str) -> MetroZone:
    return ZONE.get(zid) or ROW_ZONE[zid]


def _pip(lat: float, lon: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    for (y1, x1), (y2, x2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def bank_of(lat: float, lon: float) -> str:
    return "norte" if _pip(lat, lon, NORTH_BANK) else "sul"


def bearing_from_baixa(lat: float, lon: float) -> float:
    """Ângulo (graus, 0 = este, 90 = norte) visto da Baixa."""
    dy = (lat - BAIXA_CENTER[0]) * 111.32
    dx = (lon - BAIXA_CENTER[1]) * 111.32 * math.cos(math.radians(BAIXA_CENTER[0]))
    return math.degrees(math.atan2(dy, dx))


def zone_of(lat: float, lon: float, bank: str | None = None) -> str:
    """Zona de um ponto. `bank` força a margem (o grafo sabe-a pela ligação das estradas)."""
    s, w, n, e = BAIXA_BOX
    if s <= lat <= n and w <= lon <= e:
        return "n-baixa"
    if (bank or bank_of(lat, lon)) == "norte":
        if _pip(lat, lon, LISBOA_CITY):
            return "n-centro"
        a = bearing_from_baixa(lat, lon)
        if -90 < a < 75:
            return "n-este"
        if 75 <= a <= 135:
            return "n-norte"
        return "n-oeste"
    if lon < -9.19:
        return "s-oeste"
    if lon > -9.00 and lat > 38.60:
        return "s-este"
    if lat > 38.60:
        return "s-norte"
    return "s-sul"


def nearest_bridge(lat: float, lon: float) -> str:
    return min(BRIDGES, key=lambda b: (BRIDGES[b][1][0] - lat) ** 2 + (BRIDGES[b][1][1] - lon) ** 2)


def bridge_distance_km(lat: float, lon: float) -> float:
    b = BRIDGES[nearest_bridge(lat, lon)][1]
    return math.hypot((b[0] - lat) * 111.32, (b[1] - lon) * 111.32 * math.cos(math.radians(lat)))


BRIDGE_REACH_KM = 2.5     # troços que mudam de margem perto de uma ponte fazem parte dela
LAND_EDGE_KM = 1.5        # estradas que acabam a menos disto do limite terrestre ligam-se à extremidade


def land_edge_km(lat: float, lon: float) -> float | None:
    """Distância (km) ao limite terrestre do mapa (norte, este, e o sul a leste de -8,95); None no mar."""
    s, w, n, e = BOX
    d = [(n - lat) * 111.32, (e - lon) * 111.32 * math.cos(math.radians(lat))]
    if lon > -8.95:
        d.append((lat - s) * 111.32)
    return min(d)


# ---------------------------------------------------------------- estradas
# Classes do Overture/OSM. Neste mundo reina o ciclismo e a corrida: as
# autoestradas também contam. Na cidade de Lisboa entra tudo; fora dela, só a
# rede principal (o resto da malha fica para os NPCs).
# Ciclismo e corrida partilham o MESMO mapa de terra, e só em pavimento
# (asfalto ou calçada): sem escadas, trilhos, caminhos de terra nem passeios
# desenhados à parte (duplicariam as ruas). Ruas pedonais e praças entram.
MAIN_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "cycleway"}
CITY_CLASSES = MAIN_CLASSES | {"residential", "living_street", "pedestrian", "service"}
EXCLUDED_CLASSES = {"steps", "footway", "path", "track", "bridleway", "unknown"}
PAVED_SURFACES = {"paved", "paving_stones", "asphalt", "concrete", "sett", "cobblestone", "metal"}
UNPAVED_SURFACES = {"unpaved", "dirt", "gravel", "ground", "grass", "sand", "wood", "compacted", "fine_gravel"}

# ---------------------------------------------------------------- rio
# Faixas de remo (lat, lon), a umas centenas de metros da margem.
ROW_LANES = {
    "linha-norte": [
        (38.6915, -9.4160), (38.6800, -9.3600), (38.6700, -9.3300), (38.6830, -9.2950),
        (38.6900, -9.2650), (38.6940, -9.2330), (38.6895, -9.2150), (38.6905, -9.2000),
        (38.6960, -9.1770), (38.7005, -9.1560), (38.7030, -9.1450), (38.7035, -9.1340),
        (38.7090, -9.1170), (38.7210, -9.1020), (38.7340, -9.0930), (38.7550, -9.0850),
        (38.7750, -9.0800), (38.7950, -9.0780), (38.8150, -9.0690), (38.8600, -9.0450),
        (38.8950, -9.0150), (38.9500, -8.9777),
    ],
    "linha-sul": [
        (38.6749, -9.2333), (38.6830, -9.2050), (38.6880, -9.1750), (38.6900, -9.1500),
        (38.6850, -9.1250), (38.6720, -9.0950), (38.6726, -9.0709), (38.6760, -9.0415),
        (38.6900, -9.0100), (38.7026, -8.9890), (38.7456, -8.9854), (38.7518, -8.9700),
    ],
}
ROW_CROSSINGS = {   # travessias entre margens (lat, lon) → (lat, lon)
    "travessia-cais-do-sodre": ((38.7030, -9.1450), (38.6900, -9.1500)),
    "travessia-belem": ((38.6895, -9.2150), (38.6830, -9.2050)),
    "travessia-terreiro-do-paco": ((38.7035, -9.1340), (38.6726, -9.0709)),
    "travessia-parque-das-nacoes": ((38.7550, -9.0850), (38.7518, -8.9700)),
}
CROSSING_NAMES = {
    "travessia-cais-do-sodre": "Cais do Sodré ↔ Cacilhas",
    "travessia-belem": "Belém ↔ Porto Brandão",
    "travessia-terreiro-do-paco": "Terreiro do Paço ↔ Barreiro",
    "travessia-parque-das-nacoes": "Parque das Nações ↔ Montijo",
}
DOCK_REACH_M = 1500.0      # uma doca liga-se à faixa de remo mais próxima até esta distância


# ---------------------------------------------------------------- serras
@dataclass(frozen=True)
class Climb:
    id: str
    name: str
    bank: str
    anchor: tuple[float, float]   # (lat, lon) perto de onde nasce, na extremidade do mapa
    up_km: float
    avg_pct: float
    down_km: float
    outward: tuple[float, float]  # direção para fora do mapa (dx, dy)


CLIMBS = (
    Climb("serra-grande", "Serra Grande", "norte", (39.07, -9.20), 20.0, 10.0, 20.0, (0.0, 1.0)),
    Climb("colo-da-moura", "Colo da Moura", "sul", (38.52, -8.70), 4.0, 9.0, 4.0, (1.0, 0.0)),
)

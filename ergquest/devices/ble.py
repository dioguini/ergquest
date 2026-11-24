"""Bluetooth Low Energy: Fitness Machine (FTMS), frequência cardíaca, potência e passada.

Formatos segundo as especificações do Bluetooth SIG (FTMS 1.0, HRS, CPS, RSCS):
campos em little-endian, presença de cada campo dada pelos bits de `flags`.
"""
from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field


def uuid16(v: int) -> str:
    return f"0000{v:04x}-0000-1000-8000-00805f9b34fb"


# Serviços
SVC_FTMS, SVC_HR, SVC_CP, SVC_RSC, SVC_CSC = (uuid16(v) for v in (0x1826, 0x180D, 0x1818, 0x1814, 0x1816))
# Características
CH_FTMS_FEATURE = uuid16(0x2ACC)
CH_TREADMILL = uuid16(0x2ACD)
CH_ROWER = uuid16(0x2AD1)
CH_INDOOR_BIKE = uuid16(0x2AD2)
CH_FTMS_CONTROL = uuid16(0x2AD9)
CH_FTMS_STATUS = uuid16(0x2ADA)
CH_HR = uuid16(0x2A37)
CH_CP = uuid16(0x2A63)
CH_RSC = uuid16(0x2A53)


@dataclass
class Reading:
    """Uma leitura normalizada, venha de onde vier."""
    power_w: float | None = None
    cadence: float | None = None          # rpm (bicicleta), passos/min (corrida), remadas/min (remo)
    speed_mps: float | None = None
    distance_m: float | None = None
    hr_bpm: int | None = None
    incline_pct: float | None = None
    stroke_count: int | None = None
    pace_s_500m: float | None = None
    elapsed_s: int | None = None
    extra: dict = field(default_factory=dict)


class _Buf:
    def __init__(self, data: bytes, pos: int = 0):
        self.d, self.p = bytes(data), pos

    def take(self, fmt: str):
        size = struct.calcsize(fmt)
        v = struct.unpack_from("<" + fmt, self.d, self.p)
        self.p += size
        return v[0] if len(v) == 1 else v

    def u24(self) -> int:
        b = self.d[self.p:self.p + 3]
        self.p += 3
        return b[0] | b[1] << 8 | b[2] << 16


# ---------------------------------------------------------------- FTMS: dados
def parse_indoor_bike(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("H")
    r = Reading()
    if not f & 0x0001:
        r.speed_mps = b.take("H") / 100 / 3.6
    if f & 0x0002:
        b.take("H")                                   # velocidade média
    if f & 0x0004:
        r.cadence = b.take("H") / 2
    if f & 0x0008:
        b.take("H")                                   # cadência média
    if f & 0x0010:
        r.distance_m = b.u24()
    if f & 0x0020:
        r.extra["resistance"] = b.take("h")
    if f & 0x0040:
        r.power_w = b.take("h")
    if f & 0x0080:
        b.take("h")                                   # potência média
    if f & 0x0100:
        b.take("HHB")                                 # energia
    if f & 0x0200:
        r.hr_bpm = b.take("B")
    if f & 0x0400:
        b.take("B")                                   # MET
    if f & 0x0800:
        r.elapsed_s = b.take("H")
    return r


def parse_treadmill(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("H")
    r = Reading()
    if not f & 0x0001:
        r.speed_mps = b.take("H") / 100 / 3.6
    if f & 0x0002:
        b.take("H")
    if f & 0x0004:
        r.distance_m = b.u24()
    if f & 0x0008:
        incl, _ramp = b.take("hh")
        r.incline_pct = incl / 10
    if f & 0x0010:
        b.take("HH")                                  # desnível positivo / negativo
    if f & 0x0020:
        b.take("B")                                   # ritmo instantâneo (km/min · 0,1)
    if f & 0x0040:
        b.take("B")
    if f & 0x0080:
        b.take("HHB")
    if f & 0x0100:
        r.hr_bpm = b.take("B")
    if f & 0x0200:
        b.take("B")
    if f & 0x0400:
        r.elapsed_s = b.take("H")
    return r


def parse_rower(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("H")
    r = Reading()
    if not f & 0x0001:
        r.cadence = b.take("B") / 2
        r.stroke_count = b.take("H")
    if f & 0x0002:
        b.take("B")
    if f & 0x0004:
        r.distance_m = b.u24()
    if f & 0x0008:
        r.pace_s_500m = b.take("H")
        if r.pace_s_500m:
            r.speed_mps = 500 / r.pace_s_500m
    if f & 0x0010:
        b.take("H")
    if f & 0x0020:
        r.power_w = b.take("h")
    if f & 0x0040:
        b.take("h")
    if f & 0x0080:
        r.extra["resistance"] = b.take("h")
    if f & 0x0100:
        b.take("HHB")
    if f & 0x0200:
        r.hr_bpm = b.take("B")
    if f & 0x0400:
        b.take("B")
    if f & 0x0800:
        r.elapsed_s = b.take("H")
    return r


# ---------------------------------------------------------------- sensores
def parse_hr(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("B")
    r = Reading(hr_bpm=b.take("H") if f & 0x01 else b.take("B"))
    if f & 0x08:
        b.take("H")
    if f & 0x10:
        rr = []
        while b.p + 2 <= len(b.d):
            rr.append(b.take("H") / 1024)
        r.extra["rr_s"] = rr
    return r


def parse_cycling_power(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("H")
    r = Reading(power_w=b.take("h"))
    if f & 0x0001:
        r.extra["balance"] = b.take("B") / 2
    if f & 0x0004:
        b.take("H")
    if f & 0x0010:
        r.extra["wheel"] = b.take("IH")               # voltas acumuladas, último evento (1/2048 s)
    if f & 0x0020:
        r.extra["crank"] = b.take("HH")               # pedaladas acumuladas, último evento (1/1024 s)
    return r


def cadence_from_crank(prev: tuple[int, int] | None, now: tuple[int, int]) -> float | None:
    """Cadência (rpm) entre duas leituras de pedaleiro (com voltas dos contadores)."""
    if prev is None:
        return None
    revs = (now[0] - prev[0]) & 0xFFFF
    dt = ((now[1] - prev[1]) & 0xFFFF) / 1024
    return revs / dt * 60 if dt > 0 else None


def parse_rsc(data: bytes) -> Reading:
    b = _Buf(data)
    f = b.take("B")
    r = Reading(speed_mps=b.take("H") / 256, cadence=b.take("B"))
    if f & 0x01:
        r.extra["stride_m"] = b.take("H") / 100
    if f & 0x02:
        r.distance_m = b.take("I") / 10
    r.extra["running"] = bool(f & 0x04)
    return r


PARSERS = {CH_INDOOR_BIKE: parse_indoor_bike, CH_TREADMILL: parse_treadmill, CH_ROWER: parse_rower,
           CH_HR: parse_hr, CH_CP: parse_cycling_power, CH_RSC: parse_rsc}


# ---------------------------------------------------------------- FTMS: controlo
OP_REQUEST_CONTROL, OP_RESET, OP_TARGET_SPEED, OP_TARGET_INCLINE = 0x00, 0x01, 0x02, 0x03
OP_TARGET_POWER, OP_START, OP_STOP, OP_SIMULATION, OP_RESPONSE = 0x05, 0x07, 0x08, 0x11, 0x80


def cmd_request_control() -> bytes:
    return bytes([OP_REQUEST_CONTROL])


def cmd_start() -> bytes:
    return bytes([OP_START])


def cmd_target_power(watts: float) -> bytes:
    """ERG: o rolo impõe a potência."""
    return struct.pack("<Bh", OP_TARGET_POWER, int(round(watts)))


def cmd_simulation(grade_pct: float, crr: float = 0.004, cw: float = 0.51, wind_mps: float = 0.0) -> bytes:
    """Simulação: o rolo sente o declive da estrada (ERG desligado)."""
    g = max(-327.68, min(327.67, grade_pct))
    return struct.pack("<BhhBB", OP_SIMULATION, int(round(wind_mps * 1000)), int(round(g * 100)),
                       int(round(crr * 10000)), int(round(cw * 100)))


def cmd_target_speed(speed_mps: float) -> bytes:
    """Passadeira: velocidade-alvo (0,01 km/h)."""
    return struct.pack("<BH", OP_TARGET_SPEED, int(round(speed_mps * 3.6 * 100)))


def cmd_target_incline(pct: float) -> bytes:
    """Passadeira: inclinação-alvo (0,1 %) — o declive do mapa na corrida."""
    return struct.pack("<Bh", OP_TARGET_INCLINE, int(round(pct * 10)))


def parse_control_response(data: bytes) -> tuple[int, int] | None:
    """(opcode pedido, resultado; 1 = sucesso) ou None."""
    if len(data) >= 3 and data[0] == OP_RESPONSE:
        return data[1], data[2]
    return None


# ---------------------------------------------------------------- descoberta
MACHINE_TYPES = {0: "treadmill", 4: "rower", 5: "indoor_bike"}


def machine_types_from_service_data(data: bytes) -> set[str]:
    """Anúncio FTMS (dados do serviço 0x1826): flags (1 byte) + tipos de máquina (2 bytes)."""
    if len(data) < 3:
        return set()
    bits = data[1] | data[2] << 8
    return {name for bit, name in MACHINE_TYPES.items() if bits & (1 << bit)}


def classify(service_uuids: list[str], characteristics: list[str] | None = None,
             ftms_service_data: bytes | None = None) -> list[str]:
    """Que tipos de dispositivo (ver hub.Kind) um aparelho BLE oferece."""
    services = {s.lower() for s in service_uuids}
    chars = {c.lower() for c in characteristics or []}
    kinds: list[str] = []
    if SVC_FTMS in services:
        types = machine_types_from_service_data(ftms_service_data or b"")
        if CH_INDOOR_BIKE in chars or "indoor_bike" in types:
            kinds.append("trainer")
        if CH_TREADMILL in chars or "treadmill" in types:
            kinds.append("treadmill")
        if CH_ROWER in chars or "rower" in types:
            kinds.append("rower")
        if not kinds:
            kinds.append("ftms")                     # tipo só se sabe depois de ligar
    if SVC_CP in services and "trainer" not in kinds:
        kinds.append("power_meter")
    if SVC_RSC in services:
        kinds.append("footpod")
    if SVC_HR in services:
        kinds.append("heart_rate")
    return kinds


# ---------------------------------------------------------------- transporte (bleak, opcional)
def bleak_available() -> bool:
    try:
        import bleak  # noqa: F401
        return True
    except ImportError:
        return False


async def scan(timeout: float = 8.0) -> list[dict]:
    """Procura aparelhos BLE: [{address, name, kinds}]. Precisa de `bleak`."""
    from bleak import BleakScanner
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    out = []
    for address, (dev, adv) in found.items():
        sd = (adv.service_data or {}).get(SVC_FTMS)
        kinds = classify(list(adv.service_uuids or []), ftms_service_data=sd)
        if kinds:
            out.append({"address": address, "name": dev.name or adv.local_name or address, "kinds": kinds})
    return out


class BleLink:
    """Ligação a um aparelho: subscreve as medições e envia comandos FTMS."""

    def __init__(self, address: str, on_reading):
        self.address, self.on_reading = address, on_reading
        self.client = None
        self.kinds: list[str] = []

    async def connect(self) -> list[str]:
        from bleak import BleakClient
        self.client = BleakClient(self.address)
        await self.client.connect()
        chars = [c.uuid for s in self.client.services for c in s.characteristics]
        services = [s.uuid for s in self.client.services]
        self.kinds = classify(services, chars)
        for ch, parse in PARSERS.items():
            if ch in chars:
                await self.client.start_notify(ch, lambda _h, data, p=parse: self.on_reading(p(bytes(data))))
        if CH_FTMS_CONTROL in chars:
            await self.client.start_notify(CH_FTMS_CONTROL, lambda _h, d: None)
            await self.client.write_gatt_char(CH_FTMS_CONTROL, cmd_request_control(), response=True)
            await self.client.write_gatt_char(CH_FTMS_CONTROL, cmd_start(), response=True)
        return self.kinds

    async def send(self, command: bytes) -> None:
        await self.client.write_gatt_char(CH_FTMS_CONTROL, command, response=True)

    async def disconnect(self) -> None:
        if self.client is not None:
            await self.client.disconnect()


def run(coro):
    """Atalho para correr uma corrotina BLE a partir de código síncrono."""
    return asyncio.run(coro)

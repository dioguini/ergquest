"""Aparelhos simulados que falam os protocolos reais (para testes e para a demo).

Cada simulador produz os mesmos bytes que um aparelho verdadeiro
(notificações FTMS / HRS, páginas ANT+), que passam pelos mesmos
descodificadores. Assim o caminho completo é testado sem hardware.
"""
from __future__ import annotations

import struct

from .hub import Device, Kind


def ftms_indoor_bike(speed_mps: float, cadence_rpm: float, power_w: float, hr: int | None = None) -> bytes:
    flags = 0x0004 | 0x0040 | (0x0200 if hr is not None else 0)
    out = struct.pack("<HHHh", flags, int(round(speed_mps * 3.6 * 100)), int(round(cadence_rpm * 2)), int(round(power_w)))
    return out + (bytes([hr]) if hr is not None else b"")


def ftms_treadmill(speed_mps: float, incline_pct: float, distance_m: int, hr: int | None = None) -> bytes:
    flags = 0x0004 | 0x0008 | (0x0100 if hr is not None else 0)
    out = struct.pack("<HH", flags, int(round(speed_mps * 3.6 * 100)))
    out += bytes([distance_m & 0xFF, distance_m >> 8 & 0xFF, distance_m >> 16 & 0xFF])
    out += struct.pack("<hh", int(round(incline_pct * 10)), 0)
    return out + (bytes([hr]) if hr is not None else b"")


def ftms_rower(stroke_rate: float, strokes: int, pace_s_500m: int, power_w: float) -> bytes:
    flags = 0x0008 | 0x0020
    return struct.pack("<HBHHh", flags, int(round(stroke_rate * 2)), strokes, pace_s_500m, int(round(power_w)))


def hr_measurement(bpm: int, rr_s: list[float] | None = None) -> bytes:
    flags = 0x10 if rr_s else 0x00
    out = bytes([flags, bpm])
    for rr in rr_s or []:
        out += struct.pack("<H", int(round(rr * 1024)))
    return out


def ant_fec_trainer(power_w: int, cadence: int) -> bytes:
    return bytes([0x19, 0, cadence, 0, 0, power_w & 0xFF, (power_w >> 8) & 0x0F, 0])


def ant_fec_general(fe_type: int, speed_mps: float, hr: int = 0xFF) -> bytes:
    return bytes([0x10, fe_type, 40, 0]) + struct.pack("<H", int(round(speed_mps * 1000))) + bytes([hr, 0])


def ant_hr(bpm: int) -> bytes:
    return bytes([0x04, 0, 0, 0, 0, 0, 0, bpm])


# Inventários de exemplo
SMART_TRAINER = Device("sim-trainer", "Rolo inteligente", Kind.TRAINER, "ble", "AA:BB:CC:00:00:01", True)
TREADMILL = Device("sim-treadmill", "Passadeira", Kind.TREADMILL, "ble", "AA:BB:CC:00:00:02", True)
ROWER = Device("sim-rower", "Remo", Kind.ROWER, "ble", "AA:BB:CC:00:00:03", False)
HR_STRAP = Device("sim-hr", "Banda cardíaca", Kind.HEART_RATE, "ant", "12345", False)
FOOTPOD = Device("sim-footpod", "Sensor de passada", Kind.FOOTPOD, "ble", "AA:BB:CC:00:00:04", False)
POWER_METER = Device("sim-pm", "Pedais de potência", Kind.POWER_METER, "ant", "777", False)

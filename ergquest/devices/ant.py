"""ANT+: antena USB, FE-C (rolo, passadeira, remo), frequência cardíaca, potência e passada.

Mensagens da antena: `A4 | comprimento | id | dados | soma XOR`. Cada sensor é
ouvido num canal configurado com o tipo de dispositivo, o período e a
frequência de rádio do ANT+. As páginas de dados têm 8 bytes; o primeiro diz
a página.

A chave da rede ANT+ é licenciada pela Garmin/thisisant.com: não vem no
código. Define-se em `ERGQUEST_ANTPLUS_KEY` (16 hex) depois de a obter.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from .ble import Reading

SYNC = 0xA4
# Mensagens
MSG_RESET, MSG_NETWORK_KEY, MSG_ASSIGN, MSG_CHANNEL_ID = 0x4A, 0x46, 0x42, 0x51
MSG_PERIOD, MSG_FREQUENCY, MSG_OPEN, MSG_BROADCAST, MSG_ACK = 0x43, 0x45, 0x4B, 0x4E, 0x4F
RF_ANTPLUS = 57                                   # 2457 MHz


@dataclass(frozen=True)
class Profile:
    name: str
    device_type: int
    period: int
    kind: str                                     # hub.Kind


PROFILES = {
    "fe-c": Profile("FE-C", 17, 8192, "trainer"),     # o tipo real (rolo/passadeira/remo) vem da página 0x10
    "hr": Profile("Frequência cardíaca", 120, 8070, "heart_rate"),
    "power": Profile("Potência", 11, 8182, "power_meter"),
    "sdm": Profile("Passada (SDM)", 124, 8134, "footpod"),
}
FE_TYPES = {19: "treadmill", 22: "rower", 25: "trainer"}


# ---------------------------------------------------------------- mensagens
def checksum(frame: bytes) -> int:
    c = 0
    for b in frame:
        c ^= b
    return c


def message(msg_id: int, payload: bytes) -> bytes:
    body = bytes([SYNC, len(payload), msg_id]) + payload
    return body + bytes([checksum(body)])


def parse_messages(buffer: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """Separa mensagens completas e válidas; devolve (mensagens, resto por ler)."""
    out, i = [], 0
    while i < len(buffer):
        if buffer[i] != SYNC:
            i += 1
            continue
        if i + 2 >= len(buffer):
            break
        n = buffer[i + 1]
        end = i + 4 + n
        if end > len(buffer):
            break
        frame = buffer[i:end]
        if checksum(frame[:-1]) == frame[-1]:
            out.append((frame[2], frame[3:3 + n]))
            i = end
        else:
            i += 1
    return out, buffer[i:]


def network_key() -> bytes | None:
    raw = os.environ.get("ERGQUEST_ANTPLUS_KEY", "").strip()
    return bytes.fromhex(raw) if len(raw) == 16 else None


def open_channel(channel: int, profile: Profile, device_number: int = 0, network: int = 0) -> list[bytes]:
    """Sequência para abrir um canal escravo para um perfil (device_number 0 = o primeiro que aparecer)."""
    return [
        message(MSG_ASSIGN, bytes([channel, 0x00, network])),
        message(MSG_CHANNEL_ID, struct.pack("<BHBB", channel, device_number, profile.device_type, 0)),
        message(MSG_PERIOD, struct.pack("<BH", channel, profile.period)),
        message(MSG_FREQUENCY, bytes([channel, RF_ANTPLUS])),
        message(MSG_OPEN, bytes([channel])),
    ]


def setup(profiles: list[str], key: bytes | None = None) -> list[bytes]:
    """Tudo o que se envia à antena para ouvir estes perfis."""
    key = key or network_key()
    if key is None:
        raise RuntimeError("falta a chave da rede ANT+ (ERGQUEST_ANTPLUS_KEY)")
    msgs = [message(MSG_RESET, b"\x00"), message(MSG_NETWORK_KEY, bytes([0]) + key)]
    for ch, name in enumerate(profiles):
        msgs += open_channel(ch, PROFILES[name])
    return msgs


# ---------------------------------------------------------------- páginas
def decode_fec(page: bytes, state: dict | None = None) -> Reading:
    """FE-C: 0x10 dados gerais, 0x19 rolo, 0x16 remo, 0x13 passadeira."""
    state = state if state is not None else {}
    p = page[0]
    r = Reading()
    if p == 0x10:
        fe = page[1] & 0x1F
        state["kind"] = FE_TYPES.get(fe, "trainer")
        r.elapsed_s = page[2] // 4
        r.speed_mps = struct.unpack_from("<H", page, 4)[0] / 1000
        r.hr_bpm = page[6] if page[6] != 0xFF else None
        r.extra["fe_type"] = state["kind"]
    elif p == 0x19:
        r.cadence = page[2] if page[2] != 0xFF else None
        r.power_w = page[5] | (page[6] & 0x0F) << 8
    elif p == 0x16:
        r.stroke_count = page[3]
        r.cadence = page[4] if page[4] != 0xFF else None
        r.power_w = struct.unpack_from("<H", page, 5)[0]
    elif p == 0x13:
        r.cadence = page[4] if page[4] != 0xFF else None
    return r


def decode_hr(page: bytes) -> Reading:
    return Reading(hr_bpm=page[7])


def decode_power(page: bytes) -> Reading:
    if page[0] != 0x10:
        return Reading()
    return Reading(power_w=struct.unpack_from("<H", page, 6)[0], cadence=page[3] if page[3] != 0xFF else None)


def decode_sdm(page: bytes) -> Reading:
    if page[0] != 0x01:
        return Reading()
    return Reading(speed_mps=(page[4] & 0x0F) + page[5] / 256)


DECODERS = {"hr": decode_hr, "power": decode_power, "sdm": decode_sdm}


# ---------------------------------------------------------------- controlo FE-C
def page_target_power(watts: float) -> bytes:
    """Página 0x31: ERG (0,25 W)."""
    return bytes([0x31, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]) + struct.pack("<H", int(round(watts * 4)))


def page_track_resistance(grade_pct: float, crr: float = 0.004) -> bytes:
    """Página 0x33: simulação de declive (0,01 %, desfasado de −200 %)."""
    raw = int(round((max(-200.0, min(200.0, grade_pct)) + 200.0) * 100))
    return bytes([0x33, 0xFF, 0xFF, 0xFF, 0xFF]) + struct.pack("<H", raw) + bytes([int(round(crr / 5e-5)) & 0xFF])


def acknowledged(channel: int, page: bytes) -> bytes:
    return message(MSG_ACK, bytes([channel]) + page)


# ---------------------------------------------------------------- antena USB (pyusb, opcional)
STICKS = ((0x0FCF, 0x1008), (0x0FCF, 0x1009))   # ANTUSB2, ANTUSB-m


def find_stick():
    """A antena USB ANT+ ligada, ou None. Precisa de `pyusb` (e libusb)."""
    try:
        import usb.core
    except ImportError:
        return None
    for vid, pid in STICKS:
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is not None:
            return dev
    return None


class AntStick:
    """Lê e escreve na antena. `poll()` devolve (canal, página) das mensagens recebidas."""

    def __init__(self, dev=None):
        self.dev = dev or find_stick()
        if self.dev is None:
            raise RuntimeError("antena ANT+ não encontrada")
        self.dev.set_configuration()
        cfg = self.dev.get_active_configuration()
        intf = cfg[(0, 0)]
        self.ep_out = next(e for e in intf if not e.bEndpointAddress & 0x80)
        self.ep_in = next(e for e in intf if e.bEndpointAddress & 0x80)
        self.buffer = b""

    def send(self, frames: list[bytes]) -> None:
        for f in frames:
            self.ep_out.write(f)

    def poll(self, timeout_ms: int = 100) -> list[tuple[int, bytes]]:
        try:
            self.buffer += bytes(self.ep_in.read(64, timeout=timeout_ms))
        except Exception:                            # sem dados neste intervalo
            return []
        msgs, self.buffer = parse_messages(self.buffer)
        return [(p[0], p[1:9]) for mid, p in msgs if mid in (MSG_BROADCAST, MSG_ACK) and len(p) >= 9]

"""O estado do banco de testes e as ações que a página pode pedir."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

from ..devices import ble
from ..devices.adapters import MANUAL_TREADMILL, DomyosRower, ManualTreadmill, looks_like_domyos
from ..devices.hub import KIND_NAMES, Device, Hub, Kind, check
from .recorder import Recorder

PRIMARY = ("trainer", "treadmill", "rower", "power_meter", "footpod", "heart_rate")


@dataclass
class Link:
    address: str
    name: str
    services: list
    device: Device | None
    kinds: list[str]
    adapter: object | None = None
    notifications: int = 0
    last_char: str = ""
    last_hex: str = ""
    reading: dict = field(default_factory=dict)
    control: bool = False
    crank: tuple | None = None
    responses: list[str] = field(default_factory=list)

    @property
    def chars(self) -> list[dict]:
        return [c for s in self.services for c in s["chars"]]


def _reading_dict(r) -> dict:
    out = {}
    for k in ("power_w", "cadence", "speed_mps", "distance_m", "hr_bpm", "incline_pct", "stroke_count", "pace_s_500m"):
        v = getattr(r, k)
        if v is not None:
            out[k] = round(v, 2) if isinstance(v, float) else v
    if r.extra.get("rr_s"):
        out["rr_ms"] = [round(x * 1000) for x in r.extra["rr_s"]]
    return out


class Bench:
    def __init__(self, backend_factory, out_dir: str, clock=time.monotonic):
        self.lock = threading.RLock()
        self.events: deque[str] = deque(maxlen=200)
        self.recorder = Recorder(out_dir)
        self.backend = backend_factory(self.log)
        self.clock = clock
        self.found: list[dict] = []
        self.links: dict[str, Link] = {}
        self.hub = Hub([], clock=clock)
        self.treadmill = ManualTreadmill()
        self.treadmill_on = False
        self.scanning = False
        self.log(f"banco de testes iniciado ({self.backend.name}); pasta: {self.recorder.dir}")

    # ------------------------------------------------------------ registo
    def log(self, text: str) -> None:
        line = self.recorder.event(text)
        with self.lock:
            self.events.append(line)

    def _save_devices(self) -> None:
        self.recorder.devices({a: {"nome": l.name, "tipos": l.kinds, "servicos": l.services} for a, l in self.links.items()})

    # ------------------------------------------------------------ ações
    def scan(self, timeout: float = 6.0) -> list[dict]:
        self.scanning = True
        self.log("a procurar aparelhos Bluetooth…")
        try:
            found = self.backend.scan(timeout)
        finally:
            self.scanning = False
        for d in found:
            d["kinds"] = ble.classify(d.get("services", []), ftms_service_data=bytes.fromhex(d.get("ftms_data") or ""))
            if not d["kinds"] and looks_like_domyos(d.get("name")):
                d["kinds"] = ["domyos"]
        found.sort(key=lambda d: (not d["kinds"], not d["name"], -(d.get("rssi") or -999)))
        with self.lock:
            self.found = found
        self.log(f"encontrados {len(found)} aparelhos ({sum(1 for d in found if d['kinds'])} reconhecidos)")
        return found

    def connect(self, address: str) -> dict:
        name = next((d["name"] for d in self.found if d["address"] == address), address)
        self.log(f"a ligar a {name}…")
        info = self.backend.connect(address, self._on_notify, self._on_disconnect)
        services = info["services"]
        chars = [c["uuid"] for s in services for c in s["chars"]]
        kinds = ble.classify([s["uuid"] for s in services], chars)
        adapter = None
        if not kinds and looks_like_domyos(name):
            adapter = DomyosRower(name)
            device = adapter.device
            kinds = ["rower"]
        else:
            main = next((k for k in PRIMARY if k in kinds), None)
            device = None
            if main:
                device = Device(address, name, Kind(main), "ble", address,
                                controllable=main in ("trainer", "treadmill") and ble.CH_FTMS_CONTROL in chars)
        link = Link(address, name, services, device, kinds, adapter)
        with self.lock:
            self.links[address] = link
            if device:
                self.hub.devices[device.id] = device
        self._save_devices()
        what = ", ".join(KIND_NAMES.get(Kind(k), k) if k in Kind._value2member_map_ else k for k in kinds) or "tipo desconhecido"
        self.log(f"ligado a {name}: {what}; {len(chars)} características")
        if device and device.controllable:
            self._control(link)
        return {"address": address, "kinds": kinds}

    def _control(self, link: Link) -> None:
        try:
            self.backend.write(link.address, ble.CH_FTMS_CONTROL, ble.cmd_request_control())
            self.backend.write(link.address, ble.CH_FTMS_CONTROL, ble.cmd_start())
            link.control = True
            self.log(f"{link.name}: controlo FTMS pedido")
        except Exception as err:
            self.log(f"{link.name}: o pedido de controlo falhou: {err}")

    def disconnect(self, address: str) -> None:
        self.backend.disconnect(address)
        self._on_disconnect(address)

    def erg(self, address: str, watts: float) -> None:
        link = self.links[address]
        self.backend.write(address, ble.CH_FTMS_CONTROL, ble.cmd_target_power(watts))
        self.log(f"{link.name}: ERG {watts:.0f} W")

    def grade(self, address: str, pct: float) -> None:
        link = self.links[address]
        self.backend.write(address, ble.CH_FTMS_CONTROL, ble.cmd_simulation(pct))
        self.log(f"{link.name}: declive {pct:+.1f} % (simulação)")

    def write_hex(self, address: str, char: str, hex_text: str, response: bool = True) -> None:
        data = bytes.fromhex(hex_text.replace(" ", ""))
        link = self.links[address]
        self.backend.write(address, char, data, response)
        self.log(f"{link.name}: escrito {data.hex(' ')} em {char}")

    def record(self, on: bool, marker: str = "") -> None:
        if on:
            self.recorder.start(marker)
        else:
            self.recorder.stop()
        with self.lock:
            self.events.append(f"{time.strftime('%H:%M:%S')} gravação {'ligada' if on else 'desligada'}")

    def set_marker(self, marker: str) -> None:
        self.recorder.set_marker(marker)
        with self.lock:
            self.events.append(f"{time.strftime('%H:%M:%S')} marca: {marker}")

    def treadmill_action(self, action: str, value: float | None = None) -> None:
        now = self.clock()
        if action == "on":
            self.treadmill_on = True
            self.treadmill.set(now=now)
            self.hub.devices[MANUAL_TREADMILL.id] = MANUAL_TREADMILL
            self.log("passadeira manual ligada")
        elif action == "off":
            self.treadmill_on = False
            self.hub.devices.pop(MANUAL_TREADMILL.id, None)
            self.log("passadeira manual desligada")
        elif action == "speed":
            self.treadmill.set(speed_kmh=value, now=now)
        elif action == "incline":
            self.treadmill.set(incline_pct=value, now=now)
        elif action == "nudge_speed":
            self.treadmill.nudge(d_speed=value or 0.0, now=now)
        elif action == "nudge_incline":
            self.treadmill.nudge(d_incline=value or 0.0, now=now)
        elif action == "ask":
            self.log(f"o jogo pede: {self.treadmill.ask(value or 12.0)}")
        elif action == "reset":
            self.treadmill.distance_m = 0.0

    # ------------------------------------------------------------ dados
    def _on_notify(self, address: str, char: str, data: bytes) -> None:
        link = self.links.get(address)
        if link is None:
            return
        self.recorder.raw(link.name, address, char, data)
        link.notifications += 1
        link.last_char, link.last_hex = char, data.hex(" ")
        r = None
        if char == ble.CH_FTMS_CONTROL:
            resp = ble.parse_control_response(data)
            if resp:
                text = f"resposta ao comando 0x{resp[0]:02x}: {'OK' if resp[1] == 1 else f'código {resp[1]}'}"
                link.responses = (link.responses + [text])[-5:]
                self.log(f"{link.name}: {text}")
            return
        parse = ble.PARSERS.get(char)
        try:
            if parse is not None:
                r = parse(data)
                if char == ble.CH_CP and "crank" in r.extra:
                    cad = ble.cadence_from_crank(link.crank, r.extra["crank"])
                    link.crank = r.extra["crank"]
                    if cad is not None:
                        r.cadence = round(cad, 1)
            elif link.adapter is not None:
                r = link.adapter.decode(data)
        except Exception as err:
            self.log(f"{link.name}: não consegui ler {char} ({data.hex(' ')}): {err}")
            return
        if r is not None:
            with self.lock:
                link.reading = {**link.reading, **_reading_dict(r)}
                if link.device:
                    self.hub.feed(link.device.id, r)
            self.recorder.reading(link.name, r, estimated=bool(link.device and link.device.estimated))

    def _on_disconnect(self, address: str) -> None:
        with self.lock:
            link = self.links.pop(address, None)
            if link and link.device:
                self.hub.devices.pop(link.device.id, None)
        if link:
            self.log(f"desligado: {link.name}")
            self._save_devices()

    def devices(self) -> list[Device]:
        out = [l.device for l in self.links.values() if l.device]
        if self.treadmill_on:
            out.append(MANUAL_TREADMILL)
        return out

    def state(self) -> dict:
        now = self.clock()
        if self.treadmill_on:
            r = self.treadmill.reading(now)
            self.hub.feed(MANUAL_TREADMILL.id, r)
            self.recorder.reading(MANUAL_TREADMILL.name, r, estimated=True)
        live = self.hub.live()
        checks = {}
        for sport in ("bike", "run", "row"):
            c = check(sport, self.devices())
            checks[sport] = {"ok": c.ok, "summary": c.using(), "missing": c.missing_text() if c.missing else "",
                             "warnings": c.warnings, "erg": c.erg_capable, "ranked": c.ranked}
        with self.lock:
            return {
                "backend": self.backend.name, "folder": str(self.recorder.dir), "scanning": self.scanning,
                "found": self.found,
                "links": [{"address": l.address, "name": l.name, "kinds": l.kinds,
                           "estimated": bool(l.device and l.device.estimated), "control": l.control,
                           "controllable": bool(l.device and l.device.controllable),
                           "notifications": l.notifications, "last_char": l.last_char, "last_hex": l.last_hex,
                           "reading": l.reading, "responses": l.responses,
                           "writable": [c["uuid"] for c in l.chars if {"write", "write-without-response"} & set(c["props"])],
                           "chars": l.chars}
                          for l in self.links.values()],
                "live": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in vars(live).items()},
                "checks": checks,
                "treadmill": {"on": self.treadmill_on, "speed_kmh": self.treadmill.speed_kmh,
                              "incline_pct": self.treadmill.incline_pct, "distance_m": round(self.treadmill.distance_m),
                              "prompt": self.treadmill.prompt},
                "recording": {"on": self.recorder.on, "marker": self.recorder.marker, "rows": self.recorder.rows},
                "events": list(self.events)[-60:],
            }

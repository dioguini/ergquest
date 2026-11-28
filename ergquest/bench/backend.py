"""Transportes do banco de testes: Bluetooth real (bleak) e simulado.

Os dois têm a mesma interface síncrona (a página chama-a a partir de pedidos
HTTP); o Bluetooth corre num ciclo asyncio numa linha própria.
"""
from __future__ import annotations

import asyncio
import math
import random
import struct
import threading
import time

from ..devices import ble, sim


class BleBackend:
    name = "Bluetooth"

    def __init__(self, log=print):
        import bleak  # noqa: F401  (falha cedo, com mensagem clara, se não estiver instalado)
        self.log = log
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.clients: dict = {}

    def _run(self, coro, timeout: float):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def scan(self, timeout: float = 6.0) -> list[dict]:
        async def go():
            from bleak import BleakScanner
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
            out = []
            for address, (dev, adv) in found.items():
                sd = (adv.service_data or {}).get(ble.SVC_FTMS)
                out.append({"address": address, "name": dev.name or adv.local_name or "", "rssi": adv.rssi,
                            "services": [s.lower() for s in adv.service_uuids or []],
                            "ftms_data": bytes(sd).hex() if sd else ""})
            return out
        return self._run(go(), timeout + 15)

    def connect(self, address: str, on_notify, on_disconnect) -> dict:
        async def go():
            from bleak import BleakClient
            client = BleakClient(address, disconnected_callback=lambda _c: on_disconnect(address))
            await client.connect(timeout=20.0)
            self.clients[address] = client
            services = [{"uuid": s.uuid.lower(),
                         "chars": [{"uuid": c.uuid.lower(), "props": sorted(c.properties)} for c in s.characteristics]}
                        for s in client.services]
            for s in client.services:
                for c in s.characteristics:
                    if "notify" in c.properties or "indicate" in c.properties:
                        try:
                            await client.start_notify(c, lambda _ch, data, u=c.uuid.lower(): on_notify(address, u, bytes(data)))
                        except Exception as err:                       # alguns aparelhos recusam certas subscrições
                            self.log(f"{address}: não subscreveu {c.uuid}: {err}")
            return {"services": services}
        return self._run(go(), 45)

    def disconnect(self, address: str) -> None:
        client = self.clients.pop(address, None)
        if client is not None:
            self._run(client.disconnect(), 15)

    def write(self, address: str, char: str, data: bytes, response: bool = True) -> None:
        client = self.clients[address]
        self._run(client.write_gatt_char(char, data, response=response), 15)


# ---------------------------------------------------------------- simulado
SIM_CUSTOM_SVC = "0000fff0-0000-1000-8000-00805f9b34fb"     # serviço próprio genérico (só no simulador)
SIM_CUSTOM_NOTIFY = "0000fff1-0000-1000-8000-00805f9b34fb"
SIM_CUSTOM_WRITE = "0000fff2-0000-1000-8000-00805f9b34fb"

SIM_DEVICES = [
    {"address": "SIM:01", "name": "KICKR CORE 5A2B (simulado)", "rssi": -48,
     "services": [ble.SVC_FTMS, ble.SVC_CP], "ftms_data": "012000",
     "gatt": [{"uuid": ble.SVC_FTMS, "chars": [{"uuid": ble.CH_FTMS_FEATURE, "props": ["read"]},
                                               {"uuid": ble.CH_INDOOR_BIKE, "props": ["notify"]},
                                               {"uuid": ble.CH_FTMS_CONTROL, "props": ["indicate", "write"]}]},
              {"uuid": ble.SVC_CP, "chars": [{"uuid": ble.CH_CP, "props": ["notify"]}]}]},
    {"address": "SIM:02", "name": "Polar H10 8C3D (simulado)", "rssi": -60, "services": [ble.SVC_HR], "ftms_data": "",
     "gatt": [{"uuid": ble.SVC_HR, "chars": [{"uuid": ble.CH_HR, "props": ["notify"]}]}]},
    {"address": "SIM:03", "name": "DOMYOS-ROW-500 (simulado)", "rssi": -66, "services": [SIM_CUSTOM_SVC], "ftms_data": "",
     "gatt": [{"uuid": SIM_CUSTOM_SVC, "chars": [{"uuid": SIM_CUSTOM_NOTIFY, "props": ["notify"]},
                                                 {"uuid": SIM_CUSTOM_WRITE, "props": ["write", "write-without-response"]}]}]},
]


class SimBackend:
    """Aparelhos simulados que respondem como os reais (ERG, declive, pedidos de controlo)."""
    name = "Simulado"

    def __init__(self, log=print, period: float = 1.0):
        self.log, self.period = log, period
        self.links: dict[str, tuple] = {}
        self.erg_w: float | None = None
        self.grade = 0.0
        self.t0 = time.monotonic()
        self.strokes = 0
        self._stop = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()

    def scan(self, timeout: float = 1.0) -> list[dict]:
        return [{k: v for k, v in d.items() if k != "gatt"} for d in SIM_DEVICES]

    def connect(self, address: str, on_notify, on_disconnect) -> dict:
        d = next(d for d in SIM_DEVICES if d["address"] == address)
        self.links[address] = (on_notify, on_disconnect)
        return {"services": d["gatt"]}

    def disconnect(self, address: str) -> None:
        link = self.links.pop(address, None)
        if link:
            link[1](address)

    def write(self, address: str, char: str, data: bytes, response: bool = True) -> None:
        if char == ble.CH_FTMS_CONTROL and data:
            op = data[0]
            if op == ble.OP_TARGET_POWER:
                self.erg_w = struct.unpack_from("<h", data, 1)[0]
            elif op == ble.OP_SIMULATION:
                self.erg_w = None
                self.grade = struct.unpack_from("<h", data, 3)[0] / 100
            on_notify = self.links[address][0]
            on_notify(address, ble.CH_FTMS_CONTROL, bytes([ble.OP_RESPONSE, op, 0x01]))

    def emit_once(self) -> None:
        t = time.monotonic() - self.t0
        for address, (on_notify, _) in list(self.links.items()):
            if address == "SIM:01":
                w = self.erg_w if self.erg_w is not None else 180 + 12 * self.grade + 15 * math.sin(t / 5)
                w *= random.uniform(0.97, 1.03)
                v = max(2.0, 11.0 - 0.6 * self.grade)
                on_notify(address, ble.CH_INDOOR_BIKE, sim.ftms_indoor_bike(v, 88 + random.uniform(-3, 3), w))
                on_notify(address, ble.CH_CP, struct.pack("<Hh", 0, int(w)))
            elif address == "SIM:02":
                hr = int(128 + 10 * math.sin(t / 20) + random.uniform(-1, 1))
                on_notify(address, ble.CH_HR, sim.hr_measurement(hr, [60 / hr]))
            elif address == "SIM:03":
                self.strokes += 1
                on_notify(address, SIM_CUSTOM_NOTIFY, bytes([0xF0, 0xBC, self.strokes & 0xFF, 24, random.randint(0, 255)]))

    def _pump(self) -> None:
        while not self._stop.wait(self.period):
            self.emit_once()

    def close(self) -> None:
        self._stop.set()

"""Gravação do que acontece no banco de testes, numa pasta por sessão.

    ~/ErgQuest/bancada/AAAAMMDD-HHMMSS/
        eventos.log      tudo o que aconteceu (sempre)
        aparelhos.json   serviços e características de cada aparelho ligado (sempre)
        notificacoes.csv bytes de cada notificação, com a marca do momento (enquanto se grava)
        leituras.csv     leituras descodificadas (enquanto se grava)
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path


class Recorder:
    def __init__(self, root: str | Path):
        self.dir = Path(root).expanduser() / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.t0 = time.monotonic()
        self.on = False
        self.marker = ""
        self.rows = 0
        self._raw = self._read = None
        self._events = open(self.dir / "eventos.log", "a", encoding="utf-8")

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def event(self, text: str) -> str:
        line = f"{datetime.now():%H:%M:%S} {text}"
        self._events.write(line + "\n")
        self._events.flush()
        return line

    def devices(self, info: dict) -> None:
        (self.dir / "aparelhos.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")

    def start(self, marker: str = "") -> None:
        if self._raw is None:
            new = not (self.dir / "notificacoes.csv").exists()
            self._raw_f = open(self.dir / "notificacoes.csv", "a", newline="", encoding="utf-8")
            self._read_f = open(self.dir / "leituras.csv", "a", newline="", encoding="utf-8")
            self._raw, self._read = csv.writer(self._raw_f), csv.writer(self._read_f)
            if new:
                self._raw.writerow(["t_s", "aparelho", "endereco", "caracteristica", "bytes_hex", "marca"])
                self._read.writerow(["t_s", "aparelho", "potencia_w", "cadencia", "velocidade_kmh", "distancia_m",
                                     "fc_bpm", "inclinacao_pct", "remadas", "estimado", "marca"])
        self.on = True
        self.marker = marker
        self.event(f"gravação iniciada{f' — {marker}' if marker else ''}")

    def stop(self) -> None:
        if self.on:
            self.on = False
            self._raw_f.flush()
            self._read_f.flush()
            self.event(f"gravação parada ({self.rows} notificações)")

    def set_marker(self, marker: str) -> None:
        self.marker = marker
        self.event(f"marca: {marker}")

    def raw(self, name: str, address: str, char: str, data: bytes) -> None:
        if self.on:
            self._raw.writerow([self.now(), name, address, char, data.hex(" "), self.marker])
            self.rows += 1
            if self.rows % 20 == 0:
                self._raw_f.flush()

    def reading(self, name: str, r, estimated: bool = False) -> None:
        if self.on and r is not None:
            kmh = round(r.speed_mps * 3.6, 2) if r.speed_mps is not None else ""
            self._read.writerow([self.now(), name, r.power_w if r.power_w is not None else "",
                                 r.cadence if r.cadence is not None else "", kmh,
                                 r.distance_m if r.distance_m is not None else "", r.hr_bpm or "",
                                 r.incline_pct if r.incline_pct is not None else "", r.stroke_count or "",
                                 int(estimated), self.marker])

    def close(self) -> None:
        self.stop()
        for f in (getattr(self, "_raw_f", None), getattr(self, "_read_f", None), self._events):
            if f:
                f.close()

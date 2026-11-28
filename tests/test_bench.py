import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from ergquest.bench.backend import SIM_CUSTOM_WRITE, SimBackend
from ergquest.bench.core import Bench
from ergquest.bench.server import serve


class BenchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bench = Bench(lambda log: SimBackend(log, period=3600), self.tmp.name)

    def tearDown(self):
        self.bench.backend.close()
        self.bench.recorder.close()
        self.tmp.cleanup()

    def connect_all(self):
        found = self.bench.scan(0.1)
        for d in found:
            self.bench.connect(d["address"])
        return found

    def test_scan_recognises_devices(self):
        found = {d["name"]: d["kinds"] for d in self.connect_all()}
        self.assertEqual(found["KICKR CORE 5A2B (simulado)"], ["trainer"])
        self.assertEqual(found["Polar H10 8C3D (simulado)"], ["heart_rate"])
        self.assertEqual(found["DOMYOS-ROW-500 (simulado)"], ["domyos"])
        links = {l["name"]: l for l in self.bench.state()["links"]}
        self.assertTrue(links["KICKR CORE 5A2B (simulado)"]["control"])          # controlo pedido ao ligar
        self.assertTrue(links["DOMYOS-ROW-500 (simulado)"]["estimated"])

    def test_erg_live_data_and_checks(self):
        self.connect_all()
        self.bench.erg("SIM:01", 230)
        self.bench.backend.emit_once()
        st = self.bench.state()
        self.assertAlmostEqual(st["live"]["power_w"], 230, delta=10)
        self.assertIsNotNone(st["live"]["cadence"])
        self.assertIsNotNone(st["live"]["hr_bpm"])
        self.assertTrue(st["checks"]["bike"]["ok"] and st["checks"]["bike"]["erg"] and st["checks"]["bike"]["ranked"])
        self.assertTrue(st["checks"]["row"]["ok"])
        self.assertFalse(st["checks"]["row"]["ranked"])
        self.assertFalse(st["checks"]["run"]["ok"])
        self.bench.treadmill_action("on")
        self.assertTrue(self.bench.state()["checks"]["run"]["ok"])

    def test_capture_files(self):
        self.connect_all()
        self.bench.record(True, "resistência 5")
        self.bench.backend.emit_once()
        self.bench.write_hex("SIM:03", SIM_CUSTOM_WRITE, "f0 c8 01")
        self.bench.set_marker("ritmo 24")
        self.bench.backend.emit_once()
        self.bench.record(False)
        d = self.bench.recorder.dir
        raw = (d / "notificacoes.csv").read_text(encoding="utf-8").splitlines()
        self.assertTrue(raw[0].startswith("t_s,aparelho"))
        self.assertTrue(any("resistência 5" in r and "fff1" in r for r in raw))
        self.assertTrue(any("ritmo 24" in r for r in raw))
        self.assertIn("escrito f0 c8 01", (d / "eventos.log").read_text(encoding="utf-8"))
        self.assertIn("DOMYOS", (d / "aparelhos.json").read_text(encoding="utf-8"))

    def test_http_api(self):
        httpd = serve(self.bench, 0)
        port = httpd.server_address[1]
        try:
            def call(path, body=None):
                req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.read().decode("utf-8")
            self.assertIn("Banco de testes ErgQuest", call("/"))
            call("/api/scan", {"timeout": 0.1})
            call("/api/connect", {"address": "SIM:02"})
            call("/api/treadmill", {"action": "on"})
            call("/api/treadmill", {"action": "nudge_speed", "value": 0.5})
            st = json.loads(call("/api/state"))
            self.assertEqual(st["treadmill"]["speed_kmh"], 0.5)
            self.assertEqual(len(st["links"]), 1)
            with self.assertRaises(urllib.error.HTTPError):
                call("/api/erg", {"address": "SIM:99", "watts": 100})
        finally:
            httpd.shutdown()

import struct
import unittest

from ergquest.devices import ant, ble, sim
from ergquest.devices.hub import Device, Hub, Kind, available_sports, check
from ergquest.game.cities import Sport
from ergquest.game.progression import Profile, xp_for_level
from ergquest.game.session import PlayerState, SessionError


class BleTest(unittest.TestCase):
    def test_indoor_bike_round_trip(self):
        r = ble.parse_indoor_bike(sim.ftms_indoor_bike(10.0, 90, 250, hr=142))
        self.assertAlmostEqual(r.speed_mps, 10.0, places=2)
        self.assertEqual((r.cadence, r.power_w, r.hr_bpm), (90, 250, 142))

    def test_indoor_bike_spec_example(self):
        # flags 0x0044: velocidade, cadência, potência — 30,00 km/h, 85 rpm, 200 W
        data = struct.pack("<HHHh", 0x0044, 3000, 170, 200)
        r = ble.parse_indoor_bike(data)
        self.assertAlmostEqual(r.speed_mps * 3.6, 30.0)
        self.assertEqual((r.cadence, r.power_w), (85, 200))

    def test_treadmill_and_rower(self):
        t = ble.parse_treadmill(sim.ftms_treadmill(3.5, 4.0, 1234, hr=150))
        self.assertAlmostEqual(t.speed_mps, 3.5, places=2)
        self.assertEqual((t.incline_pct, t.distance_m, t.hr_bpm), (4.0, 1234, 150))
        r = ble.parse_rower(sim.ftms_rower(24, 310, 120, 210))
        self.assertEqual((r.cadence, r.stroke_count, r.pace_s_500m, r.power_w), (24, 310, 120, 210))
        self.assertAlmostEqual(r.speed_mps, 500 / 120)

    def test_hr_power_rsc(self):
        h = ble.parse_hr(sim.hr_measurement(151, [0.8, 0.79]))
        self.assertEqual(h.hr_bpm, 151)
        self.assertAlmostEqual(h.extra["rr_s"][0], 0.8, places=2)
        self.assertEqual(ble.parse_hr(bytes([0x01, 0x2C, 0x01])).hr_bpm, 300)     # formato de 16 bits
        cp = ble.parse_cycling_power(struct.pack("<HhHH", 0x0020, 320, 1000, 2048))
        self.assertEqual(cp.power_w, 320)
        self.assertAlmostEqual(ble.cadence_from_crank((999, 1024), cp.extra["crank"]), 60.0)
        self.assertAlmostEqual(ble.cadence_from_crank((65535, 65024), (0, 512)), 60.0)   # volta dos contadores
        rsc = ble.parse_rsc(struct.pack("<BHB", 0x04, 3 * 256, 170))
        self.assertEqual((rsc.speed_mps, rsc.cadence, rsc.extra["running"]), (3.0, 170, True))

    def test_control_commands(self):
        self.assertEqual(ble.cmd_target_power(250), bytes([0x05, 0xFA, 0x00]))
        sim_cmd = ble.cmd_simulation(5.0)
        self.assertEqual(sim_cmd[0], 0x11)
        self.assertEqual(struct.unpack("<hhBB", sim_cmd[1:]), (0, 500, 40, 51))
        self.assertEqual(struct.unpack("<Bh", ble.cmd_target_incline(3.5)), (0x03, 35))
        self.assertEqual(ble.parse_control_response(bytes([0x80, 0x05, 0x01])), (0x05, 1))

    def test_classify(self):
        self.assertEqual(ble.classify([ble.SVC_FTMS], [ble.CH_INDOOR_BIKE]), ["trainer"])
        self.assertEqual(ble.classify([ble.SVC_FTMS], ftms_service_data=bytes([1, 0x10, 0])), ["rower"])
        self.assertEqual(ble.classify([ble.SVC_FTMS], ftms_service_data=bytes([1, 0x01, 0])), ["treadmill"])
        self.assertEqual(ble.classify([ble.SVC_HR, ble.SVC_CP]), ["power_meter", "heart_rate"])
        self.assertEqual(ble.classify([ble.SVC_RSC]), ["footpod"])


class AntTest(unittest.TestCase):
    def test_framing(self):
        m = ant.message(ant.MSG_OPEN, bytes([0]))
        self.assertEqual(m, bytes([0xA4, 1, 0x4B, 0, 0xA4 ^ 1 ^ 0x4B]))
        junk = b"\x00\x13" + m + ant.message(ant.MSG_BROADCAST, bytes(9))[:-3]
        msgs, rest = ant.parse_messages(junk)
        self.assertEqual(msgs, [(0x4B, b"\x00")])
        self.assertTrue(rest.startswith(b"\xa4"))                  # mensagem incompleta fica para depois

    def test_channel_setup(self):
        frames = ant.open_channel(1, ant.PROFILES["hr"])
        msgs = [ant.parse_messages(f)[0][0] for f in frames]
        self.assertEqual([m[0] for m in msgs], [0x42, 0x51, 0x43, 0x45, 0x4B])
        self.assertEqual(struct.unpack("<BHBB", msgs[1][1]), (1, 0, 120, 0))
        self.assertEqual(struct.unpack("<BH", msgs[2][1]), (1, 8070))
        self.assertEqual(msgs[3][1], bytes([1, 57]))
        with self.assertRaises(RuntimeError):
            ant.setup(["hr"], key=None) if ant.network_key() is None else (_ for _ in ()).throw(RuntimeError())
        self.assertEqual(len(ant.setup(["fe-c", "hr"], key=bytes(8))), 2 + 2 * 5)

    def test_pages(self):
        st = {}
        g = ant.decode_fec(sim.ant_fec_general(22, 4.2, 150), st)
        self.assertEqual((st["kind"], g.hr_bpm), ("rower", 150))
        self.assertAlmostEqual(g.speed_mps, 4.2)
        t = ant.decode_fec(sim.ant_fec_trainer(1234, 92))
        self.assertEqual((t.power_w, t.cadence), (1234, 92))
        self.assertEqual(ant.decode_hr(sim.ant_hr(133)).hr_bpm, 133)
        self.assertEqual(ant.page_target_power(250)[6:], struct.pack("<H", 1000))
        p = ant.page_track_resistance(5.0)
        self.assertEqual(struct.unpack("<H", p[5:7])[0], 20500)
        self.assertEqual(p[7], 80)                                  # crr 0,004 em unidades de 5e-5


class HubTest(unittest.TestCase):
    def test_requirements_per_sport(self):
        home = [sim.SMART_TRAINER, sim.HR_STRAP]
        self.assertTrue(check("bike", home).ok)
        self.assertTrue(check("bike", home).erg_capable)
        run = check("run", home)
        self.assertFalse(run.ok)
        self.assertEqual(run.missing, ["passadeira", "sensor de passada"])
        self.assertEqual(available_sports(home), ["bike"])
        self.assertEqual(available_sports([sim.TREADMILL, sim.ROWER]), ["run", "row"])

    def test_heart_rate_when_required(self):
        self.assertTrue(check("row", [sim.ROWER]).ok)
        self.assertIn("sem banda cardíaca", " ".join(check("row", [sim.ROWER]).warnings))
        strict = check("row", [sim.ROWER], hr_required=True)
        self.assertFalse(strict.ok)
        self.assertEqual(strict.missing, ["banda cardíaca"])
        self.assertTrue(check("gym", []).ok)

    def test_power_meter_bike_without_control(self):
        c = check("bike", [sim.POWER_METER])
        self.assertTrue(c.ok)
        self.assertFalse(c.erg_capable)
        self.assertTrue(any("ERG" in w for w in c.warnings))

    def test_priority_and_staleness(self):
        now = [0.0]
        hub = Hub([sim.SMART_TRAINER, sim.POWER_METER, sim.HR_STRAP], clock=lambda: now[0])
        hub.feed("sim-trainer", ble.parse_indoor_bike(sim.ftms_indoor_bike(9.0, 88, 240, hr=120)))
        hub.feed("sim-pm", ant.decode_power(bytes([0x10, 1, 0xFF, 91, 0, 0]) + struct.pack("<H", 236)))
        hub.feed("sim-hr", ant.decode_hr(sim.ant_hr(141)))
        live = hub.live()
        self.assertEqual((live.power_w, live.cadence, live.hr_bpm), (236, 91, 141))   # pedais e banda mandam
        self.assertEqual(live.sources["power_w"], "Pedais de potência")
        now[0] = 5.0
        hub.feed("sim-trainer", ble.parse_indoor_bike(sim.ftms_indoor_bike(9.0, 88, 240, hr=120)))
        live = hub.live()
        self.assertEqual((live.power_w, live.hr_bpm), (240, 120))   # os outros calaram-se: o rolo assume


class SwapTest(unittest.TestCase):
    def setUp(self):
        self.ana = Profile("ana", 64, xp={"bike": xp_for_level(9), "run": xp_for_level(3)})

    def test_swap_needs_devices(self):
        p = PlayerState("ana", "lisboa", "n-baixa")
        p.start(Sport.BIKE, 0, devices=[sim.SMART_TRAINER], profile=self.ana)
        with self.assertRaises(SessionError) as ctx:
            p.swap(Sport.RUN, 60, devices=[sim.SMART_TRAINER], profile=self.ana)
        self.assertIn("passadeira", str(ctx.exception))
        self.assertIsNone(p.current.ended_at)                       # a sessão de bicicleta continua
        old, new = p.swap(Sport.RUN, 60, devices=[sim.SMART_TRAINER, sim.TREADMILL], profile=self.ana)
        self.assertEqual((old.sport, new.sport, p.world_map), (Sport.BIKE, Sport.RUN, "terra"))

    def test_swap_needs_zone_open_for_the_new_sport(self):
        p = PlayerState("ana", "lisboa", "n-norte")                 # aberta para o ciclismo (6), não para a corrida
        p.start(Sport.BIKE, 0, devices=[sim.SMART_TRAINER], profile=self.ana)
        with self.assertRaises(SessionError) as ctx:
            p.swap(Sport.RUN, 60, devices=[sim.TREADMILL], profile=self.ana)
        self.assertIn("Norte", str(ctx.exception))

    def test_rowing_changes_map(self):
        p = PlayerState("ana", "lisboa", "n-baixa", at_dock=True)
        p.start(Sport.BIKE, 0, devices=[sim.SMART_TRAINER], profile=self.ana)
        p.swap(Sport.ROW, 60, devices=[sim.ROWER], profile=self.ana)
        self.assertEqual((p.world_map, p.map_zone()), ("rio", "r-baixa"))
        p2 = PlayerState("ana", "lisboa", "n-centro", at_dock=True)
        p2.start(Sport.BIKE, 0, devices=[sim.SMART_TRAINER], profile=self.ana)
        with self.assertRaises(SessionError):                       # Tejo · Centro abre no nível 3 de remo
            p2.swap(Sport.ROW, 60, devices=[sim.ROWER], profile=self.ana)

"""Demonstração sem hardware: um dia no ErgQuest, na Área Metropolitana de Lisboa.

    python -m ergquest.demo

Usa o grafo de `data/lisboa-metro.json.gz` (OpenStreetMap via Overture +
altimetria Copernicus; para o refazer: `python tools/build_metro.py`).
Cada modalidade tem o seu nível. A Ana: ciclismo 9, corrida 4, remo 1; tem
rolo e passadeira (Bluetooth) e banda cardíaca (ANT+), mas não tem remo.

1. TREINO — 3 × 6′ a 95 % FTP, ERG desligado, no mundo: no Cais do Sodré a
   Ana vê os ramos reais da interseção, o jogo sugere o que encaixa nos
   blocos, e ela pedala a marginal com o declive real a chegar ao rolo.
2. JOGO — entrega de comida de um restaurante (fictício, num sítio real) até
   ao Miradouro de Santa Luzia, pela rota do GPS.
3. TROCA + JOGO — em Santa Luzia troca para a corrida (o jogo verifica a
   passadeira e o mapa passa a mostrar as zonas da corrida); tenta remar e
   não pode (sem remo); faz um recado a pé em Alfama.
4. JOGO — riquexó com dois passageiros da Praça do Comércio ao Castelo.
5. EFEITO COLATERAL — carga, forma, XP e desbloqueios.
6. LIVRE — a Ana pedala para oeste sem destino, chega ao limite da zona
   Oeste (ainda fechada) e o GPS leva-a de volta.
7. EXPERIENTE — o Rui (nível 20) leva uma entrega à outra margem pela Ponte
   25 de Abril e aceita um pedido de remo de margem a margem.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path

from .game import errands, strength, taxi
from .game.cities import Sport
from .game.missions import Kind, OrderBoard, sources_for
from .game.progression import Profile
from .game.session import Mode, PlayerState
from .server import anticheat
from .shared import load, physics
from .shared.movement import PEDICAB, Bike, Runner, ascent, distance
from .training.setup import Branch, TrainingSetup, Venue, rank_branches, trainer_command
from .training.workout import Step, Workout, WorkoutRunner
from .devices import sim as devsim
from .devices.hub import available_sports, check
from .game.progression import SPORT_NAMES, xp_for_level
from .game.session import SessionError
from .shared.movement import Rower
from .world import metro
from .world.access import Access
from .world.graph import CityGraph
from .world.jobs import cross_bank_allowed, distances, pick_destination
from .world.navigation import Navigator, fastest_route, lookahead_profile, route_profile, street_names

DATA = Path(__file__).resolve().parents[1] / "data" / "lisboa-metro.json.gz"

SPOTS = {   # (lat, lon) de sítios conhecidos
    "Cais do Sodré": (38.7062, -9.1444),
    "Praça do Comércio": (38.7075, -9.1365),
    "Campo das Cebolas": (38.7090, -9.1310),
    "Miradouro de Santa Luzia": (38.7117, -9.1301),
    "Castelo de São Jorge": (38.7126, -9.1335),
    "Largo do Chafariz de Dentro": (38.7118, -9.1263),
    "Algés": (38.6985, -9.2330),
    "Almada": (38.6790, -9.1570),
}


def compass(edge, forward: bool) -> str:
    pts = edge.points if forward else list(reversed(edge.points))
    (x1, y1), (x2, y2) = pts[0], pts[min(len(pts) - 1, 3)]
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360
    return ("este", "nordeste", "norte", "noroeste", "oeste", "sudoeste", "sul", "sudeste")[int((ang + 22.5) // 45) % 8]


def stars_txt(n: int) -> str:
    return "★" * n + "☆" * (5 - n)


class City:
    def __init__(self, graph: CityGraph, access: Access | None = None):
        self.g = graph
        self.access = access

    def junction(self, spot: str, sport: str, zone: str | None = None) -> int:
        lat, lon = SPOTS[spot]
        where = (lambda j: j.zone == zone) if zone else None
        return self.g.nearest(*self.g.projection.to_xy(lat, lon), sport=sport, where=where).id

    def route(self, a: int, b: int, mover, extra_kg: float = 0.0, access=None):
        return fastest_route(self.g, a, b, mover, 0.75, extra_kg, access or self.access)

    def where(self, j: int) -> str:
        names = [e.name for e, _ in self.g.outgoing(j, "run") if e.name] or ["sem nome"]
        return names[0]


def ride(city: City, route, bike: Bike, watts_fn, t0: float, rng, extra_kg=0.0, on_sample=None,
         sport="bike", runner: Runner | None = None, intensity=0.0):
    """Percorre a rota segundo a segundo com o declive real (o que o rolo recebe)."""
    nav = Navigator.at(city.g, 0, sport, route)
    veh = bike.vehicle if bike else None
    t, v, hr, out = t0, 0.0, 100.0, []
    while True:
        g = nav.grade()
        if runner is not None:
            v = runner.speed_at(intensity, g, extra_kg)
            w = 0.0
        else:
            w = watts_fn(t, g)
            v = physics.step_velocity(bike.weight_kg + veh.mass_kg + extra_kg, veh.cda, veh.crr, v, w,
                                      g / 100.0, 1.0, veh.min_v)
        hr += (100 + (w / bike.ftp_w if bike else intensity) * 70 - hr) * 0.03
        out.append(anticheat.Sample(t, w, round(hr + rng.gauss(0, 1.0)), rng.uniform(82, 92), g))
        if on_sample:
            on_sample(t, v, g, w)
        t += 1
        if not nav.route and nav.remaining_on_edge <= v:
            break
        nav.advance(v)
        if t - t0 > 4 * 3600:
            raise RuntimeError("rota sem fim")
    return out, t, nav


def main(seed: int = 7) -> dict:
    if not DATA.exists():
        raise SystemExit(f"Falta {DATA.name}: corre `python tools/build_metro.py`.")
    rng = random.Random(seed)
    city = City(CityGraph.load(DATA))
    today = date(2026, 11, 23)
    ana = Profile("ana", weight_kg=64, ftp_w=230, run_threshold_mps=3.6, row_ftp_w=190,
                  xp={"bike": xp_for_level(9), "run": xp_for_level(4)}, active_weeks_last8=6)
    ana_devices = [devsim.SMART_TRAINER, devsim.TREADMILL, devsim.HR_STRAP]
    gym = [strength.GymSession(today - timedelta(days=d), 45, with_hr=d % 2 == 0) for d in (2, 5, 9, 13, 16, 20)]
    ana.robustness = strength.robustness(gym, today)
    bike, run = Bike(ana.weight_kg, ana.ftp_w), Runner(ana.weight_kg, ana.run_threshold_mps)
    player = PlayerState("ana", "lisboa", "n-baixa")
    city.access = ana.access("bike")
    ana_bike_access = city.access
    loads: list[float] = []
    stars: list[int] = []
    st = city.g.stats()
    print(f"== ErgQuest · Área Metropolitana de Lisboa ({st['junctions']} interseções, {st['bike_km']:.0f} km de "
          f"estradas, {st['water_km']} km de rio, {st['docks']} docas)")
    print(f"   Ana · Robustez {ana.robustness:.2f} · aparelhos: " + ", ".join(
        f"{d.name} ({d.transport.upper()})" for d in ana_devices))
    for sp in ("bike", "run", "row"):
        acc = ana.access(sp)
        zones = ", ".join(metro.any_zone(z).name for z in metro.ladder(sp) and [z.id for z in metro.ladder(sp)]
                          if z in acc.zones)
        nxt = acc.next_unlock()
        ok = check(sp, ana_devices).ok
        print(f"   {SPORT_NAMES[sp]:<9} nível {ana.level_in(sp):>2} · mapa {'rio' if sp == 'row' else 'terra'} · "
              f"{zones} · a seguir {nxt[0]} (nível {nxt[1]}) · {'aparelho OK' if ok else 'sem aparelho'}")

    # ================================================================ 1. TREINO
    wo = Workout("3×6′ limiar", [Step("steady", 600, target_lo=60)]
                 + [Step("steady", 360, target_lo=95), Step("steady", 180, target_lo=55)] * 3)
    setup = TrainingSetup(erg=False, venue=Venue.WORLD)
    runner = WorkoutRunner(wo, ana.ftp_w)
    print(f"\n[TREINO] {wo.name} · ERG desligado · no mundo · ~{wo.estimated_tss(ana.ftp_w):.0f} TSS")
    start = city.junction("Cais do Sodré", "bike")
    upcoming = runner.upcoming(540, 600)
    branches = [Branch(f"{e.name or e.highway} (para {compass(e, fwd)})", lookahead_profile(city.g, e, fwd, "bike"))
                for e, fwd in city.g.outgoing(start, "bike", city.access)]
    ranked = rank_branches(bike, branches, upcoming)
    print("  No Cais do Sodré, próximos blocos:", ", ".join(f"{s/60:.0f}′@{(f or 0):.0%}" for s, f in upcoming))
    for name, score in ranked:
        b = next(b for b in branches if b.name == name)
        print(f"   {'→' if name == ranked[0][0] else ' '} {name:<38} +{ascent(b.profile):3.0f} m em "
              f"{distance(b.profile)/1000:.1f} km · encaixe {score:.0%}")
    # a Ana faz a marginal ida e volta (Cais do Sodré ↔ Campo das Cebolas)
    east = city.junction("Campo das Cebolas", "bike")
    lap = city.route(start, east, bike) + city.route(east, start, bike)
    print("  Volta:", " → ".join(street_names(city.g, lap)[:6]), "…")
    samples, t, cmds = [], 0.0, []
    player.start(Sport.BIKE, 0.0, Mode.TRAINING, training=setup, devices=ana_devices, profile=ana)
    while t < wo.total_seconds:
        def train_watts(tt, g):
            return (runner.target_watts(tt) or ana.ftp_w * 0.5) * rng.uniform(0.96, 1.04)

        def watch(tt, v, g, w):
            runner.observe(tt, w)
            cmds.append(trainer_command(setup, runner.target_watts(tt), g).grade_pct)

        s, t, _ = ride(city, lap, bike, train_watts, t, rng, on_sample=watch)
        samples += s
    samples = [s for s in samples if s.t < wo.total_seconds]
    train_tss = load.tss([s.power for s in samples], ana.ftp_w)
    loads.append(train_tss)
    print(f"  Feito: cumprimento {runner.overall_compliance():.0f} % no alvo · TSS {train_tss:.0f} · "
          f"declive enviado ao rolo entre {min(cmds):+.1f} % e {max(cmds):+.1f} %")
    claimed, vv, checked = 0.0, 0.0, []
    for s in samples:
        vv = physics.step_velocity(bike.weight_kg + bike.vehicle.mass_kg, bike.vehicle.cda, bike.vehicle.crr,
                                   vv, s.power, s.grade_pct / 100, 1.0)
        claimed += vv
        checked.append(anticheat.Sample(s.t, s.power, s.hr, s.cadence, s.grade_pct, claimed))
    report = anticheat.validate(checked, ana.weight_kg)
    player.end(t)

    # ================================================================ 2. JOGO: entrega
    print("\n[JOGO] Sem treino marcado: a Ana só quer jogar.")
    player.start(Sport.BIKE, t, Mode.MISSION, devices=ana_devices, profile=ana)
    board = OrderBoard("ana", ana.level_in("bike"), lambda s, i: bike.speed_at(i, 0.0), ana.robustness,
                       strength.max_cargo_kg(ana.robustness), movers={Sport.BIKE: bike, Sport.RUN: run})
    srcs = sources_for("lisboa", "n-baixa")
    food = ana.available_sources([s for s in srcs if s.kind is Kind.FOOD])[0]
    # o restaurante (fictício) fica num restaurante real da Baixa, perto do Cais do Sodré
    cx, cy = city.g.projection.to_xy(*SPOTS["Cais do Sodré"])
    spot = min((a for a in city.g.anchors if a.kind == "restaurant" and city.g.junctions[a.junction].zone == "n-baixa"),
               key=lambda a: (a.x - cx) ** 2 + (a.y - cy) ** 2)
    a = city.g.nearest(spot.x, spot.y, "bike", where=lambda j: j.zone == "n-baixa").id
    b = city.junction("Miradouro de Santa Luzia", "bike")
    r = city.route(a, b, bike)
    prof = route_profile(city.g, r)
    order = board.make_order(food, profile=prof)
    print(f"  📱 {food.name} ({city.where(a)}) → Miradouro de Santa Luzia: {order.route_m/1000:.2f} km, "
          f"+{ascent(prof):.0f} m · prazo {order.deadline_s/60:.1f} min")
    print("     GPS:", " → ".join(street_names(city.g, r)))
    board.accept(order.id, t)
    board.pick_up(order.id, t)
    s2, t, _ = ride(city, r, bike, lambda tt, g: ana.ftp_w * (0.9 if g > 4 else 0.75) * rng.uniform(0.94, 1.06), t, rng)
    d = board.deliver(order.id, t)
    ana.record_job("food")
    stars.append(d.stars)
    tss2 = load.tss([s.power for s in s2], ana.ftp_w)
    loads.append(tss2)
    print(f"  ✔ {stars_txt(d.stars)} · {d.elapsed(t)/60:.1f} min · {d.detail['temperature_c']} °C · TSS {tss2:.0f}")

    # ================================================================ 3. JOGO: recado
    print("\n[TROCA] Em Santa Luzia, a Ana encosta a bicicleta e passa para a passadeira.")
    player.swap(Sport.RUN, t, devices=ana_devices, profile=ana)
    run_access = ana.access("run")
    city.access = run_access
    print(f"  ✔ {player.devices_check.summary()}")
    print(f"  O mapa muda para o nível de corrida ({ana.level_in('run')}): zonas abertas " + ", ".join(
        metro.ZONE[z].name for z in metro.UNLOCK_ORDER if z in run_access.zones)
          + f" — o Norte e o Este, abertos no ciclismo, estão fechados a correr")
    player.at_dock = True
    try:
        player.swap(Sport.ROW, t, devices=ana_devices, profile=ana)
        swap_blocked = None
    except SessionError as err:
        swap_blocked = str(err)
        print(f"  ✗ Trocar para o remo na doca: {swap_blocked}")
    player.at_dock = False
    print("\n[JOGO] Um NPC acena: recado a pé por Alfama.")
    here = city.junction("Miradouro de Santa Luzia", "run")
    home = city.junction("Largo do Chafariz de Dentro", "run")
    hx, hy = city.g.junctions[here].x, city.g.junctions[here].y
    shops = sorted({a.junction for a in city.g.anchors if a.kind in ("cafe", "restaurant")}
                   & city.g.main_network("run"),
                   key=lambda j: (city.g.junctions[j].x - hx) ** 2 + (city.g.junctions[j].y - hy) ** 2)[:25]
    rng_stops = random.Random(seed + 1)
    chain = [here]

    def route_for(i, n):
        if len(chain) == 1:
            chain.extend(rng_stops.sample(shops, n - 1) + [home])
        leg = city.route(chain[i], chain[i + 1], run)
        return city.where(chain[i + 1]), route_profile(city.g, leg)

    offer = errands.make_offer("ana", 11, run, ana.level_in("run"), route_for=route_for)
    print("  " + offer.summary().replace("\n", "\n  "))
    job = errands.accept(offer, t)
    intensity = offer.required_intensity * 1.08
    speeds = []
    for i, leg in enumerate(offer.legs):
        r = city.route(chain[i], chain[i + 1], run)
        _, t, _ = ride(city, r, None, None, t, rng, extra_kg=leg.carrying_kg, sport="run", runner=run,
                       intensity=intensity, on_sample=lambda tt, v, g, w: speeds.append(v))
        job.arrive(leg.to, t)
    res3 = job.result
    tss3 = load.rtss(speeds, ana.run_threshold_mps) or 0.0
    loads.append(tss3)
    stars.append(res3["stars"])
    ana.record_job("errand")
    print(f"  ✔ {'cumprido' if res3['completed'] else 'falhado'} em {res3['elapsed_s']/60:.1f} min · "
          f"{stars_txt(res3['stars'])} · +{res3['xp']} XP · rTSS {tss3:.0f}")
    player.end(t)

    # ================================================================ 4. JOGO: táxi
    print("\n[JOGO] Praça do Comércio: dois turistas querem ir ao Castelo de riquexó.")
    city.access = ana_bike_access
    ok, why = taxi.can_drive(PEDICAB, ana.level_in("bike"), ana.robustness)
    print(f"  Licença de riquexó (nível de ciclismo {ana.level_in('bike')}): {'sim' if ok else why}")
    player.start(Sport.BIKE, t, Mode.MISSION, devices=ana_devices, profile=ana)
    cab = Bike(ana.weight_kg, ana.ftp_w, PEDICAB)
    a, b = city.junction("Praça do Comércio", "bike"), city.junction("Castelo de São Jorge", "bike")
    r = city.route(a, b, cab, 140)
    quote = taxi.make_offer("ana", 5, cab, ana.level_in("bike"), "Castelo de São Jorge", profile=route_profile(city.g, r))
    print("  " + quote.summary().replace("\n", "\n  "))
    print("     GPS:", " → ".join(street_names(city.g, r)))
    trip = taxi.accept(quote, t, ana.level_in("bike"), ana.robustness)
    target = cab.ftp_w * quote.required_intensity * 1.05

    def cab_watts(tt, g):
        k = 0.3 if g < -1 else max(1.0, min(1.3 * cab.ftp_w / target, 1 + g / 6)) if g > 3 else 1.0
        return target * k * rng.uniform(0.95, 1.05)

    s4, t, _ = ride(city, r, cab, cab_watts, t, rng, extra_kg=quote.extra_kg,
                    on_sample=lambda tt, v, g, w: trip.observe(1.0, v, g))
    res4 = trip.finish(t)
    tss4 = load.tss([s.power for s in s4], ana.ftp_w)
    loads.append(tss4)
    stars.append(res4["stars"])
    ana.record_job("taxi")
    print(f"  ✔ {stars_txt(res4['stars'])} · {res4['elapsed_s']/60:.1f} min · {res4['crawl_s']} s mais devagar do que a pé · "
          f"conforto {res4['comfort']} · ganhou {res4['earned']} ¤ · TSS {tss4:.0f}")
    player.end(t)

    # ================================================================ 5. efeito colateral
    history = {today - timedelta(days=i): 55.0 + 20 * math.sin(i) for i in range(1, 60)}
    history[today] = sum(loads)
    p = load.pmc(history, today)
    before, after = p[-2], p[-1]
    before_lv = dict(ana.levels)
    xp_bike = ana.add_session(loads[0] + loads[1] + loads[3], [stars[0], stars[2]], sport="bike")
    xp_run = ana.add_session(loads[2], [stars[1]], sport="run")
    print(f"\n[EFEITO COLATERAL] carga do dia {sum(loads):.0f} TSS "
          f"(treino {loads[0]:.0f} + jogo {sum(loads[1:]):.0f}) — a forma real é uma só")
    print(f"  Fitness CTL {before['ctl']:.0f}→{after['ctl']:.0f} · Fadiga ATL {before['atl']:.0f}→{after['atl']:.0f} · "
          f"Forma amanhã {after['ctl'] - after['atl']:+.0f} ({load.form_state(after['ctl'] - after['atl'])})")
    print(f"  Ciclismo +{xp_bike} XP (nível {before_lv['bike']}→{ana.level_in('bike')}) · Corrida +{xp_run} XP "
          f"(nível {before_lv['run']}→{ana.level_in('run')}) · Remo sem sessões (nível {ana.level_in('row')})")
    print(f"  Restaurantes abertos: {ana.establishments_unlocked('food')}")
    print(f"  Anti-cheat do treino: confiança {report.trust} · rankings {'OK' if report.ranked_ok else 'em revisão'}")

    # ================================================================ 6. LIVRE: o limite do mundo
    print("\n[LIVRE] A Ana pedala sem destino para oeste, pela marginal.")
    ana_access = ana_bike_access
    start = city.junction("Cais do Sodré", "bike")
    alges = city.junction("Algés", "bike", zone="n-oeste")
    towards = fastest_route(city.g, start, alges, bike, access=Access.everything())
    nav = Navigator.at(city.g, start, "bike", towards, access=ana_access)
    limit = None
    while limit is None and nav.travelled_m < 30_000:
        nav.advance(8.0)
        limit = next((l for l in nav.log if l.startswith("limite:")), None)
    here_name = nav.edge.name or {"service": "uma rua de serviço", "footway": "um passeio",
                                  "cycleway": "uma ciclovia"}.get(nav.edge.highway, nav.edge.highway)
    print(f"  Ao fim de {nav.travelled_m/1000:.1f} km, em {here_name}: 🔒 {limit[8:] if limit else '—'}")
    print("  As ruas para a zona fechada aparecem bloqueadas; ela carrega em «regressar»:")
    back = nav.go_back(start, bike)
    back_km = sum(city.g.edges[e].length for e, _ in back) / 1000 + nav.remaining_on_edge / 1000
    print(f"  GPS de volta ao Cais do Sodré: {back_km:.1f} km por " + " → ".join(street_names(city.g, back)[:5]) + " …")
    free_km = nav.travelled_m / 1000

    # ================================================================ 7. EXPERIENTE: as duas margens
    rui = Profile("rui", weight_kg=72, ftp_w=300, xp={"bike": xp_for_level(20), "row": xp_for_level(14)},
                  robustness=0.6)
    rui_devices = [devsim.SMART_TRAINER, devsim.ROWER, devsim.HR_STRAP]
    rui_access, rui_row = rui.access("bike"), rui.access("row")
    rbike, rrow = Bike(rui.weight_kg, rui.ftp_w), Rower(rui.weight_kg, 260)
    print(f"\n[EXPERIENTE] Rui · ciclismo {rui.level_in('bike')} (pontes "
          f"{'abertas' if cross_bank_allowed(rui.level_in('bike'), 'bike') else 'fechadas'}) · remo {rui.level_in('row')} "
          f"(travessias {'abertas' if cross_bank_allowed(rui.level_in('row'), 'row') else 'fechadas'}) · "
          f"pode: {', '.join(SPORT_NAMES[s] for s in available_sports(rui_devices))}")
    almada = city.junction("Almada", "bike", zone="s-norte")
    over = fastest_route(city.g, a, almada, rbike, 0.75, access=rui_access)
    prof = route_profile(city.g, over)
    bridge = next((metro.BRIDGES[city.g.edges[e].lock][0] for e, _ in over if city.g.edges[e].lock in metro.BRIDGES), "—")
    print(f"  📱 Entrega {food.name} → Almada: {distance(prof)/1000:.1f} km, +{ascent(prof):.0f} m, pela {bridge} "
          f"(a Ana, nível {ana.level}: {'pode' if fastest_route(city.g, a, almada, bike, access=ana_access) else 'não pode'})")
    dock = min((j for j in city.g.docks() if j.zone in ("n-baixa", "n-centro")),
               key=lambda j: (j.x - cx) ** 2 + (j.y - cy) ** 2)
    dest = pick_destination(city.g, dock.id, "row", rui_row, random.Random(seed), 1500, 9000, other_bank=True)
    if dest is not None:
        d_km = distances(city.g, dock.id, "row", rui_row)[dest] / 1000
        rroute = fastest_route(city.g, dock.id, dest, rrow, 0.75, access=rui_row)
        cross = next((city.g.edges[e].lock for e, _ in rroute if city.g.edges[e].lock), "")
        print(f"  🚣 Passeio de margem a margem: doca em {metro.ZONE[dock.zone].name} → doca em "
              f"{metro.ZONE[city.g.junctions[dest].zone].name} ({city.where(dest)}), {d_km:.1f} km pelo rio, "
              f"pela travessia {metro.CROSSING_NAMES.get(cross, cross)}")
    print(f"  (a Ana nem pode remar: {swap_blocked})")
    print(f"\n  Dados: {city.g.attribution}")
    return {"loads": loads, "stars": stars, "trust": report.trust,
            "compliance": runner.overall_compliance(), "errand": res3["completed"], "taxi": res4["stars"],
            "limit": limit, "free_km": free_km, "bridge": bridge, "cross_dest": dest,
            "swap_blocked": swap_blocked, "levels": ana.levels}


if __name__ == "__main__":
    main()

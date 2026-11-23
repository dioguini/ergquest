"""Mapa 2D de uma zona, em HTML com SVG embutido, para validar o grafo.

Ruas coloridas pelo declive mais duro do troço, escadinhas tracejadas,
margem do rio, docas, âncoras de estabelecimentos e uma rota opcional.
"""
from __future__ import annotations

import html
from pathlib import Path

from .graph import CityGraph

GRADE_BANDS = ((3, "var(--g0)", "0–3 %"), (6, "var(--g1)", "3–6 %"), (10, "var(--g2)", "6–10 %"),
               (15, "var(--g3)", "10–15 %"), (99, "var(--g4)", "> 15 %"))
ANCHOR_LABEL = {"restaurant": "restaurante", "cafe": "café", "fast_food": "comida rápida",
                "police": "esquadra", "ferry_terminal": "terminal fluvial"}


def _color(edge) -> str:
    steep = max((abs(g) for _, g in edge.profile), default=0.0)
    return next(c for lim, c, _ in GRADE_BANDS if steep < lim)


def render(graph: CityGraph, title: str, route: list[tuple[int, bool]] | None = None) -> str:
    xs = [x for e in graph.edges.values() for x, _ in e.points] or [0, 1]
    ys = [y for e in graph.edges.values() for _, y in e.points] or [0, 1]
    pad = 40
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    w, h = maxx - minx, maxy - miny

    def pts(points):
        return " ".join(f"{x - minx:.1f},{maxy - y:.1f}" for x, y in points)

    out = []
    for line in graph.water:
        out.append(f'<polyline class="water" points="{pts(line)}"/>')
    for e in graph.edges.values():
        cls = "street steps" if e.highway == "steps" else "street"
        tip = html.escape(f"{e.name or e.highway} · {e.length:.0f} m · +{e.ascent(True):.0f}/+{e.ascent(False):.0f} m")
        out.append(f'<polyline class="{cls}" style="stroke:{_color(e)}" points="{pts(e.points)}"><title>{tip}</title></polyline>')
    if route:
        line = []
        for eid, fwd in route:
            p = graph.edges[eid].points
            line += p if fwd else list(reversed(p))
        out.append(f'<polyline class="route" points="{pts(line)}"/>')
    for j in graph.docks():
        out.append(f'<circle class="dock" cx="{j.x - minx:.1f}" cy="{maxy - j.y:.1f}" r="7"><title>doca</title></circle>')
    for a in graph.anchors:
        label = html.escape(ANCHOR_LABEL.get(a.kind, a.kind))
        out.append(f'<circle class="anchor {a.kind}" cx="{a.x - minx:.1f}" cy="{maxy - a.y:.1f}" r="5"><title>{label}</title></circle>')

    st = graph.stats()
    legend = "".join(f'<span><i style="background:{c}"></i>{t}</span>' for _, c, t in GRADE_BANDS)
    facts = (f"{st['junctions']} interseções · {st['bike_km']} km de bicicleta · {st['foot_km']} km a pé · "
             f"altitude {st['ele_min']}–{st['ele_max']} m · rampa máx. {st['steepest_pct']} % · "
             f"{st['docks']} docas · {st['anchors']} âncoras")
    return f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f6f4ef;--fg:#1d1d1b;--muted:#6b6b66;--water:#4a90c2;--route:#1d1d1b;--dock:#4a90c2;--anchor:#c2410c;
--g0:#9aa39a;--g1:#d9b44a;--g2:#e07b39;--g3:#c2410c;--g4:#7f1d1d}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#151514;--fg:#ecebe6;--muted:#9a9a94;
--water:#5fa8d8;--route:#ecebe6;--dock:#5fa8d8;--anchor:#fb923c;--g0:#5d655d;--g1:#c9a23a;--g2:#e58a4b;--g3:#f06a3a;--g4:#ff9a8a}}}}
:root[data-theme="dark"]{{--bg:#151514;--fg:#ecebe6;--muted:#9a9a94;--water:#5fa8d8;--route:#ecebe6;--dock:#5fa8d8;
--anchor:#fb923c;--g0:#5d655d;--g1:#c9a23a;--g2:#e58a4b;--g3:#f06a3a;--g4:#ff9a8a}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}}
h1{{font-size:1.3rem;margin:0 0 4px}} p{{margin:0 0 10px;color:var(--muted)}}
svg{{width:100%;height:auto;display:block}}
.street{{fill:none;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}}
.steps{{stroke-dasharray:3 4}} .water{{fill:none;stroke:var(--water);stroke-width:6;opacity:.6}}
.route{{fill:none;stroke:var(--route);stroke-width:2;stroke-dasharray:8 5}}
.dock{{fill:none;stroke:var(--dock);stroke-width:2.5}} .anchor{{fill:var(--anchor)}}
.legend{{display:flex;flex-wrap:wrap;gap:12px;font-size:13px;color:var(--muted);margin:8px 0}}
.legend i{{display:inline-block;width:18px;height:4px;margin-right:6px;vertical-align:middle}}
small{{color:var(--muted)}}
</style></head><body><main>
<h1>{html.escape(title)}</h1><p>{facts}</p>
<div class="legend">{legend}<span>┄ escadinhas (só a pé)</span><span>◯ doca</span><span>● estabelecimento</span></div>
<svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="Mapa da zona">{''.join(out)}</svg>
<small>Dados {html.escape(graph.to_json()['attribution'])}</small>
</main></body></html>"""


def save(graph: CityGraph, path: str | Path, title: str, route=None) -> Path:
    p = Path(path)
    p.write_text(render(graph, title, route), encoding="utf-8")
    return p

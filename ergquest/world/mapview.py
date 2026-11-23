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


def render(graph: CityGraph, title: str, route: list[tuple[int, bool]] | None = None,
           labels: list[tuple[str, float, float]] | None = None, route_label: str = "") -> str:
    """Página do mapa (conteúdo sem esqueleto HTML: abre num browser e publica-se como está)."""
    xs = [x for e in graph.edges.values() for x, _ in e.points] or [0, 1]
    ys = [y for e in graph.edges.values() for _, y in e.points] or [0, 1]
    pad = 40
    lx = [x + 30 + 22 * len(n) for n, x, _ in labels or []]
    minx, maxx, miny, maxy = min(xs) - pad, max([*xs, *lx]) + pad, min(ys) - pad, max(ys) + pad
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

    for name, x, y in labels or []:
        cx, cy = x - minx, maxy - y
        out.append(f'<g class="label"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="9"/>'
                   f'<text x="{cx + 14:.1f}" y="{cy + 6:.1f}">{html.escape(name)}</text></g>')

    st = graph.stats()
    legend = "".join(f'<span><i style="background:{c}"></i>{t}</span>' for _, c, t in GRADE_BANDS)
    facts = (f"{st['junctions']} interseções · {st['bike_km']} km de bicicleta · {st['foot_km']} km a pé · "
             f"altitude {st['ele_min']}–{st['ele_max']} m · rampa máx. {st['steepest_pct']} % · "
             f"{st['docks']} docas · {st['anchors']} âncoras")
    route_key = f'<span><i class="rk"></i>{html.escape(route_label)}</span>' if route and route_label else ""
    return f"""<title>{html.escape(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Space+Grotesk:wght@600&display=swap">
<style>
/* mapa a toda a largura; cabeçalho curto; legenda por baixo */
:root{{--bg:#f4f5f2;--fg:#1b1f1d;--muted:#5f6862;--water:#3f86b8;--route:#9d174d;--dock:#3f86b8;--anchor:#b4532a;
--g0:#a3aba5;--g1:#d4a63a;--g2:#df7a35;--g3:#c2410c;--g4:#7c1d1d;
--display:"Space Grotesk",system-ui,sans-serif;--body:Inter,system-ui,sans-serif}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#121514;--fg:#e8ebe8;--muted:#9aa39d;
--water:#5aa5d6;--route:#f472b6;--dock:#5aa5d6;--anchor:#f0905a;--g0:#56605a;--g1:#c99d33;--g2:#e88a4c;--g3:#f26b3a;--g4:#ff9c8c;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#121514;--fg:#e8ebe8;--muted:#9aa39d;--water:#5aa5d6;--route:#f472b6;--dock:#5aa5d6;
--anchor:#f0905a;--g0:#56605a;--g1:#c99d33;--g2:#e88a4c;--g3:#f26b3a;--g4:#ff9c8c;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 var(--body)}}
main{{max-width:1200px;margin:0 auto;padding-block:20px 28px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:10px}}
h1{{font:600 1.5rem/1.2 var(--display);margin:0;text-wrap:balance}}
p{{margin:0;color:var(--muted);font-variant-numeric:tabular-nums}}
.map{{overflow-x:auto}} svg{{width:100%;min-width:640px;height:auto;display:block}}
.street{{fill:none;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}}
.steps{{stroke-dasharray:3 4}} .water{{fill:none;stroke:var(--water);stroke-width:7;opacity:.55}}
.route{{fill:none;stroke:var(--route);stroke-width:11;stroke-linecap:round;stroke-linejoin:round;opacity:.9}}
.dock{{fill:none;stroke:var(--dock);stroke-width:2.5}} .anchor{{fill:var(--anchor);opacity:.8}}
.label circle{{fill:var(--bg);stroke:var(--fg);stroke-width:3}}
.label text{{font:600 40px var(--display);fill:var(--fg);paint-order:stroke;stroke:var(--bg);stroke-width:6px}}
.legend{{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted)}}
.legend i{{display:inline-block;width:18px;height:4px;margin-right:6px;vertical-align:middle;border-radius:2px}}
.legend .rk{{background:var(--route);height:5px}}
small{{color:var(--muted);font-size:12px}}
</style>
<main>
<h1>{html.escape(title)}</h1><p>{facts}</p>
<div class="legend">{legend}<span>┄ escadinhas (só a pé)</span><span>◯ doca</span><span>● estabelecimento</span>{route_key}</div>
<div class="map"><svg viewBox="0 0 {w:.0f} {h:.0f}" role="img" aria-label="Mapa da zona com as ruas coloridas pelo declive">{''.join(out)}</svg></div>
<small>Dados {html.escape(graph.attribution)}</small>
</main>"""


def save(graph: CityGraph, path: str | Path, title: str, route=None, labels=None, route_label: str = "") -> Path:
    p = Path(path)
    p.write_text(render(graph, title, route, labels, route_label), encoding="utf-8")
    return p

"""Mapa interativo da Área Metropolitana: dados compactos + página em canvas.

`export(g)` reduz o grafo ao que o mapa desenha (traçados simplificados, em
metros inteiros, agrupados por zona e por classe de via). `PAGE` é a página
(HTML sem esqueleto) que lê `metro-map.json` ao lado e desenha: zonas, o que
um atleta de um dado nível tem aberto, pontes, rio, travessias, docas e serras.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import metro
from .graph import CityGraph, simplify

MAJOR = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
MID = {"secondary", "tertiary", "unclassified", "secondary_link", "tertiary_link", "cycleway"}

LABELS = {
    "Baixa": (38.7110, -9.1370), "Belém": (38.6970, -9.2060), "Parque das Nações": (38.7680, -9.0940),
    "Benfica": (38.7510, -9.2000), "Loures": (38.8300, -9.1690), "Odivelas": (38.7930, -9.1830),
    "Vila Franca de Xira": (38.9550, -8.9900), "Sintra": (38.8000, -9.3800), "Cascais": (38.6970, -9.4200),
    "Oeiras": (38.6910, -9.3100), "Mafra": (38.9400, -9.3300), "Almada": (38.6790, -9.1570),
    "Seixal": (38.6400, -9.1000), "Barreiro": (38.6630, -9.0720), "Montijo": (38.7060, -8.9740),
    "Alcochete": (38.7550, -8.9610), "Costa da Caparica": (38.6420, -9.2350), "Sesimbra": (38.4440, -9.1010),
    "Setúbal": (38.5240, -8.8930), "Palmela": (38.5690, -8.9010),
}


def _cls(e) -> int:
    if e.highway == "serra":
        return 4
    if e.highway == "ligação":
        return 3
    if e.highway in MAJOR:
        return 0
    if e.highway in MID:
        return 1
    return 2


def export(g: CityGraph) -> dict:
    xs = [j.x for j in g.junctions.values()]
    ys = [j.y for j in g.junctions.values()]
    roads: dict[str, list] = {z.id: [] for z in metro.ZONES}
    bridges: dict[str, list] = {}
    crossings: list = []
    water: list = []
    climbs: dict[str, list] = {}
    for e in g.edges.values():
        pts = simplify(e.points, 8.0 if e.highway not in MAJOR else 15.0)
        flat_pts = [int(round(v)) for p in pts for v in p]
        if e.mode == "water":
            if e.lock:
                crossings.append({"id": e.lock, "pts": flat_pts})
            else:
                water.append(flat_pts)
            continue
        if e.mode == "dock":
            continue
        if e.lock in metro.BRIDGES:
            bridges.setdefault(e.lock, []).append(flat_pts)
            continue
        if e.highway == "serra":
            climbs.setdefault(e.name, []).append(flat_pts)
        zone = g.junctions[e.a].zone or g.junctions[e.b].zone
        if zone in roads:
            roads[zone].append([_cls(e)] + flat_pts)
    summits = {}
    for c in metro.CLIMBS:
        es = [e for e in g.edges.values() if e.name == c.name]
        if es:
            top = max((g.junctions[j] for e in es for j in (e.a, e.b)), key=lambda j: j.ele)
            summits[c.name] = {"x": round(top.x), "y": round(top.y), "ele": round(top.ele),
                               "up_km": c.up_km, "avg": c.avg_pct, "zone": top.zone}
    return {
        "attribution": g.attribution,
        "bounds": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))],
        "zones": [{"id": z.id, "name": z.name, "bank": z.bank, "level": z.level, "hue": z.hue,
                   "junctions": sum(1 for j in g.junctions.values() if j.zone == z.id)} for z in metro.ZONES],
        "bridge_level": metro.BRIDGE_LEVEL, "crossing_level": metro.CROSSING_LEVEL,
        "bridges": [{"id": b, "name": metro.BRIDGES[b][0], "lines": lines} for b, lines in bridges.items()],
        "crossings": crossings, "water": water, "roads": roads,
        "climbs": [{"name": n, "lines": lines, **summits.get(n, {})} for n, lines in climbs.items()],
        "docks": [[round(j.x), round(j.y), j.zone] for j in g.docks()],
        "labels": [[n, *[round(v) for v in g.projection.to_xy(*p)]] for n, p in LABELS.items()],
        "stats": g.stats(),
    }


def save_data(g: CityGraph, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(export(g), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


PAGE = r"""<title>Lisboa Metropolitana</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* mapa à esquerda, painel de zonas à direita; em telemóvel, empilhados */
:root{--bg:#f3f4f1;--panel:#ffffff;--fg:#1a1e1c;--muted:#5d6661;--line:#d9ddd8;--locked:#b9bfba;--water:#3b82b8;
--bridge:#1a1e1c;--accent:#0f766e;--zl:44%;--zs:62%;
--display:"Space Grotesk",system-ui,sans-serif;--body:Inter,system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111413;--panel:#1a1e1c;--fg:#e7eae7;
--muted:#9aa39e;--line:#2c322f;--locked:#3c4440;--water:#5aa7dc;--bridge:#f1f3f1;--accent:#2dd4bf;--zl:62%;--zs:58%;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#111413;--panel:#1a1e1c;--fg:#e7eae7;--muted:#9aa39e;--line:#2c322f;--locked:#3c4440;
--water:#5aa7dc;--bridge:#f1f3f1;--accent:#2dd4bf;--zl:62%;--zs:58%;color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:14px/1.5 var(--body)}
.wrap{max-width:1320px;margin:0 auto;padding-block:18px 24px;
padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));
display:grid;gap:14px;grid-template-columns:minmax(0,1fr) 320px}
@media (max-width:900px){.wrap{grid-template-columns:minmax(0,1fr)}}
header{grid-column:1/-1;display:grid;gap:4px}
h1{font:600 1.55rem/1.15 var(--display);margin:0;text-wrap:balance}
.facts{color:var(--muted);font-variant-numeric:tabular-nums;margin:0}
.stage{position:relative;min-width:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--bg);
aspect-ratio:1/1;max-height:78vh}
canvas{width:100%;height:100%;display:block;touch-action:none;cursor:grab}
canvas.drag{cursor:grabbing}
.zoom{position:absolute;right:10px;top:10px;display:grid;gap:6px}
.zoom button{width:34px;height:34px;border-radius:8px;border:1px solid var(--line);background:var(--panel);color:var(--fg);
font:600 16px var(--body);cursor:pointer}
.zoom button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
aside{display:grid;gap:14px;align-content:start;min-width:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;display:grid;gap:10px}
.card h2{font:600 1rem/1.2 var(--display);margin:0}
.lvl{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center}
.lvl output{font:600 1.4rem var(--display);font-variant-numeric:tabular-nums;min-width:2ch;text-align:right}
input[type=range]{width:100%;accent-color:var(--accent)}
ol{list-style:none;margin:0;padding:0;display:grid;gap:4px}
ol li{display:grid;grid-template-columns:14px 1fr auto;gap:8px;align-items:center;padding:3px 0;font-variant-numeric:tabular-nums}
ol li i{width:12px;height:12px;border-radius:3px}
ol li.off{color:var(--muted)} ol li.off i{opacity:.35}
ol li small{color:var(--muted)}
.bank{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-top:4px}
.state{font-size:12px;padding:1px 7px;border-radius:99px;border:1px solid var(--line)}
.on .state{border-color:var(--accent);color:var(--accent)}
.climb{display:grid;gap:2px} .climb b{font:600 15px var(--display)}
.climb span{color:var(--muted);font-variant-numeric:tabular-nums}
.keys{display:flex;flex-wrap:wrap;gap:6px 14px;color:var(--muted);font-size:12.5px}
.keys i{display:inline-block;width:16px;height:3px;margin-right:6px;vertical-align:middle;border-radius:2px}
footer{grid-column:1/-1;color:var(--muted);font-size:12px}
.err{padding:20px;color:var(--muted)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
<div class="wrap">
<header><h1>Lisboa Metropolitana</h1><p class="facts" id="facts">A carregar o mapa…</p></header>
<div class="stage"><canvas id="map" aria-label="Mapa da Área Metropolitana de Lisboa por zonas"></canvas>
<div class="zoom"><button id="zin" aria-label="Aproximar">+</button><button id="zout" aria-label="Afastar">−</button>
<button id="zfit" aria-label="Ver tudo">⤢</button></div></div>
<aside>
<div class="card"><h2>Nível do atleta</h2>
<div class="lvl"><label for="level">Nível</label><input type="range" id="level" min="1" max="30" value="9"><output id="lvlout">9</output></div>
<div id="locks" class="keys"></div></div>
<div class="card"><h2>Zonas, por ordem de desbloqueio</h2><ol id="zones"></ol></div>
<div class="card"><h2>Serras</h2><div id="climbs" style="display:grid;gap:10px"></div></div>
<div class="card"><h2>Legenda</h2><div class="keys">
<span><i style="background:var(--fg);height:4px"></i>autoestrada / principal</span>
<span><i style="background:var(--muted)"></i>secundária / cidade</span>
<span><i style="background:var(--muted);height:2px;border-top:2px dashed var(--muted);background:none"></i>estrada de ligação</span>
<span><i style="background:var(--water)"></i>faixa de remo</span>
<span><i style="background:none;border-top:3px dotted var(--water);height:0"></i>travessia</span>
<span><i style="background:var(--bridge);height:5px"></i>ponte</span>
<span>◦ doca</span></div></div>
</aside>
<footer id="foot"></footer>
</div>
<script>
(async function(){
const $=id=>document.getElementById(id);
let D;
try{D=await (await fetch("metro-map.json")).json();}
catch(e){$("facts").textContent="Não foi possível carregar os dados do mapa.";return;}
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const cv=$("map"),ctx=cv.getContext("2d");
const [x0,y0,x1,y1]=D.bounds;
let view={cx:(x0+x1)/2,cy:(y0+y1)/2,s:1},W=0,H=0,dpr=1;
const zoneById=Object.fromEntries(D.zones.map(z=>[z.id,z]));
const st=D.stats;
$("facts").textContent=`${st.junctions.toLocaleString("pt-PT")} interseções · ${Math.round(st.bike_km).toLocaleString("pt-PT")} km de estradas · ${st.water_km} km de rio · ${st.docks} docas · altitude até ${Math.round(st.ele_max)} m`;
$("foot").textContent="Dados: "+D.attribution;
function fit(){const sx=W/(x1-x0),sy=H/(y1-y0);view={cx:(x0+x1)/2,cy:(y0+y1)/2,s:Math.min(sx,sy)*0.96};}
function resize(){const r=cv.getBoundingClientRect();dpr=window.devicePixelRatio||1;W=r.width;H=r.height;
cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);if(!view.init){fit();view.init=true;}draw();}
const tx=x=>(x-view.cx)*view.s+W/2, ty=y=>H/2-(y-view.cy)*view.s;
function line(a,start){ctx.moveTo(tx(a[start]),ty(a[start+1]));for(let i=start+2;i<a.length;i+=2)ctx.lineTo(tx(a[i]),ty(a[i+1]));}
const level=()=>+$("level").value;
function zcol(z,on){return on?`hsl(${z.hue} ${css("--zs")} ${css("--zl")})`:css("--locked");}
function draw(){
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);ctx.lineCap="round";ctx.lineJoin="round";
 const L=level(),k=Math.max(0.6,Math.min(2.2,view.s*60));
 ctx.strokeStyle=css("--water");ctx.globalAlpha=.85;ctx.lineWidth=2.2*k;ctx.beginPath();
 for(const w of D.water)line(w,0);ctx.stroke();
 ctx.setLineDash([2*k,4*k]);ctx.lineWidth=2*k;ctx.globalAlpha=L>=D.crossing_level?.95:.3;ctx.beginPath();
 for(const c of D.crossings)line(c.pts,0);ctx.stroke();ctx.setLineDash([]);ctx.globalAlpha=1;
 const widths=[1.6,0.9,0.45,1.1,2.4];
 const order=[...D.zones].sort((a,b)=>(L>=a.level)-(L>=b.level));
 for(const cls of [2,1,3,0,4]){
  for(const z of order){const on=L>=z.level;ctx.strokeStyle=zcol(z,on);ctx.globalAlpha=on?(cls==2?.75:1):.55;
   ctx.lineWidth=widths[cls]*k;if(cls==3)ctx.setLineDash([3*k,3*k]);ctx.beginPath();
   for(const r of D.roads[z.id])if(r[0]===cls)line(r,1);ctx.stroke();ctx.setLineDash([]);}
 }
 ctx.globalAlpha=1;
 for(const b of D.bridges){const on=L>=D.bridge_level;ctx.strokeStyle=on?css("--bridge"):css("--locked");
  ctx.lineWidth=(on?3.4:2.6)*k;ctx.setLineDash(on?[]:[4*k,3*k]);ctx.beginPath();for(const l of b.lines)line(l,0);ctx.stroke();}
 ctx.setLineDash([]);
 ctx.fillStyle=css("--bg");ctx.strokeStyle=css("--water");ctx.lineWidth=1.4;
 for(const [x,y,z] of D.docks){const on=L>=(zoneById[z]||{level:99}).level;ctx.globalAlpha=on?1:.35;
  ctx.beginPath();ctx.arc(tx(x),ty(y),2.6*k,0,7);ctx.fill();ctx.stroke();}
 ctx.globalAlpha=1;
 ctx.font=`600 ${Math.round(11+2*Math.min(k,1.6))}px Space Grotesk, system-ui, sans-serif`;ctx.textBaseline="middle";
 ctx.lineWidth=3.5;ctx.strokeStyle=css("--bg");ctx.fillStyle=css("--fg");
 const text=(t,X,Y,gap)=>{const w=ctx.measureText(t).width,left=X+gap+w>W-8;const tx2=left?X-gap-w:X+gap;
  ctx.strokeText(t,tx2,Y);ctx.fillText(t,tx2,Y);};
 for(const [n,x,y] of D.labels){const X=tx(x),Y=ty(y);if(X<-50||X>W+50||Y<-20||Y>H+20)continue;text(n,X,Y,5);}
 for(const c of D.climbs){if(c.x==null)continue;const X=tx(c.x),Y=ty(c.y);ctx.beginPath();ctx.moveTo(X,Y-9);ctx.lineTo(X+7,Y+4);ctx.lineTo(X-7,Y+4);ctx.closePath();
  ctx.fillStyle=css("--fg");ctx.fill();text(`${c.name} · ${c.ele} m`,X,Y,10);}
}
function panel(){
 const L=level();$("lvlout").textContent=L;
 const zl=$("zones");zl.innerHTML="";let bank="";
 for(const z of D.zones){if(z.bank!==bank){bank=z.bank;const h=document.createElement("li");h.className="bank";
  h.style.display="block";h.textContent=bank==="norte"?"Margem norte":"Margem sul (pelas pontes)";zl.appendChild(h);}
  const on=L>=z.level,li=document.createElement("li");li.className=on?"on":"off";
  li.innerHTML=`<i style="background:hsl(${z.hue} ${css("--zs")} ${css("--zl")})"></i><span>${z.name} <small>· nível ${z.level}</small></span><span class="state">${on?"aberta":"fechada"}</span>`;
  zl.appendChild(li);}
 const bOn=L>=D.bridge_level,cOn=L>=D.crossing_level;
 $("locks").innerHTML=`<span>Pontes: <b>${bOn?"abertas":"fechadas"}</b> (nível ${D.bridge_level})</span><span>Remo entre margens: <b>${cOn?"aberto":"fechado"}</b> (nível ${D.crossing_level})</span>`;
 draw();
}
$("climbs").innerHTML=D.climbs.map(c=>`<div class="climb"><b>${c.name}</b><span>${c.up_km} km a ${c.avg} % · cume a ${c.ele} m · ${(zoneById[c.zone]||{}).name||""}</span></div>`).join("");
$("level").addEventListener("input",panel);
// zoom e arrastar (rato, roda, dedos)
const pts=new Map();let last=null;
function zoomAt(f,px,py){const wx=(px-W/2)/view.s+view.cx,wy=view.cy-(py-H/2)/view.s;view.s*=f;
 view.cx=wx-(px-W/2)/view.s;view.cy=wy+(py-H/2)/view.s;draw();}
cv.addEventListener("wheel",e=>{e.preventDefault();const r=cv.getBoundingClientRect();zoomAt(Math.exp(-e.deltaY*0.0015),e.clientX-r.left,e.clientY-r.top);},{passive:false});
cv.addEventListener("pointerdown",e=>{cv.setPointerCapture(e.pointerId);pts.set(e.pointerId,[e.clientX,e.clientY]);cv.classList.add("drag");last=null;});
cv.addEventListener("pointermove",e=>{if(!pts.has(e.pointerId))return;const prev=pts.get(e.pointerId);pts.set(e.pointerId,[e.clientX,e.clientY]);
 if(pts.size===1){view.cx-=(e.clientX-prev[0])/view.s;view.cy+=(e.clientY-prev[1])/view.s;draw();}
 else if(pts.size===2){const [a,b]=[...pts.values()];const d=Math.hypot(a[0]-b[0],a[1]-b[1]);
  if(last){const r=cv.getBoundingClientRect();zoomAt(d/last,(a[0]+b[0])/2-r.left,(a[1]+b[1])/2-r.top);}last=d;}});
const up=e=>{pts.delete(e.pointerId);if(!pts.size)cv.classList.remove("drag");last=null;};
cv.addEventListener("pointerup",up);cv.addEventListener("pointercancel",up);
$("zin").onclick=()=>zoomAt(1.5,W/2,H/2);$("zout").onclick=()=>zoomAt(1/1.5,W/2,H/2);$("zfit").onclick=()=>{fit();draw();};
new ResizeObserver(resize).observe(cv);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change",panel);
new MutationObserver(panel).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
panel();
})();
</script>"""


def save_page(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(PAGE, encoding="utf-8")
    return p

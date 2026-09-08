"""coverage_from_plans.py — Compute covered footprint from a set of FLOWN .plan files (clean plan
geometry, no .nav extraction). Buffer each plan's flight path by the LiDAR half-swath; add any
polygon-survey areas; union; diff against a target KML. Reports % covered and writes missed KML.

Buffering the waypoint PATH by half-swath (= AGL for 90 deg FOV) is correct for these plans:
a 2-transect corridor / 2-pass tap already flies both offset lines, so path-buffer by AGL gives
the full +/-1.5*AGL corridor coverage; a polygon survey's own polygon IS its coverage.

USAGE:
  python coverage_from_plans.py --plans a.plan b.plan ... --target t.kml --agl 50 --fov 90 --out missed.kml
  python coverage_from_plans.py --glob "F:/.../Fergus50_S*.plan" --also-glob "F:/.../Fergus50_Gap*.plan" --target ...
"""
import os, re, json, math, argparse, glob
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

def kml_poly(path):
    m=re.search(r'<coordinates>([\s\S]*?)</coordinates>',open(path,encoding='utf-8',errors='ignore').read())
    return [(float(t.split(',')[1]),float(t.split(',')[0])) for t in m.group(1).split() if len(t.split(','))>=2]

def plan_geoms(path, to_xy, half):
    """Return list of shapely polys covering this plan: path buffer + any survey polygons."""
    p=json.load(open(path)); its=p['mission']['items']; out=[]
    pts=[to_xy(it['params'][4],it['params'][5]) for it in its if it.get('command') in (16,17)]
    if len(pts)>1: out.append(LineString(pts).buffer(half))
    for it in its:
        if it.get('complexItemType')=='survey':
            out.append(Polygon([to_xy(a,o) for a,o in it['polygon']]).buffer(0))
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--plans",nargs="*",default=[]); ap.add_argument("--glob",nargs="*",default=[])
    ap.add_argument("--target",required=True); ap.add_argument("--agl",type=float,default=50.0)
    ap.add_argument("--fov",type=float,default=90.0); ap.add_argument("--out",default="C:/Users/rharbach.STAHLY/Downloads/Fergus_missed_fromplans.kml")
    a=ap.parse_args()
    files=list(a.plans)
    for g in a.glob: files+=sorted(glob.glob(g))
    files=[f for f in files if f.lower().endswith('.plan')]
    half=a.agl*math.tan(math.radians(a.fov/2))
    tll=kml_poly(a.target); reflat=sum(p[0] for p in tll)/len(tll); reflon=sum(p[1] for p in tll)/len(tll)
    ml=111132; mo=111132*math.cos(math.radians(reflat))
    to_xy=lambda la,lo:((lo-reflon)*mo,(la-reflat)*ml); from_xy=lambda x,y:(reflat+y/ml,reflon+x/mo)
    tgt=Polygon([to_xy(*p) for p in tll]).buffer(0)
    print(f"{len(files)} plan files; half-swath {half:.0f} m")
    geoms=[]
    for f in files:
        g=plan_geoms(f,to_xy,half); geoms+=g
    combined=unary_union(geoms)
    cov=tgt.intersection(combined); uncov=tgt.difference(combined)
    print(f"Target: {tgt.area/4046.86:.1f} ac | Covered {cov.area/4046.86:.1f} ac ({100*cov.area/tgt.area:.1f}%) | MISSED {uncov.area/4046.86:.1f} ac ({100*uncov.area/tgt.area:.1f}%)")
    chunks=[g for g in (uncov.geoms if isinstance(uncov,MultiPolygon) else [uncov]) if g.area>1000]
    chunks.sort(key=lambda g:-g.area)
    out=['<?xml version="1.0" encoding="UTF-8"?>','<kml xmlns="http://www.opengis.net/kml/2.2"><Document>','<name>Missed (from plans)</name>',
         '<Style id="m"><LineStyle><color>ff0000ff</color><width>2</width></LineStyle><PolyStyle><color>7f0000ff</color></PolyStyle></Style>']
    for i,g in enumerate(chunks,1):
        c=g.centroid;cll=from_xy(c.x,c.y)
        ring=' '.join(f"{from_xy(x,y)[1]},{from_xy(x,y)[0]},0" for x,y in g.exterior.coords)
        out.append(f'<Placemark><name>Missed {i} ({g.area/4046.86:.1f} ac) @ {cll[0]:.5f},{cll[1]:.5f}</name><styleUrl>#m</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Document></kml>')
    open(a.out,'w',encoding='utf-8').write('\n'.join(out))
    print(f"Missed chunks >0.25 ac: {len(chunks)}; wrote {a.out}")
    for i,g in enumerate(chunks[:15],1):
        c=g.centroid;cll=from_xy(c.x,c.y);print(f"  Missed {i}: {g.area/4046.86:5.1f} ac @ {cll[0]:.5f},{cll[1]:.5f}")

if __name__=="__main__": main()

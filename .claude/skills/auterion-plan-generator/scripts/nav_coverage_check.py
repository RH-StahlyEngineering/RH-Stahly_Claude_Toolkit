"""nav_coverage_check.py — Compute the actual LiDAR-covered footprint from a flown Phoenix .nav
trajectory, and (optionally) diff it against a target/gap polygon to find uncovered holes.

WHY: a plan can pass every generation check and still leave a real hole if the survey polygon
was drawn smaller than the target (see Gap 1 / Area4, 2026-07-17 — 47% uncovered, caught only
after demob). This closes the loop between PLANNED and ACTUALLY-FLOWN coverage.

METHOD (read-only on the .nav):
  1. Scan the NovAtel-binary .nav for little-endian doubles that fall in a plausible lat/lon
     window (a robust heuristic — no full log parse needed; same trick used for extent checks).
  2. Decimate to a manageable path, buffer each fix by the LiDAR half-swath, union -> footprint.
     Half-swath = AGL * tan(FOV/2). For the MiniRanger (90 deg FOV): half-swath = AGL
     (so swath = 2*AGL; at 50 m AGL the ground swath is ~100 m per pass).
  3. Report footprint area. If --target <polygon.kml> given, report % of the target covered and
     write the uncovered remainder to a KML for a quick eyeball.

USAGE:
  python nav_coverage_check.py <scan.nav> [--agl 50] [--fov 90] [--target gap.kml] [--out cover.kml]

NOTE: overlap % is a PLANNING input (sets line spacing); it does NOT affect footprint-from-flown,
because the flown trajectory already reflects where the lines actually went. AGL (-> swath) is
the parameter that matters here.
"""
import sys, os, re, math, struct, argparse
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

def load_nav_points(path, lat_win=(47.0,47.6), lon_win=(-109.6,-108.7), step=4):
    data=open(path,'rb').read(); pts=[]
    for off in range(0,len(data)-16,step):
        a=struct.unpack_from("<d",data,off)[0]
        if lat_win[0]<a<lat_win[1]:
            b=struct.unpack_from("<d",data,off+8)[0]
            if lon_win[0]<b<lon_win[1]:
                pts.append((a,b))
    return pts

def load_kml_polygon(path):
    m=re.search(r'<coordinates>([\s\S]*?)</coordinates>',open(path).read())
    return [(float(t.split(',')[1]),float(t.split(',')[0])) for t in m.group(1).split() if len(t.split(','))>=2]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("nav"); ap.add_argument("--agl",type=float,default=50.0)
    ap.add_argument("--fov",type=float,default=90.0); ap.add_argument("--target",default=None)
    ap.add_argument("--out",default=None); ap.add_argument("--decimate",type=int,default=25)
    a=ap.parse_args()
    half_swath=a.agl*math.tan(math.radians(a.fov/2))
    print(f"AGL {a.agl} m, FOV {a.fov} deg -> ground swath {2*half_swath:.0f} m (half {half_swath:.0f} m)")
    pts=load_nav_points(a.nav)
    if not pts: print("No trajectory fixes found in lat/lon window."); return
    reflat=sum(p[0] for p in pts)/len(pts); reflon=sum(p[1] for p in pts)/len(pts)
    ml=111132; mo=111132*math.cos(math.radians(reflat))
    to_xy=lambda la,lo:((lo-reflon)*mo,(la-reflat)*ml); from_xy=lambda x,y:(reflat+y/ml,reflon+x/mo)
    xy=[to_xy(*p) for p in pts][::a.decimate]
    print(f"{len(pts)} fixes -> {len(xy)} after decimate; building footprint...")
    foot=unary_union([__import__('shapely.geometry',fromlist=['Point']).Point(x,y).buffer(half_swath) for x,y in xy])
    print(f"Flown footprint area: {foot.area/4046.86:.1f} ac")
    if a.target:
        tgt=Polygon([to_xy(*p) for p in load_kml_polygon(a.target)]).buffer(0)
        cov=tgt.intersection(foot).area; uncov=tgt.difference(foot)
        print(f"Target: {tgt.area/4046.86:.1f} ac | covered {100*cov/tgt.area:.0f}% | UNCOVERED {uncov.area/4046.86:.1f} ac")
        if uncov.area>200:
            geoms=uncov.geoms if isinstance(uncov,MultiPolygon) else [uncov]
            out=['<?xml version="1.0"?>','<kml xmlns="http://www.opengis.net/kml/2.2"><Document>','<name>Uncovered</name>',
                 '<Style id="u"><PolyStyle><color>7f0000ff</color></PolyStyle></Style>']
            for g in geoms:
                ring=' '.join(f"{from_xy(x,y)[1]},{from_xy(x,y)[0]},0" for x,y in g.exterior.coords)
                out.append(f'<Placemark><styleUrl>#u</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
            out.append('</Document></kml>')
            op=a.out or (os.path.splitext(a.nav)[0]+"_uncovered.kml")
            open(op,'w').write('\n'.join(out)); print(f"Wrote uncovered polygon: {op}")

if __name__=="__main__": main()

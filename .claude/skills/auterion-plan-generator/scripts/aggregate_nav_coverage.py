"""aggregate_nav_coverage.py — Extract the flown footprint from EVERY scan .nav under one or more
roots, union them, and diff against a target KML to find what was missed.

Builds on nav_coverage_check.py's single-scan method (read-only lat/lon double-scan -> buffer each
fix by the LiDAR half-swath -> union). Aggregates across all scans, intersects the combined
footprint with the target, and writes the uncovered remainder to a KML.

USAGE:
  python aggregate_nav_coverage.py --roots D:\ E:\ --target "target.kml" --agl 50 --fov 90 --out missed.kml
"""
import os, sys, re, math, argparse, glob
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

LAT_WIN=(47.0,47.6); LON_WIN=(-109.7,-108.6)

def find_navs(roots):
    out=[]
    for r in roots:
        for d in sorted(glob.glob(os.path.join(r,"*"))):
            if os.path.isdir(d):
                for nav in glob.glob(os.path.join(d,"*.nav")):
                    out.append(nav)
    return out

def _hav(a1,o1,a2,o2):
    R=6371000;p1=math.radians(a1);p2=math.radians(a2);dp=math.radians(a2-a1);dl=math.radians(o2-o1)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*R*math.asin(math.sqrt(x))

def nav_points(path):
    """DENSE extraction: scan ALL 8 byte-alignments (the lat/lon field is not 8-byte aligned in the
    .nav record structure — a step=8 scan misses ~99% of fixes and leaves large holes). Returns fixes
    in file/time order after rejecting isolated spikes."""
    raw=np.frombuffer(open(path,'rb').read(),dtype=np.uint8)
    offs=[]; la=[]; lo=[]
    for al in range(8):
        n=(len(raw)-al)//8
        if n<2: continue
        d=raw[al:al+n*8].view(np.float64)
        m=(d[:-1]>LAT_WIN[0])&(d[:-1]<LAT_WIN[1])&(d[1:]>LON_WIN[0])&(d[1:]<LON_WIN[1])
        idx=np.where(m)[0]
        if idx.size:
            offs.append(al+idx*8); la.append(d[idx]); lo.append(d[idx+1])
    if not offs: return []
    offs=np.concatenate(offs); la=np.concatenate(la); lo=np.concatenate(lo)
    order=np.argsort(offs); la=la[order]; lo=lo[order]
    # vectorized spike reject: drop point isolated from BOTH neighbors (>~300 m).
    # approx planar metres (fine for a spike test): dlat*111132, dlon*111132*cos(lat)
    coslat=np.cos(np.radians(la))
    dyp=np.empty_like(la); dxp=np.empty_like(la); dyn=np.empty_like(la); dxn=np.empty_like(la)
    dyp[1:]=(la[1:]-la[:-1])*111132; dxp[1:]=(lo[1:]-lo[:-1])*111132*coslat[1:]; dyp[0]=dxp[0]=0
    dyn[:-1]=(la[1:]-la[:-1])*111132; dxn[:-1]=(lo[1:]-lo[:-1])*111132*coslat[:-1]; dyn[-1]=dxn[-1]=0
    dprev=np.hypot(dyp,dxp); dnext=np.hypot(dyn,dxn)
    keep=(dprev<300)|(dnext<300); keep[0]=keep[-1]=True
    return list(zip(la[keep].tolist(), lo[keep].tolist()))

def kml_poly(path):
    m=re.search(r'<coordinates>([\s\S]*?)</coordinates>',open(path,encoding='utf-8',errors='ignore').read())
    return [(float(t.split(',')[1]),float(t.split(',')[0])) for t in m.group(1).split() if len(t.split(','))>=2]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--roots",nargs="+",required=True); ap.add_argument("--target",required=True)
    ap.add_argument("--agl",type=float,default=50.0); ap.add_argument("--fov",type=float,default=90.0)
    ap.add_argument("--decimate",type=int,default=30); ap.add_argument("--min-fixes",type=int,default=500)
    ap.add_argument("--out",default="C:/Users/rharbach.STAHLY/Downloads/Fergus_missed.kml")
    a=ap.parse_args()
    half=a.agl*math.tan(math.radians(a.fov/2))
    tgt_ll=kml_poly(a.target); reflat=sum(p[0] for p in tgt_ll)/len(tgt_ll); reflon=sum(p[1] for p in tgt_ll)/len(tgt_ll)
    ml=111132; mo=111132*math.cos(math.radians(reflat))
    to_xy=lambda la,lo:((lo-reflon)*mo,(la-reflat)*ml); from_xy=lambda x,y:(reflat+y/ml,reflon+x/mo)
    tgt=Polygon([to_xy(*p) for p in tgt_ll]).buffer(0)
    navs=find_navs(a.roots)
    print(f"Found {len(navs)} .nav files; half-swath {half:.0f} m (swath {2*half:.0f} m)")
    foots=[]; valid=0; skipped=[]
    for nav in navs:
        pts=nav_points(nav)
        if len(pts)<a.min_fixes: skipped.append((os.path.basename(nav),len(pts))); continue
        xy=[to_xy(*p) for p in pts][::a.decimate]
        # buffer the trajectory as a continuous PATH (hole-free regardless of sample density)
        f=LineString(xy).buffer(half) if len(xy)>1 else None
        if f is None: skipped.append((os.path.basename(nav),len(pts))); continue
        foots.append(f); valid+=1
        print(f"  {os.path.basename(nav):28s} {len(pts):6d} fixes -> {f.area/4046.86:6.1f} ac")
    if skipped:
        print(f"  (skipped {len(skipped)} scans with <{a.min_fixes} in-area fixes: {', '.join(s[0][:15] for s in skipped[:8])}{'...' if len(skipped)>8 else ''})")
    combined=unary_union(foots)
    cov=tgt.intersection(combined); uncov=tgt.difference(combined)
    print(f"\n=== {valid} valid flights ===")
    print(f"Target area:      {tgt.area/4046.86:.1f} ac")
    print(f"Covered:          {cov.area/4046.86:.1f} ac ({100*cov.area/tgt.area:.1f}%)")
    print(f"MISSED:           {uncov.area/4046.86:.1f} ac ({100*uncov.area/tgt.area:.1f}%)")
    geoms=[g for g in (uncov.geoms if isinstance(uncov,MultiPolygon) else [uncov]) if g.area>1000]  # >0.25 ac
    geoms.sort(key=lambda g:-g.area)
    print(f"Missed chunks >0.25 ac: {len(geoms)}")
    out=['<?xml version="1.0" encoding="UTF-8"?>','<kml xmlns="http://www.opengis.net/kml/2.2"><Document>','<name>Fergus MISSED coverage</name>',
         '<Style id="m"><LineStyle><color>ff0000ff</color><width>2</width></LineStyle><PolyStyle><color>7f0000ff</color></PolyStyle></Style>']
    for i,g in enumerate(geoms,1):
        c=g.centroid;cll=from_xy(c.x,c.y)
        ring=' '.join(f"{from_xy(x,y)[1]},{from_xy(x,y)[0]},0" for x,y in g.exterior.coords)
        out.append(f'<Placemark><name>Missed {i} ({g.area/4046.86:.1f} ac) @ {cll[0]:.5f},{cll[1]:.5f}</name><styleUrl>#m</styleUrl><Polygon><outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>')
    out.append('</Document></kml>')
    open(a.out,'w',encoding='utf-8').write('\n'.join(out))
    print(f"Wrote {a.out}")
    for i,g in enumerate(geoms[:12],1):
        c=g.centroid;cll=from_xy(c.x,c.y);print(f"  Missed {i}: {g.area/4046.86:5.1f} ac @ {cll[0]:.5f},{cll[1]:.5f}")

if __name__=="__main__": main()

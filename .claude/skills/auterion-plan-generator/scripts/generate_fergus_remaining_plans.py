"""Generate the 3 base-constrained power-cycle .plan files for the Fergus remaining taps+areas.

Per session decisions (2026-07-16):
  - 3 power cycles, one PPK base each, whole trajectory <=10 mi from base:
      Cycle1 (CP5): Tap1,Tap2,Area1,Tap3-9
      Cycle2 (CP1): Tap10-27
      Cycle3 (CP2): Tap28,Tap29,Area2,Area3,Tap30-33,Area4
  - Taps = 2-pass line corridor, +/-25 m offset, 50 ft (15.24 m) end buffer, NO closing transect.
  - Areas = TransectStyleComplexItem polygon survey, angle=long axis, 50 ft ends + 25 ft (7.62 m) sides buffer.
  - AGL 50 m, line spacing 50 m, speed 11.5 m/s.
  - Cal (kinematic line + figure-8) brackets each power cycle: start = kinematic->fig8, end = fig8->kinematic.
  - Rally point near last WP (Ryan's 8BA pattern).
Output: Fergus_Remaining_Cycle{1,2,3}_{CP5,CP1,CP2}.plan in AMC Missions + E-drive.
"""
import os, sys, json, re, math, shutil
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, 'scripts'))
import dem_lookup
_explicit = os.path.expanduser('~/.claude/dem_cache/dem_ee0aa3a8a9d0.json')
if os.path.exists(_explicit):
    dem_lookup._explicit_meta_paths.insert(0, _explicit); dem_lookup._local_dem=None; dem_lookup._local_meta=None
from dem_lookup import terrain_amsl
from figure8 import fig8_waypoints
from shapely.geometry import Polygon
from shapely.affinity import rotate as shp_rotate

KML = "C:/Users/rharbach.STAHLY/Downloads/2026-07-16_lidar_remaining.kml"
OUT_DIR = "C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions"
E_DRIVE = "E:/Fergus_Electric_Lidar/Lidar_mission_plans"
AGL=50.0; SPEED=11.5; OFFSET=AGL/2; SPACING=50.0
END_BUF=15.24; SIDE_BUF=7.62; KIN_LEN=SPEED*11.0; FIG8_DUR=15.0
RALLY_E=37.3; RALLY_N=45.4; RALLY_ALT=45.72

CYCLES = [
    ("C1_CP5", ["Tap1","Tap2","Area1","Tap3","Tap4","Tap5","Tap6","Tap7","Tap8","Tap9"]),
    ("C2_CP1", [f"Tap{i}" for i in range(10,28)]),
    ("C3_CP2", ["Tap28","Tap29","Area2","Area3","Tap30","Tap31","Tap32","Tap33","Area4"]),
]
FLY_THRESHOLD_M = 4000 * 0.3048   # 4000 ft: gaps larger than this -> land & drive (new sub-mission plan)
TERRAIN_TOL_M = 10.0              # lesson #39f: hold AGL within +/-10 m
TERRAIN_SAMPLE_M = 5.0
TERRAIN_MIN_SEG_M = 30.0          # min spacing before override

def load_items():
    txt=open(KML).read(); items={}
    for pm in re.findall(r'<Placemark[\s\S]*?</Placemark>',txt):
        nm=re.search(r'<name>((Tap|Area)\d+)</name>',pm)
        if not nm: continue
        m=re.search(r'<coordinates>([\s\S]*?)</coordinates>',pm)
        pts=[(float(t.split(',')[1]),float(t.split(',')[0])) for t in m.group(1).split() if len(t.split(','))>=2]
        kind='tap' if '<LineString>' in pm else 'area'
        items[nm.group(1)]=(kind,pts)
    return items

def proj(reflat,reflon):
    ml=111132.0; mo=111132.0*math.cos(math.radians(reflat))
    return (lambda la,lo:((lo-reflon)*mo,(la-reflat)*ml)), (lambda x,y:(reflat+y/ml,reflon+x/mo))

def wp(cmd,lat,lon,amsl,dj,idx,frame=0,params=None):
    it={'MISSION_ITEM_ID':str(idx),'autoContinue':True,'command':cmd,'doJumpId':dj,'frame':frame,
        'groupTag':0,'params':params or [0,0,0,None,lat,lon,amsl],'type':'SimpleItem'}
    if cmd in (16,17): it['AMSLAltAboveTerrain']=amsl; it['Altitude']=AGL; it['AltitudeMode']=3
    return it

def unit(dx,dy):
    L=math.hypot(dx,dy); return (dx/L,dy/L) if L>1e-9 else (1.0,0.0)

def densify_offset(pts_xy, off, extend):
    """Return offset polyline (perp offset 'off'), extended 'extend' m at both ends, along-direction."""
    # per-vertex offset using average of adjacent segment normals
    out=[]
    n=len(pts_xy)
    for i in range(n):
        if i==0: dx,dy=pts_xy[1][0]-pts_xy[0][0],pts_xy[1][1]-pts_xy[0][1]
        elif i==n-1: dx,dy=pts_xy[-1][0]-pts_xy[-2][0],pts_xy[-1][1]-pts_xy[-2][1]
        else: dx,dy=pts_xy[i+1][0]-pts_xy[i-1][0],pts_xy[i+1][1]-pts_xy[i-1][1]
        ux,uy=unit(dx,dy); nx,ny=uy,-ux  # right normal
        out.append((pts_xy[i][0]+nx*off, pts_xy[i][1]+ny*off))
    # extend ends
    ux0,uy0=unit(out[1][0]-out[0][0],out[1][1]-out[0][1])
    out[0]=(out[0][0]-ux0*extend,out[0][1]-uy0*extend)
    uxn,uyn=unit(out[-1][0]-out[-2][0],out[-1][1]-out[-2][1])
    out[-1]=(out[-1][0]+uxn*extend,out[-1][1]+uyn*extend)
    return out

def terrain_refine(pts_xy, from_xy):
    """Lesson #39f: subdivide each segment so straight-line AMSL stays within TERRAIN_TOL_M of terrain+AGL.
    pts_xy = list of (x,y). Returns list of (x,y,amsl)."""
    def amsl_at(x,y):
        la,lo=from_xy(x,y); return terrain_amsl(la,lo)+AGL
    pts=[(x,y,amsl_at(x,y)) for x,y in pts_xy]
    def refine(p1,p2):
        dx=p2[0]-p1[0]; dy=p2[1]-p1[1]; L=math.hypot(dx,dy)
        if L<TERRAIN_MIN_SEG_M: return [p1,p2]
        n=max(2,int(L/TERRAIN_SAMPLE_M)); mdev=0; mk=None
        for k in range(1,n):
            f=k/n; x=p1[0]+dx*f; y=p1[1]+dy*f; interp=p1[2]+(p2[2]-p1[2])*f
            dev=amsl_at(x,y)-interp
            if abs(dev)>abs(mdev): mdev=dev; mk=f
        if abs(mdev)<=TERRAIN_TOL_M or mk is None: return [p1,p2]
        sx=p1[0]+dx*mk; sy=p1[1]+dy*mk; sp=(sx,sy,amsl_at(sx,sy))
        return refine(p1,sp)[:-1]+refine(sp,p2)
    out=[pts[0]]
    for i in range(len(pts)-1): out+=refine(pts[i],pts[i+1])[1:]
    return out

def emit_line(items,pts_xy,from_xy,dj,idx):
    for x,y,a in terrain_refine(pts_xy,from_xy):
        la,lo=from_xy(x,y)
        items.append(wp(16,la,lo,a,dj[0],idx[0])); dj[0]+=1; idx[0]+=1

def build_tap(items,pts,to_xy,from_xy,dj,idx):
    xy=[to_xy(la,lo) for la,lo in pts]
    p1=densify_offset(xy,+OFFSET,END_BUF)      # pass 1 (+25)
    p2=densify_offset(xy,-OFFSET,END_BUF)      # pass 2 (-25)
    emit_line(items,p1,from_xy,dj,idx)
    emit_line(items,list(reversed(p2)),from_xy,dj,idx)  # return pass

def build_area(items,pts,to_xy,from_xy,dj,idx):
    xy=[to_xy(la,lo) for la,lo in pts]
    poly=Polygon(xy)
    if not poly.is_valid: poly=poly.buffer(0)
    cx,cy=poly.centroid.x,poly.centroid.y
    # PCA long axis
    Sxx=Syy=Sxy=0
    for x,y in xy: dx=x-cx;dy=y-cy;Sxx+=dx*dx;Syy+=dy*dy;Sxy+=dx*dy
    th=0.5*math.atan2(2*Sxy,Sxx-Syy); thd=math.degrees(th)
    # buffer in rotated (axis-aligned) frame: +END_BUF along axis (x), +SIDE_BUF perp (y)
    pr=shp_rotate(poly,-thd,origin=(cx,cy))
    minx,miny,maxx,maxy=pr.bounds
    from shapely.geometry import box
    buf=box(minx-END_BUF,miny-SIDE_BUF,maxx+END_BUF,maxy+SIDE_BUF)
    bufpoly=shp_rotate(buf,thd,origin=(cx,cy))
    coords_ll=[list(from_xy(x,y)) for x,y in list(bufpoly.exterior.coords)[:-1]]
    compass=(90.0-thd)%360.0
    it={'MISSION_ITEM_ID':str(idx[0]),'complexItemType':'survey','polygon':coords_ll,
        'angle':compass,'entryLocation':0,'flyAlternateTransects':False,'splitConcavePolygons':False,
        'type':'ComplexItem','version':5,'doJumpId':dj[0],
        'TransectStyleComplexItem':{'CameraCalc':{'CameraName':'Manual (no camera specs)','DistanceToSurface':AGL,
            'DistanceToSurfaceRelative':False,'AdjustedFootprintSide':SPACING,'AdjustedFootprintFrontal':25.0,'version':1},
            'CameraShots':0,'CameraTriggerInTurnAround':False,'FlightSpeed':SPEED,'FollowTerrain':True,
            'HoverAndCapture':False,'Items':[],'Refly90Degrees':False,'TerrainAdjustMaxClimbRate':3.0,
            'TerrainAdjustMaxDescentRate':3.0,'TerrainAdjustTolerance':5.0,'TurnAroundDistance':15.24,
            'VisualTransectPoints':[],'version':1}}
    items.append(it); dj[0]+=1; idx[0]+=1

def cal_block(items,center_ll,to_xy,from_xy,dj,idx,order):
    """order='start' -> kinematic then fig8; 'end' -> fig8 then kinematic."""
    clat,clon=center_ll
    cx,cy=to_xy(clat,clon)
    def kinematic():
        # perpendicular-ish straight line KIN_LEN, centered at (cx,cy), heading east
        k1=(cx-KIN_LEN/2,cy); k2=(cx+KIN_LEN/2,cy)
        for x,y in (k1,k2):
            la,lo=from_xy(x,y); a=terrain_amsl(la,lo)+AGL
            items.append(wp(16,la,lo,a,dj[0],idx[0])); dj[0]+=1; idx[0]+=1
    def fig8():
        camsl=terrain_amsl(clat,clon)+AGL
        f=fig8_waypoints(lat=clat,lon=clon,alt_amsl=camsl,speed=SPEED,duration=FIG8_DUR,frame=0)
        for w in f:
            la=w['params'][4];lo=w['params'][5];a=terrain_amsl(la,lo)+AGL
            items.append(wp(16,la,lo,a,dj[0],idx[0])); dj[0]+=1; idx[0]+=1
    if order=='start': kinematic(); fig8()
    else: fig8(); kinematic()

def item_center(kind,pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def nearest_gap(a_pts,b_pts):
    def hav(p,q):
        R=6371000;p1=math.radians(p[0]);p2=math.radians(q[0]);dp=math.radians(q[0]-p[0]);dl=math.radians(q[1]-p[1])
        x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*R*math.asin(math.sqrt(x))
    return min(hav(a,b) for a in a_pts for b in b_pts)

def main():
    allitems=load_items()
    allpts=[p for k,(kind,pts) in allitems.items() for p in pts]
    reflat=sum(p[0] for p in allpts)/len(allpts); reflon=sum(p[1] for p in allpts)/len(allpts)
    to_xy,from_xy=proj(reflat,reflon)

    # Build sub-missions: within each cycle, split at gaps > FLY_THRESHOLD_M
    plan_specs=[]  # (cycle_name, seq_in_cycle, n_runs_in_cycle, names, is_cycle_first, is_cycle_last)
    for cyc_name,names in CYCLES:
        runs=[[names[0]]]
        for i in range(1,len(names)):
            gap=nearest_gap(allitems[names[i-1]][1],allitems[names[i]][1])
            if gap>FLY_THRESHOLD_M: runs.append([names[i]])
            else: runs[-1].append(names[i])
        for si,run in enumerate(runs):
            plan_specs.append((cyc_name,si+1,len(runs),run,si==0,si==len(runs)-1))

    print(f"{len(plan_specs)} plan files across {len(CYCLES)} power cycles\n")
    for cyc_name,seq,nruns,names,is_first,is_last in plan_specs:
        items=[]; dj=[1]; idx=[0]
        items.append({'MISSION_ITEM_ID':'0','autoContinue':True,'command':530,'doJumpId':1,'frame':2,
                      'groupTag':0,'params':[0,2,None,None,None,None,None],'type':'SimpleItem'}); dj[0]=2; idx[0]=1
        items.append({'MISSION_ITEM_ID':'1','autoContinue':True,'command':178,'doJumpId':2,'frame':2,
                      'groupTag':0,'params':[1,SPEED,-1,0,0,0,0],'type':'SimpleItem'}); dj[0]=3; idx[0]=2
        first=allitems[names[0]]; last=allitems[names[-1]]
        if is_first: cal_block(items,item_center(*first),to_xy,from_xy,dj,idx,'start')
        for nm in names:
            kind,pts=allitems[nm]
            if kind=='tap': build_tap(items,pts,to_xy,from_xy,dj,idx)
            else: build_area(items,pts,to_xy,from_xy,dj,idx)
        if is_last: cal_block(items,item_center(*last),to_xy,from_xy,dj,idx,'end')
        hlat,hlon=item_center(*first); hg=terrain_amsl(hlat,hlon)
        lastwp=next(it for it in reversed(items) if it.get('command') in (16,17))
        rlat=lastwp['params'][4]+RALLY_N/111132.0
        rlon=lastwp['params'][5]+RALLY_E/(111132.0*math.cos(math.radians(lastwp['params'][4])))
        plan={'fileType':'Plan','geoFence':{'circles':[],'polygons':[],'version':2},'groundStation':'QGroundControl',
              'mission':{'cruiseSpeed':15,'firmwareType':12,'globalPlanAltitudeMode':3,'hoverSpeed':10,
                         'items':items,'plannedHomePosition':[hlat,hlon,hg],'vehicleType':2,'version':2},
              'rallyPoints':{'points':[[rlat,rlon,RALLY_ALT]],'version':2},'version':1}
        tag='+startcal' if is_first else ('+endcal' if is_last else '')
        label=names[0]+("-"+names[-1] if len(names)>1 else "")
        fn=f"Fergus_Rem_{cyc_name}_p{seq}of{nruns}_{label}.plan"
        with open(os.path.join(OUT_DIR,fn),'wb') as f: f.write(json.dumps(plan,separators=(',',':')).encode())
        if os.path.isdir(E_DRIVE): shutil.copy(os.path.join(OUT_DIR,fn),os.path.join(E_DRIVE,fn))
        print(f"{fn}: {len(items)} items, {len(names)} item(s) [{', '.join(names)}] {tag}")

if __name__=='__main__': main()

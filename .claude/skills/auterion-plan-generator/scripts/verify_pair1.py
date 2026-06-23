"""Verify Fergus3.plan + Fergus4.plan structure."""
import json, os, math

OUT = 'C:/Users/rharbach.STAHLY/Documents/Auterion Mission Control/Missions'

def hav(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1]); dp = p2 - p1
    x = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

for nm in ['Fergus3', 'Fergus4']:
    p = f'{OUT}/{nm}.plan'
    sz = os.path.getsize(p)
    with open(p, 'rb') as f:
        raw = f.read()
    has_cr = b'\r' in raw
    has_lf = b'\n' in raw
    pretty = b'    ' in raw
    plan = json.loads(raw.decode('utf-8'))
    items = plan['mission']['items']
    cmd_counts = {}
    for it in items:
        c = it.get('command', it.get('complexItemType', '?'))
        cmd_counts[c] = cmd_counts.get(c, 0) + 1
    cs = next((it for it in items if it.get('complexItemType') == 'CorridorScan'), None)
    poly = cs['polyline']
    fig8 = [it for it in items if it.get('command') == 16 and it.get('frame') == 0]
    cs_idx = items.index(cs)
    print(f'=== {nm}.plan ({sz} B) ===')
    print(f'  format: CRLF={has_cr}  LF={has_lf}  pretty-indent={pretty}')
    print(f'  outer item count: {len(items)}')
    print(f'  command tally: {cmd_counts}')
    print(f'  CorridorScan at outer index: {cs_idx}')
    print(f'  fig-8 items (cmd 16, frame 0) total: {len(fig8)}')
    fig8_before = sum(1 for it in items[:cs_idx] if it.get('command') == 16 and it.get('frame') == 0)
    fig8_after = sum(1 for it in items[cs_idx + 1:] if it.get('command') == 16 and it.get('frame') == 0)
    print(f'  fig-8 before CorridorScan: {fig8_before}')
    print(f'  fig-8 after  CorridorScan: {fig8_after}')
    print(f'  CorridorScan polyline: {len(poly)} pts')
    print(f'    first: ({poly[0][0]:.6f}, {poly[0][1]:.6f})  (away end)')
    print(f'    last:  ({poly[-1][0]:.6f}, {poly[-1][1]:.6f})  (entry/exit per EntryPoint=2)')
    total = sum(hav(poly[i-1], poly[i]) for i in range(1, len(poly)))
    print(f'  polyline total length: {total:.0f} m')
    cs_inner = cs['TransectStyleComplexItem']
    print(f'  CorridorScan internals:')
    print(f'    CorridorWidth = {cs["CorridorWidth"]}, EntryPoint = {cs["EntryPoint"]}')
    print(f'    DistanceToSurface = {cs_inner["CameraCalc"]["DistanceToSurface"]}')
    print(f'    FollowTerrain = {cs_inner["FollowTerrain"]}, TurnAround = {cs_inner["TurnAroundDistance"]}')
    print(f'    FlightSpeed = {cs_inner["FlightSpeed"]}')
    print(f'    Items (transects, AMC will regen): {len(cs_inner["Items"])}')
    print(f'  plannedHomePosition: {plan["mission"]["plannedHomePosition"]}')
    print(f'  cruiseSpeed = {plan["mission"]["cruiseSpeed"]}, globalPlanAltMode = {plan["mission"]["globalPlanAltitudeMode"]}')
    if fig8:
        alts = [it['params'][6] for it in fig8]
        print(f'  fig-8 alt AMSL range: [{min(alts):.2f}, {max(alts):.2f}]')
        # Fig-8 centroid is meeting_pt
        meeting = (47.34723084585915, -108.8744816613465)
        # Verify centroid presence (one of the 11 vertices should be at meeting_pt)
        match = next((it for it in fig8 if abs(it['params'][4] - meeting[0]) < 1e-7 and abs(it['params'][5] - meeting[1]) < 1e-7), None)
        print(f'  fig-8 contains meeting-point vertex: {match is not None}')
    print()

print('Cross-checks:')
# Open Fergus3 and Fergus4 and confirm their polylines share the meeting point
with open(f'{OUT}/Fergus3.plan', 'rb') as f:
    f3 = json.loads(f.read())
with open(f'{OUT}/Fergus4.plan', 'rb') as f:
    f4 = json.loads(f.read())
poly3 = f3['mission']['items'][next(i for i, it in enumerate(f3['mission']['items']) if it.get('complexItemType') == 'CorridorScan')]['polyline']
poly4 = f4['mission']['items'][next(i for i, it in enumerate(f4['mission']['items']) if it.get('complexItemType') == 'CorridorScan')]['polyline']
print(f'  Fergus3 last (meeting): {tuple(poly3[-1])}')
print(f'  Fergus4 last (meeting): {tuple(poly4[-1])}')
d_meet = hav(poly3[-1], poly4[-1])
print(f'  meeting-point match: {d_meet:.3f} m (should be 0)')
print(f'  Fergus3 first (east end = F2_W): {tuple(poly3[0])}')
F2_W = (47.350576, -108.851527)
d_f2w = hav(poly3[0], F2_W)
print(f'  Fergus3 east end vs F2_W: {d_f2w:.3f} m (should be 0)')
# Check Fergus2's polyline last point matches Fergus3 first (should be F2_W -- they meet at -108.851527)
with open(f'{OUT}/Fergus2.plan', 'rb') as f:
    f2 = json.loads(f.read())
poly2 = f2['mission']['items'][1]['polyline']
print(f'  Fergus2 first (= meets Fergus3 east end): {tuple(poly2[0])}')
d_f2_f3 = hav(poly2[0], poly3[0])
print(f'  Fergus2-Fergus3 boundary match: {d_f2_f3:.1f} m (within 1-2 m is fine)')

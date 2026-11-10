# session_activity.py — per-day active windows per Claude Code project from ~/.claude/projects JSONL message timestamps (15-min gap merge). Edit S/E dates.
import json,glob,os,sys,datetime as dt,collections
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
S=dt.datetime(2026,11,2).astimezone();E=dt.datetime(2026,11,8).astimezone()
ev=collections.defaultdict(list); first={}
for f in glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl')):
    p=os.path.basename(os.path.dirname(f))
    key=p
    for line in open(f,encoding='utf-8',errors='replace'):
        try:d=json.loads(line)
        except:continue
        t=d.get('timestamp')
        if not t or d.get('type') not in('user','assistant'):continue
        t=dt.datetime.fromisoformat(t.replace('Z','+00:00')).astimezone()
        if not(S<=t<E):continue
        if 'scratch' in p:
            # label scratch sessions by first real prompt
            if f not in first:first[f]=None
            if first[f] is None and d['type']=='user':
                c=d['message'].get('content')
                if isinstance(c,list):c=' '.join(x.get('text','') for x in c if isinstance(x,dict) and x.get('type')=='text')
                if c and not c.startswith('<') and len(c)>15:first[f]=' '.join(c.split())[:70]
            key='scratch:'+os.path.basename(f)[:8]
        elif 'Toole' in p or 'rthouse' in p: key='TooleCH'
        elif 'Agisoft' in p: key='Agisoft/DroneMapper'
        else: key=p[-30:]
        ev[key].append(t)
labels={'scratch:'+os.path.basename(f)[:8]:v for f,v in first.items()}
GAP=dt.timedelta(minutes=15)
byday=collections.defaultdict(list)
for k,ts in ev.items():
    ts.sort();s=e=ts[0]
    for t in ts[1:]+[None]:
        if t and t-e<=GAP and t.date()==s.date():e=t;continue
        byday[s.date()].append((s,e+dt.timedelta(minutes=5),k));
        if t:s=e=t
for day in sorted(byday):
    print(f"\n== {day:%a %m/%d}")
    tot=collections.defaultdict(float)
    for s,e,k in sorted(byday[day]):
        h=(e-s).total_seconds()/3600; tot[k]+=h
        if h>=0.25:print(f"  {s:%H:%M}-{e:%H:%M} {h:4.2f} {k} {labels.get(k) or ''}")
    for k,v in sorted(tot.items(),key=lambda x:-x[1]):
        if v>=0.2:print(f"   SUM {v:4.2f} {k} {labels.get(k) or ''}")

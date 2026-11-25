"""Print each new job row, job event and upload-check state from production Supabase (read-only).

Usage (bridge venv or any Python 3.11):
    python -I watch_job.py --job <uuid>            # one job
    python -I watch_job.py --since 2026-11-02T00:00Z  # any job created since
    python -I watch_job.py --job <uuid> --once     # exit after the first new line (single-fire)

State (lines already printed) lives in C:/t/watch/<key>.json, outside the session scratchpad,
so a restarted watch does not repeat old lines. Polls every 60 s; prints a WATCH ERROR line
after 5 failed polls in a row.
"""
import argparse
import json
import os
import subprocess
import time

CLI = r"C:\tools\supabase-cli\node_modules\.bin\supabase.cmd"
REF = "nyhfimkuazzuxojzqzka"

ap = argparse.ArgumentParser()
ap.add_argument("--job")
ap.add_argument("--since", default="2026-01-01T00:00:00Z")
ap.add_argument("--once", action="store_true")
args = ap.parse_args()

if args.job:
    jobs = f"select * from jobs where id='{args.job}'"
    ev_filter = f"e.job_id='{args.job}'"
    ck_filter = f"c.job_id='{args.job}'"
    key = args.job[:8]
else:
    jobs = f"select * from jobs where created_at > '{args.since}'"
    ev_filter = f"e.created_at > '{args.since}'"
    ck_filter = f"c.started_at > '{args.since}'"
    key = "since-" + args.since[:10]

SQL = f"""
with j as ({jobs})
select 'JOB ' || j.id || ' | ' || coalesce(j.project_name,'?') || ' | status=' || j.status
  || ' | images=' || coalesce(j.image_count::text,'-') || coalesce(' | REJECTED: ' || j.rejected_reason,'') as l from j
union all
select 'EVENT ' || e.job_id || ' | ' || e.event_type || ' @ '
  || to_char(e.created_at at time zone 'America/Denver','MM-DD HH24:MI:SS') || ' | ' || left(coalesce(e.payload::text,''),300)
  from job_events e where {ev_filter}
union all
select 'CHECK ' || c.job_id || ' | state=' || c.state || ' progress=' || coalesce(c.cursor::text,'-') || '/' || coalesce(c.total::text,'-')
  || coalesce(' | PARKED: ' || c.parked_reason,'') from job_upload_checks c where {ck_filter}
"""
SQL = " ".join(SQL.split())  # supabase.cmd breaks on multi-line SQL

os.makedirs("C:/t/watch", exist_ok=True)
state_path = f"C:/t/watch/{key}.json"
seen = set(json.load(open(state_path))) if os.path.exists(state_path) else set()
fails = 0
while True:
    try:
        out = subprocess.run([CLI, "db", "query", "--linked", "--project-ref", REF, SQL],
                             capture_output=True, text=True, timeout=120).stdout
        rows = json.loads(out[out.index("{"):out.rindex("}") + 1])["rows"]
        fails = 0
        new = [r["l"] for r in rows if r["l"] not in seen]
        for line in new:
            seen.add(line)
            print(line, flush=True)
        json.dump(sorted(seen), open(state_path, "w"))
        if new and args.once:
            break
    except Exception as ex:  # noqa: BLE001 -- a watch reports failure, it does not crash
        fails += 1
        if fails == 5:
            print(f"WATCH ERROR: 5 failed polls in a row: {ex}", flush=True)
    time.sleep(60)

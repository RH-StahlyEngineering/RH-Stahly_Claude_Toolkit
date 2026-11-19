"""Lead from the plan: print the backlog plan, then record in the state file what it calls for.

Usage: python -X utf8 -I lead.py --repo OWNER/NAME --areas AREAS.json [--base master]
       python -X utf8 -I lead.py --snapshot FILE --areas AREAS.json

Only the owning master may run it (a side conversation reads the plan with planner.py).
It replaces the plan's rows in the state file's queue, go and frozen lists, in ranked order:

  build:<group>      ready     tickets under a spec: start them, past the implement gate, without asking
  go:<group>         needs-rh  standalone ready issues: one go from RH per group (also a `go` row)
  win:#<n>           a quick win: one ready issue, under its own group's start rule (ready under a spec,
                     needs-rh standalone). The lane comes after the focus and rung 1-2 groups.
  held:#<n>          needs-rh  a held issue, as one question
  grill:<group>      needs-rh  a grill to propose        wayfinder:<group>  needs-rh  a map to propose
  triage:<group>     ready     the next group to triage, one at a time
  spec-check:<group> ready     a grill's spec is published: check the group's ready issues against it

Freeze: a group is frozen while an issue in it needs a grill, while a grill session runs in it (a
`running` row of kind grill), and from `frozen add <group> --reason "spec check: <spec>"` until
`frozen drop <group>`. A frozen group gets no build or go row, and none of its issues is offered through
another group or as a quick win; one with an open grill gets no second grill row. `unsorted` is never
frozen. Grill rows come with the one that unfreezes the most ready issues first, then by group rank.

A running session whose owed command is not confirmed run (`running add ... --command`, until `running sent`)
is printed first, under COMMAND NOT SENT. A group with a running session gets no build, go or triage row. A plan row whose state the master
changed (`blocked`: RH said not now) and every row the master added itself are kept as they are.
Read-only on GitHub: the open issues, and one compare per checked commit for the freshness check.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` leaves the script's folder out

import planner  # noqa: E402
import state as store  # noqa: E402

GRILL, WIN = "grill:", "win:"
PLAN_ROWS = (store.BUILD, store.GO, store.HELD, GRILL, WIN, "wayfinder:", "triage:", "spec-check:")
SESSION_POINTS = 8      # work one build session takes: sizes S 1, M 2, L 4, as in the planner
COMPARE_FILE_CAP = 300  # GitHub lists at most this many changed files in a compare
PRINT_ASKS = 20
TEXT_NUMBERS = 12


def _under(filename, path):
    path = path.strip("/")
    return filename == path or filename.startswith(path + "/")


def merged_since(repo, commit, base, gh):
    """Files merged to `base` since `commit`. None when that can't be read (count it as changed)."""
    try:
        found = json.loads(gh(["api", f"repos/{repo}/compare/{commit}...{base}"]))
        if not found["ahead_by"]:
            return []
        files = [f["filename"] for f in found["files"]]
        return files if 0 < len(files) < COMPARE_FILE_CAP else None
    except Exception:  # noqa: BLE001 - an unreadable compare means re-check
        return None


def needs_recheck(issue, plan, area_paths, merged):
    """True when the overnight check of this standalone issue may no longer hold."""
    if not issue["checked_commit"]:
        return True
    files = merged(issue["checked_commit"])
    if files is None:
        return True
    if not issue["areas"]:
        return bool(files)  # no area to match files against: any merge counts
    paths = [p for area in issue["areas"] for p in area_paths.get(area, [])]
    if any(_under(f, p) for f in files for p in paths):
        return True
    # A spec published in one of its areas after the check may have changed the design.
    for group in plan["groups"]:
        head = plan["issues"].get(group["id"].split("#")[-1]) if group["kind"] == "spec" else None
        if head and set(head["areas"]) & set(issue["areas"]) and (head["created_at"] or "") > (issue["checked_at"] or ""):
            return True
    return False


def _sessions(numbers, group, plan):
    """How many build sessions a group's ready issues start: related issues share one."""
    if group["kind"] == planner.UNSORTED:
        return len(numbers)  # no shared area, so nothing says they are related
    points = sum(planner.SIZE_POINTS.get(plan["issues"][str(n)]["size"], planner.SIZE_POINTS["M"]) for n in numbers)
    return max(1, math.ceil(points / SESSION_POINTS))


def _held_question(number, issue):
    """One held issue as one question with a pick."""
    reasons = issue["held"]
    replaced = next((r for r in reasons if r.startswith("replaced-by")), None)
    if replaced:
        ask = f"it is replaced by {replaced.split()[-1]}. Close it? Pick: close."
    elif "verdict-done" in reasons:
        ask = "the overnight check found it already done. Close it? Pick: close."
    elif "needs-human" in reasons:
        ask = "ready-for-agent but flagged needs-human. Keep it for you, or build it? Pick: keep it for you."
    else:
        ask = "the overnight check found it partly done. Send it back to triage? Pick: yes."
    title = issue["title"].replace("?", "")[:50]
    return f"Held #{number} {title} ({', '.join(reasons)}): {ask}"


def plan_rows(plan, state, area_paths, merged):
    """The queue, go and frozen rows this plan calls for, given what the state says is running or declined."""
    running = {s.get("group") for s in state["running"]}
    triaging = any(s.get("kind") == "triage" for s in state["running"])
    before = {r["id"]: r for r in state["queue"] if str(r.get("id", "")).startswith(PLAN_ROWS)}
    own = [r for r in state["queue"] if not str(r.get("id", "")).startswith(PLAN_ROWS)]
    queue, go, frozen, offered, asked = [], [], [], set(), set()
    briefs = {}  # the short form of each row for the printed list; the full question is the row's text

    def add(row_id, kind, row_state, group, text, brief):
        old = before.get(row_id)
        if old and old.get("state") != row_state:  # the master changed its state: it stays as the master set it
            queue.append(old)
            return False
        queue.append({"id": row_id, "kind": kind, "state": row_state, "group": group, "text": text})
        briefs[row_id] = brief
        return True

    # A grill is open in the group its session runs in, and in every group sharing an issue it grills.
    grilling = {s.get("group"): s.get("id") for s in state["running"] if s.get("kind") == "grill"}
    grilled = {n: grilling[g["id"]] for g in plan["groups"] if g["id"] in grilling for n in g["frozen_by"]}
    checks = {f["group"]: f["reason"][len(store.SPEC_CHECK):] for f in state["frozen"]
              if str(f.get("reason", "")).startswith(store.SPEC_CHECK)}

    # Why each group is frozen, if it is. The freeze is per issue: an issue that sits in any frozen group
    # is not offered or started through another group's row either.
    open_grills, reasons = {}, {}
    for group in plan["groups"]:
        gid = group["id"]
        if group["kind"] != planner.UNSORTED:
            open_grills[gid] = grilling.get(gid) or next((grilled[n] for n in group["frozen_by"] if n in grilled), None)
        if gid in checks:  # first, so the reason that holds the spec survives every run
            reasons[gid] = store.SPEC_CHECK + checks[gid]
        elif open_grills.get(gid):
            reasons[gid] = f"{store.GRILL_OPEN}: {open_grills[gid]}"
        elif group["frozen_by"]:
            reasons[gid] = f"{store.GRILL_NEEDED}: " + planner.numbers(group["frozen_by"], TEXT_NUMBERS)
    frozen_issues = {n for g in plan["groups"] if g["id"] in reasons for n in g["issues"]}

    def spec_check(gid, numbers):
        """A published spec waits for its check: the group stays frozen and the check is the master's step."""
        listed = planner.numbers(numbers, TEXT_NUMBERS)
        drop = f"`{store.RUN}state.py frozen drop {gid}`"
        if numbers:
            text = (f"Check {listed} of {gid} against spec {checks[gid]} with a read-only subagent, "
                    f"put the changed ones to RH, then {drop}.")
        else:
            text = f"Spec {checks[gid]}: nothing ready in {gid} to check. Unfreeze it: {drop}."
        frozen.append({"group": gid, "reason": store.SPEC_CHECK + checks[gid]})
        add(f"spec-check:{gid}", "spec-check", "ready", gid, text,
            f"{listed or 'nothing ready'} against spec {checks[gid]}")

    def fresh(ready):
        """', re-check #a #b first' or ', checks still stand' for standalone issues about to be offered."""
        stale = [n for n in ready if needs_recheck(plan["issues"][str(n)], plan, area_paths, merged)]
        return f", re-check {planner.numbers(stale, TEXT_NUMBERS)} first" if stale else ", checks still stand"

    def quick_wins():
        """The quick-wins lane: single ready issues, each under the start rules of its own group."""
        for win in plan["quick_wins"]:
            number = win["number"]
            home = next((g for g in plan["groups"] if number in g["ready"]), None)  # ready: not held, blocked or frozen
            if not home or number in frozen_issues or number in offered or home["id"] in running:
                continue
            offered.add(number)
            what = f"Quick win #{number} {win['title'].replace('?', '')[:50]} (rung {win['rung']}"
            what += ", found in use)" if win["found_in_use"] else ")"
            if home["kind"] == "spec":
                add(f"{WIN}#{number}", "build", "ready", home["id"],
                    f"{what}: start it under {home['id']} in one session. No ask needed once the implement gate "
                    "holds; if it does not, hold and ask RH for what is missing.",
                    f"{win['title'][:50]}, ticket under a spec, 1 session")
            else:
                line = "1 session" + fresh([number])
                add(f"{WIN}#{number}", "build", "needs-rh", home["id"], f"{what}: go? {line}. Pick: go.",
                    f"{win['title'][:50]}, {line}")

    wins_placed = False
    for group in plan["groups"]:
        gid, steps = group["id"], group["next_steps"]
        if not wins_placed and group["lane"] not in ("focus", "rung"):  # the lane's place in the spec's order
            wins_placed = True
            quick_wins()
        open_grill = open_grills.get(gid)
        if gid in checks:
            spec_check(gid, steps.get("build", []))
        elif gid in reasons:
            frozen.append({"group": gid, "reason": reasons[gid]})
        if steps.get("grill") and not open_grill:
            add(f"{GRILL}{gid}", "grill", "needs-rh", gid,
                f"Grill needed in {gid} ({group['title'][:40]}): {planner.numbers(steps['grill'], TEXT_NUMBERS)}. "
                "Start it? Pick: yes.", planner.numbers(steps["grill"], TEXT_NUMBERS))
        if steps.get("wayfinder"):
            add(f"wayfinder:{gid}", "wayfinder", "needs-rh", gid,
                f"Wayfinder work waits in {gid} ({group['title'][:40]}): "
                f"{planner.numbers(steps['wayfinder'], TEXT_NUMBERS)}. Start a wayfinder session? Pick: yes.",
                planner.numbers(steps["wayfinder"], TEXT_NUMBERS))
        ready = [n for n in group["ready"] if n not in offered and n not in frozen_issues]
        if ready and gid not in running:
            offered.update(ready)
            numbers = planner.numbers(ready, TEXT_NUMBERS)
            if group["kind"] == "spec":
                add(f"{store.BUILD}{gid}", "build", "ready", gid,
                    f"Start {numbers} under {gid} ({group['title'][:40]}) in one session. "
                    "No ask needed once the implement gate holds; if it does not, hold and ask RH for what is missing.",
                    f"{numbers}, tickets under a spec, 1 session")
            else:
                count = _sessions(ready, group, plan)
                line = f"{numbers}, {count} session{'s' if count != 1 else ''}" + fresh(ready)
                if add(f"{store.GO}{gid}", "build", "needs-rh", gid,
                       f"Go for {gid} ({group['title'][:40]})? {line}. Pick: go.", line):
                    go.append({"group": gid, "line": line})
        for number in group["held"]:
            issue = plan["issues"][str(number)]
            if issue["held"] != ["no-verdict"] and number not in asked:
                asked.add(number)
                add(f"{store.HELD}#{number}", "held", "needs-rh", gid, _held_question(number, issue),
                    f"{', '.join(issue['held'])}: {issue['title']}")
        if steps.get("triage") and not triaging and gid not in running:
            triaging = True  # one group at a time
            add(f"triage:{gid}", "triage", "ready", gid,
                f"Triage {gid}: {planner.numbers(steps['triage'], TEXT_NUMBERS)}. Start one triage session for it.",
                planner.numbers(steps["triage"], TEXT_NUMBERS))
    if not wins_placed:
        quick_wins()
    for gid in checks:
        if not any(f["group"] == gid for f in frozen):  # the group left the plan: the master still ends the check
            spec_check(gid, [])

    # Grills are proposed with the one that unfreezes the most ready issues first, then by group rank.
    # They keep the places grill rows hold in the queue; only their order among themselves changes.
    by_id = {g["id"]: g for g in plan["groups"]}

    def unfreezes(row):
        issues = set(by_id[row["group"]]["frozen_by"])
        return len({n for g in plan["groups"] if issues & set(g["frozen_by"]) for n in g["held_back"]})

    places = [i for i, r in enumerate(queue) if r["id"].startswith(GRILL) and r["id"] in briefs]
    proposed = sorted((queue[i] for i in places), key=lambda r: (-unfreezes(r), by_id[r["group"]]["rank"]))
    for place, grill in zip(places, proposed):
        queue[place] = grill
    return {"queue": own + queue, "go": go, "frozen": frozen}, briefs


def render(plan, rows, briefs, state_path, owed=()):
    """The lead list: commands owed to started sessions, what is the master's to start, what to ask RH and in which order."""
    def line(row):
        return f"  {row['id']}  {briefs.get(row['id']) or row.get('text') or ''}"[:planner.PRINT_WIDTH]

    mine = [r for r in rows["queue"] if r.get("state") == "ready"]
    asks = [r for r in rows["queue"] if r.get("state") == "needs-rh"]
    declined = [r for r in rows["queue"] if r.get("state") == "blocked"]
    lines = [f"LEAD  recorded in {state_path}"[:planner.PRINT_WIDTH]]
    if owed:  # a started session with no command has not begun its work: this comes before any new start
        lines.append(f"COMMAND NOT SENT  {len(owed)} (send each through peer-slash, confirm it ran, then "
                     "state.py running sent <session>)")
        lines += [f"  {s.get('id')}  {s.get('command')}"[:planner.PRINT_WIDTH] for s in owed]
    lines.append(f"START NOW  {len(mine)} (yours to take; a build only under the limits)")
    lines += [line(r) for r in mine]
    lines.append(f"ASK RH  {len(asks)}, one at a time, in this order (full question: {store.RUN}state.py show)")
    lines += [line(r) for r in asks[:PRINT_ASKS]]
    if len(asks) > PRINT_ASKS:
        lines.append(f"  +{len(asks) - PRINT_ASKS} more")
    grills = [r["id"].split(":", 1)[1] for r in asks if r["id"].startswith(GRILL)]
    opened = [f["group"] for f in rows["frozen"] if f["reason"].startswith(store.GRILL_OPEN)]
    if grills or opened:
        text = f"GRILLS  {len(grills)} to propose: " + ", ".join(grills)
        lines.append((text + ("; open: " + ", ".join(opened) if opened else ""))[:planner.PRINT_WIDTH])
    unchecked = sum(entry["reasons"] == ["no-verdict"] for entry in plan["held"])
    his = plan["counts"]["next_step"].get("show-rh", 0)
    lines.append(f"WAITING  {unchecked} wait for the overnight check (no Verdict); {his} are RH's own (ready-for-human); "
                 f"{len(declined)} set aside")
    return "\n".join(lines) + "\n"


def main(argv=None, gh=planner.real_gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="OWNER/NAME to read with gh")
    source.add_argument("--snapshot", type=Path, help="a file written by planner.py --save-snapshot")
    parser.add_argument("--areas", type=Path, required=True, help="the repo's area list (JSON)")
    parser.add_argument("--base", default="master", help="the branch merges land on (default: master)")
    parser.add_argument("--state", help="state file (default: as state.py)")
    parser.add_argument("--session", help="this session's id (default: as state.py)")
    args = parser.parse_args(argv)
    path = Path(args.state) if args.state else store.default_state_path()
    session = args.session or os.environ.get(store.SESSION_ENV)
    try:
        state = store.owned_state(path, session)
    except store.Refused as err:
        print(f"refused: {err}\nNothing was recorded. To read the plan without leading, run "
              f"{store.RUN}planner.py with the same --repo and --areas.", file=sys.stderr)
        return 2
    try:
        areas = planner.load_areas(args.areas)
        snapshot = planner.load_snapshot(args.repo, args.snapshot, gh)
    except planner.Unreadable as error:
        print(f"lead: {error}. Nothing was recorded.", file=sys.stderr)
        return 2
    area_paths = {a["slug"]: a.get("paths") or [] for a in areas["areas"]}
    plan = planner.build_plan(snapshot, areas)
    seen = {}

    def merged(commit):
        if commit not in seen:
            seen[commit] = merged_since(plan["repo"], commit, args.base, gh)
        return seen[commit]

    rows, briefs = plan_rows(plan, state, area_paths, merged)
    try:
        store.set_rows(path, session, rows)
    except store.Refused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    limits = "\n".join([f"LIMITS  before any start ({store.RUN}state.py room)", *(f"  {line.strip()}" for line in store.room(state)["lines"])])
    sys.stdout.write(planner.render(plan) + render(plan, rows, briefs, path, store.owed_commands(state)) + limits + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

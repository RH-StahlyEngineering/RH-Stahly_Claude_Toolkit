"""Turn a repo's open GitHub issues into a short plan the master session can read.

Usage: python -X utf8 -I planner.py --repo OWNER/NAME --areas AREAS.json [--save-snapshot FILE] [--json]
       python -X utf8 -I planner.py --snapshot FILE --areas AREAS.json [--json]

Read-only: the only GitHub call is one paged GraphQL query for open issues.
AREAS.json is the repo's area list: {"areas": [{"slug", "name", "description", "paths"}]}.
The plan holds groups (a spec with its tickets; other issues by area), frozen groups,
held issues with the reason, parked Release issues and each issue's next step.

The groups come ranked: RH's focus list, then groups with a rung 1 or 2 issue, groups that
unblock the most other work, started groups closest to finished, the rest by rung against size.
Quick wins (size S on rung 2 or 3) are a lane of single issues beside that order.

The focus list is one open pinned issue whose title starts with "Focus list". Each list line
of its body names one group, first three count: "- area:upload", "- upload", "- #1066".
"""
import argparse
import json
import re
import subprocess
import sys
import textwrap
from fractions import Fraction
from pathlib import Path

BODY_KEEP = 400  # chars of an issue body kept in a saved snapshot
DATA_BLOCK = re.compile(r"```issue-ledger\s*\n(.*?)\n```", re.S)
PARENT_IN_BODY = re.compile(r"(?i)\b(?:part of|parent)(?: spec)?:? #(\d+)")  # tickets not linked as sub-issues

# Pocock's triage states and the step each one calls for.
NEXT_STEP = {
    "needs-triage": "triage",
    "needs-info": "wait-reporter",
    "ready-for-agent": "build",
    "ready-for-human": "show-rh",
    "wontfix": "none",
}
STEP_ORDER = ["build", "grill", "wayfinder", "triage", "show-rh", "wait-reporter", "parked", "none"]
IGNORED_LABELS = {"ledger:state"}  # bot bookkeeping issues, not work
DONE_VERDICTS = {"done": "verdict-done", "fixed": "verdict-done", "partial": "verdict-partial"}
UNSORTED = "unsorted"
TOP_RUNGS = (1, 2)  # wrong data the customer can't see; can't get what they paid for
QUICK_WIN_RUNGS = (2, 3)
SIZE_POINTS = {"S": 1, "M": 2, "L": 4}  # an issue with no size counts as M
# The printed plan must fit one screen (about 40 lines); these caps keep it there.
PRINT_WIDTH = 110
PRINT_GROUPS = 12  # groups printed in full; the next PRINT_MORE_GROUPS are named only
PRINT_MORE_GROUPS = 18
PRINT_WINS = 5
PRINT_REASONS = 6
PRINT_NUMBERS = 12
FOCUS_TITLE = "focus list"  # start of the pinned issue's title
FOCUS_MAX = 3
# One group per list line: "- area:upload", "1. #1066 some note", "* upload". Other lines are RH's notes.
FOCUS_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+`?((?:spec:|area:)?#?[\w-]+)")

QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pinnedIssues(first: 3) { nodes { issue { number title body state } } }
    issues(first: 40, after: $cursor, states: OPEN, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body createdAt
        labels(first: 50) { nodes { name } }
        milestone { title }
        parent { number title state }
        subIssues(first: 100) { nodes { number state } }
        blockedBy(first: 50) { nodes { number state } }
        comments(last: 60) { nodes { author { login } body } }
      }
    }
  }
}
"""


def real_gh(args):
    """Run gh with these arguments and return its stdout."""
    done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"gh {args[0]} failed: {done.stderr.strip()}")
    return done.stdout


def _trim(node):
    """Keep what the planner reads: a short body and only the Issue Ledger comment."""
    node["body"] = (node.get("body") or "")[:BODY_KEEP]
    comments = (node.get("comments") or {}).get("nodes") or []
    node["comments"] = {"nodes": [c for c in comments if DATA_BLOCK.search(c.get("body") or "")][-1:]}
    return node


def fetch_snapshot(repo, gh=real_gh):
    """All open issues of the repo, as trimmed GraphQL nodes."""
    owner, name = repo.split("/", 1)
    issues, pinned, cursor = [], [], None
    while True:
        args = ["api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}", "-f", f"name={name}"]
        if cursor:
            args += ["-f", f"cursor={cursor}"]
        found = json.loads(gh(args))["data"]["repository"]
        page = found["issues"]
        issues += [_trim(n) for n in page["nodes"]]
        if cursor is None:  # the pinned issues come with every page; one copy is enough
            pinned = [n["issue"] for n in (found.get("pinnedIssues") or {}).get("nodes") or [] if n.get("issue")]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return {"repo": repo, "issues": issues, "pinned": sorted(pinned, key=lambda p: p["number"])}


def _focus_issue(snapshot):
    """RH's focus list: the open pinned issue whose title starts with 'Focus list'. None when there is none."""
    for pin in snapshot.get("pinned") or []:
        if pin.get("state", "OPEN") == "OPEN" and (pin.get("title") or "").lower().startswith(FOCUS_TITLE):
            return pin
    return None


def _focus(pin, groups, issues):
    """The groups the focus list names, in RH's order. Names past the third or matching no group are reported."""
    focus = {"issue": pin["number"] if pin else None, "groups": [], "unknown": [], "over": []}
    ids = {g["id"] for g in groups}
    for line in ((pin or {}).get("body") or "").splitlines():
        named = FOCUS_LINE.match(line)
        if not named:
            continue
        name = named.group(1)
        number = _number(name.removeprefix("spec:"))
        if number is not None:  # an issue number: its spec's group, else the first group that issue is in
            own = (issues.get(number) or {}).get("groups") or [None]
            group_id = f"spec:#{number}" if f"spec:#{number}" in ids else own[0]
        else:
            group_id = name if name in ids else f"area:{name}" if f"area:{name}" in ids else None
        if group_id is None:
            focus["unknown"].append(name)
        elif group_id not in focus["groups"] + focus["over"]:
            focus["groups" if len(focus["groups"]) < FOCUS_MAX else "over"].append(group_id)
    return focus


def _data_block(node):
    """The Issue Ledger data block of an issue, or {} when it has none."""
    for comment in reversed(node["comments"]["nodes"]):
        found = DATA_BLOCK.search(comment.get("body") or "")
        if found:
            try:
                data = json.loads(found.group(1))
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
    return {}


def _labelled(labels, prefix):
    """Values of the labels in one family, e.g. 'size:' -> ['S']."""
    return [name[len(prefix):] for name in labels if name.startswith(prefix)]


def _first(values):
    return values[0] if values else None


def _number(value):
    """An issue number or rung from a label or data block value ('#12', '3', 3), else None."""
    text = str(value).lstrip("#")
    return int(text) if text.isdigit() and not isinstance(value, bool) else None


def _next_step(labels, state, parked):
    """The one step this issue calls for. Pocock's state decides; a grill or a map comes first."""
    if state == "wontfix":
        return "none"
    if parked:
        return "parked"
    if _labelled(labels, "wayfinder:"):
        return "wayfinder"
    if "grill:needed" in labels:
        return "grill"
    return NEXT_STEP.get(state, "triage")


def _held(issue):
    """Why a ready issue must not be started as it stands. Empty when it may."""
    if issue["next_step"] != "build":
        return []
    reasons = []
    if "needs-human" in issue["labels"]:
        reasons.append("needs-human")
    if issue["verdict"] in DONE_VERDICTS:
        reasons.append(DONE_VERDICTS[issue["verdict"]])
    if issue["replaced_by"]:
        reasons.append(f"replaced-by #{issue['replaced_by']}")
    if not issue["verdict"]:
        reasons.append("no-verdict")
    return reasons


def _issue(node, area_slugs):
    """One open issue in the planner's own terms."""
    labels = sorted(l["name"] for l in node["labels"]["nodes"])
    data = _data_block(node)
    parent = node.get("parent")
    body_parent = PARENT_IN_BODY.search(node.get("body") or "")
    state = _first([s for s in NEXT_STEP if s in labels])
    milestone = (node.get("milestone") or {}).get("title") or ""
    parked = milestone.startswith("Release") and state is None
    claimed = _labelled(labels, "area:") + [a for a in data.get("areas") or [] if isinstance(a, str)]
    rung = _number(_first(_labelled(labels, "impact:")) or data.get("impact"))
    # A rung 4 issue the safety net keeps catching is raised by the Issue Ledger; it ranks where it was raised to.
    raised = _number(data.get("raisedImpact")) if rung == 4 else None
    raised = raised if raised and raised < rung else None
    issue = {
        "number": node["number"],
        "title": node["title"],
        "created_at": node.get("createdAt"),
        "labels": labels,
        "triage_state": state,
        "milestone": milestone if parked else None,
        "next_step": _next_step(labels, state, parked),
        "areas": sorted(set(claimed) & area_slugs),
        "size": _first(_labelled(labels, "size:")) or data.get("size"),
        "impact": raised or rung,
        "raised_from": rung if raised else None,
        "found_in_use": "found-in-use" in labels,
        "verdict": _first(_labelled(labels, "verdict:")) or data.get("verdict"),
        "checked_commit": data.get("checkedCommit"),
        "checked_at": data.get("checkedAt"),
        "replaced_by": _number(data.get("replacedBy", data.get("replaced_by"))),
        "blocked_by": sorted(b["number"] for b in node["blockedBy"]["nodes"] if b["state"] == "OPEN"),
        "parent": parent["number"] if parent else int(body_parent.group(1)) if body_parent else None,
        "parent_title": parent["title"] if parent else None,
        "has_tickets": any(s["state"] == "OPEN" for s in node["subIssues"]["nodes"]),
        "tickets_done": sum(s["state"] != "OPEN" for s in node["subIssues"]["nodes"]),
    }
    issue["held"] = _held(issue)
    return issue


def _spec(issue, issues):
    """The spec an issue belongs to: itself when it has tickets, else its parent. None for neither."""
    number = issue["number"]
    if issue["has_tickets"] or any(other["parent"] == number for other in issues.values()):
        return number
    return issue["parent"]


def _group(group_id, kind, title):
    return {"id": group_id, "kind": kind, "title": title, "issues": []}


def _finish(group, issues):
    """Fill in what a group's issues add up to."""
    members = [issues[n] for n in group["issues"]]
    steps = {}
    for member in members:
        steps.setdefault(member["next_step"], []).append(member["number"])
    group["next_steps"] = {step: steps[step] for step in STEP_ORDER if step in steps}
    # An unsorted issue has no known area, so a grill there says nothing about its neighbours.
    group["frozen_by"] = [] if group["kind"] == UNSORTED else steps.get("grill", [])
    group["held"] = [m["number"] for m in members if m["held"]]
    group["blocked"] = [m["number"] for m in members if m["next_step"] == "build" and m["blocked_by"]]
    group["ready"] = [m["number"] for m in members if m["next_step"] == "build" and not m["held"] and not m["blocked_by"]]
    return group


def _freeze(groups):
    """The freeze is per issue: an issue that sits in any frozen group is ready in none of its groups."""
    frozen = {n for group in groups if group["frozen_by"] for n in group["issues"]}
    for group in groups:
        group["held_back"] = [n for n in group["ready"] if n in frozen]  # startable once the grill is settled
        group["ready"] = [n for n in group["ready"] if n not in frozen]
        group["state"] = "frozen" if group["frozen_by"] else "ready" if group["ready"] else "idle"
    return groups


def _quick_wins(issues):
    """Single small issues a customer would feel: found in real use first, then the newest."""
    wins = [
        i for i in issues.values()
        if i["size"] == "S" and i["impact"] in QUICK_WIN_RUNGS and i["next_step"] not in ("none", "parked")
    ]
    wins.sort(key=lambda i: i["number"])
    wins.sort(key=lambda i: i["created_at"] or "", reverse=True)
    wins.sort(key=lambda i: not i["found_in_use"])
    return [
        {"number": i["number"], "title": i["title"], "rung": i["impact"], "found_in_use": i["found_in_use"],
         "next_step": i["next_step"], "held": i["held"], "groups": i["groups"]}
        for i in wins
    ]


def _rank(groups, issues, focus):
    """Put the groups in the order they should be worked and say which lane put each one there."""
    def key(indexed):
        index, group = indexed
        if group["id"] in focus:
            group["lane"] = "focus"
            return (0, focus.index(group["id"]))
        # Closest to finished: started groups before unstarted ones, then the fewest issues left.
        finished = (not group["done"], group["left"], -group["done"])
        if group["rung"] in TOP_RUNGS:
            group["lane"] = "rung"
            return (1, group["rung"], -len(group["unblocks"]), *finished, index)
        if group["unblocks"]:
            group["lane"] = "unblocks"
            return (2, -len(group["unblocks"]), *finished, index)
        if group["done"]:
            group["lane"] = "started"
            return (3, group["left"], -group["done"], index)
        group["lane"] = "rest"
        # Rung against size: what a customer gains per point of work.
        # No rung yet: groups with work ready to start, then the smallest group first.
        worth = Fraction(6 - group["rung"], max(group["cost"], 1)) if group["rung"] else 0
        return (4, group["rung"] is None, -worth, group["state"] != "ready", group["cost"], index)

    live = [i for i in issues.values() if i["next_step"] not in ("none", "parked")]
    for group in groups:
        members = set(group["issues"])
        head = issues.get(int(group["id"].split("#")[1])) if group["kind"] == "spec" else None
        group["done"] = head["tickets_done"] if head else 0  # closed tickets of the spec
        open_work = [issues[n] for n in members if issues[n]["next_step"] != "none"]
        group["left"] = len(open_work)
        group["cost"] = sum(SIZE_POINTS.get(i["size"], SIZE_POINTS["M"]) for i in open_work)
        rungs = [issues[n]["impact"] for n in members if issues[n]["impact"] and issues[n]["next_step"] != "none"]
        group["rung"] = min(rungs, default=None)
        # Work outside the group that waits on something inside it.
        group["unblocks"] = sorted(
            i["number"] for i in live if i["number"] not in members and members & set(i["blocked_by"])
        )
    ordered = [group for _, group in sorted(enumerate(groups), key=key)]
    for rank, group in enumerate(ordered, 1):
        group["rank"] = rank
    return ordered


def build_plan(snapshot, areas):
    """The plan for one snapshot and area list. The same input always gives the same plan."""
    area_names = {a["slug"]: a.get("name") or a["slug"] for a in areas["areas"]}
    pin = _focus_issue(snapshot)
    nodes = [
        n for n in snapshot["issues"]
        if not IGNORED_LABELS & {l["name"] for l in n["labels"]["nodes"]} and not (pin and n["number"] == pin["number"])
    ]
    issues = {n["number"]: _issue(n, set(area_names)) for n in nodes}
    specs, by_area, unsorted = {}, {}, _group(UNSORTED, UNSORTED, "No area from the list")
    for number in sorted(issues):
        issue = issues[number]
        issue["groups"] = []
        if issue["next_step"] == "parked":
            continue
        head = _spec(issue, issues)
        if head is not None:
            title = issues[head]["title"] if head in issues else issue["parent_title"] or f"#{head}"
            homes = [specs.setdefault(head, _group(f"spec:#{head}", "spec", title))]
        elif issue["areas"]:
            homes = [by_area.setdefault(a, _group(f"area:{a}", "area", area_names[a])) for a in issue["areas"]]
        else:
            homes = [unsorted]
        for home in homes:
            home["issues"].append(number)
            issue["groups"].append(home["id"])
    groups = [specs[k] for k in sorted(specs)] + [by_area[k] for k in sorted(by_area)]
    groups += [unsorted] if unsorted["issues"] else []
    focus = _focus(pin, groups, issues)
    groups = _rank(_freeze([_finish(g, issues) for g in groups]), issues, focus["groups"])

    parked = {}
    for number in sorted(issues):
        if issues[number]["next_step"] == "parked":
            parked.setdefault(issues[number]["milestone"], []).append(number)
    held = [
        {"number": n, "title": issues[n]["title"], "reasons": issues[n]["held"], "groups": issues[n]["groups"]}
        for n in sorted(issues) if issues[n]["held"]
    ]
    steps = [i["next_step"] for i in issues.values()]
    public = ("number", "title", "created_at", "triage_state", "next_step", "groups", "areas", "held", "blocked_by",
              "size", "impact", "raised_from", "found_in_use", "verdict", "checked_commit", "checked_at", "replaced_by")
    return {
        "repo": snapshot["repo"],
        "counts": {
            "open": len(issues),
            "ignored": len(snapshot["issues"]) - len(issues),
            "groups": len(groups),
            "frozen": sum(g["state"] == "frozen" for g in groups),
            "held": len(held),
            "parked": sum(len(v) for v in parked.values()),
            "next_step": {s: steps.count(s) for s in STEP_ORDER if s in steps},
        },
        "focus": focus,
        "groups": groups,
        "quick_wins": _quick_wins(issues),
        "held": held,
        "parked": [{"milestone": m, "issues": parked[m]} for m in sorted(parked)],
        "issues": {str(n): {k: issues[n][k] for k in public} for n in sorted(issues)},
    }


def numbers(issues, limit=None):
    """'#1 #2 #3', cut to the first `limit` with a count of the rest."""
    shown = issues[:limit] if limit else issues
    more = f" +{len(issues) - len(shown)} more" if len(issues) > len(shown) else ""
    return " ".join(f"#{n}" for n in shown) + more


def _why(group):
    """What put a group at its place in the order, in a few words."""
    if group["lane"] == "focus":
        return "focus"
    if group["lane"] == "unblocks":
        return f"unblocks {len(group['unblocks'])}"
    if group["lane"] == "started":
        return f"{group['done']} done, {group['left']} left"
    return f"rung {group['rung']}" if group["rung"] else "no rung"


def render(plan):
    """The plan as plain text for the master to read: one screen, the whole plan is in --json."""
    counts, focus = plan["counts"], plan["focus"]
    lines = [
        f"PLAN {plan['repo']}: {counts['open']} open, {counts['groups']} groups ({counts['frozen']} frozen), "
        f"{counts['held']} held, {counts['parked']} parked",
        "NEXT STEPS  " + ", ".join(f"{step} {n}" for step, n in counts["next_step"].items()),
    ]
    if focus["issue"] is None:
        lines.append("FOCUS  no focus list pinned")
    else:
        parts = [", ".join(focus["groups"]) or "names no group"]
        parts += ["not found: " + ", ".join(focus["unknown"])] if focus["unknown"] else []
        parts += [f"over the limit of {FOCUS_MAX}: " + ", ".join(focus["over"])] if focus["over"] else []
        lines.append(f"FOCUS  #{focus['issue']}: " + "; ".join(parts)[:PRINT_WIDTH - 20])

    wins = plan["quick_wins"]
    lines.append(f"QUICK WINS  {len(wins)} (size S on rung 2 or 3)" if wins else "QUICK WINS  none")
    for win in wins[:PRINT_WINS]:
        status = "held: " + ", ".join(win["held"]) if win["held"] else win["next_step"]
        found = "  found in use" if win["found_in_use"] else ""
        lines.append(f"  #{win['number']}  rung {win['rung']}{found}  {status}  {win['title']}"[:PRINT_WIDTH])
    if len(wins) > PRINT_WINS:
        lines.append("  +" + f"{len(wins) - PRINT_WINS} more: " + numbers([w["number"] for w in wins[PRINT_WINS:]], PRINT_NUMBERS))

    lines.append(f"GROUPS  {len(plan['groups'])}, ranked")
    for group in plan["groups"][:PRINT_GROUPS]:
        state = f"frozen by {numbers(group['frozen_by'], 3)}" if group["frozen_by"] else group["state"]
        lines.append((
            f"  {group['rank']:>2} {group['id']}  {_why(group)}  {state}  {len(group['issues'])} issues, "
            f"{len(group['ready'])} ready, {len(group['held'])} held  {group['title']}"
        )[:PRINT_WIDTH])
    rest = plan["groups"][PRINT_GROUPS:]
    if rest:
        names = " ".join(f"{g['id']}({g['state']})" for g in rest[:PRINT_MORE_GROUPS])
        names += f" +{len(rest) - PRINT_MORE_GROUPS} more" if len(rest) > PRINT_MORE_GROUPS else ""
        lines += textwrap.wrap(f"+{len(rest)} more: {names}", PRINT_WIDTH - 10, initial_indent="  ",
                               subsequent_indent="    ", break_on_hyphens=False)

    by_reason = {}
    for entry in plan["held"]:
        by_reason.setdefault(", ".join(entry["reasons"]), []).append(entry["number"])
    lines.append(f"HELD  {counts['held']}")
    reasons = sorted(by_reason)
    lines += [f"  {r} {len(by_reason[r])}: {numbers(by_reason[r], PRINT_NUMBERS)}" for r in reasons[:PRINT_REASONS]]
    if len(reasons) > PRINT_REASONS:
        lines.append(f"  +{len(reasons) - PRINT_REASONS} more reasons")
    lines.append(f"PARKED  {counts['parked']}")
    lines += [f"  {entry['milestone']}: {numbers(entry['issues'], PRINT_NUMBERS + 3)}" for entry in plan["parked"][:3]]
    return "\n".join(lines) + "\n"


class Unreadable(Exception):
    """An input the plan needs could not be read; the message is one line for the caller."""


def load_areas(path):
    """The repo's area list from its JSON file. Raises Unreadable."""
    try:
        areas = json.loads(Path(path).read_text(encoding="utf-8"))
        areas["areas"][0]["slug"]
    except (OSError, ValueError, LookupError, TypeError) as error:
        raise Unreadable(f"area list {path} is missing or unreadable ({error})") from None
    return areas


def load_snapshot(repo, snapshot_file, gh=real_gh):
    """The open issues: from a saved snapshot when one is given, else from GitHub. Raises Unreadable."""
    if snapshot_file:
        try:
            snapshot = json.loads(Path(snapshot_file).read_text(encoding="utf-8"))
            if not isinstance(snapshot["issues"], list) or not isinstance(snapshot["repo"], str):
                raise ValueError("no issue list in it")
        except (OSError, ValueError, LookupError, TypeError) as error:
            raise Unreadable(f"snapshot {snapshot_file} is missing or unreadable ({error})") from None
        return snapshot
    try:
        return fetch_snapshot(repo, gh)
    except (OSError, RuntimeError, ValueError, LookupError, TypeError) as error:
        reason = " ".join(str(error).split()) or type(error).__name__
        raise Unreadable(f"could not read the issues of {repo} with gh ({reason})") from None


def main(argv=None, gh=real_gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="OWNER/NAME to read with gh")
    source.add_argument("--snapshot", type=Path, help="a file written by --save-snapshot, read instead of gh")
    parser.add_argument("--areas", type=Path, required=True, help="the repo's area list (JSON)")
    parser.add_argument("--save-snapshot", type=Path, help="also write the trimmed issues here")
    parser.add_argument("--json", action="store_true", help="print the whole plan as JSON")
    args = parser.parse_args(argv)
    try:
        areas = load_areas(args.areas)
        snapshot = load_snapshot(args.repo, args.snapshot, gh)
    except Unreadable as error:
        print(f"planner: {error}", file=sys.stderr)
        return 2
    if args.save_snapshot:
        args.save_snapshot.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    plan = build_plan(snapshot, areas)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # titles carry dashes and quotes a Windows console can't encode
    sys.stdout.write(json.dumps(plan, indent=1, ensure_ascii=False) + "\n" if args.json else render(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())

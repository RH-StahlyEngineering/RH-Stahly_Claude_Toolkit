"""The master session's state file: its only writer, and the Stop decision read from it.

    python -X utf8 -I state.py [--state FILE] [--session ID] <command> ...

The owning master records what changed; the Stop hook (`stop`) and the panel only read.
`stop` takes the app's Stop message on stdin and prints one JSON line:
{"decision": "allow"} or {"decision": "refuse", "reason": ...}, plus "warning" when
the state file is damaged or unreadable. With no state file (no master has run `init`
on this PC) it allows and says nothing. It always exits 0 and never refuses on a failure.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

FLOOR_ENV = "WORKTREE_DISK_FLOOR_GB"  # the same floor RH's low-disk worktree hook reads
DEFAULT_FLOOR_GB = 5.0
STATE_ENV = "MASTER_SESSION_STATE"
SESSION_ENV = "CLAUDE_CODE_SESSION_ID"
RUN = "python -X utf8 -I scripts/"  # how the master runs a script of this skill, from the skill's folder
# On Windows a replace fails while a reader (the panel, the hook) has the file open: retry for about two seconds.
SAVE_TRIES = 40
SAVE_WAIT = 0.05

# Row ids and freeze reasons that lead.py writes and this store reads.
GO = "go:"                    # queue row: one go from RH for a group
BUILD = "build:"              # queue row: tickets under a spec, the master's to start
HELD = "held:"                # queue row: one held issue as one question
GRILL_OPEN = "grill open"     # frozen reason: "grill open: <session>"
GRILL_NEEDED = "grill needed"  # frozen reason: "grill needed: #n #m"
SPEC_CHECK = "spec check: "   # frozen reason while a published spec waits for its check
UNSORTED = "unsorted"         # the group of issues with no listed area: never frozen

# name -> (key field, other fields). Every row is a dict; `add` upserts by key.
COLLECTIONS = {
    "queue": ("id", ("text", "group", "kind", "state")),      # next items, ranked
    # running sessions; `command`: the one it is owed; `pr`: the PRs it opened (`merged` and `landed` follow them)
    "running": ("id", ("group", "kind", "deadline", "command", "pr")),
    "prs": ("number", ("line", "rung", "checks", "approved", "head")),  # PRs waiting on RH (merges.py)
    "go": ("group", ("line",)),                               # groups waiting for RH's go
    "frozen": ("group", ("reason",)),                         # frozen groups
    "waiting": ("id", ("line",)),                             # sessions waiting on RH
    "jobs": ("id", ("line",)),                                # job asks
}
QUEUE_STATES = ("ready", "needs-rh", "blocked")
# Options parsed under another name: `state` is the file option's, `command` the subcommand's.
FLAG_DESTS = {("queue", "state"): "item_state", ("running", "command"): "owed_command"}
KINDS_HELP = "build (adds a PR, counts against both limits), triage (counts against the session cap) or any other word"
CAPPED_KINDS = ("build", "triage")  # sessions that work unattended: each takes a place under the session cap
OWED_KINDS = ("build", "triage", "grill", "wayfinder")  # Pocock routes: the work arrives as a command, the second message
RETRO = "/mattpocock-skills:retro"  # owed to every landed build session, after its cleanup and before its archive
RETRO_KINDS = ("build",)
RETRO_ISSUE = "Retro candidates"    # the repo's pinned issue the master writes the candidates on
# What the master does with a landed session, in order. `retro` and `candidates` only for a build session.
LANDED_STEPS = ("cleanup", "retro", "candidates", "archive")
# Closeout's recorded steps, in order. Its first step, start nothing new, holds from `closeout start` on.
CLOSEOUT_STEPS = ("question", "fixes", "landed", "handoff", "said")
CLOSEOUT_LINE = "Closeout done. Compact me or start a new master."
HANDOFF_DIR = r".scratch\handoffs"  # in the ledger repo


class Refused(Exception):
    """A command the store will not run; the message is for the caller."""


def default_state_path():
    return Path(os.environ.get(STATE_ENV) or Path.home() / ".claude" / "master-session" / "state.json")


def new_state(owner=None):
    return {
        "version": 1,
        "owner": owner,
        "paused": False,
        "handover": None,            # {words, at, from}: RH's words that moved the role here (`take`)
        "question": None,            # {short, explain, explain_short, recommendation, asked_at}; before: `full`
        "displaced": [],             # questions a hard stop displaced, the last one comes back first
        "nothing_needed_said": None,  # the master's "Nothing needs you: ..." line, until the next change
        **{name: [] for name in COLLECTIONS},
        "digest": [],                # "since I asked" lines
        "limits": {"prs": 5, "sessions": 6, "lowered_sessions": None, "lowered_reason": None},
        "blocked_notified": False,
        "retro": {"issue": None, "count": 0},  # the Retro candidates issue and how many wait on it for RH
        "closeout": None,            # {words, started_at, asked, done: {step: note}} from `closeout start` to `closeout end`
        "handoff_note": None,        # {file, at}: the last handoff note a closeout wrote
    }


def _check(state):
    """Raise ValueError unless `state` has the shape this store writes."""
    if not isinstance(state, dict):
        raise ValueError("not a JSON object")
    for name in COLLECTIONS:
        rows = state[name]
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise ValueError(f"'{name}' is not a list of objects")
    if not isinstance(state["digest"], list):
        raise ValueError("'digest' is not a list")
    if state["question"] is not None and not isinstance(state["question"], dict):
        raise ValueError("'question' is not an object")
    if not isinstance(state["displaced"], list) or not all(isinstance(q, dict) for q in state["displaced"]):
        raise ValueError("'displaced' is not a list of objects")
    if not isinstance(state["paused"], bool):
        raise ValueError("'paused' is not true or false")
    limits = state["limits"]
    if not isinstance(limits, dict):
        raise ValueError("'limits' is not an object")
    for key in ("prs", "sessions"):
        if not isinstance(limits.get(key), int):
            raise ValueError(f"limit '{key}' is not a number")
    if limits.get("lowered_sessions") is not None and not isinstance(limits["lowered_sessions"], int):
        raise ValueError("limit 'lowered_sessions' is not a number")
    if not isinstance(state["retro"], dict) or not isinstance(state["retro"].get("count"), int):
        raise ValueError("'retro' is not an object with a count")
    closeout = state["closeout"]
    if closeout is not None and not (isinstance(closeout, dict) and isinstance(closeout.get("done"), dict)):
        raise ValueError("'closeout' is not an object with its done steps")


def load(path):
    """The state at `path` with defaults filled in. OSError or ValueError if unusable."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("not a JSON object")
    state = {**new_state(), **raw}
    if isinstance(raw.get("limits"), dict):
        state["limits"] = {**new_state()["limits"], **raw["limits"]}
    if isinstance(raw.get("retro"), dict):
        state["retro"] = {**new_state()["retro"], **raw["retro"]}
    _check(state)
    return state


def save(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")  # one per write
    try:
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for attempt in range(SAVE_TRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == SAVE_TRIES - 1:
                    raise
                time.sleep(SAVE_WAIT)
    finally:
        tmp.unlink(missing_ok=True)  # gone already when the replace landed


# --- the Stop decision -------------------------------------------------------

def session_cap(limits):
    lowered = limits.get("lowered_sessions")
    return limits["sessions"] if lowered is None else lowered


def room(state):
    """What may start now under the two limits, with the lines that say so."""
    limits = state["limits"]
    prs, pr_limit, cap = len(state["prs"]), limits["prs"], session_cap(limits)
    working = sum(1 for s in state["running"] if s.get("kind") in CAPPED_KINDS and not is_landed(s))
    closing = closeout_next(state) if state["closeout"] else None
    free = 0 if state["closeout"] else max(0, cap - working)
    pile_full = prs >= pr_limit
    lowered = limits.get("lowered_sessions") is not None
    lines = []
    if state["closeout"]:
        lines.append("Closeout is on: start nothing new. Running sessions keep running. The one new session is "
                     f"closeout's own, for the retro fixes. Next closeout step: {closing or 'none, all done'}.")
    lines.append(f"PRs waiting on RH: {prs} of {pr_limit}." + (" Start no new building." if pile_full else ""))
    if pile_full:
        lines.append("  Still yours: read-only checks, triage preparation, keeping waiting PRs current.")
    lines.append(f"Sessions working: {working} of {cap}"
                 + (f" (cap lowered from {limits['sessions']}: {limits.get('lowered_reason') or 'no reason given'})"
                    if lowered else "") + ".")
    if state["closeout"]:
        why = "no session (closeout)"
    elif pile_full:
        why = "no build session (PR pile full)"
    elif not free:
        why = "no session (cap reached)"
    else:
        why = _count(free, "session", "sessions")
    lines.append(f"May start now: {why}" + (f"; {_count(free, 'triage session', 'triage sessions')}"
                                            if pile_full and free else "") + ".")
    landed = [{"id": s.get("id"), "prs": s["pr"], "next": landed_next(s)} for s in landed_sessions(state)]
    lines += [landed_line(s) + "." for s in landed_sessions(state)]
    retro = state["retro"]
    if retro["count"]:
        lines.append(f"Retro candidates: {retro['count']} on issue #{retro['issue']}. RH sees them at closeout.")
    return {"prs": prs, "pr_limit": pr_limit, "sessions": working, "cap": cap,
            "lowered_reason": limits.get("lowered_reason") if lowered else None,
            "build_starts": 0 if pile_full else free, "other_starts": free, "lines": lines,
            "owed": [{"id": s.get("id"), "command": s.get("command")} for s in owed_commands(state)],
            "landed": landed, "closeout": closing, "closeout_on": bool(state["closeout"])}


def owed_commands(state):
    """Running sessions whose recorded command is not confirmed run: each is the master's step, never RH's.

    A row with no `command` (a mechanical session, or one written by a master on the older skill text) owes nothing.
    """
    return [s for s in state["running"] if s.get("command") and not s.get("command_sent")]


def owed_line(session):
    return f"Command not sent: {session.get('id')} is owed `{session.get('command')}`"


# --- landed sessions and closeout --------------------------------------------

def is_landed(session):
    """True once every PR the session recorded is merged. A row with no `pr` (a session with no PR, or one
    written by a master on the older skill text) never lands: archiving it stays a question to RH."""
    prs = session.get("pr")
    return bool(prs) and isinstance(prs, list) and set(prs) <= set(session.get("merged") or [])


def landed_sessions(state):
    return [s for s in state["running"] if is_landed(s)]


def landed_next(session):
    """The landed session's next step: the first of LANDED_STEPS not done."""
    done = session.get("landed") or []
    steps = LANDED_STEPS if session.get("kind") in RETRO_KINDS else ("cleanup", "archive")
    return next(step for step in steps if step not in done)


def _prs(numbers):
    return ("PR " if len(numbers) == 1 else "PRs ") + " ".join(f"#{n}" for n in numbers)


def landed_line(session):
    return f"Landed: {session.get('id')} ({_prs(session['pr'])} merged), next: {landed_next(session)}"


def mark_merged(state, number):
    """Record that PR `number` is merged on each running session that opened it. Returns one line per such
    session: that it has landed, or how many of its PRs are still open."""
    said = []
    for session in state["running"]:
        prs = session.get("pr")
        if not isinstance(prs, list) or number not in prs:
            continue
        was = is_landed(session)
        session["merged"] = sorted({*(session.get("merged") or []), number})
        if is_landed(session):
            said.append(f"session {session.get('id')} has landed, next: {landed_next(session)}"
                        + ("" if was else f" (its steps are yours, in order: {', '.join(LANDED_STEPS)})"))
        else:
            left = [n for n in prs if n not in session["merged"]]
            said.append(f"session {session.get('id')} has not landed yet: {_prs(left)} still open")
    return said


def landed_reason(state, session):
    """What the master does now for a landed session, and how it records it."""
    sid, step, run = session.get("id"), landed_next(session), f"{RUN}state.py"
    more = len(landed_sessions(state)) - 1
    head = (f"session {sid} has landed ({_prs(session['pr'])} merged) and its next step is yours, untouched"
            + (f" ({more} more landed after it)" if more > 0 else "") + ": ")
    if step == "cleanup":
        return head + (
            "confirm its cleanup: its worktree, its local branches and the merged remote branch are gone "
            f"(the after-merge rule). All gone: `{run} landed {sid} cleanup`. Something left: tell the session to "
            "clean it up and report, then end your turn; its turn-end note brings you back.")
    if step == "retro":
        return head + (
            f"send it `{RETRO}` through peer-slash as the whole message, confirm it ran "
            f"(references/pocock-flow.md, Sending), then `{run} running sent {sid}`. The session reports its "
            "candidates to you and implements nothing.")
    if step == "candidates":
        return head + (
            f"write the candidates its retro reported on the pinned \"{RETRO_ISSUE}\" issue (one line each with the "
            "session and the date; a repeat raises that line's count), then "
            f"`{run} landed {sid} candidates <how many> --issue <the issue's number>`. No report yet: end your turn; "
            "its turn-end note brings you back. None of this is a question to RH.")
    return head + (
        f"archive it without asking RH (`archive_session`), move its roster row to Archive, then "
        f"`{run} landed {sid} archived --title \"<its title>\"`: that adds the digest line.")


def closeout_next(state):
    """The first closeout step not recorded done, or None when all are (or closeout is off)."""
    if not state["closeout"]:
        return None
    return next((step for step in CLOSEOUT_STEPS if step not in state["closeout"]["done"]), None)


def closeout_verdict(state):
    """The Stop decision while closeout is on: its next step, ahead of the queue."""
    step, run, retro = closeout_next(state), f"{RUN}state.py", state["retro"]
    if step is None:
        return {"decision": "allow", "why": "closeout done"}
    head = f"Master session: Closeout is on and its next step is yours ({step}): "
    if step == "question":
        asked = [q for q in [state["question"], *state["displaced"]] if q and q.get("closeout")]
        if state["question"] and asked:
            return {"decision": "allow", "why": "closeout waits on RH's retro answer"}
        if state["closeout"].get("asked"):
            return {"decision": "refuse", "reason": head + (
                f"RH answered the retro question. Record his answer on the \"{RETRO_ISSUE}\" issue, "
                f"then `{run} closeout done question`.")}
        how = "ask --closeout --displace" if state["question"] else "ask --closeout"
        return {"decision": "refuse", "reason": head + (
            f"ask RH ONE question that lists the retro candidates on issue #{retro['issue']} "
            f"({retro['count']} recorded), each repeat as one line with its count, with your pick of the ones to fix. "
            f"Record it with `{run} {how} --short ... --explain ... --explain-short ... --pick ...`, then end your "
            f"turn. No candidates on the issue: `{run} closeout done question --skip \"no candidates\"`.")}
    if step == "fixes":
        return {"decision": "refuse", "reason": head + (
            "start ONE new sub-session for the retro fixes RH chose: pointer brief with the chosen list and the "
            f"\"{RETRO_ISSUE}\" issue, \"Received.\", then its route's command (references/pocock-flow.md). Build "
            f"nothing here or in a landed session. Then `{run} closeout done fixes --session <its id>`. "
            f"RH chose none: `{run} closeout done fixes --skip \"<why>\"`.")}
    if step == "landed":
        landed = landed_sessions(state)
        if landed:
            return {"decision": "refuse", "reason": "Master session: Closeout, finish every landed session: "
                    + landed_reason(state, landed[0])}
        return {"decision": "refuse", "reason": head + f"no landed session is left. Record it: `{run} closeout done landed`."}
    if step == "handoff":
        return {"decision": "refuse", "reason": head + (
            "bring the state file and the ledger up to date, then write the handoff note in the ledger repo at "
            f"`{HANDOFF_DIR}\\<date>-<time>.md`: paste what `{run} handoff` prints and fill in each TO ADD line. "
            f"Then `{run} closeout done handoff --file <the note's path>`.")}
    return {"decision": "refuse", "reason": head + (
        f"end with the one line `{CLOSEOUT_LINE}` and record it with `{run} closeout done said`.")}


def handoff_text(state, now=None):
    """The state-derived part of the handoff note, as Markdown. TO ADD lines are the master's to fill in."""
    now = now or datetime.now().isoformat(timespec="minutes")

    def part(title, lines, to_add=None):
        return [f"## {title}", "", *(lines or ["None."]), *([f"TO ADD: {to_add}"] if to_add else []), ""]

    running = []
    for s in state["running"]:
        bits = [str(s.get("group") or "no group"), str(s.get("kind") or "no kind")]
        if isinstance(s.get("pr"), list) and s["pr"]:
            bits.append(_prs(s["pr"]))
        if is_landed(s):
            bits.append(f"landed, next: {landed_next(s)}")
        if s.get("command") and not s.get("command_sent"):
            bits.append(f"command not sent: {s['command']}")
        if s.get("deadline"):
            bits.append(f"time box until {s['deadline']}")
        running.append(f"- {s.get('id')}: {', '.join(bits)}. TO ADD: last verified state, with the time")
    question = []
    if state["question"]:
        q = state["question"]
        question = [f"- {q.get('short')} (asked {q.get('asked_at')}; pick: {q.get('recommendation') or 'none given'})"]
        question += [f"- comes back after it: {old.get('short')}" for old in reversed(state["displaced"])]
    out = [f"# Master session handoff, {now}", "",
           f"Owner: {state['owner']}. Paused: {'yes' if state['paused'] else 'no'}. "
           "Printed from the state file; the TO ADD lines are filled in by the master that wrote this note.", ""]
    out += part("Running", running)
    out += part("Waiting on RH", [f"- {line}" for line in waiting_on_rh(state)])
    out += part("Open question", question)
    out += part("Monitors and timers to re-arm",
                [f"- time box of {s.get('id')} until {s['deadline']}" for s in state["running"] if s.get("deadline")],
                "every other timer, monitor or scheduled task you set, with what it watches; or \"none\"")
    hand = state.get("handover")
    out += part("RH's hand-over words",
                [f"- \"{hand.get('words')}\" ({hand.get('at')}), role taken from {hand.get('from') or 'no one'}"]
                if hand else [],
                "his words naming the next master, word for word with the time; or \"none\"")
    retro = state["retro"]
    out += part("Retro candidates", [f"- {retro['count']} waiting on issue #{retro['issue']}"] if retro["issue"] else [])
    out += part("Since I asked (digest not yet delivered)", [f"- {line}" for line in state["digest"]])
    out += part("Frozen groups", [f"- {f.get('group')}: {f.get('reason')}" for f in state["frozen"]])
    out += part("Job asks", [f"- {j.get('line') or j.get('id')}" for j in state["jobs"]])
    limits = state["limits"]
    lowered = (f"; session cap lowered to {limits['lowered_sessions']}: {limits.get('lowered_reason')}"
               if limits.get("lowered_sessions") is not None else "")
    out += part("Limits", [f"- PRs {limits['prs']}, sessions {limits['sessions']}{lowered}"])
    closeout = state["closeout"]
    if closeout:
        done = ", ".join(f"{step} ({note})" for step, note in closeout["done"].items()) or "none"
        out += part("Closeout", [f"- started {closeout.get('started_at')} on RH's words \"{closeout.get('words')}\"; "
                                 f"done: {done}; next: {closeout_next(state) or 'none'}"])
    return "\n".join(out)


def disk_report(path, lowered):
    """Free disk at `path` against the worktree floor, and the limit command it calls for."""
    try:
        floor = float(os.environ.get(FLOOR_ENV, DEFAULT_FLOOR_GB))
    except ValueError:
        floor = DEFAULT_FLOOR_GB
    free = shutil.disk_usage(path).free / 1024**3
    low = free < floor
    shown = int(floor) if floor == int(floor) else floor
    line = f"Disk: {free:.1f} GB free at {path}, {'under' if low else 'above'} the {shown} GB worktree floor."
    if low and not lowered:
        line += f' Run: limit lower --reason "disk {free:.1f} GB free", and tell RH the line it prints.'
    elif lowered and not low:
        line += " If the cap was lowered for disk, run: limit restore."
    return {"free_gb": round(free, 1), "floor_gb": floor, "low": low, "line": line}


def untouched_steps(state):
    """Ready queue items the master may take now, within the two limits."""
    now = room(state)
    frozen = {f.get("group") for f in state["frozen"]}
    steps = []
    for item in state["queue"]:
        if item.get("state") != "ready":
            continue
        if item.get("kind") == "build" and (not now["build_starts"] or item.get("group") in frozen):
            continue
        if item.get("kind") in CAPPED_KINDS and not now["other_starts"]:
            continue
        steps.append(item)
    return steps


def waiting_on_rh(state):
    """One line per item that waits on RH, in the order to ask them.

    Sessions waiting on him first (a hard stop needs his yes); then, when the PR pile is full, a merge;
    then the plan's `needs-rh` rows, top row first. SKILL.md gives the same order (Ending a turn).
    """
    lines = [f"session {s.get('id')}: {s.get('line') or 'waiting on him'}" for s in state["waiting"]]
    prs = [f"PR {p.get('number')}: {p.get('line') or 'waiting on his decision'}" for p in state["prs"]]
    if prs and len(prs) >= state["limits"]["prs"]:
        prs[0] = f"merge, the PR pile is full ({RUN}merges.py list shows it): {prs[0]}"
        lines, prs = lines + prs, []
    lines += [f"{i.get('text') or i.get('id')}" for i in state["queue"] if i.get("state") == "needs-rh"]
    asked = {i.get("id") for i in state["queue"]}  # a go the plan put in the queue is one item, not two
    lines += [f"go for group {g.get('group')}" for g in state["go"] if f"{GO}{g.get('group')}" not in asked]
    return lines + prs


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def blocked_report(state):
    """Whether every remaining step waits on RH, the line that tells him what waits, and whether to send it.

    Blocked: something waits on RH, no step is the master's to take, no session is still
    running and RH has not paused. `send` is true once per block: `notified` records it
    and only `answered` clears it.
    """
    offers = {f"{GO}{g.get('group')}" for g in state["go"]}  # a go the plan put in the queue counts as a group
    questions = sum(1 for i in state["queue"] if i.get("state") == "needs-rh" and i.get("id") not in offers)
    questions += len(state["waiting"])
    parts = []
    if state["prs"]:
        parts.append(_count(len(state["prs"]), "PR to approve", "PRs to approve"))
    if state["go"]:
        parts.append(_count(len(state["go"]), "group waiting for your go", "groups waiting for your go"))
    if questions or (state["question"] and not parts):
        parts.append(_count(questions or 1, "question", "questions"))
    blocked = (bool(parts) and not state["paused"] and not state["running"] and not owed_commands(state)
               and not untouched_steps(state))
    notified = bool(state.get("blocked_notified"))
    line = None
    if blocked:
        line = "Waiting on you: " + (parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}") + "."
    return {"blocked": blocked, "line": line, "notified": notified, "send": blocked and not notified}


def decide(state, message):
    """Allow or refuse a stop: the turn-end rule over one state and one Stop message."""
    if message.get("session_id") != state["owner"] or not state["owner"]:
        return {"decision": "allow", "why": "not the owner"}
    if state["paused"]:
        return {"decision": "allow", "why": "paused"}
    if message.get("stop_hook_active"):
        return {"decision": "allow", "why": "already sent back this turn"}
    owed = [s for s in owed_commands(state) if not is_landed(s)]  # a landed session's retro is its own step, below
    if owed:
        first = owed[0]
        more = f" ({len(owed) - 1} more after it)" if len(owed) > 1 else ""
        return {"decision": "refuse", "reason": (
            f"Master session: session {first.get('id')} is owed its command and it is not confirmed run{more}: "
            f"`{first.get('command')}`. When its start turn has ended, send that line through peer-slash as the "
            "whole message, confirm it ran (references/pocock-flow.md, Sending), then record it: "
            f"`{RUN}state.py running sent {first.get('id')}`. Its start turn still runs: end your turn; "
            "its turn-end note brings you back."
        )}
    if state["closeout"]:
        return closeout_verdict(state)
    landed = landed_sessions(state)
    if landed:
        return {"decision": "refuse", "reason": "Master session: " + landed_reason(state, landed[0])}
    steps = untouched_steps(state)
    if steps:
        step = steps[0]
        more = f" ({len(steps) - 1} more after it)" if len(steps) > 1 else ""
        return {"decision": "refuse", "reason": (
            f"Master session: a ready step is untouched: {step.get('text') or step.get('id')}{more}. "
            f"Take it now (Ending a turn), then record it: `{RUN}state.py queue drop "
            f"{step.get('id')}` once started or done, or `{RUN}state.py queue add {step.get('id')} --state needs-rh` "
            "(or blocked) if it turns out not to be yours to take."
        )}
    report = blocked_report(state)
    tell = (f"the first line of your closing message must be `{report['line']}` (the app's turn-end notification "
            f"carries it to RH's phone); record it with `{RUN}state.py notified`") if report["send"] else ""
    if state["question"]:
        if tell:
            return {"decision": "refuse", "reason": (
                f"Master session: every remaining step waits on RH and he has not been told. End this turn once more: "
                f"{tell}, then the open question as before. Start no timer."
            )}
        return {"decision": "allow", "why": "one question open, nothing untouched"}
    waiting = waiting_on_rh(state)
    if waiting:
        return {"decision": "refuse", "reason": (
            f"Master session: RH has no open question and {len(waiting)} item(s) wait on him; the first: "
            f"{waiting[0]}. Ask him that one question with your pick, in the next-step box, and record it with "
            f"`{RUN}state.py ask --short ... --explain ... --explain-short ... --pick ...`."
            + (f" Every remaining step waits on him: {tell}." if tell else "")
        )}
    if not state["nothing_needed_said"]:
        return {"decision": "refuse", "reason": (
            "Master session: no question is open and nothing waits on RH. End with the one line "
            f"`Nothing needs you: <what is running>.` and record it with `{RUN}state.py idle \"<what is running>\"`."
        )}
    return {"decision": "allow", "why": "nothing needs RH, and the master said so"}


def stop_verdict(path, stdin_text):
    """`decide` with every failure turned into allow-with-a-warning: never trap the session.

    No state file is not a failure: no master has run `init` here, so the stop is allowed in silence.
    """
    try:
        state = load(path)
    except FileNotFoundError:
        return {"decision": "allow", "why": "no state file"}
    except (OSError, ValueError, KeyError, TypeError) as err:
        return {"decision": "allow",
                "warning": f"master-session Stop hook: state file {path} is damaged or unreadable ({err}); stop allowed."}
    try:
        message = json.loads(stdin_text)
        if not isinstance(message, dict):
            raise ValueError("not a JSON object")
        return decide(state, message)
    except Exception as err:  # noqa: BLE001 - any failure allows the stop
        return {"decision": "allow",
                "warning": f"master-session Stop hook: could not decide ({type(err).__name__}: {err}); stop allowed."}


# --- writing -----------------------------------------------------------------

def _upsert(rows, key, value, fields):
    for row in rows:
        if str(row.get(key)) == str(value):
            row.update(fields)
            return
    rows.append({key: value, **fields})


def _one_grill_per_group(running, session, fields):
    """Refuse a second grill in a group with one open. `unsorted` issues share no area, so it is exempt."""
    row = {**next((r for r in running if str(r.get("id")) == session), {}), **fields}
    if row.get("kind") != "grill" or row.get("group") in (None, UNSORTED):
        return
    for other in running:
        if str(other.get("id")) != session and other.get("kind") == "grill" and other.get("group") == row["group"]:
            raise Refused(
                f"a grill is already open in {row['group']} (session {other.get('id')}): two grills never run in "
                "one group at once. Tell RH; start this one after that grill's spec is checked.")


def _pr_number(key):
    """A PR's number from `12` or `#12`. Raises Refused for anything else."""
    text = str(key).lstrip("#")
    if not text.isdigit():
        raise Refused(f"a PR is named by its number (`prs add 12`), not '{key}'")
    return int(text)


def _spec_check_groups(rows, group):
    """The frozen groups the same grill froze as `group`: its spec is checked against each of them."""
    reason = next((str(r.get("reason") or "") for r in rows if r.get("group") == group), "")
    if reason.startswith(GRILL_OPEN):  # "grill open: <session>": the same session's grill
        return [r["group"] for r in rows if r.get("reason") == reason and r.get("group") != group]
    if reason.startswith(GRILL_NEEDED):  # "grill needed: #n #m": a grilled issue in common
        issues = set(re.findall(r"#\d+", reason))
        return [r["group"] for r in rows if r.get("group") != group
                and str(r.get("reason") or "").startswith(GRILL_NEEDED)
                and issues & set(re.findall(r"#\d+", r["reason"]))]
    return []


def apply(state, args):
    """Change `state` as one writing command asks. Raises Refused."""
    cmd = args.command
    if cmd == "pause":
        state["paused"] = True
    elif cmd == "resume":
        state["paused"] = False
    elif cmd == "retro":
        if args.issue is not None:
            state["retro"]["issue"] = _pr_number(args.issue)
        if args.count is not None:
            state["retro"]["count"] = args.count
    elif cmd == "landed":
        _landed_step(state, args)
    elif cmd == "closeout":
        _closeout(state, args)
    elif cmd == "ask":
        if state["question"] and not (args.displace or args.replace):
            raise Refused(
                f"a question is open ({state['question'].get('short')}). RH answered it: `answered` first. "
                "A hard stop that goes ahead of it: `ask --displace` (the open one is kept and comes back). "
                "The same question reworded: `ask --replace`.")
        if state["question"] and args.displace:
            state["displaced"].append(state["question"])
        explain, explain_short = (text if text and text.strip() else None
                                  for text in (args.explain, args.explain_short))
        state["question"] = {"short": args.short, "explain": explain or args.short, "explain_short": explain_short,
                             "recommendation": args.pick,
                             "asked_at": args.at or datetime.now().isoformat(timespec="seconds")}
        if args.closeout:
            if not state["closeout"]:
                raise Refused("closeout is not on: it starts only on RH's word, with `closeout start --words ...`")
            state["question"]["closeout"] = True
            state["closeout"]["asked"] = True
        missing = [flag for flag, text in (("--explain", explain), ("--explain-short", explain_short)) if not text]
        if missing:  # recorded all the same: a master on the older wording must not be stopped
            args.said = (f"Recorded, but missing: {' and '.join(missing)}. The panel shows RH both explanations, in "
                         "wait-what style: --explain is the full one (a little context, the decision, the options and "
                         "what each causes, the pick and why), --explain-short the same in three to five sentences. "
                         "Give both: `ask --replace --short ... --explain ... --explain-short ... --pick ...`.")
    elif cmd == "answered":
        state["question"] = state["displaced"].pop() if state["displaced"] else None
        if state["question"]:
            args.said = f"Open again, the question this one displaced: {state['question'].get('short')}"
        state["blocked_notified"] = False
    elif cmd == "idle":
        state["nothing_needed_said"] = args.text
    elif cmd == "notified":
        state["blocked_notified"] = True
    elif cmd == "digest":
        if args.action == "add":
            state["digest"].append(args.line)
        else:
            state["digest"] = []
    elif cmd == "limit":
        limits = state["limits"]
        if args.action in ("prs", "sessions"):
            name = "PR limit" if args.action == "prs" else "Session cap"
            args.said = f"{name} is now {args.n} (was {limits[args.action]})"
            limits[args.action] = args.n
            if args.action == "sessions" and limits.get("lowered_sessions") is not None:
                args.said += f"; still lowered to {limits['lowered_sessions']}: {limits.get('lowered_reason')}"
            args.said += "."
        elif args.action == "lower":
            # With no number: hold what runs, start nothing new.
            n = room(state)["sessions"] if args.n is None else args.n
            limits["lowered_sessions"], limits["lowered_reason"] = n, args.reason
            args.said = (f"Session cap lowered from {limits['sessions']} to {n}: {args.reason}. "
                         "Nothing new starts until it clears.")
        else:
            limits["lowered_sessions"], limits["lowered_reason"] = None, None
            args.said = f"Session cap back to {limits['sessions']}."
    elif cmd in COLLECTIONS:
        key, fields = COLLECTIONS[cmd]
        rows = state[cmd]
        if cmd == "prs" and args.action in ("add", "drop"):
            args.key = str(_pr_number(args.key))
        if cmd == "prs" and args.action == "drop" and not args.closed:
            landed = mark_merged(state, int(args.key))  # dropped after its merge: the session that built it lands
            if landed:
                args.said = f"PR #{args.key} merged: " + "; ".join(landed) + "."
        if cmd == "running" and args.action == "drop":
            gone = next((r for r in rows if str(r.get(key)) == args.key), None)
            if gone and is_landed(gone):
                raise Refused(
                    f"session {args.key} has landed and its steps are not done (next: {landed_next(gone)}). It leaves "
                    f"the list with `landed {args.key} archived --title \"<its title>\"`, after its steps; a session "
                    "that is gone: add `--skip \"<why>\"`.")
        if args.action == "add":
            value = int(args.key) if cmd == "prs" else args.key
            # `--state` on `queue add` is parsed as item_state: the file option owns `state`.
            flags = {f: getattr(args, FLAG_DESTS.get((cmd, f), f)) for f in fields}
            given = {f: v for f, v in flags.items() if v is not None}
            if cmd == "running" and "pr" in given:  # the PRs it opened: each `--pr` adds one
                had = next((r.get("pr") for r in rows if str(r.get(key)) == args.key), None)
                given["pr"] = sorted({*(had if isinstance(had, list) else []), *(_pr_number(n) for n in given["pr"])})
            if cmd == "queue" and not any(str(r.get(key)) == args.key for r in rows):
                if "kind" not in given:
                    raise Refused(f"a new queue item needs --kind: {KINDS_HELP}")
                given = {"text": args.key, "group": None, "state": "ready", **given}
            if cmd == "running":
                _one_grill_per_group(rows, args.key, given)
                if "command" in given:
                    given["command_sent"] = False
            also = []
            if cmd == "frozen" and str(given.get("reason") or "").startswith(SPEC_CHECK):
                also = _spec_check_groups(rows, args.key)
            for group in [value, *also]:
                _upsert(rows, key, group, given)
            if also:
                args.said = (f"Spec check recorded for {args.key} and for {', '.join(also)}: the same grill froze "
                             "them. Each gets its own spec-check row; drop each freeze when its check is settled.")
            if cmd == "running":
                row = next(r for r in rows if str(r.get(key)) == args.key)
                if row.get("kind") in OWED_KINDS and not row.get("command"):
                    # recorded all the same: a master on the older wording must not be stopped
                    args.said = (f"Recorded, but with no owed command: a {row['kind']} session gets its route's "
                                 f"command as its second message. Add it: `running add {args.key} --command "
                                 '"/mattpocock-skills:<skill> <args>"`, then `running sent` once it ran.')
        elif args.action == "sent":
            row = next((r for r in rows if str(r.get(key)) == args.key), None)
            if row is None:
                raise Refused(f"no running session '{args.key}' is recorded: `running add {args.key} ...` first")
            if row.get("command"):
                row["command_sent"] = True
                if is_landed(row) and row["command"] == RETRO and "cleanup" in (row.get("landed") or []):
                    row["landed"] = [*row["landed"], "retro"] if "retro" not in row["landed"] else row["landed"]
            else:
                args.said = f"Session {args.key} has no owed command recorded: nothing to confirm."
        elif args.action == "drop":
            state[cmd] = [r for r in rows if str(r.get(key)) != args.key]
        elif args.action == "clear":
            state[cmd] = []
        else:  # set
            try:
                new_rows = json.loads(args.stdin_text)
            except ValueError as err:
                raise Refused(f"`{cmd} set` needs a JSON list on stdin ({err})") from None
            if not isinstance(new_rows, list) or not all(isinstance(r, dict) and key in r for r in new_rows):
                raise Refused(f"`{cmd} set` needs a JSON list of objects, each with '{key}'")
            state[cmd] = new_rows
    if cmd != "idle":
        state["nothing_needed_said"] = None


def _landed_step(state, args):
    """Record one step of a landed session, in order. Raises Refused."""
    sid = args.key
    row = next((r for r in state["running"] if str(r.get("id")) == sid), None)
    if row is None:
        raise Refused(f"no running session '{sid}' is recorded")
    if not is_landed(row):
        raise Refused(
            f"session {sid} has not landed: its PR is not merged, or it recorded none (`running add {sid} --pr <n>`). "
            "Archiving a session whose PR is not merged, or that still has work, is a question to RH (Archive offer).")
    step = "archive" if args.step == "archived" else args.step
    done, due = row.setdefault("landed", []), landed_next(row)
    if step == "archive" and args.skip:  # the session is gone: its remaining steps cannot run
        state["running"] = [r for r in state["running"] if r is not row]
        state["digest"].append(f"archived: {args.title} (steps skipped: {args.skip})")
        return
    if step in done:
        raise Refused(f"session {sid}: {step} is already recorded; its next step is {due}")
    if step == "candidates" and row.get("kind") not in RETRO_KINDS:
        raise Refused(f"session {sid} owes no retro: only a build session gets one. Its next step is {due}.")
    if step != due:
        how = (f"send it `{RETRO}` and confirm it ran: `running sent {sid}`" if due == "retro"
               else f"`landed {sid} {due}" + (" <how many>`" if due == "candidates" else "`"))
        raise Refused(f"session {sid}: {due} comes first ({how}). The steps go in order: {', '.join(LANDED_STEPS)}.")
    if step == "cleanup":
        done.append("cleanup")
        if row.get("kind") in RETRO_KINDS:  # owed like a route command: named until `running sent`
            row["command"], row["command_sent"] = RETRO, False
            args.said = (f"Cleanup recorded. Session {sid} is owed `{RETRO}`: send it through peer-slash as the "
                         f"whole message, confirm it ran, then `running sent {sid}`.")
    elif step == "candidates":
        if args.n is None or args.n < 0:
            raise Refused(f"say how many candidates its retro reported: `landed {sid} candidates <n>` (0 for none)")
        if args.issue is not None:
            state["retro"]["issue"] = _pr_number(args.issue)
        if args.n and state["retro"]["issue"] is None:
            raise Refused(
                f"the candidates go on the repo's pinned \"{RETRO_ISSUE}\" issue first (none yet: create it with that "
                f"title and pin it), then name it once: `landed {sid} candidates {args.n} --issue <its number>`")
        state["retro"]["count"] += args.n
        done.append("candidates")
    else:
        if not args.title:
            raise Refused(f"give the session's title for the digest line: `landed {sid} archived --title \"<title>\"`")
        state["running"] = [r for r in state["running"] if r is not row]
        state["digest"].append(f"archived: {args.title}")


def _closeout(state, args):
    """Start closeout, record one of its steps in order, or end it. Raises Refused."""
    if args.action == "start":
        if state["closeout"]:
            args.said = f"Closeout is already on. Next step: {closeout_next(state) or 'none, all done'}."
            return
        state["closeout"] = {"words": args.words, "started_at": args.at or datetime.now().isoformat(timespec="seconds"),
                             "asked": False, "done": {}}
        args.said = ("Closeout is on: start nothing new; running sessions keep running. Steps, in order, each "
                     "recorded with `closeout done <step>`: question (one retro question to RH, with your pick), "
                     "fixes (one new sub-session for what he chose), landed (every landed session finished), "
                     "handoff (state and ledger current, the handoff note written), said (the one closing line).")
        return
    if args.action == "end":
        state["closeout"] = None
        return
    if not state["closeout"]:
        raise Refused("closeout is not on: it starts only on RH's word, with `closeout start --words ...`")
    step, due = args.step, closeout_next(state)
    if step != due:
        raise Refused(f"closeout step {step} is " + ("already recorded" if step in state["closeout"]["done"]
                      else "not next") + f"; the next step is {due or 'none: all are done'}.")
    note = "done"
    if step == "question":
        if any(q.get("closeout") for q in [state["question"], *state["displaced"]] if q):
            raise Refused("the retro question is still open: RH has not answered it. After his answer: `answered`, "
                          f"his answer recorded on the \"{RETRO_ISSUE}\" issue, then this.")
        if args.skip:
            note = f"skipped: {args.skip}"
        elif not state["closeout"].get("asked"):
            raise Refused("the retro question was not asked (`ask --closeout ...`). No candidates to ask about: "
                          "`closeout done question --skip \"no candidates\"`.")
        else:
            state["retro"]["count"] = 0  # RH has seen them; his answer is on the issue
    elif step == "fixes":
        if bool(args.session_id) == bool(args.skip):
            raise Refused("name the one sub-session started for the fixes (`closeout done fixes --session <id>`), "
                          "or why none was (`--skip \"<why>\"`)")
        note = f"session {args.session_id}" if args.session_id else f"skipped: {args.skip}"
    elif step == "landed":
        left = landed_sessions(state)
        if left:
            raise Refused("landed sessions are not finished: " + "; ".join(landed_line(s) for s in left)
                          + ". Finish each (cleanup, retro, candidates, archive), then this.")
    elif step == "handoff":
        if not args.file or not Path(args.file).is_file():
            raise Refused(f"the handoff note is not there: {args.file or 'no --file given'}. Write it in the ledger "
                          f"repo under {HANDOFF_DIR} from `handoff`'s output, then `closeout done handoff --file <path>`.")
        note = str(args.file)
        state["handoff_note"] = {"file": str(args.file), "at": datetime.now().isoformat(timespec="seconds")}
    state["closeout"]["done"][step] = note
    if step == "said":
        args.said = "Closeout recorded done. After the compact, or as the new master: read the state file and the handoff note, then `closeout end`."


def write_command(path, session, args):
    if not session:
        raise Refused(f"no session id: pass --session or set {SESSION_ENV}")
    cmd = args.command
    try:
        state = load(path)
    except (OSError, ValueError, KeyError, TypeError) as err:
        if cmd != "init":
            raise Refused(f"state file {path} is missing or damaged ({err}); run `init` as the master") from None
        state = None
    if cmd in ("init", "take"):
        owner = state["owner"] if state else None
        if cmd == "init" and owner and owner != session:
            raise Refused(
                f"session {owner} already leads as master. Ask RH which of the two he wants (One master); "
                "after his hand-over run `take --words \"<his words>\"`.")
        if state is None or args.fresh:
            state = new_state()
        if owner != session:
            state["closeout"] = None  # a new owner starts past the old master's closeout; its handoff note stays
        if cmd == "take":
            state["handover"] = {"words": args.words, "at": args.at or datetime.now().isoformat(timespec="seconds"),
                                 "from": owner}
            args.said = f'Role taken from {owner or "no one"} on RH\'s words: "{args.words}" ({state["handover"]["at"]}).'
        state["owner"] = session
        state["nothing_needed_said"] = None
    else:
        if state["owner"] != session:
            raise Refused(
                f"only the master writes the state: session {session} is not the owner ({state['owner']}). "
                "A side conversation reads (`show`) and writes nothing.")
        apply(state, args)
    save(path, state)


def set_rows(path, session, collections):
    """Replace whole collections ({name: rows}) in one write, as the owner. Raises Refused."""
    state = owned_state(path, session)
    for name, rows in collections.items():
        state[name] = rows
    state["nothing_needed_said"] = None
    save(path, state)


def owned_state(path, session):
    """The state at `path` when `session` is its owner. Raises Refused otherwise."""
    if not session:
        raise Refused(f"no session id: pass --session or set {SESSION_ENV}")
    try:
        state = load(path)
    except (OSError, ValueError, KeyError, TypeError) as err:
        raise Refused(f"state file {path} is missing or damaged ({err}); run `init` as the master") from None
    if state["owner"] != session:
        raise Refused(
            f"only the master writes the state: session {session} is not the owner ({state['owner']}). "
            "A side conversation reads (`show`) and writes nothing.")
    return state


# --- command line ------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state", help=f"state file (default: ${STATE_ENV} or ~/.claude/master-session/state.json)")
    parser.add_argument("--session", help=f"this session's id (default: ${SESSION_ENV})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stop", help="decide a stop: the app's Stop message on stdin, a JSON verdict out")
    sub.add_parser("show", help="print the state (anyone may read)")
    sub.add_parser("handoff", help="print the state-derived part of the handoff note, as Markdown (anyone may read)")
    p = sub.add_parser("retro", help="the Retro candidates issue and how many candidates wait on it")
    p.add_argument("--issue", help="the pinned issue's number")
    p.add_argument("--count", type=int, help="set the count to match the issue")
    p = sub.add_parser("landed", help="record one step of a landed session, in order: cleanup, (retro: `running "
                                      "sent`), candidates, archived")
    p.add_argument("key", metavar="SESSION")
    p.add_argument("step", choices=("cleanup", "candidates", "archived"))
    p.add_argument("n", type=int, nargs="?", help="candidates: how many its retro reported (0 for none)")
    p.add_argument("--issue", help="candidates: the Retro candidates issue's number (once)")
    p.add_argument("--title", help="archived: the session's title, for the digest line")
    p.add_argument("--skip", metavar="WHY", help="archived: the session is gone and its remaining steps cannot run")
    p = sub.add_parser("closeout", help="the fixed process before a compact or a new master; starts only on RH's word")
    osub = p.add_subparsers(dest="action", required=True)
    op = osub.add_parser("start", help="RH said to close out")
    op.add_argument("--words", required=True, help="RH's message, word for word")
    op.add_argument("--at", help="when he said it (default: now)")
    op = osub.add_parser("done", help="record a closeout step, in order")
    op.add_argument("step", choices=CLOSEOUT_STEPS)
    op.add_argument("--session", dest="session_id", metavar="ID", help="fixes: the one sub-session started for them")
    op.add_argument("--skip", metavar="WHY", help="question: no candidates; fixes: RH chose none")
    op.add_argument("--file", help="handoff: the note's path")
    osub.add_parser("end", help="after the compact: clear the closeout mark")
    sub.add_parser("blocked", help="whether every remaining step waits on RH, the line that tells him, and whether to send it")
    p = sub.add_parser("room", help="what may start now under the two limits (anyone may read)")
    p.add_argument("--json", action="store_true", help="the counts as JSON instead of lines")
    p.add_argument("--disk", metavar="PATH", help=f"also check free disk at PATH (the repo) against the worktree floor "
                                                  f"(${FLOOR_ENV}, default {DEFAULT_FLOOR_GB:g} GB)")
    for name, text in (("init", "become the owner of a new or unowned state file"),
                       ("take", "take the role over on RH's hand-over, keeping the content")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--fresh", action="store_true", help="start from an empty state")
        if name == "take":
            p.add_argument("--words", required=True, help="RH's hand-over message, word for word")
            p.add_argument("--at", help="when he said it (default: now)")
    sub.add_parser("pause", help="RH said pause: the Stop rule is suspended")
    sub.add_parser("resume", help="RH said resume: the Stop rule applies again")
    p = sub.add_parser("ask", help="record the one open question to RH")
    p.add_argument("--short", required=True, help="the next-step box form (100 characters at most)")
    p.add_argument("--explain", "--full", dest="explain",
                   help="the full explanation in wait-what style: a little context, the decision, the options and "
                        "what each causes, the pick and why (--full is the older name)")
    p.add_argument("--explain-short", help="the same in three to five sentences: context, the decision, the pick "
                                           "with its reason")
    p.add_argument("--pick", help="your recommendation")
    p.add_argument("--at", help="when asked (default: now)")
    over = p.add_mutually_exclusive_group()
    over.add_argument("--displace", action="store_true",
                      help="a hard stop goes ahead of the open question, which is kept and comes back on `answered`")
    over.add_argument("--replace", action="store_true", help="the open question, reworded")
    p.add_argument("--closeout", action="store_true", help="closeout's one retro question")
    sub.add_parser("answered", help="RH answered: the question it displaced is open again, else none is")
    p = sub.add_parser("idle", help="record that you told RH `Nothing needs you: <text>`")
    p.add_argument("text")
    sub.add_parser("notified", help="the blocked notification was sent (cleared by `answered`)")
    p = sub.add_parser("digest", help="the 'since I asked' lines")
    dsub = p.add_subparsers(dest="action", required=True)
    dsub.add_parser("add").add_argument("line")
    dsub.add_parser("clear")
    p = sub.add_parser("limit", help="the two limits")
    lsub = p.add_subparsers(dest="action", required=True)
    lsub.add_parser("prs", help="PRs waiting on RH").add_argument("n", type=int)
    lsub.add_parser("sessions", help="sessions building").add_argument("n", type=int)
    lp = lsub.add_parser("lower", help="lower the session cap for now")
    lp.add_argument("n", type=int, nargs="?", help="default: the sessions working now, so nothing new starts")
    lp.add_argument("--reason", required=True)
    lsub.add_parser("restore", help="the lowered cap is lifted")
    helps = {"queue": "next items in ranked order", "running": "running sessions",
             "prs": "PRs waiting on RH", "go": "groups waiting for RH's go", "frozen": "frozen groups",
             "waiting": "sessions waiting on RH", "jobs": "job asks"}
    for name, (key, fields) in COLLECTIONS.items():
        p = sub.add_parser(name, help=helps[name])
        csub = p.add_subparsers(dest="action", required=True)
        add = csub.add_parser("add", help=f"add a row, or change the row with this {key}")
        add.add_argument("key", metavar=key.upper())
        for field in fields:
            if (name, field) == ("queue", "state"):
                add.add_argument("--state", dest="item_state", choices=QUEUE_STATES,
                                 help="ready: yours to take now; needs-rh: waits on RH; blocked: waits on something else")
            elif (name, field) == ("queue", "kind"):
                add.add_argument("--kind", help=KINDS_HELP)
            elif (name, field) == ("running", "command"):
                add.add_argument("--command", dest="owed_command", metavar="LINE",
                                 help="the slash command line this session is owed as its second message, e.g. "
                                      '"/mattpocock-skills:implement #593"; none for a mechanical session')
            elif (name, field) == ("running", "pr"):
                add.add_argument("--pr", action="append", metavar="N",
                                 help="a PR this session opened; repeat for more, a later call adds to them")
            else:
                add.add_argument(f"--{field}")
        if name == "running":
            csub.add_parser("sent", help="the session's owed command is confirmed run").add_argument(
                "key", metavar=key.upper())
        drop = csub.add_parser("drop", help="remove a row")
        drop.add_argument("key", metavar=key.upper())
        if name == "prs":
            drop.add_argument("--closed", action="store_true",
                              help="closed without a merge: the session that opened it does not land")
        csub.add_parser("clear", help="remove every row")
        csub.add_parser("set", help="replace all rows with the JSON list on stdin")
    return parser


def main(argv=None, stdin=None):
    """Run one command. Anything unexpected is one line and a non-zero exit; `stop` still allows."""
    args = build_parser().parse_args(argv)
    try:
        return run(args, stdin or sys.stdin)
    except Exception as err:  # noqa: BLE001 - a traceback tells the master nothing it can act on
        what = f"{type(err).__name__}: {err}"
        if args.command == "stop":
            print(json.dumps({"decision": "allow",
                              "warning": f"master-session Stop hook: could not decide ({what}); stop allowed."}))
            return 0
        print(f"state.py {args.command} failed ({what}). It may not have been recorded: run it again.", file=sys.stderr)
        return 1


def run(args, stdin):
    path = Path(args.state) if args.state else default_state_path()

    if args.command == "stop":
        try:
            text = stdin.read()
        except Exception as err:  # noqa: BLE001
            text = f"unreadable: {err}"
        verdict = stop_verdict(path, text)
        if "warning" in verdict:
            print(verdict["warning"], file=sys.stderr)
        print(json.dumps(verdict, ensure_ascii=False))
        return 0
    if args.command == "blocked":
        try:
            print(json.dumps(blocked_report(load(path)), ensure_ascii=False))
        except (OSError, ValueError, KeyError, TypeError) as err:
            print(f"state file {path} is missing or damaged ({err})", file=sys.stderr)
            return 1
        return 0
    if args.command == "room":
        try:
            now = room(load(path))
        except (OSError, ValueError, KeyError, TypeError) as err:
            print(f"state file {path} is missing or damaged ({err})", file=sys.stderr)
            return 1
        if args.disk:
            now["disk"] = disk_report(args.disk, now["lowered_reason"] is not None)
            now["lines"].append(now["disk"]["line"])
        now["lines"] += [f"{owed_line(s)}. Send it, confirm it ran, then: running sent {s['id']}." for s in now["owed"]]
        print(json.dumps(now, ensure_ascii=False) if args.json else "\n".join(now["lines"]))
        return 0
    if args.command == "handoff":
        try:
            print(handoff_text(load(path)))
        except (OSError, ValueError, KeyError, TypeError) as err:
            print(f"state file {path} is missing or damaged ({err})", file=sys.stderr)
            return 1
        return 0
    if args.command == "show":
        try:
            print(json.dumps(load(path), indent=2, ensure_ascii=False))
        except (OSError, ValueError, KeyError, TypeError) as err:
            print(f"state file {path} is missing or damaged ({err})", file=sys.stderr)
            return 1
        return 0
    if args.command in COLLECTIONS and args.action == "set":
        args.stdin_text = stdin.read()
    try:
        write_command(path, args.session or os.environ.get(SESSION_ENV), args)
    except Refused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    if getattr(args, "said", None):
        print(args.said)  # the one line to pass on to RH
    return 0


if __name__ == "__main__":
    sys.exit(main())

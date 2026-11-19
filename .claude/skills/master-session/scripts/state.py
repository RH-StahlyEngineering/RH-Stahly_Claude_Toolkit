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
    "running": ("id", ("group", "kind", "deadline", "command")),  # running sessions; `command`: the one it is owed
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


def load(path):
    """The state at `path` with defaults filled in. OSError or ValueError if unusable."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("not a JSON object")
    state = {**new_state(), **raw}
    if isinstance(raw.get("limits"), dict):
        state["limits"] = {**new_state()["limits"], **raw["limits"]}
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
    working = sum(1 for s in state["running"] if s.get("kind") in CAPPED_KINDS)
    free = max(0, cap - working)
    pile_full = prs >= pr_limit
    lowered = limits.get("lowered_sessions") is not None
    lines = [f"PRs waiting on RH: {prs} of {pr_limit}." + (" Start no new building." if pile_full else "")]
    if pile_full:
        lines.append("  Still yours: read-only checks, triage preparation, keeping waiting PRs current.")
    lines.append(f"Sessions working: {working} of {cap}"
                 + (f" (cap lowered from {limits['sessions']}: {limits.get('lowered_reason') or 'no reason given'})"
                    if lowered else "") + ".")
    if pile_full:
        why = "no build session (PR pile full)"
    elif not free:
        why = "no session (cap reached)"
    else:
        why = _count(free, "session", "sessions")
    lines.append(f"May start now: {why}" + (f"; {_count(free, 'triage session', 'triage sessions')}"
                                            if pile_full and free else "") + ".")
    return {"prs": prs, "pr_limit": pr_limit, "sessions": working, "cap": cap,
            "lowered_reason": limits.get("lowered_reason") if lowered else None,
            "build_starts": 0 if pile_full else free, "other_starts": free, "lines": lines,
            "owed": [{"id": s.get("id"), "command": s.get("command")} for s in owed_commands(state)]}


def owed_commands(state):
    """Running sessions whose recorded command is not confirmed run: each is the master's step, never RH's.

    A row with no `command` (a mechanical session, or one written by a master on the older skill text) owes nothing.
    """
    return [s for s in state["running"] if s.get("command") and not s.get("command_sent")]


def owed_line(session):
    return f"Command not sent: {session.get('id')} is owed `{session.get('command')}`"


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
    owed = owed_commands(state)
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
        if args.action == "add":
            value = int(args.key) if cmd == "prs" else args.key
            # `--state` on `queue add` is parsed as item_state: the file option owns `state`.
            flags = {f: getattr(args, FLAG_DESTS.get((cmd, f), f)) for f in fields}
            given = {f: v for f, v in flags.items() if v is not None}
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
                                      '"/mattpocock-skills:tdd #593"; none for a mechanical session')
            else:
                add.add_argument(f"--{field}")
        if name == "running":
            csub.add_parser("sent", help="the session's owed command is confirmed run").add_argument(
                "key", metavar=key.upper())
        csub.add_parser("drop", help="remove a row").add_argument("key", metavar=key.upper())
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

"""The PRs waiting on RH: list them, record his approval, and say whether one may be merged now.

Usage: python -X utf8 -I merges.py list --repo OWNER/NAME
       python -X utf8 -I merges.py approve N [N ...] --words "<RH's message, word for word>" --repo OWNER/NAME
       python -X utf8 -I merges.py check N --repo OWNER/NAME

It merges nothing and writes nothing on GitHub: it reads each PR's head commit, checks, labels and
GitHub's own answer on merge conflicts, the compares between commits, and the repo's open "Master is red"
and gate-problem issues. How far a PR is behind its base is printed and never holds a merge. `list` and `approve` update the `prs` rows of
the state file when the owning master runs them; anyone else gets the list and nothing is written.
`check` exits 0 when the PR may be merged now and 1 when it may not, with the reason and the next step.
"""
import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `python -I` leaves the script's folder out

import planner  # noqa: E402
import state as store  # noqa: E402

RED_TITLE = "master is red"        # Agisoft_Coding ADR 0005: open while master is red
RED_LABEL = "master-red"
FIX_LABEL = "fixes-master"         # the CI owner's label on the one PR that may merge meanwhile
GATE_TITLE = "gate problems"       # ADR 0007: the standing issue gate problems are reported on
PASSED = ("SUCCESS", "NEUTRAL", "SKIPPED")
PR_FIELDS = "number,title,state,headRefOid,baseRefName,labels,statusCheckRollup,mergeable,mergeStateStatus"
FILE_LIMIT = 300                   # a compare lists this many files at most: at the limit, some may be unseen
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@.*$", re.M)  # where a hunk sits, not what it changes


def check_state(rollup):
    """(green | red | pending | missing, what to say about it) for the checks on a PR's head commit."""
    if not rollup:
        return "missing", "no checks ran on the head commit"
    failed, running = [], []
    for check in rollup:
        name = check.get("name") or check.get("context") or "a check"
        link = check.get("detailsUrl") or check.get("targetUrl") or ""
        if "context" in check and "status" not in check:  # a commit status, not a check run
            done, result = check.get("state") not in ("PENDING", "EXPECTED"), check.get("state")
        else:
            done, result = check.get("status") == "COMPLETED", check.get("conclusion")
        if not done:
            running.append(f"{name} still running")
        elif result not in PASSED:
            failed.append(f"{name} failed {link}".rstrip())
    if failed:
        return "red", ", ".join(failed)
    if running:
        return "pending", ", ".join(running)
    return "green", "every check is green"


def read_pr(repo, number, gh):
    """One PR as GitHub has it now: head commit, checks on it, labels, whether GitHub reports a merge conflict,
    how far behind its base it is, and its own change (the files of its compare with its base)."""
    pr = json.loads(gh(["pr", "view", str(number), "--repo", repo, "--json", PR_FIELDS]))
    pr["checks"], pr["checks_say"] = check_state(pr.get("statusCheckRollup"))
    pr["labels"] = [label["name"] for label in pr.get("labels") or []]
    # True, False, or None while GitHub has not said: only its plain "MERGEABLE" is a no-conflict answer.
    if pr.get("mergeable") == "CONFLICTING" or pr.get("mergeStateStatus") == "DIRTY":
        pr["conflict"] = True
    else:
        pr["conflict"] = False if pr.get("mergeable") == "MERGEABLE" else None
    pr["behind"], pr["files"] = 0, None  # commits behind its base; None when that could not be read
    if pr.get("state") == "OPEN":
        try:
            compare = json.loads(gh(["api", f"repos/{repo}/compare/{pr['baseRefName']}...{pr['headRefOid']}"]))
            pr["behind"], pr["files"] = int(compare["behind_by"]), compare.get("files")
        except Exception:  # noqa: BLE001
            pr["behind"] = None
    return pr


def behind_say(pr):
    """How far behind its base, in words. Information only: it never holds a merge."""
    if pr["behind"] is None:
        return f"behind {pr['baseRefName']} unknown"
    return f"{pr['behind']} behind {pr['baseRefName']}" if pr["behind"] else f"current with {pr['baseRefName']}"


def own_change(files):
    """A PR's own change, comparable across heads: per file its status and its patch without the hunk positions.
    Raises when the files are not all there to compare."""
    if files is None or len(files) >= FILE_LIMIT:
        raise ValueError("the compare's file list is missing or cut off")
    change = {}
    for f in files:
        if not f.get("patch"):  # binary or too large: GitHub gives nothing to compare
            raise ValueError(f"no patch for {f.get('filename')}")
        change[f["filename"]] = (f.get("status"), f.get("previous_filename"), HUNK.sub("@@", f["patch"]))
    return change


def carries(repo, approved_head, pr, gh):
    """(True, None) when RH's approval of `approved_head` still covers the PR's head: every commit since is a
    merge of the base, and the PR's own change against its base is the same patch as when he approved.
    Otherwise (False, why); anything unreadable is a no."""
    base, head = pr["baseRefName"], pr["headRefOid"]

    def compare(pair):
        return json.loads(gh(["api", f"repos/{repo}/compare/{pair}"]))

    try:
        since = compare(f"{approved_head}...{head}")
        if since["status"] != "ahead":
            return False, "the commit he approved is no longer in its history"
        parents = {c["sha"]: [p["sha"] for p in c["parents"]] for c in since["commits"]}
        if int(since["total_commits"]) != len(parents):
            raise ValueError("the compare's commit list is cut off")
        at = head
        for _ in parents:  # the PR's own line of commits, newest first, back to the one he approved
            if at == approved_head:
                break
            mine, *merged = parents[at]
            if len(merged) != 1 or int(compare(f"{base}...{merged[0]}")["ahead_by"]) != 0:
                return False, f"{at[:7]} is not a merge of {base}"
            at = mine
        if at != approved_head:
            raise ValueError("the commits since do not lead back to the approved one")
        if own_change(compare(f"{base}...{approved_head}")["files"]) != own_change(pr["files"]):
            return False, f"its own change against {base} is no longer the one he approved"
    except Exception:  # noqa: BLE001 - unreadable is never "it carries"
        return False, "what was pushed since could not be read (run the check once more before you ask him)"
    return True, None


def repo_gate(repo, gh):
    """The repo's open "Master is red" issue and its gate-problem issue, each a number or None."""
    def issues(*query):
        return json.loads(gh(["issue", "list", "--repo", repo, "--state", "open", "--limit", "50",
                              "--json", "number,title,labels", *query]))

    def title(issue):
        return (issue.get("title") or "").strip().lower()

    found = issues("--search", '"Master is red" in:title') + issues("--label", RED_LABEL)
    red = [i["number"] for i in found
           if title(i).startswith(RED_TITLE) or RED_LABEL in [label["name"] for label in i.get("labels") or []]]
    gate = [i["number"] for i in issues("--search", '"Gate problems" in:title') if title(i).startswith(GATE_TITLE)]
    return {"red": min(red) if red else None, "gate": min(gate) if gate else None}


def _row(state, number):
    return next((p for p in state["prs"] if str(p.get("number")) == str(number)), None)


def verdict(row, pr, gate, repo, carry=None):
    """(may merge, lines): RH's approval still valid, green on the current commit, no merge conflict reported,
    master not red. `carry` is carries()'s answer when the head moved since his approval."""
    n, base, head = pr["number"], pr.get("baseRefName"), str(pr.get("headRefOid"))[:7]
    drop = f"{store.RUN}state.py prs drop {n}"
    approve = f'{store.RUN}merges.py approve {n} --words "<his words>" --repo {repo}'
    again = f"Tell him in one line what was pushed and ask again; on his yes: {approve}."
    if pr.get("state") != "OPEN":
        return False, [f"MERGE #{n}: no. It is {str(pr.get('state')).lower()} on GitHub. Run: {drop}."]
    if not row or not row.get("approved"):
        return False, [f"MERGE #{n}: no. RH has not approved merging it. Every merge is his: list it "
                       f"({store.RUN}merges.py list) and ask him."]
    if not row.get("head"):
        return False, [f"MERGE #{n}: no. RH's approval was recorded without the commit it was for (now {head}). "
                       f"Ask him again; on his yes: {approve}."]
    carried = []
    if row["head"] != pr["headRefOid"]:
        ok, why = carry or (False, "what was pushed since could not be read")
        if not ok:
            return False, [f"MERGE #{n}: no. RH approved {row['head'][:7]} and it is on {head} now: {why}. Only "
                           f"merges of {base} that leave its own change as it was keep his approval. {again}"]
        carried = [f"RH's approval of {row['head'][:7]} carries: only merges of {base} since."]
    if pr["conflict"]:
        return False, [f"MERGE #{n}: no. GitHub reports a merge conflict with {base}. Tell the owning session to "
                       f"merge {base} in and resolve it. The resolution is new work, so RH's approval ends there: "
                       f"when it is green, show him what was resolved and ask again; on his yes: {approve}."]
    is_fix = FIX_LABEL in pr["labels"]
    if gate["red"] and not is_fix:
        return False, [f"MERGE #{n}: no. Master is red (#{gate['red']}): nothing merges but the PR the CI owner "
                       f"labels {FIX_LABEL}. RH's approval stands; merge when #{gate['red']} is closed. "
                       "Never label it yourself."] + carried
    if pr["checks"] != "green":
        return False, [f"MERGE #{n}: no. Checks on {head}: {pr['checks_say']}. "
                       + ("Tell RH which check failed with its link, and tell the owning session what to fix. "
                          if pr["checks"] == "red" else "Wait for them. ")
                       + "Never re-run, skip or bypass a check or branch protection to get green; a check that "
                         f"fails for a reason outside the PR is a gate problem ({store.RUN}merges.py list says where "
                         "it goes)."] + carried
    if pr["conflict"] is None:
        return False, [f"MERGE #{n}: no. GitHub has not said whether it merges without conflict "
                       f"(mergeable: {pr.get('mergeable') or 'no answer'}). It works that out shortly after a push: "
                       "run the check again. Never merge on a guess."] + carried
    return True, [f"MERGE #{n}: yes. RH approved: {row['approved']}. Every check is green on {head} and GitHub "
                  f"reports no merge conflict ({behind_say(pr)}"
                  + ("" if pr["behind"] == 0 else ", which holds no merge") + ")."
                  + (f" It is the fix for a red master (#{gate['red']})." if gate["red"] else "")
                  + f" Merge it now, then: {drop}."] + carried


def listing(state, lives, gate, repo, limit):
    """The lines for RH and for the master, the `prs` rows as GitHub has them now, and the `running` rows with
    each merged PR recorded on the session that opened it (a session whose PRs are all merged has landed)."""
    lines = [f"PRS WAITING ON RH  {len(state['prs'])} of {limit}"]
    went_red, conflict, gone, rows = [], [], [], []
    after = {"running": copy.deepcopy(state["running"])}  # the running rows once each merge is recorded on them
    for row in state["prs"]:
        pr = lives[str(row["number"])]
        n = row["number"]
        if pr.get("state") != "OPEN":
            # The session that opened it lands with the merge (`after`), never with a close.
            is_merged = pr.get("state") == "MERGED"
            owners = store.mark_merged(after, int(n)) if is_merged else [
                f"session {s.get('id')} opened it and has not landed" for s in state["running"]
                if isinstance(s.get("pr"), list) and int(n) in s["pr"]]
            gone.append(f"GONE  #{n} is {str(pr.get('state')).lower()}"
                        + (f" ({'; '.join(owners)})" if owners else "")
                        + f": {store.RUN}state.py prs drop {n}" + ("" if is_merged else " --closed"))
            rows.append(row)
            continue
        checks = (pr["checks"] + ("" if pr["behind"] == 0 else f", {behind_say(pr)}")
                  + (f", conflict with {pr['baseRefName']}" if pr["conflict"] else ""))
        lines.append(f"PR #{n}  rung {row.get('rung') or '?'}  {checks}  {row.get('line') or pr.get('title')}"
                     + ("  (approved)" if row.get("approved") else ""))
        if pr["checks"] == "red" and row.get("checks") != "red":
            went_red.append(f"WENT RED  #{n}: {pr['checks_say']}. Tell RH now, in one line with the link, and tell "
                            "the owning session what to fix.")
        if pr["conflict"]:
            conflict.append(f"CONFLICT  #{n}: GitHub reports a merge conflict with {pr['baseRefName']}. Tell the "
                            f"owning session to merge {pr['baseRefName']} in and resolve it; RH approves the result "
                            "again.")
        rows.append({**row, "checks": pr["checks"]})
    if gate["red"]:
        lines.append(f"MASTER IS RED  #{gate['red']}: merge nothing but a PR labelled {FIX_LABEL} by the CI owner")
    where = gate["red"] or gate["gate"]
    lines.append(f"GATE PROBLEMS  comment on #{where} (symptom, log, branch) and carry on; never patch a gate file"
                 if where else "GATE PROBLEMS  no gate-problem issue in this repo: tell RH")
    return lines + went_red + conflict + gone, rows, after["running"]


def main(argv=None, gh=planner.real_gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {"list": sub.add_parser("list", help="one line per waiting PR, read from GitHub now"),
                "approve": sub.add_parser("approve", help="record RH's approval, word for word, on each PR he named"),
                "check": sub.add_parser("check", help="may this PR be merged now? (exit 0 yes, 1 no)")}
    commands["approve"].add_argument("numbers", nargs="+", type=int, metavar="N")
    commands["approve"].add_argument("--words", required=True, help="RH's whole message, unchanged")
    commands["approve"].add_argument("--at", help="when he said it (default: now)")
    commands["check"].add_argument("number", type=int, metavar="N")
    for p in commands.values():
        p.add_argument("--repo", required=True, help="OWNER/NAME")
        p.add_argument("--state", help="state file (default: as state.py)")
        p.add_argument("--session", help="this session's id (default: as state.py)")
    args = parser.parse_args(argv)
    path = Path(args.state) if args.state else store.default_state_path()
    session = args.session or os.environ.get(store.SESSION_ENV)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        state = store.load(path)
    except (OSError, ValueError, KeyError, TypeError) as err:
        print(f"state file {path} is missing or damaged ({err})", file=sys.stderr)
        return 2
    owner = bool(session) and state["owner"] == session
    try:
        return run(args, state, owner, path, session, gh)
    except store.Refused as err:
        print(f"refused: {err}", file=sys.stderr)
    except Exception as err:  # noqa: BLE001 - gh failed or answered something unreadable: never a yes
        reason = " ".join(str(err).split()) or type(err).__name__
        print(f"merges {args.command}: could not read GitHub ({reason}). Nothing was recorded and nothing may "
              "merge on this; run it again.", file=sys.stderr)
    return 2


def run(args, state, owner, path, session, gh):
    if args.command == "check":
        pr, row = read_pr(args.repo, args.number, gh), _row(state, args.number)
        moved = (pr.get("state") == "OPEN" and row and row.get("approved") and row.get("head")
                 and row["head"] != pr["headRefOid"])
        carry = carries(args.repo, row["head"], pr, gh) if moved else None
        ok, lines = verdict(row, pr, repo_gate(args.repo, gh), args.repo, carry)
        print("\n".join(lines))
        return 0 if ok else 1

    if args.command == "approve":
        if not owner:
            print("refused: only the master records RH's approval; a side conversation merges nothing.", file=sys.stderr)
            return 2
        missing = [n for n in args.numbers if not _row(state, n)]
        if missing:
            print("refused: not in the waiting list: " + " ".join(f"#{n}" for n in missing)
                  + f". Nothing was recorded. Add it first ({store.RUN}state.py prs add <n>), then approve again.",
                  file=sys.stderr)
            return 2
        quote = f'"{args.words}" ({args.at or datetime.now().isoformat(timespec="seconds")})'
        heads = {n: read_pr(args.repo, n, gh)["headRefOid"] for n in args.numbers}  # all read before any is recorded
        for n in args.numbers:
            _row(state, n).update(approved=quote, head=heads[n])
        store.set_rows(path, session, {"prs": state["prs"]})
        print(f"RH: {quote}\nRecorded on " + " ".join(f"#{n}" for n in args.numbers)
              + ", each for the commit it is on now; later merges of its base alone keep it. "
              + "Quote these words unchanged in any relay. "
              + f"Next, per PR: {store.RUN}merges.py check <n> --repo {args.repo}.")
        return 0

    lives = {str(row["number"]): read_pr(args.repo, row["number"], gh) for row in state["prs"]}
    lines, rows, running = listing(state, lives, repo_gate(args.repo, gh), args.repo, state["limits"]["prs"])
    if owner and (rows != state["prs"] or running != state["running"]):
        store.set_rows(path, session, {"prs": rows, "running": running})
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

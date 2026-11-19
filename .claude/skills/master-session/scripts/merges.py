"""The PRs waiting on RH: list them, record his approval, and say whether one may be merged now.

Usage: python -X utf8 -I merges.py list --repo OWNER/NAME
       python -X utf8 -I merges.py approve N [N ...] --words "<RH's message, word for word>" --repo OWNER/NAME
       python -X utf8 -I merges.py check N --repo OWNER/NAME

It merges nothing and writes nothing on GitHub: it reads each PR's head commit, checks and labels and
the repo's open "Master is red" and gate-problem issues. `list` and `approve` update the `prs` rows of
the state file when the owning master runs them; anyone else gets the list and nothing is written.
`check` exits 0 when the PR may be merged now and 1 when it may not, with the reason and the next step.
"""
import argparse
import json
import os
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
PR_FIELDS = "number,title,state,headRefOid,baseRefName,labels,statusCheckRollup"


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
    """One PR as GitHub has it now: head commit, checks on it, labels, and how far behind its base it is."""
    pr = json.loads(gh(["pr", "view", str(number), "--repo", repo, "--json", PR_FIELDS]))
    pr["checks"], pr["checks_say"] = check_state(pr.get("statusCheckRollup"))
    pr["labels"] = [label["name"] for label in pr.get("labels") or []]
    pr["behind"] = 0  # commits behind its base; None when that could not be read (never "current" unverified)
    if pr.get("state") == "OPEN":
        try:
            compare = json.loads(gh(["api", f"repos/{repo}/compare/{pr['baseRefName']}...{pr['headRefOid']}"]))
            pr["behind"] = int(compare["behind_by"])
        except Exception:  # noqa: BLE001
            pr["behind"] = None
    return pr


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


def verdict(row, pr, gate, repo):
    """(may merge, lines): RH's approval of the current commit, green on it, current with its base, master not red."""
    n = pr["number"]
    update = f"gh pr update-branch {n} --repo {repo}"
    drop = f"{store.RUN}state.py prs drop {n}"
    approve = f'{store.RUN}merges.py approve {n} --words "<his words>" --repo {repo}'
    if pr.get("state") != "OPEN":
        return False, [f"MERGE #{n}: no. It is {str(pr.get('state')).lower()} on GitHub. Run: {drop}."]
    if not row or not row.get("approved"):
        return False, [f"MERGE #{n}: no. RH has not approved merging it. Every merge is his: list it "
                       f"({store.RUN}merges.py list) and ask him."]
    if row.get("head") != pr["headRefOid"]:
        was = f"{row['head'][:7]} -> {pr['headRefOid'][:7]}" if row.get("head") else f"now {pr['headRefOid'][:7]}"
        return False, [f"MERGE #{n}: no. RH's approval is not for the commit it is on now ({was}): commits pushed "
                       "after his approval need a new one. Tell him in one line what was pushed and ask again; "
                       f"on his yes: {approve}."]
    is_fix = FIX_LABEL in pr["labels"]
    if gate["red"] and not is_fix:
        return False, [f"MERGE #{n}: no. Master is red (#{gate['red']}): nothing merges but the PR the CI owner "
                       f"labels {FIX_LABEL}. RH's approval stands; merge when #{gate['red']} is closed. "
                       "Never label it yourself."]
    if pr["checks"] != "green":
        return False, [f"MERGE #{n}: no. Checks on {pr['headRefOid'][:7]}: {pr['checks_say']}. "
                       + ("Tell RH which check failed with its link, and tell the owning session what to fix. "
                          if pr["checks"] == "red" else "Wait for them. ")
                       + "Never re-run, skip or bypass a check or branch protection to get green; a check that "
                         f"fails for a reason outside the PR is a gate problem ({store.RUN}merges.py list says where "
                         "it goes)."]
    if pr["behind"] is None:
        return False, [f"MERGE #{n}: no. Its compare with {pr['baseRefName']} could not be read, so nothing says it "
                       "is up to date. Run the check again; if it still fails, tell RH."]
    if pr["behind"]:
        return False, [f"MERGE #{n}: no. It is {pr['behind']} behind {pr['baseRefName']}. Run: {update}. That puts "
                       "a new commit on it, so RH's approval no longer covers it: when its checks are green again, "
                       f"ask him again, then {approve}. On a conflict, the owning session rebases."]
    return True, [f"MERGE #{n}: yes. RH approved: {row['approved']}. Every check is green on {pr['headRefOid'][:7]}, "
                  f"the commit he approved, current with {pr['baseRefName']}."
                  + (f" It is the fix for a red master (#{gate['red']})." if gate["red"] else "")
                  + f" Merge it now, then: {drop}."]


def listing(state, lives, gate, repo, limit):
    """The lines for RH and for the master, and the `prs` rows as GitHub has them now."""
    lines = [f"PRS WAITING ON RH  {len(state['prs'])} of {limit}"]
    went_red, update, gone, rows = [], [], [], []
    for row in state["prs"]:
        pr = lives[str(row["number"])]
        n = row["number"]
        if pr.get("state") != "OPEN":
            gone.append(f"GONE  #{n} is {str(pr.get('state')).lower()}: {store.RUN}state.py prs drop {n}")
            rows.append(row)
            continue
        behind = f", behind {pr['baseRefName']} unknown" if pr["behind"] is None else ""
        checks = pr["checks"] + (f", {pr['behind']} behind {pr['baseRefName']}" if pr["behind"] else behind)
        lines.append(f"PR #{n}  rung {row.get('rung') or '?'}  {checks}  {row.get('line') or pr.get('title')}"
                     + ("  (approved)" if row.get("approved") else ""))
        if pr["checks"] == "red" and row.get("checks") != "red":
            went_red.append(f"WENT RED  #{n}: {pr['checks_say']}. Tell RH now, in one line with the link, and tell "
                            "the owning session what to fix.")
        if pr["behind"]:
            update.append(f"UPDATE  #{n}: gh pr update-branch {n} --repo {repo}")
        rows.append({**row, "checks": pr["checks"]})
    if gate["red"]:
        lines.append(f"MASTER IS RED  #{gate['red']}: merge nothing but a PR labelled {FIX_LABEL} by the CI owner")
    where = gate["red"] or gate["gate"]
    lines.append(f"GATE PROBLEMS  comment on #{where} (symptom, log, branch) and carry on; never patch a gate file"
                 if where else "GATE PROBLEMS  no gate-problem issue in this repo: tell RH")
    return lines + went_red + update + gone, rows


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
        pr = read_pr(args.repo, args.number, gh)
        ok, lines = verdict(_row(state, args.number), pr, repo_gate(args.repo, gh), args.repo)
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
              + ", each for the commit it is on now. Quote these words unchanged in any relay. "
              + f"Next, per PR: {store.RUN}merges.py check <n> --repo {args.repo}.")
        return 0

    lives = {str(row["number"]): read_pr(args.repo, row["number"], gh) for row in state["prs"]}
    lines, rows = listing(state, lives, repo_gate(args.repo, gh), args.repo, state["limits"]["prs"])
    if owner and rows != state["prs"]:
        store.set_rows(path, session, {"prs": rows})
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

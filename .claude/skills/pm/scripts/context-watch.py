"""Context watch: warn the coordinator before fleet sessions compact.

Scans every recently-active conversation transcript (*.jsonl) for this
project family, reads each session's LATEST usage block, and estimates how
full its context window is. The live context consumption of a session is the
prompt side of its most recent assistant turn:

    input_tokens + cache_read_input_tokens + cache_creation_input_tokens

Outputs (all under .claude/handoffs/):
  context-watch.txt        status table, rewritten every cycle (read this)
  CONTEXT-WARNINGS.md      append-only; a line per threshold crossing or
                           suspected compaction (a >30% drop between cycles)
  context-watch.log        the monitor's own diagnostics

The window size is per-MODEL, not global: fable/1m-class sessions run ~1M;
everything else is assumed 200k. Session->fleet-name mapping is a HEURISTIC
from the transcript's recorded cwd (worktree paths name the session); treat
names as best-effort, session ids as truth.

Launch detached (never blocks a turn):
  Start-Process python -ArgumentList '<this file>' -WindowStyle Hidden
Stop: kill the PID named at the top of context-watch.txt.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
PROJECT_MATCH = "Agisoft-Coding"          # matches main tree + worktree slugs
HANDOFFS = Path(r"C:\Users\rharbach\Desktop\Agisoft_Coding\.claude\handoffs")
STATUS = HANDOFFS / "context-watch.txt"
WARNINGS = HANDOFFS / "CONTEXT-WARNINGS.md"
LOG = HANDOFFS / "context-watch.log"
STATE = HANDOFFS / ".context-watch-state.json"

CYCLE_SECONDS = 60
ACTIVE_WINDOW_HOURS = 6                    # ignore transcripts idle longer
TAIL_BYTES = 262_144
WARN_AT = 0.75                             # first warning threshold
WARN_STEP = 0.05                           # re-warn every further 5%
DROP_AS_COMPACTION = 0.30                  # >30% shrink between cycles

CWD_NAMES = {                              # heuristic: worktree cwd -> fleet name
    "worktrees/landing-page": "dmai-dev",
    "worktrees/back-half": "back-half-dev",
    "worktrees/bridge-core": "bridge-core",
    "worktrees/persona-fleet": "persona-fleet-wt",
    "worktrees/arc4-suite-integrity": "arc4-dev",
    "worktrees/thinning-commit": "thinning-wt",
}
SESSION_NAMES = {                          # known ids beat the cwd heuristic
    "e06a2843": "dmai-pm",
}


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def window_for(model: str, observed_total: int = 0) -> int:
    m = (model or "").lower()
    if "fable" in m or "[1m]" in m or "-1m" in m:
        return 1_000_000
    # A measured total above the assumed window PROVES the window is bigger
    # (some opus sessions run the 1M beta; the transcript does not say so).
    if observed_total > 190_000:
        return 1_000_000
    return 200_000


def latest_usage(path: Path):
    """Return (total, model, cwd, ts) from the newest usage-bearing event."""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        tail = f.read()
    best = None
    for line in tail.split(b"\n"):
        if b"usage" not in line or b"input_tokens" not in line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        msg = e.get("message") or {}
        u = msg.get("usage") or e.get("usage") or {}
        if "input_tokens" not in u:
            continue
        total = (
            u.get("input_tokens", 0)
            + u.get("cache_read_input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0)
        )
        best = (total, msg.get("model", ""), e.get("cwd", ""), e.get("timestamp", ""))
    return best


def name_for(session_id: str, cwd: str) -> str:
    for prefix, name in SESSION_NAMES.items():
        if session_id.startswith(prefix):
            return name
    c = (cwd or "").replace("\\", "/")
    for frag, name in CWD_NAMES.items():
        if frag in c:
            return name
    return "main-tree?"


def warn(text: str) -> None:
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with WARNINGS.open("a", encoding="utf-8") as f:
        f.write(f"- **{stamp}** {text}\n")
    log(f"WARN {text}")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state), encoding="utf-8")


def cycle(state: dict) -> list[str]:
    rows = []
    cutoff = time.time() - ACTIVE_WINDOW_HOURS * 3600
    for pdir in PROJECTS.iterdir():
        if PROJECT_MATCH not in pdir.name or not pdir.is_dir():
            continue
        for jf in pdir.glob("*.jsonl"):
            try:
                st = jf.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff or st.st_size < 10_000:
                continue
            got = latest_usage(jf)
            if not got:
                continue
            total, model, cwd, ts = got
            sid = jf.stem
            name = name_for(sid, cwd)
            win = window_for(model, total)
            pct = total / win
            age_min = int((time.time() - st.st_mtime) / 60)
            rows.append(
                f"{name:<16} {sid[:8]}  {pct:>5.0%}  {total:>9,} / {win:>9,}  "
                f"{(model or '?')[:28]:<28} idle {age_min:>3}m"
            )
            prev = state.get(sid, {})
            prev_total = prev.get("total", 0)
            prev_warned = prev.get("warned_pct", 0.0)
            if prev_total and total < prev_total * (1 - DROP_AS_COMPACTION):
                warn(
                    f"{name} ({sid[:8]}) context DROPPED {prev_total:,} -> {total:,} "
                    f"— likely COMPACTED. Re-brief it (resume-brief pattern) before it builds."
                )
                prev_warned = 0.0
            if pct >= WARN_AT and pct >= prev_warned + WARN_STEP:
                warn(
                    f"{name} ({sid[:8]}) at {pct:.0%} of its ~{win:,} window "
                    f"({total:,} tokens) — order its compaction anchor NOW."
                )
                prev_warned = pct
            state[sid] = {"total": total, "warned_pct": prev_warned}
    return rows


def main() -> None:
    HANDOFFS.mkdir(parents=True, exist_ok=True)
    log(f"context-watch started pid={os.getpid()}")
    state = load_state()
    while True:
        try:
            rows = cycle(state)
            save_state(state)
            stamp = datetime.now().isoformat(timespec="seconds")
            body = (
                f"# context-watch  pid={os.getpid()}  updated={stamp}\n"
                f"# warn at {WARN_AT:.0%} (+{WARN_STEP:.0%} steps) -> CONTEXT-WARNINGS.md\n"
                f"# name          session   pct       used /    window  model"
                f"                        activity\n" + "\n".join(sorted(rows)) + "\n"
            )
            STATUS.write_text(body, encoding="utf-8")
        except Exception as exc:  # keep the watch alive through anything
            log(f"cycle error: {exc!r}")
        time.sleep(CYCLE_SECONDS)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""dirty-fix bundle manager.

Stdlib only. Cross-platform. No dependency on the skill being installed --
a bundle produced here is self-describing and its gate runs anywhere.

Storage is split by durability:

  <repo>/dirty-fix/<slug>/          committed    spec + gate
  <store>/<project-id>/<slug>/      never        fixtures, dirty code, appendix

State is DERIVED from which files exist. There is no status file to desync.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

STATES = (
    "FRAMING", "REDUCING", "LOOPING", "HARVESTED",
    "SEALED", "CONSUMED", "ABANDONED", "NOT_REDUCIBLE",
)

ARCHETYPES = ("transform", "extract", "decide", "integrate", "perform")
DISPOSITIONS = ("answer", "feature")
MODES = ("exact", "tolerance", "invariant", "set", "behavioral", "statistical")


# --------------------------------------------------------------------------
# locations
# --------------------------------------------------------------------------

def _git(args, cwd=None):
    try:
        out = subprocess.run(
            ["git"] + args, cwd=str(cwd or Path.cwd()),
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def main_repo_root(start=None):
    """Root of the MAIN repo, never a worktree.

    Worktrees have a different path than the repo they belong to. Keying the
    store on cwd would make bundles vanish the moment implementation starts in
    a worktree, so we key on the git common dir instead.
    """
    start = Path(start or Path.cwd())
    common = _git(["rev-parse", "--git-common-dir"], cwd=start)
    if not common:
        return None
    p = Path(common)
    if not p.is_absolute():
        p = (start / p)
    try:
        p = p.resolve()
    except OSError:
        pass
    # <root>/.git  ->  <root>;  bare repos point at themselves
    return p.parent if p.name == ".git" else p


def in_worktree(start=None):
    start = Path(start or Path.cwd())
    gd = _git(["rev-parse", "--git-dir"], cwd=start)
    gc = _git(["rev-parse", "--git-common-dir"], cwd=start)
    if not gd or not gc:
        return False
    if _git(["rev-parse", "--show-superproject-working-tree"], cwd=start):
        return False  # submodule, not a worktree
    resolve = lambda x: str((start / x).resolve() if not Path(x).is_absolute() else Path(x).resolve())
    try:
        return resolve(gd) != resolve(gc)
    except OSError:
        return False


def branch_dirty(start=None):
    out = _git(["status", "--porcelain"], cwd=start or Path.cwd())
    return bool(out)


def project_key(start=None):
    """(identity_path, project_id). Falls back to cwd outside a repo."""
    root = main_repo_root(start)
    if root is None:
        root = Path(start or Path.cwd()).resolve()
    norm = str(root).replace("\\", "/").rstrip("/").lower()
    return root, hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def store_root():
    env = os.environ.get("DIRTY_FIX_HOME")
    return Path(env).expanduser() if env else Path.home() / ".dirty-fix"


def store_dir(slug=None, start=None):
    root, pid = project_key(start)
    d = store_root() / pid
    return d / slug if slug else d


def repo_dir(slug=None, start=None):
    root, _ = project_key(start)
    d = root / "dirty-fix"
    return d / slug if slug else d


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return datetime.now().strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------

def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def nonempty_dir(p):
    p = Path(p)
    return p.is_dir() and any(p.iterdir())


def bundle_state(slug, start=None):
    s = store_dir(slug, start)
    r = repo_dir(slug, start)
    if not s.exists():
        return None
    if (s / "ABANDONED").exists():
        return "ABANDONED"
    if (s / "NOT_REDUCIBLE").exists():
        return "NOT_REDUCIBLE"
    if (s / "CONSUMED").exists():
        return "CONSUMED"
    # SEALED is a *verified* transition, so it is marked rather than derived --
    # otherwise merely writing acceptance.md would claim a gate nobody validated.
    if (s / "SEALED").exists():
        return "SEALED"
    metrics = read_json(r / "metrics.json", {})
    if metrics.get("checks"):
        return "HARVESTED"
    if nonempty_dir(s / "fixture"):
        return "LOOPING"
    if (s / "profile.json").exists():
        return "REDUCING"
    return "FRAMING"


def list_bundles(start=None):
    d = store_dir(start=start)
    if not d.is_dir():
        return []
    out = []
    for b in sorted(d.iterdir()):
        if not b.is_dir():
            continue
        meta = read_json(b / "meta.json", {}) or {}
        out.append({
            "slug": b.name,
            "state": bundle_state(b.name, start),
            "disposition": meta.get("disposition", "?"),
            "archetype": meta.get("archetype", "?"),
            "sub_spike": meta.get("sub_spike", False),
            "created": meta.get("created", "?"),
            "store": str(b),
            "repo": str(repo_dir(b.name, start)),
        })
    return out


def dir_size(p):
    total = 0
    for root, _dirs, files in os.walk(str(p)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0


def require(slug, start=None):
    st = bundle_state(slug, start)
    if st is None:
        die(f"no bundle '{slug}' for this project. `df.py status` to list.")
    return st


def die(msg, code=2):
    print(f"dirty-fix: {msg}", file=sys.stderr)
    sys.exit(code)


def ok(msg):
    print(msg)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_status(a):
    root, pid = project_key()
    bundles = list_bundles()
    if a.json:
        print(json.dumps({
            "project": str(root), "project_id": pid,
            "store": str(store_dir()), "worktree": in_worktree(),
            "bundles": bundles,
        }, indent=2))
        return 0

    print(f"project : {root}")
    print(f"id      : {pid}")
    print(f"store   : {store_dir()}")
    if in_worktree():
        print("context : GIT WORKTREE -- sub-spike mode; store keyed to main repo")
    if not bundles:
        print("\nno bundles. `df.py init <topic>` after Phase 0 is framed.")
        return 0

    print(f"\n{'STATE':<14} {'SLUG':<34} {'DISP':<8} {'ARCH':<10} SIZE")
    for b in bundles:
        size = human(dir_size(b["store"])) if a.size else "-"
        tag = b["slug"] + (" [sub]" if b["sub_spike"] else "")
        print(f"{b['state']:<14} {tag:<34} {b['disposition']:<8} {b['archetype']:<10} {size}")

    active = [b for b in bundles if b["state"] in ("FRAMING", "REDUCING", "LOOPING", "HARVESTED")]
    sealed = [b for b in bundles if b["state"] == "SEALED"]
    if active:
        print(f"\n!! {len(active)} unsealed bundle(s). Resume, or abandon before starting new work.")
    if sealed:
        print(f"\n!! {len(sealed)} sealed bundle(s) awaiting escort:")
        for b in sealed:
            print(f"     {b['repo']}{os.sep}acceptance.md")
    return 0


def cmd_init(a):
    slug = f"{today()}-{a.topic.strip().lower().replace(' ', '-')}"
    s, r = store_dir(slug), repo_dir(slug)
    if s.exists():
        die(f"bundle '{slug}' already exists ({bundle_state(slug)})")

    others = [b for b in list_bundles() if b["state"] in ("FRAMING", "REDUCING", "LOOPING", "HARVESTED")]
    if others and not a.force:
        die("an unsealed bundle already exists:\n  " +
            "\n  ".join(f"{b['state']:<12} {b['slug']}" for b in others) +
            "\nresume it, abandon it, or pass --force. Never run two loops at once.")

    sub = in_worktree()
    if sub and branch_dirty() and not a.force:
        die("inside a worktree with uncommitted work. Commit or stash before "
            "creating a bundle here, or pass --force to keep the store half only.")

    for d in ("fixture", "holdout", "expected", "work"):
        (s / d).mkdir(parents=True, exist_ok=True)
    (s / "rejections.jsonl").touch()
    (s / "appendix-hacks.md").write_text(
        f"# Appendix: how it was actually made to work\n\n"
        f"Bundle: {slug}\n\n"
        f"NOT part of the specification. Do not read during design.\n"
        f"Techniques, workarounds, and dead ends only.\n\n", encoding="utf-8")

    root, _ = project_key()
    write_json(s / "meta.json", {
        "slug": slug, "version": VERSION, "created": utcnow(),
        "disposition": a.disposition, "archetype": a.archetype,
        "budget_seconds": a.budget, "nondeterministic": a.nondeterministic,
        "sub_spike": sub, "project_path": str(root),
        "frame": a.frame or "",
    })

    if not (sub and not a.force):
        r.mkdir(parents=True, exist_ok=True)
        write_json(r / "metrics.json", {
            "slug": slug, "version": VERSION, "archetype": a.archetype,
            "nondeterministic": a.nondeterministic,
            "checks": [], "subjective": [],
        })
        _write_check_py(r / "check.py", slug)

    ok(f"bundle    {slug}")
    ok(f"store     {s}")
    ok(f"repo      {r}" + ("   (deferred -- sub-spike on dirty branch)" if sub and not a.force else ""))
    ok(f"state     {bundle_state(slug)}")
    if sub:
        ok("mode      SUB-SPIKE -- escort returns to the current implementation, no /clear")
    ok("\nnext: profile production before reducing. See references/fixture-minimization.md")
    return 0


def cmd_profile(a):
    require(a.slug)
    src = Path(a.source_json)
    if not src.is_file():
        die(f"not a file: {src}")
    data = read_json(src)
    if data is None:
        die(f"not valid JSON: {src}")
    prof = {
        "recorded": utcnow(),
        "source": a.source or "",
        "method": a.method,
        "sampled": a.sampled,
        "inventory": data,
    }
    write_json(store_dir(a.slug) / "profile.json", prof)
    ok(f"profile recorded ({len(data) if isinstance(data, (list, dict)) else '?'} dimensions)")
    ok(f"state   {bundle_state(a.slug)}")
    if a.sampled:
        ok("note    sampled profile -- confidence claim is reduced; record this in coverage.md")
    return 0


def cmd_log(a):
    require(a.slug)
    p = store_dir(a.slug) / "rejections.jsonl"
    prior = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
    entry = {
        "iter": a.iter if a.iter is not None else len(prior) + 1,
        "at": utcnow(), "verdict": a.verdict,
        "observation": a.observation, "locus": a.locus or "",
        "check_id": None,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    ok(f"logged iteration {entry['iter']} ({a.verdict})")
    if a.verdict == "reject":
        ok("REMINDER: when this gets fixed, write its check immediately and validate it")
        ok("          against THIS iteration's output. Do not defer to the end.")
    return 0


def cmd_check_add(a):
    require(a.slug)
    mp = repo_dir(a.slug) / "metrics.json"
    m = read_json(mp)
    if m is None:
        die(f"no metrics.json at {mp} (sub-spike with deferred repo half?)")
    if any(c["id"] == a.id for c in m["checks"]):
        die(f"check '{a.id}' already exists")
    if not a.subjective and not a.validated_against:
        die("--validated-against is required: a check that was never run against a real\n"
            "failure is decoration. Run it against the output that provoked the rejection.")

    entry = {
        "id": a.id, "mode": a.mode, "desc": a.desc,
        "assert": a.assertion, "negative": a.negative,
        "from_rejection": a.from_rejection,
        "validated_against": a.validated_against or "",
        "added": utcnow(),
    }
    if a.subjective:
        entry["review_artifact"] = a.review_artifact or ""
        m["subjective"].append(entry)
    else:
        m["checks"].append(entry)
    write_json(mp, m)

    if a.from_rejection is not None:
        rp = store_dir(a.slug) / "rejections.jsonl"
        if rp.exists():
            lines = []
            for l in rp.read_text(encoding="utf-8").splitlines():
                if not l.strip():
                    continue
                e = json.loads(l)
                if e.get("iter") == a.from_rejection and not e.get("check_id"):
                    e["check_id"] = a.id
                lines.append(json.dumps(e))
            rp.write_text("\n".join(lines) + "\n", encoding="utf-8")

    kind = "subjective criterion" if a.subjective else ("negative check" if a.negative else "check")
    ok(f"{kind} '{a.id}' added  ({len(m['checks'])} gated, {len(m['subjective'])} subjective)")
    return 0


def cmd_freeze(a):
    require(a.slug)
    src = Path(a.candidate)
    if not src.exists():
        die(f"not found: {src}")
    dst = store_dir(a.slug) / "expected"
    dst.mkdir(parents=True, exist_ok=True)
    files = []
    if src.is_file():
        shutil.copy2(src, dst / src.name)
        files = [dst / src.name]
    else:
        for f in src.rglob("*"):
            if f.is_file():
                t = dst / f.relative_to(src)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
                files.append(t)
    man = {"frozen": utcnow(), "source": str(src), "command": a.command or "", "files": []}
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        man["files"].append({"path": str(f.relative_to(dst)), "sha256": h, "bytes": f.stat().st_size})
    write_json(store_dir(a.slug) / "expected" / "MANIFEST.json", man)
    ok(f"froze {len(files)} file(s) as approved reference")
    return 0


def cmd_holdout(a):
    require(a.slug)
    write_json(store_dir(a.slug) / "holdout.json", {
        "run": utcnow(), "result": a.result, "notes": a.notes or "",
        "source": a.source or "", "consumed": True,
    })
    ok(f"holdout recorded: {a.result.upper()}")
    if a.result == "fail":
        ok("the fixture was unrepresentative. Return to the loop, fix, then cut a NEW")
        ok("holdout -- this one is consumed and has no evidentiary value now.")
    return 0


def cmd_seal(a):
    st = require(a.slug)
    if st in ("SEALED", "CONSUMED"):
        die(f"already {st}")
    r, s = repo_dir(a.slug), store_dir(a.slug)
    m = read_json(r / "metrics.json")
    if m is None:
        die("no metrics.json -- sub-spike repo half was deferred; re-run init once the branch is clean")

    problems = []
    if not m["checks"]:
        problems.append("no checks recorded")
    unvalidated = [c["id"] for c in m["checks"] if not c.get("validated_against")]
    if unvalidated:
        problems.append("checks never validated against a real failure: " + ", ".join(unvalidated))
    if not any(c.get("negative") for c in m["checks"]):
        problems.append("no negative check -- the gate would pass an implementation that "
                        "labels/emits everything")
    if not (s / "holdout.json").exists():
        problems.append("holdout never run")
    else:
        h = read_json(s / "holdout.json", {})
        if h.get("result") == "fail":
            problems.append("holdout FAILED -- fixture is unrepresentative; fix and cut a new one")
    if not (s / "profile.json").exists():
        problems.append("no profile recorded -- coverage cannot be computed, unknown-unknowns "
                        "stay unknown (use --no-profile only if profiling was impossible)")
    if not (r / "coverage.md").exists():
        problems.append("no coverage.md")
    if not (r / "acceptance.md").exists():
        problems.append("no acceptance.md -- write it from references/acceptance-template.md")

    if a.no_profile:
        problems = [p for p in problems if not p.startswith("no profile")]
    if problems:
        print("dirty-fix: cannot seal:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(2)

    leaks = _scan_leaks(r / "acceptance.md")
    if leaks and not a.allow_leaks:
        print("dirty-fix: acceptance.md may leak implementation guidance:", file=sys.stderr)
        for l in leaks:
            print(f"  - {l}", file=sys.stderr)
        print("  fix, or pass --allow-leaks if these are genuinely format/interface names.",
              file=sys.stderr)
        sys.exit(2)

    write_json(s / "SEALED", {
        "at": utcnow(), "checks": len(m["checks"]),
        "subjective": len(m["subjective"]),
        "negative": [c["id"] for c in m["checks"] if c.get("negative")],
    })
    ok(f"SEALED  {a.slug}")
    ok(f"  spec  {r / 'acceptance.md'}")
    ok(f"  gate  {r / 'check.py'}  ({len(m['checks'])} gated, {len(m['subjective'])} subjective)")
    meta = read_json(s / "meta.json", {})
    if meta.get("disposition") == "answer":
        ok("\ndisposition is 'answer' -- no escort. The output is the deliverable.")
    elif meta.get("sub_spike"):
        ok("\nSUB-SPIKE: return to the implementation in progress. Do NOT /clear.")
    else:
        ok("\nnext: verify the destination pipeline is installed for this project, then")
        ok("      tell the human: \"The bundle is verified. Type /clear -- I'll pick it up")
        ok("      from the other side.\"")
    return 0


LEAK_HINTS = (
    "algorithm", "library", "import ", "pip install", "npm install",
    "the approach is", "it works by", "implemented using", "we used",
    "def ", "function ", "class ",
)


def _scan_leaks(p):
    try:
        text = Path(p).read_text(encoding="utf-8")
    except OSError:
        return []
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower().strip()
        if low.startswith("|") or low.startswith("<!--"):
            continue
        for h in LEAK_HINTS:
            if h in low:
                found.append(f"line {i}: {line.strip()[:80]}")
                break
    return found


def cmd_consume(a):
    st = require(a.slug)
    if st != "SEALED":
        die(f"state is {st}; only SEALED bundles can be consumed")
    s = store_dir(a.slug)
    (s / "CONSUMED").write_text(utcnow() + "\n", encoding="utf-8")
    work = s / "work"
    n = 0
    if work.is_dir():
        n = dir_size(work)
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(exist_ok=True)
    ok(f"consumed. dirty code deleted ({human(n)} reclaimed) -- leak risk is now zero.")
    ok("fixture, holdout, expected, profile and rejections retained so the gate can be")
    ok("re-run as a regression test.")
    return 0


def cmd_abandon(a):
    require(a.slug)
    marker = "NOT_REDUCIBLE" if a.not_reducible else "ABANDONED"
    (store_dir(a.slug) / marker).write_text(
        json.dumps({"at": utcnow(), "reason": a.reason}, indent=2) + "\n", encoding="utf-8")
    ok(f"{marker}: {a.slug}")
    if a.not_reducible:
        ok("record what proving it large would require -- that is the deliverable here.")
    return 0


def cmd_gc(a):
    freed = 0
    acted = []
    for b in list_bundles():
        s = Path(b["store"])
        work = s / "work"
        if b["state"] in ("CONSUMED", "ABANDONED", "NOT_REDUCIBLE") and nonempty_dir(work):
            sz = dir_size(work)
            acted.append((b["slug"], b["state"], sz))
            freed += sz
            if not a.dry_run:
                shutil.rmtree(work, ignore_errors=True)
                work.mkdir(exist_ok=True)
    if not acted:
        ok("nothing to collect. (gc only ever removes dirty code from terminal bundles;")
        ok("fixtures are never deleted without you asking.)")
        return 0
    for slug, st, sz in acted:
        ok(f"{'would remove' if a.dry_run else 'removed'}  work/ of {slug} [{st}]  {human(sz)}")
    ok(f"{'would reclaim' if a.dry_run else 'reclaimed'} {human(freed)}")
    return 0


def cmd_export(a):
    require(a.slug)
    out = Path(a.out or f"{a.slug}.dirty-fix.zip").resolve()
    s, r = store_dir(a.slug), repo_dir(a.slug)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BUNDLE.json", json.dumps({
            "slug": a.slug, "version": VERSION, "exported": utcnow(),
            "layout": {"repo": "repo/", "store": "store/"},
        }, indent=2))
        for base, prefix in ((r, "repo"), (s, "store")):
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(base)
                if not a.with_dirty and rel.parts and rel.parts[0] == "work":
                    continue
                z.write(f, f"{prefix}/{rel.as_posix()}")
    ok(f"exported {out}  ({human(out.stat().st_size)})")
    if not a.with_dirty:
        ok("dirty code excluded. --with-dirty to include it (rarely correct).")
    return 0


def cmd_import(a):
    src = Path(a.zip)
    if not src.is_file():
        die(f"not found: {src}")
    with zipfile.ZipFile(src) as z:
        meta = json.loads(z.read("BUNDLE.json"))
        slug = a.slug or meta["slug"]
        s, r = store_dir(slug), repo_dir(slug)
        if s.exists() and not a.force:
            die(f"bundle '{slug}' already exists here; --force to overwrite")
        for n in z.namelist():
            if n == "BUNDLE.json" or n.endswith("/"):
                continue
            top, _, rest = n.partition("/")
            base = r if top == "repo" else s
            t = base / rest
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(z.read(n))
    ok(f"imported {slug} -> {bundle_state(slug)}")
    return 0


def cmd_doctor(a):
    root, pid = project_key()
    print(f"version       {VERSION}")
    print(f"python        {sys.version.split()[0]}")
    print(f"project       {root}")
    print(f"project id    {pid}")
    print(f"store         {store_dir()}  {'(exists)' if store_dir().is_dir() else '(will be created)'}")
    print(f"repo half     {repo_dir()}")
    print(f"git           {'yes' if main_repo_root() else 'NO -- keyed on cwd'}")
    print(f"worktree      {'YES -- sub-spike mode' if in_worktree() else 'no'}")
    print(f"DIRTY_FIX_HOME{'  ' + os.environ['DIRTY_FIX_HOME'] if 'DIRTY_FIX_HOME' in os.environ else '  (unset)'}")
    st = store_root()
    if st.is_dir():
        print(f"store size    {human(dir_size(st))} across {len(list(st.iterdir()))} project(s)")
    hp = Path.home() / ".claude" / "settings.json"
    s = read_json(hp, {}) or {}
    hooks = json.dumps(s.get("hooks", {}))
    print(f"escort hook   {'registered' if 'dirty-fix' in hooks or 'dirty_fix' in hooks else 'NOT registered -- run: df.py install-hook'}")
    return 0


# --------------------------------------------------------------------------
# hook installation
# --------------------------------------------------------------------------

def cmd_install_hook(a):
    skill = Path(__file__).resolve().parent.parent
    hook = skill / "hooks" / "session_start.py"
    if not hook.is_file():
        die(f"hook script missing: {hook}")

    settings = Path(a.settings).expanduser() if a.settings else Path.home() / ".claude" / "settings.json"
    data = read_json(settings, {}) if settings.exists() else {}
    if data is None:
        die(f"{settings} is not valid JSON -- refusing to touch it")

    cmd = f'python "{hook}"'
    entry = {
        "matcher": "startup|clear|compact",
        "hooks": [{"type": "command", "command": cmd, "async": False}],
    }
    hooks = data.setdefault("hooks", {})
    ss = hooks.setdefault("SessionStart", [])
    for e in ss:
        if "session_start.py" in json.dumps(e) and "dirty-fix" in json.dumps(e):
            ok("already registered.")
            return 0
    ss.append(entry)

    if a.dry_run:
        print(json.dumps({"hooks": {"SessionStart": ss}}, indent=2))
        ok("\n(dry run -- nothing written)")
        return 0

    if settings.exists():
        bak = settings.with_suffix(f".json.bak-dirtyfix-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(settings, bak)
        ok(f"backup   {bak}")
    payload = json.dumps(data, indent=2) + "\n"
    json.loads(payload)  # validate before writing
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(payload, encoding="utf-8")
    ok(f"registered escort hook in {settings}")
    ok("takes effect in new sessions (startup / clear / compact).")
    return 0


# --------------------------------------------------------------------------
# generated gate
# --------------------------------------------------------------------------

CHECK_PY = '''#!/usr/bin/env python3
"""Acceptance gate for {slug}.

Generated by dirty-fix. Runs standalone -- the skill does not need to be installed.
Stdlib only unless comparators.py (beside this file) declares otherwise.

    python check.py --candidate <path>          exit 0 = acceptable
    python check.py --selfcheck                 verify env + gate sanity
    python check.py --fixture <path> --candidate <path>

This never claims the output is CORRECT. It claims it matches an approved
reference within stated tolerance.
"""
import argparse, importlib.util, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
METRICS = HERE / "metrics.json"


def load_comparators():
    """Optional domain logic, copied into the bundle at harvest time."""
    p = HERE / "comparators.py"
    if not p.is_file():
        return None
    spec = importlib.util.spec_from_file_location("comparators", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description="acceptance gate for {slug}")
    ap.add_argument("--candidate", help="path to the output under test")
    ap.add_argument("--fixture", help="override fixture (gate is fixture-parameterized)")
    ap.add_argument("--expected", help="override frozen reference")
    ap.add_argument("--strict", action="store_true", help="fail on known PARTIAL gaps too")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    m = json.loads(METRICS.read_text(encoding="utf-8"))
    checks, subjective = m.get("checks", []), m.get("subjective", [])
    comp = load_comparators()

    if a.selfcheck:
        print(f"gate       {{m.get('slug')}}")
        print(f"checks     {{len(checks)}} gated, {{len(subjective)}} subjective")
        print(f"comparators{{' loaded' if comp else ' none (generic modes only)'}}")
        missing = [c["id"] for c in checks if not c.get("validated_against")]
        print(f"validated  {{'all' if not missing else 'MISSING: ' + ', '.join(missing)}}")
        neg = [c["id"] for c in checks if c.get("negative")]
        print(f"negative   {{', '.join(neg) if neg else 'NONE -- gate is one-sided'}}")
        return 0 if checks and not missing and neg else 1

    if not a.candidate:
        ap.error("--candidate is required")

    results, failed = [], 0
    for c in checks:
        fn = getattr(comp, f"check_{{c['id']}}", None) if comp else None
        if fn is None:
            results.append((c["id"], "SKIP", "no comparator implemented"))
            continue
        try:
            passed, detail = fn(candidate=Path(a.candidate),
                                fixture=Path(a.fixture) if a.fixture else None,
                                expected=Path(a.expected) if a.expected else None)
        except Exception as e:  # a crashing check is a failing check
            passed, detail = False, f"{{type(e).__name__}}: {{e}}"
        results.append((c["id"], "PASS" if passed else "FAIL", detail))
        if not passed:
            failed += 1

    skipped = sum(1 for _, s, _ in results if s == "SKIP")
    if a.json:
        print(json.dumps({{"slug": m.get("slug"), "failed": failed, "skipped": skipped,
                          "results": [{{"id": i, "status": s, "detail": d}} for i, s, d in results],
                          "subjective": [s["id"] for s in subjective]}}, indent=2))
    else:
        w = max([len(i) for i, _, _ in results] + [4])
        for i, s, d in results:
            print(f"{{s:<5}} {{i:<{{w}}}}  {{d}}")
        if subjective:
            print("\\nrequires human sign-off (not gated):")
            for s in subjective:
                print(f"      {{s['id']}}  {{s.get('desc','')}}")
        print(f"\\n{{len(results) - failed - skipped}} passed, {{failed}} failed, {{skipped}} skipped")
        if skipped:
            print("\\nA check with no comparator is an unmet requirement, not a pass.")

    # skipped counts as failure: a gate that cannot evaluate a check has not
    # cleared it, and exiting 0 here would launder false confidence.
    return 1 if (failed or skipped) else 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _write_check_py(path, slug):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CHECK_PY.format(slug=slug), encoding="utf-8")
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass


# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="df.py", description="dirty-fix bundle manager")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("status", help="what is happening in this project (ALWAYS run first)")
    q.add_argument("--size", action="store_true")
    q.add_argument("--json", action="store_true")
    q.set_defaults(fn=cmd_status)

    q = sub.add_parser("init", help="create a bundle after Phase 0 is framed")
    q.add_argument("topic")
    q.add_argument("--disposition", choices=DISPOSITIONS, required=True)
    q.add_argument("--archetype", default="transform")
    q.add_argument("--budget", type=int, default=90, help="iteration budget, seconds")
    q.add_argument("--nondeterministic", action="store_true")
    q.add_argument("--frame", help="the one sentence: this input -> this output")
    q.add_argument("--force", action="store_true")
    q.set_defaults(fn=cmd_init)

    q = sub.add_parser("profile", help="record the production profile (BEFORE reducing)")
    q.add_argument("slug")
    q.add_argument("source_json", help="JSON file holding the inventory")
    q.add_argument("--source", help="what was profiled")
    q.add_argument("--method", default="full-scan")
    q.add_argument("--sampled", action="store_true")
    q.set_defaults(fn=cmd_profile)

    q = sub.add_parser("log", help="log a human verdict on an iteration")
    q.add_argument("slug")
    q.add_argument("--verdict", choices=("accept", "reject"), required=True)
    q.add_argument("--observation", required=True)
    q.add_argument("--locus")
    q.add_argument("--iter", type=int)
    q.set_defaults(fn=cmd_log)

    q = sub.add_parser("check-add", help="record a check the moment its fix lands")
    q.add_argument("slug")
    q.add_argument("--id", required=True)
    q.add_argument("--mode", choices=MODES, default="invariant")
    q.add_argument("--desc", required=True)
    q.add_argument("--assert", dest="assertion", default="")
    q.add_argument("--negative", action="store_true", help="asserts what must NOT appear")
    q.add_argument("--from-rejection", type=int)
    q.add_argument("--validated-against", help="output that this check must FAIL on")
    q.add_argument("--subjective", action="store_true", help="human sign-off, not gated")
    q.add_argument("--review-artifact", help="what check.py emits to make review fast")
    q.set_defaults(fn=cmd_check_add)

    q = sub.add_parser("freeze", help="freeze the approved output as reference")
    q.add_argument("slug")
    q.add_argument("candidate")
    q.add_argument("--command", help="exact dirty command that produced it")
    q.set_defaults(fn=cmd_freeze)

    q = sub.add_parser("holdout", help="record the single holdout run")
    q.add_argument("slug")
    q.add_argument("--result", choices=("pass", "fail"), required=True)
    q.add_argument("--notes")
    q.add_argument("--source")
    q.set_defaults(fn=cmd_holdout)

    q = sub.add_parser("seal", help="validate the gate and seal the bundle")
    q.add_argument("slug")
    q.add_argument("--no-profile", action="store_true", help="profiling was impossible")
    q.add_argument("--allow-leaks", action="store_true")
    q.set_defaults(fn=cmd_seal)

    q = sub.add_parser("consume", help="mark escorted; deletes the dirty code")
    q.add_argument("slug")
    q.set_defaults(fn=cmd_consume)

    q = sub.add_parser("abandon", help="terminal exit")
    q.add_argument("slug")
    q.add_argument("--reason", required=True)
    q.add_argument("--not-reducible", action="store_true")
    q.set_defaults(fn=cmd_abandon)

    q = sub.add_parser("gc", help="remove dirty code from terminal bundles")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(fn=cmd_gc)

    q = sub.add_parser("export", help="zip a portable bundle")
    q.add_argument("slug")
    q.add_argument("--out")
    q.add_argument("--with-dirty", action="store_true")
    q.set_defaults(fn=cmd_export)

    q = sub.add_parser("import", help="import a bundle zip")
    q.add_argument("zip")
    q.add_argument("--slug")
    q.add_argument("--force", action="store_true")
    q.set_defaults(fn=cmd_import)

    q = sub.add_parser("doctor", help="environment and wiring check")
    q.set_defaults(fn=cmd_doctor)

    q = sub.add_parser("install-hook", help="register the escort SessionStart hook")
    q.add_argument("--settings")
    q.add_argument("--dry-run", action="store_true")
    q.set_defaults(fn=cmd_install_hook)

    return p


def main():
    a = build_parser().parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

# Verification recipes — how to write a "stated check" for common task types

The stated check is the literal command that proves convergence. Picking the right one is half the battle.

## Test suites

| Language / framework | Recipe |
|---|---|
| Python (pytest) | `pytest tests/path -x --tb=short` exits 0 |
| Python (unittest) | `python -m unittest discover -s tests -p "test_*.py"` exits 0 |
| Node (jest) | `npm test -- --ci` exits 0 |
| Node (mocha) | `npm test` exits 0 |
| Go | `go test ./...` exits 0 |
| Rust | `cargo test --quiet` exits 0 |
| Ruby (RSpec) | `bundle exec rspec --fail-fast` exits 0 |

**Pattern:** add `-x` / `--fail-fast` so the evaluator sees the failure quickly. Use `--tb=short` (or equivalent) to shorten the traceback so it fits in the transcript.

## Build / compile

| Toolchain | Recipe |
|---|---|
| TypeScript | `tsc --noEmit` exits 0 (type check only) or `npm run build` exits 0 |
| Webpack/Vite | `npm run build` exits 0 |
| Python wheel | `python -m build` exits 0 AND `dist/*.whl` exists |
| Go binary | `go build -o /tmp/x ./cmd/...` exits 0 |
| Rust release | `cargo build --release` exits 0 |
| Docker | `docker build -t local .` exits 0 |

## Lint / format / quality

| Tool | Recipe |
|---|---|
| ESLint | `npm run lint -- --max-warnings 0` exits 0 |
| Prettier | `npx prettier --check .` exits 0 |
| Ruff (Python) | `ruff check .` exits 0 |
| Black (Python) | `black --check .` exits 0 |
| mypy | `mypy --strict src/` exits 0 |
| Pylint | `pylint src/ --fail-under 9.0` exits 0 |
| interrogate (docstring coverage) | `interrogate -i src/ --fail-under 100` exits 0 |

## File existence + schema

| Goal type | Recipe |
|---|---|
| File X exists | `test -f path/to/file` exits 0 (POSIX); `[ -f "path" ]` on bash |
| JSON has schema | `python -c "import json,jsonschema; jsonschema.validate(json.load(open('a.json')), json.load(open('schema.json')))"` exits 0 |
| All rows in JSON list have non-null field X | `python -c "import json; d=json.load(open('a.json')); n=[r for r in d if r.get('X') is None]; assert len(n)==0, f'{len(n)} null'"` |
| File line count > N | `awk 'END {exit !(NR>100)}' file.txt` |
| File matches regex | `grep -E "^pattern" file && echo OK` |

## Git state

| Goal type | Recipe |
|---|---|
| No staged changes | `test -z "$(git diff --cached)"` |
| All changes committed | `test -z "$(git status --porcelain)"` |
| Branch matches main + N commits | `git rev-list --count main..HEAD` returns expected N |
| PR has rebase against main | `git merge-base --is-ancestor main HEAD` exits 0 |
| No merge conflicts in tree | `git ls-files -u | wc -l` returns 0 |

## Database state

| Goal type | Recipe |
|---|---|
| Postgres row count | `psql -d X -tc "SELECT COUNT(*) FROM users WHERE Y IS NULL;" | xargs test 0 -eq` |
| MySQL column non-null | `mysql -e "SELECT COUNT(*) FROM users WHERE y IS NULL" -BNs db | xargs test 0 -eq` |
| SQLite migration ran | `sqlite3 db.sqlite "SELECT 1 FROM schema_migrations WHERE version='X'"` returns 1 |

## Background processes / services

| Goal type | Recipe |
|---|---|
| HTTP endpoint returns 200 | `curl -fsS http://localhost:8080/health` exits 0 |
| Docker container running | `docker ps --filter "name=X" --format "{{.Status}}" | grep -q Up` |
| Process listening on port | `nc -z localhost 8080` |

## Custom verification command

For tasks where no single off-the-shelf tool checks the condition, write a small Python script:

```python
# verify.py
import sys, json
data = json.load(open('output.json'))
# whatever specific assertion the task needs
nulls = [r for r in data if r.get('source_type') is None]
print(f"total={len(data)}, null={len(nulls)}")
assert len(data) > 0 and len(nulls) == 0
```

Then the /goal references it: `python verify.py` exits 0.

This is the pattern used by the trailquipt lineage audit.

## Anti-patterns to avoid

| Bad recipe | Why bad |
|---|---|
| "the tests pass" | implicit — evaluator has to guess command |
| `pytest` (no path, no -x) | runs everything, may pass for wrong reason |
| `make` (vague) | depends on what `make` does in this repo |
| "compilation succeeds" | not a command |
| "review the code" | not a verification |
| `grep "TODO" .` returns 0 results | too strict — meaningful TODOs may live forever |

## Combining multiple checks

If the goal genuinely has multiple necessary conditions, list them all as a sequence in the VERIFIABLE END STATE section. Use `&&` to make a single composite command that exits 0 only if ALL pass:

```
Verify with:
  pytest -x && npm test && grep -L "TODO" src/api/*.py | wc -l | xargs test 0 -eq
```

But prefer ONE main check + the others as constraints, since a single composite is harder to debug when it fails.

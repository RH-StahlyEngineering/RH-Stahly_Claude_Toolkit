# Staging pof.json into the dev-browser sandbox

**Problem:** dev-browser scripts run in a QuickJS sandbox, NOT Node.js. They have no `fs`, no `import()`, no arbitrary filesystem access. The sandbox only exposes `readFile(name)` / `writeFile(name, data)` against dev-browser's own temp dir. A pof.json sitting on the network share at `\\Stahly\...\pof.json` is NOT directly readable from a dev-browser script.

**Wrong (will fail silently):**

```bash
dev-browser --connect --timeout 10 <<'EOF'
const fs = await import('fs/promises');     # No `import()` in QuickJS
const pof = JSON.parse(await fs.readFile("\\\\Stahly\\...\\pof.json", "utf8"));
await writeFile("pof.json", JSON.stringify({ pof }));
EOF
```

This was the pattern in an early SKILL.md draft. It silently fails (exit 1, empty output) because `import` is undefined in QuickJS. `fs` doesn't exist.

**Right:** read pof.json on the HOST side, embed its contents inside the JS script via preprocessing, then run the embedded-payload script through `dev-browser run`. The script uses only the in-sandbox `writeFile` primitive.

## PowerShell preprocess

```powershell
$pof = Get-Content "\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\<YYYY>\<City>\<NNN>\pof.json" -Raw
$wrapped = '{"pof":' + $pof + '}'
$escaped = $wrapped -replace '\\','\\' -replace '"','\"' -replace "`r",'\r' -replace "`n",'\n'
$script = "const payload = `"$escaped`";`nawait writeFile(`"pof.json`", payload);`nconsole.log(`"staged ok, bytes:`", payload.length);"
Set-Content "$env:TEMP\stage_pof.js" $script -NoNewline
dev-browser --connect --timeout 10 run "$env:TEMP\stage_pof.js"
```

## Python preprocess (equivalent)

```bash
python3 - <<'PY' > "$TEMP/stage_pof.js"
import json
with open(r"\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\<YYYY>\<City>\<NNN>\pof.json") as f:
    pof = json.load(f)
payload = json.dumps({"pof": pof})
print('const payload =', json.dumps(payload) + ';')
print('await writeFile("pof.json", payload);')
print('console.log("staged ok, bytes:", payload.length);')
PY
dev-browser --connect --timeout 10 run "$TEMP/stage_pof.js"
```

## Why it works

Once `writeFile("pof.json", payload)` runs inside the sandbox, dev-browser's temp dir contains the file. Subsequent `dev-browser run fill-pof.js` (which does `await readFile("pof.json")`) finds it there. The temp dir persists across `dev-browser run` invocations within the same session.

## Smoke test

After staging, confirm the file is readable:

```bash
dev-browser --connect --timeout 5 <<'EOF'
const raw = await readFile("pof.json");
const parsed = JSON.parse(raw);
console.log("keys:", Object.keys(parsed.pof).length);
EOF
```

If this prints a positive key count, staging succeeded and fill-pof.js will work. If it prints "ReferenceError: readFile is not defined" or similar, dev-browser is broken — check Phase 0 prereqs in SKILL.md.

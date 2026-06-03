# dev-browser sandbox + CDP quirks (catalogued)

`dev-browser` looks like Puppeteer/Playwright but ISN'T — scripts run in a **QuickJS WASM sandbox** with restricted globals. CDP semantics also differ from standard browser scripts. This doc catalogues the differences that bit us during pof skill development.

## Sandbox: no Node.js

| Want | Available? | Use this instead |
|---|---|---|
| `require('fs')` / `import('fs/promises')` | No | `readFile(name)` / `writeFile(name, data)` (temp dir only) |
| `process.env` / `process.argv` | No | Embed config in the script via preprocessing (see `staging-pattern.md`) |
| `fetch` / `WebSocket` | No | Drive via the browser instead (`page.evaluate(() => fetch(...))`) |
| Arbitrary host paths | No | Stage files into dev-browser temp dir; access via `readFile("<name>")` |
| Network requests outside browser | No | All I/O goes through the page DOM or `browser.*` |
| `globalThis.crypto`, `Buffer`, etc. | Limited | Stick to plain JS: `String`, `Array`, `JSON`, `Math` |

## `page.evaluate` API differences

**Single arg only.** Puppeteer/Playwright allow `page.evaluate(fn, a, b, c)` — dev-browser does NOT. Pass an object instead:

```js
// WRONG — dev-browser throws "assertMaxArguments" at the second arg
await page.evaluate((id, value) => { /* ... */ }, "input_4", "Hello");

// RIGHT — pack into one object
await page.evaluate(({id, value}) => { /* ... */ }, {id: "input_4", value: "Hello"});
```

Return values must be JSON-serializable (no DOM nodes, no functions, no `Map`/`Set`).

## Cross-origin iframes ARE scriptable

Standard browser JS can't reach into a cross-origin iframe due to same-origin policy. **CDP-driven evaluate bypasses this.** `page.frames()` returns ALL frames on the page including cross-origin ones; `frame.evaluate(...)` works on each:

```js
const frames = await page.frames();
for (const f of frames) {
  let url;
  try { url = typeof f.url === 'function' ? await f.url() : f.url; } catch { url = ''; }
  if (url.includes('widgets.jotform.io')) {
    // Direct DOM access inside the cross-origin widget
    const result = await f.evaluate(() => document.querySelectorAll('input[type=text]').length);
  }
}
```

We use this for the JotForm Configurable List widgets (Additional Team Scheduling rows) inside the Mosaic chained form. See `scripts/fill-mosaic.js` for the working pattern.

## Tab discovery

`browser.listPages()` returns ALL Chrome tabs across ALL profiles attached via CDP. Filter by URL substring; don't assume the JotForm tab is first or last:

```js
const tabs = await browser.listPages();
const jot = tabs.find(t => (t.url||'').includes('form.jotform.com'));
```

Use `form.jotform.com` (not the specific form ID) as the filter so the same code survives form chaining — e.g., the POF (form `232545214343146`) chains to Mosaic (form `231225238538051`) on submit, and the tab URL changes.

## Hidden buttons are still clickable

Elements with `offsetParent == null` (i.e., `display:none` or `visibility:hidden`) often filter out of visibility checks but **`.click()` still fires the handler**. JotForm's Configurable List widget has remove-row "x" buttons that are hidden until row hover; calling `.click()` on them works regardless. Don't gate row-removal logic on `b.offsetParent != null`.

```js
// Force-click hidden remove buttons inside the widget
await widget.evaluate(() => {
  Array.from(document.querySelectorAll('[class*="remove"]'))
    .forEach(el => { try { el.click(); } catch {} });
});
```

## CLI flags

| Flag | Notes |
|---|---|
| `--help` | Use this to confirm install. `--version` is NOT a valid flag (returns error). |
| `--connect [URL]` | Attach to existing CDP target. URL defaults to `http://localhost:9222`. |
| `--timeout <sec>` | Per-script timeout. Use generously (>= 15s) for any script that does multiple page interactions. |
| `run <file>` | Read script from a file path. Better than heredoc when the script contains backslashes (Windows paths). |
| `<<'EOF' ... EOF` | Heredoc form. Single-quoted EOF tag prevents shell variable expansion in the script body. |

## Error patterns

| Error | Cause | Fix |
|---|---|---|
| `assertMaxArguments` at line ~N of `user-script.js` | `page.evaluate(fn, a, b)` with multiple args | Wrap args in a single object |
| Empty output + exit 1 | Script ran but a runtime error happened during JSON serialization OR a top-level error swallowed | Add `console.log` statements throughout to bisect; check `tabs.find()` filter |
| `TypeError: Cannot read property 'X' of undefined` from `getPage(undefined)` | Tab filter didn't match (e.g., form URL changed mid-session) | Broaden tab filter (`includes('form.jotform.com')` instead of full ID) |
| `not found` in fill output for hidden fields like `input_456` | Conditional field that needs its parent set first (e.g., `is_new_client = Yes` shows `client_type`) | Order fields so parents fill before dependents |

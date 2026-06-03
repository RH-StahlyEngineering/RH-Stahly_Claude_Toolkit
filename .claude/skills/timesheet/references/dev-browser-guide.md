# dev-browser Quick Reference for Timesheet Skill

## Setup
- Install: `npm i -g dev-browser` (already installed)
- Enable Chrome remote debugging: `chrome://inspect/#remote-debugging`
- Skill installed at `~/.claude/skills/dev-browser/SKILL.md`

## Connection
```bash
# Auto-discover Chrome with debugging enabled
dev-browser --connect <<'EOF'
const tabs = await browser.listPages();
console.log(JSON.stringify(tabs, null, 2));
EOF
```

## Key API for Timesheet Entry

### List tabs to find Deltek
```javascript
const tabs = await browser.listPages();
// Returns [{id, url, title, name}]
// Find Deltek tab by URL containing "deltekfirst.com"
```

### Connect to existing Deltek tab
```javascript
const page = await browser.getPage(tabId); // use targetId from listPages()
```

### Direct DOM manipulation (fastest approach)
```javascript
// Execute JS directly in Deltek's page context
await page.evaluate(() => {
    // Find elements, set values, trigger events
    const input = document.querySelector('selector');
    input.value = '8.0';
    input.dispatchEvent(new Event('change', { bubbles: true }));
});
```

### Playwright selectors (more reliable)
```javascript
await page.click('selector');
await page.fill('selector', '8.0');
await page.locator('text=Save').click();
```

### AI snapshot for element discovery
```javascript
const result = await page.snapshotForAI();
console.log(result.full);
// Returns accessible tree — use to find selectors for Kendo grid cells
```

### Screenshots for verification
```javascript
const buf = await page.screenshot();
const path = await saveScreenshot(buf, "timesheet-verify.png");
console.log(path);
```

## Script Patterns for Timesheet

### Enter a single cell value
```javascript
// 1. Click the project row
// 2. Click the day cell
// 3. Fill REGULAR input
// 4. Fill Comment
// 5. Click Save
```

### Batch enter multiple entries
```javascript
const entries = JSON.parse(await readFile("entries.json"));
for (const entry of entries) {
    // find row, click day, enter hours + comment, save
}
const results = { success: true, entered: entries.length };
console.log(JSON.stringify(results));
```

## Key Differences from Chrome MCP
- Scripts run as Playwright code — full page API, no find/click round-trips
- page.evaluate() runs JS directly in page context — instant DOM manipulation
- No screenshots needed for interaction — only for verification
- Named pages persist between script runs
- --timeout flag prevents hangs (default 30s, increase for batch operations)

## Gotchas
- Inside page.evaluate(), write plain JavaScript only (no TypeScript)
- QuickJS sandbox: no require/import, no fetch, no fs access
- File I/O restricted to ~/.dev-browser/tmp/
- Use --timeout 60 or higher for batch operations
- Kendo UI grids need event dispatch (change, mousedown/mouseup/click) not just value setting

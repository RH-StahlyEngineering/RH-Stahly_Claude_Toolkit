// add-line.js — Add a project row to the Deltek timesheet via the +Add Line workflow.
// Usage:
//   1. Write { project_search, phase_text, task_text? } to ~/.dev-browser/tmp/add-line.json
//      Multiple rows: { rows: [ {...}, {...} ] }
//   2. dev-browser --connect --timeout 60 run add-line.js
//
// project_search: substring to match in the Project pane (e.g. "3963" or "Cushing")
// phase_text:     substring to match in the Phase pane (e.g. "Topo Survey", "Engineering Survey")
// task_text:      (optional) substring to match in the Task pane

const tabs = await browser.listPages();
const deltekTab = tabs.find(t => t.url && t.url.includes('deltekfirst.com'));
if (!deltekTab) {
  console.log(JSON.stringify({ success: false, error: "no_deltek_tab" }));
} else {
  const page = await browser.getPage(deltekTab.id);
  const data = JSON.parse(await readFile("add-line.json"));
  const rows = data.rows || [data];
  const results = [];

  // Helper to dismiss any unexpected dialogs (especially the help dialog hazard)
  async function dismissUnexpectedDialogs() {
    await page.evaluate(() => {
      // Help dialogs have ui-dialog-titlebar-close
      const helpClose = document.querySelector('.ui-dialog-titlebar-close');
      if (helpClose && helpClose.offsetParent !== null) helpClose.click();
    });
    await page.waitForTimeout(500);
  }

  for (const row of rows) {
    try {
      await dismissUnexpectedDialogs();

      // 0. Make sure no cell-editor popup is open from a prior entry — it
      // blocks +Add Line silently.
      await page.evaluate(() => {
        const r = document.getElementById('regHrs');
        if (r && r.offsetParent !== null) {
          const banner = document.querySelector('.gridHeader');
          if (banner) banner.click();
        }
      });
      await page.waitForTimeout(500);

      // 1. Click +Add Line
      const addBtn = await page.evaluate(() => {
        for (const el of document.querySelectorAll('button')) {
          if (el.textContent.trim() === '+Add Line' && el.offsetParent !== null) {
            const rect = el.getBoundingClientRect();
            return { x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2) };
          }
        }
        return null;
      });
      if (!addBtn) { results.push({ ...row, status: "no_add_line_button" }); continue; }
      await page.mouse.click(addBtn.x, addBtn.y);
      await page.waitForTimeout(1500);

      // 2. Find the unlocked Project search input (the new row's leftmost field)
      const projInput = await page.evaluate(() => {
        for (const inp of document.querySelectorAll('input.input-element.search-input.searchCol')) {
          if (inp.offsetParent !== null && !inp.className.includes('locked')) {
            const rect = inp.getBoundingClientRect();
            return { x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2) };
          }
        }
        return null;
      });
      if (!projInput) { results.push({ ...row, status: "no_project_input" }); continue; }
      await page.mouse.click(projInput.x, projInput.y);
      await page.waitForTimeout(500);

      // 3. Type project search
      await page.keyboard.type(row.project_search, { delay: 80 });
      await page.waitForTimeout(2500);

      // Help dialog hazard check
      await dismissUnexpectedDialogs();

      // 3.5. If the Lookup dialog opened with a stale "Find Project" filter from
      // a prior add-line attempt, the project list won't match our search.
      // Clear and retype the filter inside the dialog.
      const filterCleared = await page.evaluate((search) => {
        const dialog = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]'))
          .find(d => d.offsetParent !== null);
        if (!dialog) return { hasDialog: false };
        const filter = dialog.querySelector('input[placeholder="Find Project"]');
        if (!filter) return { hasDialog: true, hasFilter: false };
        if (filter.value && filter.value !== search) {
          // Clear it
          const rect = filter.getBoundingClientRect();
          return { hasDialog: true, hasFilter: true, staleValue: filter.value,
            x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2) };
        }
        return { hasDialog: true, hasFilter: true, staleValue: null };
      }, row.project_search);
      if (filterCleared.hasDialog && filterCleared.staleValue) {
        await page.mouse.click(filterCleared.x, filterCleared.y, { clickCount: 3 });
        await page.waitForTimeout(200);
        await page.keyboard.press('Delete');
        await page.waitForTimeout(200);
        await page.keyboard.type(row.project_search, { delay: 80 });
        await page.waitForTimeout(2000);
      }

      // 4. Wait for Project/Phase/Task Lookup dialog and click matching project
      const projClicked = await page.evaluate((search) => {
        const dialog = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]'))
          .find(d => d.offsetParent !== null && d.textContent.includes('Project'));
        if (!dialog) return { err: "no_lookup_dialog" };
        // Find row matching search
        for (const r of dialog.querySelectorAll('tr')) {
          const t = r.textContent.trim();
          if (t && t.includes(search)) {
            const rect = r.getBoundingClientRect();
            // Use mouse click via click event
            r.click();
            return { ok: true, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: t.substring(0, 100) };
          }
        }
        return { err: "no_matching_project_row" };
      }, row.project_search);

      if (projClicked.err) { results.push({ ...row, status: projClicked.err }); continue; }

      // Use mouse click for reliability
      await page.mouse.click(projClicked.x, projClicked.y);
      await page.waitForTimeout(1200);

      // 5. Click matching phase row
      if (row.phase_text) {
        const phaseClicked = await page.evaluate((search) => {
          const dialog = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]'))
            .find(d => d.offsetParent !== null);
          if (!dialog) return { err: "no_dialog_for_phase" };
          // Phase pane is the middle grid; find row containing the phase text
          for (const r of dialog.querySelectorAll('tr')) {
            const t = r.textContent.trim();
            if (t && t.includes(search) && !t.includes('Project') && !t.includes('Cushing') && !t.includes(search.charAt(0).match(/[0-9]/) ? '' : '#')) {
              // crude filter to avoid project rows
            }
          }
          // Better approach: look only at phase grid (typically a div with phase data)
          const allRows = Array.from(dialog.querySelectorAll('tr')).filter(r => {
            const t = r.textContent.trim();
            return t && t.includes(search);
          });
          // Heuristic: phase rows are typically shorter than project rows
          const sorted = allRows.sort((a, b) => a.textContent.length - b.textContent.length);
          const target = sorted[0];
          if (!target) return { err: "no_matching_phase_row" };
          const rect = target.getBoundingClientRect();
          return { x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: target.textContent.substring(0, 100) };
        }, row.phase_text);

        if (phaseClicked.err) { results.push({ ...row, status: phaseClicked.err }); continue; }
        await page.mouse.click(phaseClicked.x, phaseClicked.y);
        await page.waitForTimeout(800);
      }

      // 6. Click optional task row.
      // IMPORTANT: r.click() and page.mouse.click() do NOT select task rows in the
      // Lookup dialog (the Select button stays disabled). The Kendo task grid
      // requires a full mousedown/mouseup sequence on a TD cell — and the cell,
      // not the row itself, is the click target. Symptom of getting this wrong:
      // taskClicked: { ... } reports success but Select button is "btn primary disabled".
      if (row.task_text) {
        const taskCoord = await page.evaluate((search) => {
          const dialog = Array.from(document.querySelectorAll('.ui-dialog, [role="dialog"]'))
            .find(d => d.offsetParent !== null);
          if (!dialog) return null;
          for (const r of dialog.querySelectorAll('tr')) {
            if (r.offsetParent === null) continue;
            if (r.textContent.includes(search)) {
              const td = r.querySelector('td');
              const rect = (td || r).getBoundingClientRect();
              return { x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2) };
            }
          }
          return null;
        }, row.task_text);
        if (taskCoord) {
          await page.mouse.move(taskCoord.x, taskCoord.y);
          await page.waitForTimeout(100);
          await page.mouse.down();
          await page.waitForTimeout(50);
          await page.mouse.up();
          await page.waitForTimeout(800);
        }
      }

      // 7. Click Select
      const selectClicked = await page.evaluate(() => {
        for (const el of document.querySelectorAll('span, button')) {
          if (el.textContent.trim() === 'Select' && el.offsetParent !== null) {
            el.click();
            return true;
          }
        }
        return false;
      });
      if (!selectClicked) { results.push({ ...row, status: "no_select_button" }); continue; }
      await page.waitForTimeout(2000);

      // 8. Save — the new row only persists to the visible grid AFTER Save
      // finishes (it does not appear immediately after Select). Wait longer.
      await page.evaluate(() => {
        for (const el of document.querySelectorAll('span, button')) {
          if (el.textContent.trim() === 'Save' && el.offsetParent !== null) {
            el.click();
            return;
          }
        }
      });
      await page.waitForTimeout(3500);

      // Verify the row exists — use the project number (more specific) when
      // available, falling back to project_search. After Save the project
      // number is what's rendered in the row, so a name-only search may miss.
      const verified = await page.evaluate((args) => {
        const grids = document.querySelectorAll('.gridBody.absolute');
        for (const r of grids[0].querySelectorAll('tr')) {
          if (r.offsetParent === null) continue;
          const t = r.textContent;
          if (args.task && t.includes(args.task) && t.includes(args.search)) return true;
          if (!args.task && t.includes(args.search)) return true;
        }
        return false;
      }, { search: row.project_search, task: row.task_text });

      results.push({ ...row, status: verified ? "added" : "save_unverified" });
    } catch (err) {
      results.push({ ...row, status: "error", err: String(err) });
    }
  }

  console.log(JSON.stringify({
    added: results.filter(r => r.status === "added").length,
    failed: results.filter(r => r.status !== "added").length,
    results
  }, null, 2));
}

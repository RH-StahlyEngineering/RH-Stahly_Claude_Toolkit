# Independent review prompt

Send one reviewer per sheet. Use a cheaper model, run them in parallel, and keep them read-only. Fill in the brackets. The ground truth is the crew's own words, copied from chat or the form, not the sheet's notes or the job file. A reviewer checking the sheet against itself finds nothing.

```
Independent QA of one manhole/inlet note sheet. Read-only; report findings only.

Sheet: <path to .docx>
Rendered pages (view with Read): <png paths from check_sheets.py>
Field photo (original, unrotated): <path>

Field notes exactly as the surveyor gave them (ground truth):
<paste the dictated values for this structure, verbatim>

Job settings: field north = true N<az>E (<reference>); "top of pipe" = outside top; invert = top + wall + ID.

Check:
1. Every page-1 value matches the field notes. Anything the surveyor did not give must read NOT RECORDED (final) or blank (draft), never a guess, "none" or "presumed".
2. Calculated values (marked CALC, and shown in OTHER NOTES) follow the formula with the surveyor's numbers.
3. Pipe boxes are labeled with true directions and sit in the matching grid cell.
4. Plan view and pipe boxes use true directions only: field directions converted to true by the offset, pipes and lid rotated together. Pipe widths are to scale. Unknown sizes are drawn as a single centerline, never as a "?" or a callout. Pipe projections match the photo. Street labels run along their bearings, sit on the correct side, and carry no distance text.
5. Page 2: the photo is turned to true north (stated orientation plus offset). A final sheet never shows an unrotated photo; if the orientation is unknown, the photo should be absent.
6. Form fits on page 1. Nothing is clipped or overlapping. OTHER NOTES is short: crew notes plus calculations, with no boilerplate about field directions.

Reply: one PASS line, then each FAIL with location and fix. Under 250 words.
```

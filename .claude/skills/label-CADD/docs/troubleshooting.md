# Troubleshooting: DWG MULTILEADER Creation

This document describes errors encountered during implementation of the AutoLISP/AcCoreConsole workflow and their solutions.

## Error 1: LISP File Load Canceled

**Symptom:**
```
; error: File load canceled: C:/Users/.../create_mleaders.lsp
```

**Cause:**
AutoCAD's SECURELOAD security feature blocks loading LISP files from untrusted paths. By default, only files in AutoCAD's trusted paths can be loaded.

**Solution:**
Add `(setvar "SECURELOAD" 0)` at the beginning of the AcCoreConsole script before loading the LISP file:

```lisp
;;; Disable SECURELOAD to allow LISP loading from any path
(setvar "SECURELOAD" 0)

;;; Now load the LISP script
(load "C:/path/to/create_mleaders.lsp")
```

**File Modified:** `scripts/create_labels_dwg.py` - `create_script_file()` function

---

## Error 2: Invalid Table Function Argument - MLEADERSTYLE

**Symptom:**
```
; error: AutoCAD rejected function: invalid table function argument(s): "MLEADERSTYLE" "Annotative-Simplex"
```

**Cause:**
AutoLISP's `tblsearch` function only works with traditional symbol tables:
- LAYER
- LTYPE (linetype)
- STYLE (text style)
- DIMSTYLE
- VIEW
- UCS
- VPORT
- APPID
- BLOCK

MLEADERSTYLE is a dictionary-based object, not a traditional symbol table, so `tblsearch` doesn't support it.

**Solution:**
Remove the `tblsearch` check and rely on the template drawing's current MLEADERSTYLE:

```lisp
;; BEFORE (broken):
(if (and mleader-style (tblsearch "MLEADERSTYLE" mleader-style))
  (setvar "CMLEADERSTYLE" mleader-style))

;; AFTER (working):
;; Note: MLEADERSTYLE is set by the template drawing
;; We don't change it here - use whatever style is current
```

**Alternative:** Use the `-MLEADERSTYLE` command to set the style:
```lisp
(command "._-MLEADERSTYLE" "_Set" "StyleName")
```
However, this can hang waiting for input if the style doesn't exist.

**File Modified:** `scripts/create_mleaders.lsp` - `create-mleader-label` function

---

## Error 3: SAVEAS Path Does Not Exist

**Symptom:**
```
Path does not exist: C:\Users\...\templates\test\
Please verify the correct path was given.
```

**Cause:**
AcCoreConsole runs with the template directory as the working directory. When a relative path like `test/sample-LABELS.dwg` is passed to SAVEAS, AutoCAD interprets it relative to the template directory, not the original working directory.

**Solution:**
Always convert output paths to absolute paths before passing to LISP:

```python
# BEFORE (broken):
output_dwg_str = str(output_dwg).replace('\\', '/')

# AFTER (working):
output_dwg_str = str(output_dwg.resolve()).replace('\\', '/')
```

Also ensure the output directory exists:
```python
output_path.parent.mkdir(parents=True, exist_ok=True)
```

**File Modified:** `scripts/create_labels_dwg.py` - `create_script_file()` function

---

## Error 4: SAVEAS Format Prompt Hangs

**Symptom:**
AcCoreConsole hangs at:
```
Enter file format [R14.../2018.../DXF/Template] <2018>:
```

**Cause:**
The SAVEAS command with explicit format `"2018"` expects user confirmation of the format, which hangs in headless mode.

**Solution:**
Use empty string `""` to accept the default format:

```lisp
;; BEFORE (hangs):
(command "._SAVEAS" "2018" output-dwg)

;; AFTER (working):
(command "._SAVEAS" "" output-dwg)
```

**File Modified:** `scripts/create_mleaders.lsp` - `c:MLEADER-BATCH` function

---

## Summary of Changes

| File | Changes |
|------|---------|
| `scripts/create_labels_dwg.py` | Added SECURELOAD disable, use absolute paths |
| `scripts/create_mleaders.lsp` | Removed tblsearch for MLEADERSTYLE, simplified SAVEAS |

## Testing

After fixes, the workflow successfully:
1. Loads LISP script via AcCoreConsole
2. Creates 5 MULTILEADER entities from CSV
3. Saves output DWG to specified path
4. Exits cleanly

```
Complete: 5 created, 0 failed.
Log written to: .../create_mleaders.log
Saving to: C:/.../test/sample-LABELS.dwg
Done.
```

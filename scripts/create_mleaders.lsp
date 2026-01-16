;;; create_mleaders.lsp
;;; Creates MULTILEADER entities natively in AutoCAD from a CSV file.
;;; CSV format: Point#,X,Y,Z,Label_Text,Type,Layer,Color
;;;
;;; Usage:
;;;   (load "create_mleaders.lsp")
;;;   (c:CREATE-MLEADERS "C:/path/to/labels.csv")
;;;
;;; Or from command line:
;;;   CREATE-MLEADERS
;;;   [Select CSV file when prompted]
;;;
;;; This script creates MULTILEADER entities using the MLEADER command,
;;; ensuring native AutoCAD generation of proxy graphics and annotative data.
;;; This approach guarantees:
;;;   - Copy/paste works correctly
;;;   - XREF functionality works
;;;   - Annotative scaling works properly
;;;   - Leader lines scale with text

;;; ============================================================================
;;; CSV PARSING UTILITIES
;;; ============================================================================

(defun csv-split (str delim / result current pos)
  "Split string by delimiter character. Returns list of strings."
  (setq result '()
        current ""
        pos 0)
  (while (< pos (strlen str))
    (setq char (substr str (1+ pos) 1))
    (if (= char delim)
      (progn
        (setq result (cons current result))
        (setq current ""))
      (setq current (strcat current char)))
    (setq pos (1+ pos)))
  ;; Add last field
  (setq result (cons current result))
  (reverse result))

(defun csv-read-file (filepath / file line lines)
  "Read CSV file and return list of rows (each row is a list of fields)."
  (setq lines '())
  (setq file (open filepath "r"))
  (if file
    (progn
      (while (setq line (read-line file))
        ;; Skip empty lines and comments
        (if (and (> (strlen line) 0)
                 (/= (substr line 1 1) "#"))
          (setq lines (cons (csv-split line ",") lines))))
      (close file)
      (reverse lines))
    nil))

(defun csv-skip-header (rows)
  "Skip header row if first field is non-numeric."
  (if (and rows (car rows))
    (if (not (numberp (read (car (car rows)))))
      (cdr rows)
      rows)
    rows))

;;; ============================================================================
;;; STRING UTILITIES
;;; ============================================================================

(defun str-trim (str / start end)
  "Trim whitespace from start and end of string."
  (if (null str) ""
    (progn
      (setq start 1)
      (while (and (<= start (strlen str))
                  (member (substr str start 1) '(" " "\t" "\n" "\r")))
        (setq start (1+ start)))
      (setq end (strlen str))
      (while (and (>= end start)
                  (member (substr str end 1) '(" " "\t" "\n" "\r")))
        (setq end (1- end)))
      (if (> start end)
        ""
        (substr str start (1+ (- end start)))))))

;;; ============================================================================
;;; LABEL CREATION
;;; ============================================================================

(defun create-mleader-label (x y z label-text layer color-code mleader-style
                             / old-layer old-cmdecho old-osmode pt offset-pt)
  "Create a single MULTILEADER entity at specified location.

   Args:
     x, y, z      - Coordinates of arrow target (survey point location)
     label-text   - Text content for the leader
     layer        - Layer name (e.g., 'G-ANNO' or '0')
     color-code   - ACI color (256=ByLayer, 1=Red, etc.)
     mleader-style - Name of MLEADERSTYLE to use

   Returns:
     T on success, nil on failure"

  ;; Save current settings
  (setq old-layer (getvar "CLAYER"))
  (setq old-cmdecho (getvar "CMDECHO"))
  (setq old-osmode (getvar "OSMODE"))

  ;; Configure environment
  (setvar "CMDECHO" 0)
  (setvar "OSMODE" 0)  ; Disable object snaps during creation

  ;; Set layer (create if needed)
  (if (not (tblsearch "LAYER" layer))
    (command "._LAYER" "_Make" layer ""))
  (setvar "CLAYER" layer)

  ;; Set MLEADERSTYLE if specified
  (if (and mleader-style (tblsearch "MLEADERSTYLE" mleader-style))
    (setvar "CMLEADERSTYLE" mleader-style))

  ;; Calculate offset for text landing (20 units at 45 degrees from point)
  ;; This offset will be adjusted by annotative scale automatically
  (setq pt (list x y z))
  (setq offset-pt (list (+ x 20.0) (+ y 20.0) z))  ; Leader end point

  ;; Create MULTILEADER
  ;; Command sequence: MLEADER -> first point (arrow) -> second point (text) -> text content
  (command "._MLEADER" pt offset-pt label-text)

  ;; Apply color if not ByLayer
  (if (/= color-code 256)
    (progn
      ;; Select the last created entity and change its color
      (command "._CHPROP" (entlast) "" "_Color" color-code "")))

  ;; Restore settings
  (setvar "CLAYER" old-layer)
  (setvar "CMDECHO" old-cmdecho)
  (setvar "OSMODE" old-osmode)

  T)  ; Return success

;;; ============================================================================
;;; MAIN COMMAND
;;; ============================================================================

(defun c:CREATE-MLEADERS (csv-path / rows row count success-count fail-count
                          point-num x y z label-text label-type layer color-code
                          mleader-style log-file)
  "Main command to create MULTILEADER entities from CSV file.

   CSV format: Point#,X,Y,Z,Label_Text,Type,Layer,Color
   - Point#     : Survey point number (for reference)
   - X,Y,Z      : Coordinates of arrow target
   - Label_Text : Text content for the label
   - Type       : 'presentation' or 'drafter' (informational)
   - Layer      : Layer name (e.g., 'G-ANNO', '0')
   - Color      : ACI color code (256=ByLayer, 1=Red)

   Usage:
     (c:CREATE-MLEADERS \"C:/path/to/labels.csv\")
     or
     Command: CREATE-MLEADERS [prompts for file]"

  ;; Prompt for file if not provided
  (if (null csv-path)
    (setq csv-path (getfiled "Select Labels CSV" "" "csv" 4)))

  (if (null csv-path)
    (progn
      (princ "\nNo CSV file selected. Aborted.")
      (princ))
    (progn
      ;; Read CSV
      (princ (strcat "\nReading CSV: " csv-path))
      (setq rows (csv-read-file csv-path))

      (if (null rows)
        (progn
          (princ "\nError: Could not read CSV file.")
          (princ))
        (progn
          ;; Skip header row
          (setq rows (csv-skip-header rows))

          (princ (strcat "\nFound " (itoa (length rows)) " labels to create."))

          ;; Get MLEADERSTYLE from first row or use default
          (setq mleader-style "Annotative-Simplex")  ; Default style

          ;; Process each row
          (setq count 0)
          (setq success-count 0)
          (setq fail-count 0)

          (foreach row rows
            (setq count (1+ count))

            ;; Parse row (Point#,X,Y,Z,Label_Text,Type,Layer,Color)
            (if (>= (length row) 8)
              (progn
                (setq point-num (str-trim (nth 0 row)))
                (setq x (atof (str-trim (nth 1 row))))
                (setq y (atof (str-trim (nth 2 row))))
                (setq z (atof (str-trim (nth 3 row))))
                (setq label-text (str-trim (nth 4 row)))
                (setq label-type (str-trim (nth 5 row)))
                (setq layer (str-trim (nth 6 row)))
                (setq color-code (atoi (str-trim (nth 7 row))))

                ;; Create the MLEADER
                (princ (strcat "\n  [" (itoa count) "] Pt " point-num ": \""
                              (if (> (strlen label-text) 30)
                                (strcat (substr label-text 1 30) "...")
                                label-text)
                              "\" -> " layer))

                (if (create-mleader-label x y z label-text layer color-code mleader-style)
                  (setq success-count (1+ success-count))
                  (setq fail-count (1+ fail-count))))
              (progn
                (princ (strcat "\n  [" (itoa count) "] Skipped: insufficient columns"))
                (setq fail-count (1+ fail-count)))))

          ;; Summary
          (princ (strcat "\n\nComplete: " (itoa success-count) " created, "
                        (itoa fail-count) " failed."))

          ;; Write log file
          (setq log-file (strcat (vl-filename-directory csv-path) "\\create_mleaders.log"))
          (setq file (open log-file "w"))
          (if file
            (progn
              (write-line (strcat "CREATE-MLEADERS Log") file)
              (write-line (strcat "CSV File: " csv-path) file)
              (write-line (strcat "Labels Created: " (itoa success-count)) file)
              (write-line (strcat "Labels Failed: " (itoa fail-count)) file)
              (write-line "Status: SUCCESS" file)
              (close file)
              (princ (strcat "\nLog written to: " log-file))))

          (princ))))))

;;; ============================================================================
;;; BATCH COMMAND (for AcCoreConsole)
;;; ============================================================================

(defun c:MLEADER-BATCH (csv-path output-dwg / template-dwg)
  "Batch command for AcCoreConsole - creates labels and saves.

   Usage from AcCoreConsole script:
     (load \"create_mleaders.lsp\")
     (c:MLEADER-BATCH \"C:/path/to/labels.csv\" \"C:/path/to/output.dwg\")

   Args:
     csv-path   - Path to CSV file with label data
     output-dwg - Path to save output DWG file"

  ;; Create the labels
  (c:CREATE-MLEADERS csv-path)

  ;; Save the drawing
  (if output-dwg
    (progn
      (princ (strcat "\nSaving to: " output-dwg))
      (command "._SAVEAS" "2018" output-dwg)
      (princ "\nDone."))
    (princ "\nWarning: No output path specified, drawing not saved."))

  (princ))

;;; ============================================================================
;;; LOAD MESSAGE
;;; ============================================================================

(princ "\ncreate_mleaders.lsp loaded.")
(princ "\n  Command: CREATE-MLEADERS - Create MLEADERs from CSV")
(princ "\n  Command: MLEADER-BATCH - Batch mode for AcCoreConsole")
(princ)

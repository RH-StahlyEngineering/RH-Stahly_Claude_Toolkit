# Placing marker pins by hand (MarkerRefinementRequired)

A job holds at `marker_loading` with `MarkerRefinementRequired` when a surveyed target was not
detected. Detection misses shadowed, blurred or low-contrast panels; the panel is usually
plainly visible. RH's rule: once one target needs pins, **pin every target by hand** and trust
no automatic detection. Workaround until #673 (staff placement in the browser) ships.

The scripts are in `scripts/pins/`; each one's header states how to run it and its arguments.
Read the header every time. Write outputs to the scratchpad.

## Steps

1. **Project.** `project_targets.py` lists, per target, every photo its surveyed position falls
   in, and maps each auto `point N` marker to its target; markers far from every target are
   false detections, left alone. A target with no auto marker is the missed one (below).
   Done when every target has its photo list.
2. **Pick.** One sub-agent per target crops each photo around the projected point and picks
   the **junction**: the single point where all four quadrants touch, halfway between the
   two dark quadrants' inner corners. Name the trap in the brief: pickers drift onto the inner
   corner of one dark square. Panels cut off by the frame or too defocused to show a seam are
   skipped, not guessed.
3. **Refine.** `refine.py` moves each pick to the saddle of the intensity surface. No saddle
   means the pick is not on a junction.
4. **Sort.** `triangulate.py` on the fits, then `flag.py`, splits the photos into those the fit
   settles and those that go to RH, each with its reasons. Show RH **only the flagged
   subset**, most uncertain first; RH prefers that to placing every photo. Agreement between
   photos is not correctness, so the subset comes from image evidence, never from
   triangulation alone.
5. **RH reviews** on the pin page (`build_pin_page.py --only`), published with the Artifact
   tool; the script header names the capabilities it needs and where RH's positions land.
   Done when every flagged photo is placed or marked not usable.
6. **Assemble and check.** Final pins: RH's placement where there is one, the fit for the
   unflagged photos, nothing for photos marked not usable. Triangulate again; a target whose
   pins disagree by more than about a pixel goes back to RH with its worst photos.
7. **Write** (RH approves; a hand-edit on a live job). Back up the snapshot pair outside the
   projects folder, run `write_pins.py`, confirm the tie-point count is unchanged and each
   marker carries its pins, update the snapshot record's size so the bridge resumes instead of
   realigning, then the staff Retry with a reason naming the pins and "approved by RH".
   Confirm the dispatch line resumes from the snapshot. Record the edit on #673.

## A target the detector missed

1. Its grid coordinate comes from the staged control file; `project_targets.py` converts it to
   the chunk's units and projects it.
2. Contact sheet: crop a wide window around the projected spot in every photo and look. A
   panel under the cross is visible and gets pinned in every photo it is whole in.
3. A panel away from the cross: search the wider crop before calling it absent. Looking
   straight down, even a large vertical datum offset barely moves the projection, so a large
   miss means the wrong object, not a rough projection.
4. It goes in as the next free `point N` (never its JXL name) so `marker_loading` matches it.
5. Note the cause on the hold: shadow across the panel, a fence enclosure, defocus.

## Judgement from RH's placements

- A sub-agent pick is a starting point for the fit, never a pin.
- The saddle fit is usually closer than the pick on a clean panel, and unreliable on a
  shadowed panel, near the frame edge, or on a blurred one; there the careful pick or RH
  decides. `flag.py` encodes this; its header records the evidence behind its thresholds.
- A pick far from the projected point is the wrong object: re-find the panel.

## Facts

- Tie-point cleaning runs after `marker_loading`, so a job held there still has every tie
  point; pins must be in before a run passes that step.
- The snapshot was written before marker loading: its markers are unlabelled `point N`
  detections.
